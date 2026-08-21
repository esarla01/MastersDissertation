"""Episode trace viewer: replay episode JSONs as a readable story.

Isaac-free, stdlib only. Accepts one or more episode files:

  python3 analysis/episode_trace.py out/vlm1_*.json --rounds-only

Each allocation round is printed as a block:

  STATE BEFORE   the cell as it stood when the round opened (this
                 round's own claims excluded)
  DECISIONS      one numbered item per consult, in order, each showing
                 the exact state the model saw, what it proposed, and
                 what happened to that proposal:
                   ACCEPTED  -> ASSIGN task N (object) to ARM
                   REJECTED  -> the proposal itself + why the validator
                                refused it, per attempt
                   FALLBACK  -> rule floor, and the rule's assignment
                   NOOP      -> deliberate wait + what it waits for
  STATE AFTER    the same cell view including this round's claims

Claim attribution: a claim whose tick falls within CLAIM_WINDOW ticks
at or before the round token belongs to that round. Claims land at
exactly round_token - 1, so the window is 1. A wider window was wrong
whenever two rounds fell closer together than the window: rounds 1642
and 1643 are one tick apart, and a window of 5 made round 1643 exclude
round 1642's claim, printing a STATE BEFORE that showed ur_e idle and
task 13 still queued after 1642 had already claimed both.

Sections 3-5 (timeline, per-task summary, locks) follow unless
--rounds-only is given.
"""

import argparse
import json
import os
import sys

# Optional: the capability breakdown needs the object registry and the arm
# table. If they are unavailable (rasters or Isaac paths missing) the trace
# still prints, just without the extra clause.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from analysis.episode_metrics import capability_detail
except Exception:                              # pragma: no cover
    def capability_detail(arm, obj):
        return None

CLAIM_WINDOW = 1
CONSULT_RESULTS = ("valid_first", "valid_after_feedback", "fallback",
                   "noop", "error")


def short(obj):
    """ycb_soup_can -> soup_can (episode object names are prefixed)."""
    return obj[4:] if isinstance(obj, str) and obj.startswith("ycb_") else obj


def section(title):
    print(f"\n{'=' * 8} {title} {'=' * 8}")


# ---------------------------------------------------------------- audit --

def load_audit_views(episode_path):
    """Ordered per-CONSULT model views from consults.jsonl ([] if none).
    One consult = one decision-log entry whose result is in
    CONSULT_RESULTS (rule_assigned entries consume no consult), so the
    k-th view is the true pre-decision state of the k-th such entry."""
    stem = os.path.basename(episode_path)
    stem = stem[:-5] if stem.endswith(".json") else stem
    path = os.path.join(os.path.dirname(episode_path) or ".",
                        f"{stem}_frames", "consults.jsonl")
    views = []
    if not os.path.exists(path):
        return views
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
        if start < 0 or end <= start:
            continue
        try:
            st = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            continue
        views.append({
            "seq": rec.get("seq"), "round": rec.get("round"),
            "image_file": rec.get("image_file"),
            "idle": [a["name"] for a in st.get("arms", [])
                     if a.get("state") == "IDLE" and not a.get("disabled")],
            "queued_ids": [t.get("id") for t in st.get("tasks", [])
                           if t.get("status") == "queued"],
            "zone_locks": st.get("zone_locks"),
        })
    return views


# ----------------------------------------------------------- state view --

