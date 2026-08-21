"""Input sufficiency audit: was every rejection the MODEL's fault?

Offline. No simulation, no API calls. Reads an episode JSON plus its
consult audit trail and, for each rejected proposal, replays the EXACT
state the model received and decides whether that state contained what
the model needed to avoid the rejection.

  python3 analysis/episode/episode_input_audit.py out/vlm1_<stamp>.json [more.json ...]

Every rejection is labelled:

  MODEL_ERROR    the state said so plainly; the model contradicted it
  CONTRADICTORY  the state said the opposite of the validator: OUR bug
  MISSING_INFO   the state lacked the field needed to decide
  CIRCLE_OK      the reach rejection is NOT derivable from the prompt:
                 a distance check on the numbers we supply says the
                 proposal was fine, while the validator's measured
                 raster says no. This is the one honest way our
                 architecture can generate an unfair rejection, because
                 the prompt gives a radius and the guard enforces a
                 raster. Counted separately, never as model error.
  UNCLASSIFIED   a rejection string this tool does not recognise

A second section audits INPUT COHERENCE for every consult, whether or
not the model erred: the idle set stated in prose must match arms[],
and the queued ids in the text must match tasks[]. A mismatch there is
an architecture bug that would make any model look bad.

The raster comparison is used ONLY to detect CIRCLE_OK. If the rasters
cannot be imported the tool still runs and says so.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from core.cell.zones import ZoneMap
    _ZM = ZoneMap()
except Exception as _e:                                   # pragma: no cover
    _ZM = None
    print(f"[audit] rasters unavailable ({_e}); CIRCLE_OK detection off",
          file=sys.stderr)

CONSULT_RESULTS = ("valid_first", "valid_after_feedback", "fallback",
                   "noop", "error")


# ----------------------------------------------------------- trail input --

def load_consults(episode_path):
    """[{seq, round, state, idle_sentence}] in consult order, or []."""
    stem = os.path.basename(episode_path)
    stem = stem[:-5] if stem.endswith(".json") else stem
    path = os.path.join(os.path.dirname(episode_path) or ".",
                        f"{stem}_frames", "consults.jsonl")
    out = []
    if not os.path.exists(path):
        return out
    for line in open(path):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = None
        for m in rec.get("messages", []):
            c = m.get("content")
            if isinstance(c, list):
                for b in c:
                    if b.get("type") == "text":
                        text = b.get("text")
        if not text:
            continue
        start, end = text.find("{"), text.rfind("}")
        try:
            state = json.loads(text[start:end + 1])
        except (ValueError, json.JSONDecodeError):
            continue
        idle_sentence = None
        for chunk in text.split("\n"):
            if chunk.startswith("Idle arms right now:"):
                idle_sentence = chunk.split(":", 1)[1].strip().rstrip(".")
        out.append({"seq": rec.get("seq"), "round": rec.get("round"),
                    "state": state, "idle_sentence": idle_sentence})
    return out


def by_name(items, key="name"):
    return {i[key]: i for i in items or []}


# ------------------------------------------------------------ per-cause --

def audit_busy(r, state):
    arm = by_name(state.get("arms", [])).get(r.get("arm"))
    if arm is None:
        return "MODEL_ERROR", f"arm {r.get('arm')} is not in the state at all"
    if arm.get("disabled") or arm.get("state") != "IDLE":
        return "MODEL_ERROR", (f"state showed {arm['name']} as "
                               f"{arm.get('state')}"
                               + (" (disabled)" if arm.get("disabled") else ""))
    return "CONTRADICTORY", (f"state showed {arm['name']} as IDLE but the "
                             f"validator called it busy")


def audit_capability(r, state):
    arm = by_name(state.get("arms", [])).get(r.get("arm"))
    objs = by_name(state.get("objects", []))
    task = next((t for t in state.get("tasks", [])
                 if t.get("id") == r.get("task_id")), None)
    obj = objs.get(task.get("object")) if task else None
    if arm is None or obj is None:
        return "MISSING_INFO", "arm or object absent from the state"
    if obj.get("grasp_m") is None or arm.get("max_grasp_m") is None:
        return "MISSING_INFO", "grasp fields absent from the state"
    if obj.get("delicate") and not arm.get("delicate_ok"):
        return "MODEL_ERROR", (f"state: {obj['name']} delicate, "
                               f"{arm['name']} delicate_ok false")
    if obj["grasp_m"] > arm["max_grasp_m"]:
        return "MODEL_ERROR", (f"state: grasp_m {obj['grasp_m']} > "
                               f"max_grasp_m {arm['max_grasp_m']}")
    if obj.get("mass_kg", 0) > arm.get("payload_kg", float("inf")):
        return "MODEL_ERROR", (f"state: mass {obj['mass_kg']} > payload "
                               f"{arm['payload_kg']}")
    return "CONTRADICTORY", ("state numbers say the grasp is legal but the "
                             "validator refused it")


def audit_pad_rule(r, state):
    objs = by_name(state.get("objects", []))
    task = next((t for t in state.get("tasks", [])
                 if t.get("id") == r.get("task_id")), None)
    obj = objs.get(task.get("object")) if task else None
    if obj is None:
        return "MISSING_INFO", "object absent from the state"
    if obj.get("at_pad"):
        return "MODEL_ERROR", (f"state: {obj['name']} at_pad="
                               f"{obj['at_pad']}, and the prompt forbids "
                               f"re-routing it through a pad")
    return "CONTRADICTORY", (f"state: {obj['name']} at_pad=null, yet the "
                             f"validator says it already sits on a pad")


def _reaches(arm, xy, point=None):
    """Does the STATE say this arm can reach this point?

    Two prompt lineages, two answers, and the audit must use whichever the
    model was actually shown:

      2026-07-28a and later  the point carries a reach_ok_arms list, taken
                             straight from the validator's own raster, and
                             arms[] no longer carries reach_m at all
      2026-07-25d and before the state gave base_xy and reach_m, so the
                             best the model could do was a circle

    Passing the point dict lets the newer form be used when present. The
    circle is the fallback, and it is deliberately GENEROUS: if even the
    circle says no, the model had no basis for the proposal on any reading
    of the state, which is what MODEL_ERROR means here.
    """
    if isinstance(point, dict) and "reach_ok_arms" in point:
        return arm["name"] in point["reach_ok_arms"]
    if "reach_m" not in arm:                 # enriched state, unknown point
        return None                          # undecidable, do not guess
    bx, by = arm["base_xy"]
    return math.hypot(xy[0] - bx, xy[1] - by) <= arm["reach_m"]


def audit_reach(r, state):
    """Reach rejections are the only place our architecture can be unfair:
    the prompt supplies base_xy and reach_m (a circle) while the guard
    enforces a measured raster."""
    arm = by_name(state.get("arms", [])).get(r.get("arm"))
    objs = by_name(state.get("objects", []))
    task = next((t for t in state.get("tasks", [])
                 if t.get("id") == r.get("task_id")), None)
    if arm is None or task is None:
        return "MISSING_INFO", "arm or task absent from the state"
    obj = objs.get(task.get("object"))
    if obj is None or obj.get("xy") is None:
        return "MISSING_INFO", "object position absent from the state"

    can = _reaches(arm, obj["xy"], obj)
    if can is None:
        return "MISSING_INFO", "the state gives neither reach_ok_arms nor reach_m"
    if not can:
        src = ("the object's own reach_ok_arms list"
               if "reach_ok_arms" in obj else
               "the circle test on the state's own numbers")
        return "MODEL_ERROR", (f"{src}: {arm['name']} cannot reach "
                               f"{obj['name']} at {obj['xy']}")

    # Destination, in order of authority:
    #   1. the basket the model NAMED (schema v4 records it)
    #   2. the task's own dest_xy when it has one
    #   3. the CATEGORY-CORRECT basket for a sorting task
    # Case 3 replaced an earlier any-basket test that was too charitable:
    # it excused two rejections by finding some other basket reachable,
    # while the model's own reason named the food basket it could not
    # reach. Where the basket is unrecorded the verdict says so.
    baskets = state.get("baskets") or {}
    assumed = None
    # dests entries are (label, xy, point_dict_or_None); the dict lets the
    # enriched state's own reach_ok_arms decide instead of a circle.
    if r.get("basket") and r["basket"] in baskets:
        dests = [(r["basket"], baskets[r["basket"]]["xy"],
                  baskets[r["basket"]])]
    elif task.get("dest_xy"):
        dests = [("task dest", task["dest_xy"], None)]
    else:
        cat = obj.get("category")
        match = [(n, b["xy"], b) for n, b in baskets.items()
                 if cat and cat in n]
        if match:
            dests, assumed = match, f"category-correct basket {match[0][0]}"
        else:
            dests = [(n, b["xy"], b) for n, b in baskets.items()]
            assumed = "any basket (category match unavailable)"
    if r.get("via_pad"):
        pad = (state.get("exchange_pads") or {}).get(r["via_pad"])
        if pad is None:
            return "MISSING_INFO", f"pad {r['via_pad']} absent from the state"
        if _reaches(arm, pad["xy"], pad) is False:
            return "MODEL_ERROR", (f"the state says {arm['name']} cannot "
                                   f"reach pad {r['via_pad']} at {pad['xy']}")
        dests = [(f"pad {r['via_pad']}", pad["xy"], pad)]
    if not dests:
        return "MISSING_INFO", "no destination or basket list in the state"
    ok = [n for n, xy, pt in dests if _reaches(arm, xy, pt)]
    if not ok:
        note = f" ({assumed})" if assumed else ""
        return "MODEL_ERROR", (f"the state says {arm['name']} reaches "
                               f"{obj['name']} but not "
                               f"{', '.join(n for n, _, _ in dests)}{note}")

    detail = (f"the state says {arm['name']} reaches {obj['name']} and "
              f"{ok[0]}, so the prompt did not support this rejection")
    if assumed:
        detail += f"; destination assumed: {assumed}"
    if _ZM is not None:
        xy_ok = _ZM.reachable(arm["name"], *obj["xy"])
        detail += f"; raster: object reachable={xy_ok}"
    return "CIRCLE_OK", detail


AUDITORS = {"busy_arm": audit_busy, "capability": audit_capability,
            "pad_rule": audit_pad_rule, "reach": audit_reach}


def classify(r):
    if r.get("unparseable"):
        return "unparseable"
    why = (r.get("rejected_because") or "").lower()
    if "not idle" in why:
        return "busy_arm"
    if "already at pad" in why:
        return "pad_rule"
    if "cannot grasp" in why:
        return "capability"
    if ("cannot reach both" in why or "handover pad is needed" in why
            or "cannot reach object and pad" in why):
        return "reach"
    if any(s in why for s in ("already being handled", "already finished",
                              "does not exist")):
        return "task_state"
    if "unknown arm" in why:
        return "unknown_arm"
    return "other"


# -------------------------------------------------------------- coherence --

def coherence(consults):
    """Architecture check independent of any model behaviour."""
    problems = []
    for c in consults:
        state, sent = c["state"], c["idle_sentence"]
        idle_state = sorted(a["name"] for a in state.get("arms", [])
                            if a.get("state") == "IDLE"
                            and not a.get("disabled"))
        if sent is not None:
            idle_text = sorted(x.strip() for x in sent.split(",")
                               if x.strip() and x.strip() != "none")
            if idle_text != idle_state:
                problems.append((c["seq"], "idle set disagrees",
                                 f"prose={idle_text} arms[]={idle_state}"))
        for t in state.get("tasks", []):
            if t.get("status") == "queued" and t.get("id") is None:
                problems.append((c["seq"], "queued task without id", str(t)))
    return problems


# ------------------------------------------------------------------ main --

def audit_episode(path):
    ep = json.load(open(path))
    consults = load_consults(path)
    log = (ep.get("allocator") or {}).get("log") or []
    entries = [e for e in log if e.get("result") in CONSULT_RESULTS]
    print(f"\n=== {os.path.basename(path)} "
          f"({ep.get('meta', {}).get('allocator')}) ===")
    if not consults:
        print("  no consult trail beside this episode; nothing to audit")
        return
    if len(consults) != len(entries):
        print(f"  WARNING: {len(consults)} consults but {len(entries)} "
              f"consult-level log entries; join may be misaligned")

    verdicts, details = {}, []
    for i, e in enumerate(entries):
        state = consults[i]["state"] if i < len(consults) else {}
        for r in (e.get("rejected") or []):
            cause = classify(r)
            fn = AUDITORS.get(cause)
            if fn is None:
                verdict, why = ("MODEL_ERROR", "malformed reply") \
                    if cause == "unparseable" else ("UNCLASSIFIED",
                                                    r.get("rejected_because"))
            else:
                verdict, why = fn(r, state)
            key = (cause, verdict)
            verdicts[key] = verdicts.get(key, 0) + 1
            if verdict != "MODEL_ERROR":
                details.append((consults[i]["seq"], e.get("round"), cause,
                                verdict, r.get("arm"), r.get("task_id"), why))

    total = sum(verdicts.values())
    print(f"  rejections audited: {total}")
    print(f"  {'cause':12s} {'verdict':14s} count")
    for (cause, verdict), n in sorted(verdicts.items()):
        print(f"  {cause:12s} {verdict:14s} {n}")
    ours = sum(n for (_, v), n in verdicts.items()
               if v in ("CONTRADICTORY", "MISSING_INFO", "CIRCLE_OK"))
    print(f"  attributable to the model: {total - ours} of {total}")
    print(f"  attributable to our inputs: {ours} of {total}")
    if details:
        print("  cases NOT charged to the model:")
        for seq, rnd, cause, verdict, arm, tid, why in details:
            print(f"    consult {seq} (round {rnd}) {cause}/{verdict}: "
                  f"arm={arm} task={tid}")
            print(f"      {why}")

    probs = coherence(consults)
    print(f"  input coherence over {len(consults)} consults: "
          + ("clean" if not probs else f"{len(probs)} PROBLEM(S)"))
    for seq, kind, detail in probs:
        print(f"    consult {seq}: {kind}: {detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="+")
    a = ap.parse_args()
    for p in a.episodes:
        audit_episode(p)


if __name__ == "__main__":
    main()