def reconstruct(ep, tick, exclude_claims_from=None):
    """Cell state at `tick`. If exclude_claims_from is given, claims made
    at or after that tick are treated as not yet made (the round's own
    assignments), which yields the state as the round OPENED."""
    tasks = ep.get("tasks", [])

    def claimed(t):
        c = t.get("claim_tick")
        if c is None or c > tick:
            return None
        if exclude_claims_from is not None and c >= exclude_claims_from:
            return None
        return c

    done_ids = {t["id"] for t in tasks
                if t.get("done") and (t.get("done_tick") or 0) <= tick}
    busy, queued, parked, failed = [], [], [], []
    for t in tasks:
        c, d = claimed(t), t.get("done_tick")
        if t.get("failed"):
            failed.append(t)
            continue
        if c is not None and (d is None or d > tick):
            busy.append(t)
            continue
        if t["id"] in done_ids:
            continue
        s = t.get("submit_tick")
        if s is None or s > tick or c is not None:
            continue
        w = t.get("waiting_on")
        if w is not None and w not in done_ids:
            parked.append(t)
            continue
        # waiting_on is CLEARED when the leg completes, so final records
        # hide historical parking: a primary task with a LIVE leg for the
        # same object was parked at this tick.
        leg_live = any(
            l.get("kind") == "handover_leg" and l.get("object") == t["object"]
            and (l.get("submit_tick") or 0) <= tick
            and (l.get("done_tick") is None or l["done_tick"] > tick)
            and not l.get("failed")
            for l in tasks if l is not t)
        (parked if (t.get("kind") == "primary" and leg_live)
         else queued).append(t)

    # Lock events belonging to this round are excluded from the BEFORE
    # view for the same reason its claims are.
    ledger_cut = (exclude_claims_from if exclude_claims_from is not None
                  else tick + 1)
    held, resv = {}, {}
    for e in (ep.get("locks") or {}).get("ledger", []):
        if e.get("tick", 0) > tick or e.get("tick", 0) >= ledger_cut:
            break
        z, a, act = e.get("zone"), e.get("arm"), e.get("action")
        if act == "acquire":
            held[z] = a
            if a in resv.get(z, []):        # intent became possession
                resv[z].remove(a)
        elif act == "release" and held.get(z) == a:
            del held[z]
        elif act == "reserve":
            resv.setdefault(z, []).append(a)
        elif act == "unreserve" and a in resv.get(z, []):
            resv[z].remove(a)
    resv = {z: q for z, q in resv.items() if q}

    all_arms = sorted(ep.get("per_arm", {}))
    busy_by_arm = {t.get("arm"): t for t in busy}

    # Availability (schema v3): an arm with no live task is only
    # ASSIGNABLE once it has folded back to IDLE. arm_idle events mark
    # that instant; without them (v2 episodes) fall back to task-level
    # inference and say so.
    idle_events = [e for e in ep.get("events", [])
                   if e.get("type") == "arm_idle"]
    have_ledger = bool(idle_events)
    status = {}
    for a in all_arms:
        if a in busy_by_arm:
            status[a] = "BUSY"
            continue
        if not have_ledger:
            status[a] = "IDLE?"                # v2: cannot distinguish
            continue
        last_done = max([t.get("done_tick") for t in tasks
                         if t.get("arm") == a
                         and t.get("done_tick") is not None
                         and t["done_tick"] <= tick] or [-1])
        last_idle = max([e.get("tick", 0) for e in idle_events
                         if e.get("arm") == a and e.get("tick", 0) <= tick]
                        or [0 if last_done < 0 else -1])
        status[a] = "IDLE" if last_idle >= last_done else "RESETTING"
    return {"busy": busy, "busy_by_arm": busy_by_arm, "arms": all_arms,
            "status": status, "have_ledger": have_ledger,
            "idle": [a for a in all_arms if status.get(a) == "IDLE"],
            "queued": queued, "parked": parked, "failed": failed,
            "held": held, "resv": resv,
            "done": len(done_ids), "total": len(tasks)}


def print_state(label, s):
    print(f"  {label}")
    for a in s["arms"]:
        t = s["busy_by_arm"].get(a)
        st = s["status"].get(a, "IDLE")
        if t is None:
            note = ("  (task done, still folding: NOT assignable)"
                    if st == "RESETTING" else
                    "  (task-level guess: episode predates the "
                    "availability ledger)" if st == "IDLE?" else "")
            print(f"    {a:<9} {st}{note}")
        else:
            print(f"    {a:<9} BUSY  task {t['id']:>2} {short(t['object']):<14}"
                  f" zones {t.get('required_zones')}"
                  f" since t={t.get('claim_tick')}")
    q = ", ".join(f"{t['id']}:{short(t['object'])}" for t in s["queued"])
    print(f"    queued    ({len(s['queued'])}) {q or 'none'}")
    if s["parked"]:
        p = ", ".join(f"{t['id']}:{short(t['object'])}"
                      f"(awaits {t.get('waiting_on') or 'its leg'})"
                      for t in s["parked"])
        print(f"    parked    ({len(s['parked'])}) {p}")
    if s["failed"]:
        print("    FAILED    " + ", ".join(
            f"{t['id']}:{short(t['object'])}" for t in s["failed"]))
    locks = "; ".join(f"{z}={a}" for z, a in sorted(s["held"].items()))
    res = "; ".join(f"{z}<-{','.join(q)}" for z, q in sorted(s["resv"].items()))
    print(f"    locks     {locks or 'none'}")
    print(f"    reserved  {res or 'none'}")
    print(f"    progress  {s['done']}/{s['total']} task records done")


# --------------------------------------------------------------- rounds --

def print_b2_round(e, names):
    rep = f"  (repeated x{e['repeats']})" if e.get("repeats") else ""
    print(f"\n  Hungarian solve{rep}: idle={e.get('idle')} "
          f"total_cost={e.get('total_cost')}")
    matrix = e.get("matrix", {})
    matching = {str(k): v for k, v in (e.get("matching") or {}).items()}
    if not matrix:
        print("    (empty matrix: nothing feasible this round)")
        return
    arms = sorted({k.split("|")[0] for k in matrix})
    tids = sorted({k.split("|")[1] for k in matrix}, key=int)
    print("    " + f"{'':10s}" + "".join(f"{('task ' + t):>12s}" for t in tids))
    for a in arms:
        cells = []
        for t in tids:
            v = matrix.get(f"{a}|{t}")
            star = "*" if matching.get(t) == a else " "
            cells.append(f"{v:>10.3f}{star}" if v is not None
                         else f"{'-':>10s} ")
        print(f"    {a:10s}" + " ".join(cells))
    for t, a in sorted(matching.items(), key=lambda kv: int(kv[0])):
        print(f"    -> ASSIGN task {t} ({names.get(int(t), '?')}) to {a}"
              + ("  [relay]" if t in (e.get("relays") or []) else ""))


def print_rejections(e, names, indent="     "):
    """Per-attempt rejected proposals (episodes from 2026-07-26 on)."""
    rej = e.get("rejected")
    if not rej:
        if e.get("last_reason"):
            print(f"{indent}REJECTED (proposal not recorded in this "
                  f"episode era)")
            print(f"{indent}   rejected because: {e['last_reason']}")
        return
    for r in rej:
        tid = r.get("task_id")
        who = f"task {tid} ({names.get(tid, '?')}) -> {r.get('arm')}"
        if r.get("unparseable"):
            who = "unparseable reply"
        print(f"{indent}REJECTED attempt {r.get('attempt')}: proposed {who}"
              + (f" via {r['via_pad']}" if r.get("via_pad") else ""))
        print(f"{indent}   rejected because: {r.get('rejected_because')}")
        # "cannot grasp" is one message for THREE different limits (size,
        # weight, delicate). Name which one, with the two numbers.
        why = (r.get("rejected_because") or "").lower()
        if "cannot grasp" in why and tid in names:
            detail = capability_detail(r.get("arm"), "ycb_" + names[tid])
            if detail:
                print(f"{indent}      which limit: {detail}")
        if r.get("model_reason"):
            print(f"{indent}   model reason: \"{r['model_reason']}\"")


def print_decision(n, e, names, view):
    """One numbered consult-level decision."""
    r = e.get("result")
    tid = e.get("task_id")
    if r != "rule_assigned":                 # always number the consult
        line = f"  {n}."
        if view is None:
            line += "  (no audit trail saved for this consult)"
        else:
            line += (f" model saw: idle={view['idle']} "
                     f"queued={view['queued_ids']}"
                     + (f" locks={view['zone_locks']}"
                        if view.get("zone_locks") else "")
                     + (f" frame={view['image_file']}"
                        if view.get("image_file") else ""))
        print(line)

    if r in ("valid_first", "valid_after_feedback"):
        if r == "valid_after_feedback":
            print_rejections(e, names, indent="     ")
        tag = ("ACCEPTED first try" if r == "valid_first"
               else "ACCEPTED after feedback")
        route = (f" via pad {e['via_pad']}" if e.get("via_pad") else " direct")
        print(f"     {tag}")
        print(f"     -> ASSIGN task {tid} ({names.get(tid, '?')}) "
              f"to {e.get('arm')}{route}")
        print(f"        arm chosen by {e.get('arm_by')}, "
              f"destination by {e.get('dest_by')}")
        if e.get("regions_required") is not None:
            verdict = "MISMATCH" if e.get("region_mismatch") else "ok"
            print(f"        regions declared={e.get('regions_declared')} "
                  f"required={e.get('regions_required')}  {verdict}")
        if e.get("unnecessary_pad"):
            print("        flagged: unnecessary pad (valid but wasteful)")
        if e.get("reason"):
            print(f"        model reason: \"{e['reason']}\"")
    elif r == "fallback":
        print_rejections(e, names, indent="     ")
        n_att = len(e.get("rejected") or []) or "all"
        print(f"     FALLBACK to rule floor after {n_att} rejected "
              f"attempt(s); the rule now decides this round")
    elif r == "noop":
        # a noop reached on the second attempt was preceded by a refused
        # proposal (schema v4); show it, or the wait looks proactive
        print_rejections(e, names, indent="     ")
        tag = ("NOOP after a refused proposal"
               if e.get("rejected") else "NOOP")
        print(f"     {tag}: deliberate wait, nothing assigned this consult")
        if e.get("reason"):
            print(f"        waiting because: \"{e['reason']}\"")
    elif r == "error":
        print(f"     MODEL ERROR: {e.get('detail')}")
        print("     -> rule floor decides this round")
    elif r == "rule_assigned":
        rep = f" (x{e['repeats']})" if e.get("repeats") else ""
        print(f"     -> RULE ASSIGNED task {tid} ({names.get(tid, '?')}) "
              f"to {e.get('arm')}{rep}, destination by {e.get('dest_by')}")
        return
    else:
        print(f"     {e}")
    if e.get("latency_ms") is not None:
        print(f"        latency {e['latency_ms'] / 1000:.1f} s")


def print_rounds(ep, path):
    log = (ep.get("allocator") or {}).get("log") or []
    names = {t["id"]: short(t["object"]) for t in ep.get("tasks", [])}
    views = load_audit_views(path)
    if not log:
        print("\nno decision log: b1 is the deterministic rule walk; its "
              "story is the claim order in the timeline below")
        return

    # A log whose entries carry no "round" key belongs to a column with no
    # consult rounds to reconstruct (the random floor logs one entry per
    # PICK, keyed on task). Reconstructing states per round is meaningless
    # there, and r - CLAIM_WINDOW on a None round is a crash, so print the
    # picks verbatim and stop.
    if not any("round" in e for e in log):
        print("\nno consult rounds (this column decides per pick, not per "
              "round); the pick log verbatim:")
        for e in log:
            print("  " + ", ".join(f"{k}={v}" for k, v in e.items()))
        return

    rounds = []
    for e in log:
        if not rounds or rounds[-1][0] != e.get("round"):
            rounds.append((e.get("round"), []))
        rounds[-1][1].append(e)

    consult_i = 0
    for r, entries in rounds:
        print(f"\n{'-' * 62}")
        print(f"ROUND {r}")
        print(f"{'-' * 62}")
        print_state("STATE BEFORE (this round's claims excluded)",
                    reconstruct(ep, r, exclude_claims_from=r - CLAIM_WINDOW))
        print("\n  DECISIONS")
        n = 0
        for e in entries:
            if "matrix" in e:
                print_b2_round(e, names)
                continue
            view = None
            if e.get("result") in CONSULT_RESULTS:
                n += 1
                if consult_i < len(views):
                    view = views[consult_i]
                    consult_i += 1
            print_decision(n, e, names, view)
        print()
        print_state("STATE AFTER (this round's claims applied)",
                    reconstruct(ep, r))

    stats = (ep.get("allocator") or {}).get("stats")
    if stats:
        print(f"\nstats: {stats}")


# ----------------------------------------------------------------- main --

def trace(path, rounds_only=False):
    ep = json.load(open(path))
    meta, summ = ep.get("meta", {}), ep.get("summary", {})
    section("1 HEADER")
    print(os.path.basename(path))
    print(f"allocator={meta.get('allocator')} "
          + (f"condition={meta.get('condition')} " if meta.get("condition")
             else "")
          + f"seed={meta.get('seed')} layout={meta.get('layout')} "
          f"prompt={meta.get('prompt_version')}")
    print(f"verdict={summ.get('verdict')} sorted={summ.get('sorted')} "
          f"makespan={summ.get('makespan_ticks')} "
          f"blocked_total={summ.get('blocked_ticks_total')} "
          f"requeued={summ.get('requeued')}")

    section("2 ALLOCATOR ROUNDS")
    print_rounds(ep, path)
    if rounds_only:
        return

    section("3 EXECUTION TIMELINE")
    items = []
    for t in ep.get("tasks", []):
        tid = f"task {t['id']:>2} {short(t['object'])}"
        if t.get("submit_tick") is not None:
            items.append((t["submit_tick"], 0,
                          f"{tid} submitted (kind={t.get('kind')})"))
        if t.get("claim_tick") is not None:
            items.append((t["claim_tick"], 1,
                          f"{tid} claimed by {t.get('arm')} "
                          f"(dest_by={t.get('dest_by')}, "
                          f"zones={t.get('required_zones')})"))
        if t.get("done_tick") is not None:
            items.append((t["done_tick"], 2, f"{tid} COMPLETED"))
        if t.get("failed"):
            items.append((t.get("done_tick") or 0, 2, f"{tid} FAILED"))
    for e in ep.get("events", []):
        items.append((e.get("tick", 0), 3,
                      f"[{e.get('type', 'note')}] "
                      + ", ".join(f"{k}={v}" for k, v in e.items()
                                  if k not in ("tick", "type"))))
    for tick, _, text in sorted(items, key=lambda x: (x[0], x[1])):
        print(f"  t={tick:>5}  {text}")

    section("4 PER-TASK SUMMARY")
    for t in ep.get("tasks", []):
        state = ("done" if t.get("done")
                 else "FAILED" if t.get("failed") else "open")
        print(f"  task {t['id']:>2} {short(t['object']):<16} {state:<7} "
              f"arm={str(t.get('arm')):<9} kind={t.get('kind'):<12} "
              f"wait={t.get('wait_ticks')} attempts={t.get('attempts')} "
              f"dest_by={t.get('dest_by')}"
              + (f" waiting_on={t['waiting_on']}"
                 if t.get("waiting_on") is not None else ""))

    section("5 LOCKS")
    for z, v in sorted(((ep.get("locks") or {}).get("by_zone") or {}).items()):
        print(f"  {z:8s} acquires={v.get('acquires')} "
              f"reserves={v.get('reserves')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="+", help="episode JSON path(s)")
    ap.add_argument("--rounds-only", action="store_true",
                    help="print only header + allocator rounds")
    a = ap.parse_args()
    for i, path in enumerate(a.episodes):
        if i:
            print("\n" + "#" * 70)
        trace(path, rounds_only=a.rounds_only)


if __name__ == "__main__":
    main()
