"""Metrics pipeline: episode JSONs -> per-episode metrics -> per-cell table.

Isaac-free. Imports the REAL registry (ycb_objects), basket table
(ycb_scene) and reachability rasters (zones.ZoneMap), so capability and
relay ground truth are the project's own, not re-implementations.

  python3 analysis/episode_metrics.py out/*.json [--csv out/metrics.csv]

Per episode it computes every metric of the scope PDF that the JSON can
support, and prints None with a reason for the ones it cannot yet:

  M1  completion rate            sorted_correct / sorted_total
  M2  makespan (ticks)
  M3  gap to analytical bound    bound from fastest OBSERVED per-arm task
                                 cycles over each arm's mandatory set
                                 (needs spawn_xy in objects; else None)
  M4  capability-feasible rate   1.0 by construction for executed legs
                                 (informative only; VLM raw proposal
                                 rejections appear in D-diagnostics)
  M5  exclusive task delay       mean wait of capability-exclusive tasks
  M6  relay precision            executed relays that were mandatory
  M7  relay recall               mandatory relays that were relayed
                                 (M6/M7 need spawn_xy; else None)
  M8  blocked ticks              total (and per arm in the CSV)
  M9  pad waiting                None (no pad-wait counter in the JSON
                                 yet; runner upgrade pending)
  M10 recovery latency           disruption event tick -> completion of
                                 the disrupted object's task
  M11 wasted attempts            requeues (proxy; per-arm attribution
                                 pending disruption-target logging)
  M12 completion under disruption  M1 when profile != none
  D1  travel_m                   total EE path (and per arm in CSV)
  D2  first-pass validity        valid_first / proposal rounds (vlm)
  D3  fallback rate              fallback / proposal rounds (vlm)
  D4  model-authored rate        model-valid legs / (those + rule floor)
  D5  region declaration accuracy  1 - mismatches / valid rounds (vlm)

Provenance: dest_by histogram over tasks (vlm claims must always be
conditioned on it).
"""

import argparse
import csv
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ycb"))

from ycb_objects import YCB                                   # noqa: E402
from ycb_scene import BASKETS, CATEGORY_BASKET                # noqa: E402
from core.cell import cell_config as C                        # noqa: E402

try:
    from core.cell.zones import ZoneMap
    _ZM = ZoneMap()
except Exception as e:                                        # rasters absent
    _ZM = None
    print(f"[analyze] no reachability rasters ({e}); "
          f"M3/M6/M7 will be None", file=sys.stderr)


def base_name(scene_name):
    return scene_name[4:] if scene_name.startswith("ycb_") else scene_name


def capable_arms(obj):
    """Capability-only arm set from the REAL registry flags."""
    spec = YCB.get(base_name(obj), {})
    if spec.get("delicate"):
        return [a for a in C.ARMS
                if C.ARM_TYPES[C.ARMS[a]["type"]]["delicate_ok"]]
    if spec.get("grasp_m", 0) > C.ARM_TYPES["franka"]["max_grasp_m"] \
            or spec.get("mass_kg", 0) > C.ARM_TYPES["franka"]["payload_kg"]:
        return [a for a in C.ARMS if C.ARMS[a]["type"] == "ur10"]
    return list(C.ARMS)


def exclusive(obj):
    return len({C.ARMS[a]["type"] for a in capable_arms(obj)}) == 1


def dest_of(category):
    return BASKETS[CATEGORY_BASKET[category]]["pos"]


def relay_mandatory(obj, spawn_xy, category):
    """True if NO single capable arm reaches both spawn and destination
    (the project's own reachability rasters). None if undecidable."""
    if _ZM is None or spawn_xy is None:
        return None
    dx, dy = dest_of(category)
    for a in capable_arms(obj):
        if _ZM.reachable(a, *spawn_xy) and _ZM.reachable(a, dx, dy):
            return False
    return True


# ---------------------------------------------------------------------------
# PROPOSED layer: what the MODEL asked for, before the validator repaired
# anything. Kept strictly separate from the EXECUTED layer below, because an
# episode's outcome is a joint product of model and guard and the two must
# never be reported as one number.
# ---------------------------------------------------------------------------

REJECTION_CAUSES = (                      # first match wins, order matters
    ("unparseable", ("not valid json",)),
    ("busy_arm", ("is not idle",)),
    ("pad_rule", ("already at pad",)),
    ("capability", ("cannot grasp",)),
    ("reach", ("cannot reach both", "handover pad is needed",
               "cannot reach object and pad")),
    ("task_state", ("already being handled", "already finished",
                    "does not exist")),
    ("unknown_arm", ("unknown arm",)),
)


def capability_violations(arm, obj):
    """Which of the THREE capability limits this arm fails for this object.

    cell_config.can_grasp collapses size, weight and the delicate rule into
    one boolean, and the validator returns one string for all three
    ("arm X cannot grasp object Y"), so the logs cannot tell them apart.
    For a study of capability-aware allocation that is the one breakdown a
    reader wants, so it is recovered HERE instead.

    Derived, not logged: the rejection record already carries arm and
    task_id, and the episode maps task to object, so no prompt change, no
    schema change, and every episode already recorded gets the breakdown.

    Returns a list in can_grasp's own precedence, e.g. ["delicate"] or
    ["grasp", "payload"]. Empty means this arm could in fact have taken it,
    which would indicate the rejection was not really a capability one.
    """
    spec = YCB.get(base_name(obj))
    kind = (C.ARMS.get(arm) or {}).get("type")
    if spec is None or kind is None:
        return None                       # cannot decide, do not guess
    t = C.ARM_TYPES[kind]
    out = []
    if spec.get("delicate", False) and not t["delicate_ok"]:
        out.append("delicate")
    if spec.get("grasp_m", 0) > t["max_grasp_m"]:
        out.append("grasp")
    if spec.get("mass_kg", 0) > t["payload_kg"]:
        out.append("payload")
    return out


def capability_detail(arm, obj):
    """One human line naming the limit and the two numbers that broke it."""
    v = capability_violations(arm, obj)
    if not v:
        return None
    spec, t = YCB[base_name(obj)], C.ARM_TYPES[C.ARMS[arm]["type"]]
    bits = []
    for name in v:
        if name == "delicate":
            bits.append(f"{obj} is delicate and {arm} has no "
                        f"force-controlled grasp")
        elif name == "grasp":
            bits.append(f"{arm} opens to {t['max_grasp_m']:.3f} m, "
                        f"{obj} is {spec['grasp_m']:.3f} m")
        else:
            bits.append(f"{arm} lifts {t['payload_kg']:.1f} kg, "
                        f"{obj} is {spec['mass_kg']:.3f} kg")
    return "; ".join(bits)


def classify_rejection(r):
    """Cause label for one rejected proposal (see REJECTION_CAUSES)."""
    if r.get("unparseable"):
        return "unparseable"
    why = (r.get("rejected_because") or "").lower()
    for name, needles in REJECTION_CAUSES:
        if any(n in why for n in needles):
            return name
    return "other"


def mandatory_task_ids(ep):
    """Primary task ids whose object CANNOT be delivered by any single
    capable arm (raster ground truth). None if the episode lacks
    spawn_xy or the rasters are unavailable."""
    objects = {o["name"]: o for o in ep.get("objects", []) or []}
    if _ZM is None or not objects or not all(
            "spawn_xy" in o for o in objects.values()):
        return None
    out = set()
    for t in ep.get("tasks", []):
        if t.get("kind") != "primary":
            continue
        o = objects.get(t["object"])
        if o is None:
            continue
        if relay_mandatory(t["object"], o.get("spawn_xy"), o.get("category")):
            out.add(t["id"])
    return out


def proposal_layer(ep, mandatory=None):
    """Model-authored proposals only. Returns a dict of P_* fields.

    A proposal is one model reply that named a task and an arm: every
    entry of rejected[] plus every accepted decision. Deliberate noops
    and API errors are counted but are not proposals.

    Relay figures are MODEL-level: computed from what the model itself
    routed via a pad, before any feedback or rule repair. A relay
    proposed for an object ALREADY resting on a pad is counted as stale,
    never as a correct relay, so the model cannot earn recall by
    re-proposing a handover that already happened."""
    log = (ep.get("allocator") or {}).get("log") or []
    obj_of = {t["id"]: t["object"] for t in ep.get("tasks", []) or []}
    causes, relays, missed = {}, set(), set()
    cap_causes = {}                       # which capability limit broke
    stale = accepted_first = accepted_after = rejected = 0
    noop = errors = 0
    for e in log:
        for r in (e.get("rejected") or []):
            rejected += 1
            cause = classify_rejection(r)
            causes[cause] = causes.get(cause, 0) + 1
            tid = r.get("task_id")
            if cause == "capability":
                # split the merged bucket into size / weight / delicate
                v = capability_violations(r.get("arm"), obj_of.get(tid, ""))
                key = ("capability_" + "+".join(v)) if v else (
                    "capability_unattributed" if v is not None
                    else "capability_unknown_object")
                cap_causes[key] = cap_causes.get(key, 0) + 1
            if r.get("via_pad"):
                if cause == "pad_rule":
                    stale += 1
                elif tid is not None:
                    relays.add(tid)
            elif cause == "reach" and tid is not None:
                missed.add(tid)       # proposed direct, a relay was needed
        res = e.get("result")
        if res == "valid_first":
            accepted_first += 1
        elif res == "valid_after_feedback":
            accepted_after += 1
        elif res == "noop":
            noop += 1
        elif res == "error":
            errors += 1
        if res in ("valid_first", "valid_after_feedback") and e.get("via_pad"):
            if e.get("task_id") is not None:
                relays.add(e["task_id"])

    accepted = accepted_first + accepted_after
    proposals = accepted + rejected
    p = {"P_proposals": proposals,
         "P_accepted_first": accepted_first,
         "P_accepted_after_feedback": accepted_after,
         "P_rejected": rejected,
         "P_raw_validity": round(accepted / proposals, 3) if proposals else None,
         "P_rejected_by_cause": causes,
         # the merged "capability" bucket split into the limit that broke
         "P_capability_by_limit": cap_causes,
         "P_noops": noop, "P_errors": errors,
         "P_relay_proposals": sorted(relays),
         "P_stale_relay_proposals": stale,
         "P_missed_necessity": sorted(missed)}
    if mandatory is None:
        p["P_relay_precision_model"] = None
        p["P_relay_recall_model"] = None
    else:
        hit = relays & mandatory
        p["P_relay_precision_model"] = (round(len(hit) / len(relays), 3)
                                        if relays else None)
        p["P_relay_recall_model"] = (round(len(hit) / len(mandatory), 3)
                                     if mandatory else None)
    return p


def utilisation(ep):
    """Per-arm time decomposition (U1-U4), derived from fields already
    logged. Nothing here needs a schema change.

    An arm's tick is in exactly one of three states:

      occupied   holding a claimed task, from claim_tick to done_tick
      idle       holding nothing at all
      (blocked)  a SUBSET of occupied: the coordinator only counts a
                 blocked tick for an arm that already holds a claim and
                 cannot acquire the zone lock it needs (tasks.py, the
                 _assign pad/zone branch). So blocked must be subtracted
                 out of occupied, never added beside it.

    This matters because blocked_ticks_total alone is misleading: an
    allocator that leaves arms unassigned scores well on it while losing
    makespan to idleness that the counter cannot see.
    """
    summ = ep.get("summary", {}) or {}
    span = summ.get("makespan_ticks")
    per_arm = ep.get("per_arm", {}) or {}
    if not span or not per_arm:
        return {}

    occupied = {a: 0 for a in per_arm}
    for t in ep.get("tasks", []) or []:
        a, c = t.get("arm"), t.get("claim_tick")
        if a is None or c is None or a not in occupied:
            continue
        d = t.get("done_tick")
        if d is None:                  # still held when the episode ended
            d = span
        if d > c:
            occupied[a] += d - c

    by_arm, clipped = {}, []
    for a, occ in occupied.items():
        blocked = (per_arm.get(a) or {}).get("blocked_ticks", 0) or 0
        if occ > span:                 # legs overlapped: report, do not hide
            clipped.append(a)
            occ = span
        blocked = min(blocked, occ)
        by_arm[a] = {"occupied": occ,
                     "blocked": blocked,
                     "productive": occ - blocked,
                     "idle": span - occ}

    n = len(by_arm) or 1
    tot_occ = sum(v["occupied"] for v in by_arm.values())
    tot_blk = sum(v["blocked"] for v in by_arm.values())
    out = {"U_by_arm": by_arm,
           "U1_occupied_frac": round(tot_occ / (span * n), 3),
           "U2_productive_frac": round((tot_occ - tot_blk) / (span * n), 3),
           "U3_idle_ticks_total": span * n - tot_occ,
           "U4_idle_frac": round((span * n - tot_occ) / (span * n), 3)}
    if clipped:
        out["U_overlap_warning"] = clipped
    return out


def episode_metrics(ep, cycles_by_arm=None):
    meta, summ = ep.get("meta", {}), ep.get("summary", {})
    tasks = ep.get("tasks", [])
    objects = {o["name"]: o for o in ep.get("objects", []) or []}
    m = {"file": None,
         "allocator": meta.get("allocator"),
         "condition": meta.get("condition"),
         "layout": meta.get("layout"), "seed": meta.get("seed"),
         "disruptions": meta.get("disruptions"),
         "prompt_version": meta.get("prompt_version"),
         "verdict": summ.get("verdict")}

    mx = ep.get("metrics", {})
    sc, st = mx.get("sorted_correct"), mx.get("sorted_total")
    m["M1_completion"] = (sc / st) if sc is not None and st else None
    m["M2_makespan"] = summ.get("makespan_ticks")
    m["M8_blocked"] = summ.get("blocked_ticks_total")
    m["M9_pad_wait"] = mx.get("pad_wait_ticks_total")   # None pre-lock era
    m["M9_pad_wait_by_pad"] = mx.get("pad_wait_by_pad")
    m["D1_travel_m"] = mx.get("travel_m_total")
    m["M4_capability_feasible"] = 1.0             # by construction (guard)
    m.update(utilisation(ep))   # U1-U4: where the lost time actually went

    # M5: exclusive task delay
    waits = [t.get("wait_ticks") for t in tasks
             if t.get("kind") == "primary" and exclusive(t["object"])
             and t.get("wait_ticks") is not None]
    m["M5_exclusive_wait"] = round(sum(waits) / len(waits), 1) if waits else None

    # M6/M7: relay precision and recall vs raster ground truth
    prec = rec = None
    if _ZM is not None and objects and all(
            "spawn_xy" in o for o in objects.values()):
        primaries = [t for t in tasks if t.get("kind") == "primary"]
        relayed = {t["object"] for t in tasks
                   if t.get("kind") == "handover_leg"}
        mandatory = set()
        for t in primaries:
            o = objects.get(t["object"])
            need = relay_mandatory(t["object"], o.get("spawn_xy"),
                                   o.get("category"))
            if need:
                mandatory.add(t["object"])
        if relayed:
            prec = round(len(relayed & mandatory) / len(relayed), 3)
        if mandatory:
            rec = round(len(relayed & mandatory) / len(mandatory), 3)
    m["M6_relay_precision"] = prec
    m["M7_relay_recall"] = rec

    # M3: gap to the analytical bound (needs pooled observed cycles)
    m["M3_gap"] = None
    if cycles_by_arm and _ZM is not None and objects and all(
            "spawn_xy" in o for o in objects.values()):
        per_arm_load = {}
        for t in tasks:
            if t.get("kind") != "primary":
                continue
            o = objects.get(t["object"])
            caps = capable_arms(t["object"])
            feas = [a for a in caps
                    if _ZM.reachable(a, *o["spawn_xy"])
                    and _ZM.reachable(a, *dest_of(o["category"]))]
            if len(feas) == 1:                    # single-ARM mandatory
                a = feas[0]
                cyc = cycles_by_arm.get(a)
                if cyc:
                    per_arm_load[a] = per_arm_load.get(a, 0) + cyc
        if per_arm_load and m["M2_makespan"] is not None:
            bound = max(per_arm_load.values())
            m["M3_gap"] = m["M2_makespan"] - bound
            m["bound"] = bound

    # M10-M12: disruption metrics
    m["M12_completion_disrupted"] = (m["M1_completion"]
                                     if (meta.get("disruptions")
                                         not in (None, "none")) else None)
    m["M11_wasted_attempts"] = summ.get("requeued")
    lat = []
    ev = ep.get("events", [])
    for e in ev:
        if e.get("type") in ("disruption", "sim") and e.get("obj"):
            done = [t.get("done_tick") for t in tasks
                    if t.get("object") == e["obj"]
                    and t.get("done_tick") is not None
                    and t["done_tick"] >= e.get("tick", 0)]
            if done:
                lat.append(min(done) - e.get("tick", 0))
    m["M10_recovery_latency"] = round(sum(lat) / len(lat), 1) if lat else None

    # D2-D5 + provenance (vlm only)
    stats = (ep.get("allocator") or {}).get("stats") or {}
    vf = stats.get("valid_first", 0)
    va = stats.get("valid_after_feedback", 0)
    fb = stats.get("fallback", 0)
    # Denominator = EVERY consult round, noops included. Before schema v4 a
    # noop looked like a deliberate wait and excluding it was defensible.
    # We now know every noop in every episode measured so far was issued on
    # the second attempt, after a refused proposal, so those rounds are
    # first-pass failures. Excluding them overstated D2 by about a third
    # (vlm1: 0.533 excluding, 0.400 including, against P_raw_validity 0.312
    # at the proposal level). The legacy figures are kept beside them under
    # _excl_noops so older reports remain reconstructable.
    noop = stats.get("noop", 0)
    rounds_excl = vf + va + fb
    rounds = rounds_excl + noop
    if rounds:
        m["D2_first_pass"] = round(vf / rounds, 3)
        m["D3_fallback"] = round(fb / rounds, 3)
        m["D2_first_pass_excl_noops"] = (round(vf / rounds_excl, 3)
                                         if rounds_excl else None)
        m["D3_fallback_excl_noops"] = (round(fb / rounds_excl, 3)
                                       if rounds_excl else None)
        m["D6_noop_rate"] = round(noop / rounds, 3)
    if rounds_excl:
        m["D4_model_authored"] = round(
            (vf + va) / (vf + va + stats.get("rule_assigned", 0)), 3) \
            if (vf + va + stats.get("rule_assigned", 0)) else None
        m["D5_region_accuracy"] = round(
            1 - stats.get("region_mismatches", 0) / (vf + va), 3) \
            if (vf + va) else None
        m["noop_count"] = stats.get("noop")
    prov = {}
    for t in tasks:
        prov[t.get("dest_by")] = prov.get(t.get("dest_by"), 0) + 1
    m["provenance_dest_by"] = prov
    # PROPOSED layer (model, pre-validator), reported beside the EXECUTED
    # figures above and never folded into them.
    if (ep.get("allocator") or {}).get("log"):
        m.update(proposal_layer(ep, mandatory=mandatory_task_ids(ep)))
    return m


def observed_cycles(all_eps):
    """Fastest observed claim->done cycle per arm across ALL input
    episodes (the bound's 'fastest observed' clause)."""
    best = {}
    for ep in all_eps:
        for t in ep.get("tasks", []):
            a, c, d = t.get("arm"), t.get("claim_tick"), t.get("done_tick")
            if a and c is not None and d is not None and d > c:
                if a not in best or d - c < best[a]:
                    best[a] = d - c
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="+")
    ap.add_argument("--csv", default=None)
    a = ap.parse_args()

    eps = []
    for path in a.episodes:
        ep = json.load(open(path))
        ep["_file"] = path
        eps.append(ep)
    cycles = observed_cycles(eps)

    rows = []
    for ep in eps:
        m = episode_metrics(ep, cycles_by_arm=cycles)
        m["file"] = os.path.basename(ep["_file"])
        rows.append(m)

    cols = ["file", "allocator", "condition", "seed", "layout",
            "disruptions", "verdict", "M1_completion", "M2_makespan",
            "M3_gap", "M5_exclusive_wait", "M6_relay_precision",
            "M7_relay_recall", "M8_blocked", "M9_pad_wait",
            "M11_wasted_attempts",
            "M12_completion_disrupted", "D1_travel_m",
            "U1_occupied_frac", "U2_productive_frac",
            "U3_idle_ticks_total", "U4_idle_frac", "D2_first_pass",
            "D3_fallback", "D6_noop_rate", "D2_first_pass_excl_noops",
            "D3_fallback_excl_noops",
            "D4_model_authored", "D5_region_accuracy",
            "noop_count",
            # PROPOSED layer (model, pre-validator)
            "P_proposals", "P_accepted_first", "P_accepted_after_feedback",
            "P_rejected", "P_raw_validity", "P_rejected_by_cause",
            "P_capability_by_limit",
            "P_relay_precision_model", "P_relay_recall_model",
            "P_stale_relay_proposals", "P_missed_necessity"]
    print("\nPER-EPISODE METRICS")
    for r in rows:
        print(f"\n  {r['file']}  ({r['allocator']}"
              + (f"/{r['condition']}" if r.get("condition") else "") + ")")
        print("   EXECUTED (what the cell achieved: model + guard)")
        for c in cols[7:]:
            if c in r and r[c] is not None:
                print(f"    {c:26s} {r[c]}")
        print(f"    {'provenance_dest_by':26s} {r['provenance_dest_by']}")
        if r.get("U_by_arm"):
            print("   UTILISATION (occupied = productive + blocked; "
                  "idle is invisible to M8)")
            print(f"    {'arm':12s} {'occupied':>9s} {'productive':>11s} "
                  f"{'blocked':>8s} {'idle':>7s}")
            for arm_name in sorted(r["U_by_arm"]):
                u = r["U_by_arm"][arm_name]
                print(f"    {arm_name:12s} {u['occupied']:>9d} "
                      f"{u['productive']:>11d} {u['blocked']:>8d} "
                      f"{u['idle']:>7d}")
            if r.get("U_overlap_warning"):
                print(f"    NOTE overlapping legs clipped to makespan: "
                      f"{r['U_overlap_warning']}")
        if r.get("P_proposals"):
            print("   PROPOSED (what the model asked for, pre-validator)")
            for c in ("P_proposals", "P_accepted_first",
                      "P_accepted_after_feedback", "P_rejected",
                      "P_raw_validity", "P_rejected_by_cause",
                      "P_capability_by_limit",
                      "P_relay_precision_model", "P_relay_recall_model",
                      "P_relay_proposals", "P_missed_necessity",
                      "P_stale_relay_proposals", "P_noops", "P_errors"):
                if r.get(c) not in (None, {}, [], 0):
                    print(f"    {c:26s} {r[c]}")

    # per-cell aggregation (mean over reps)
    cells = {}
    for r in rows:
        key = (r["allocator"], r["condition"], r["layout"],
               r["seed"], r["disruptions"])
        cells.setdefault(key, []).append(r)
    print("\nPER-CELL SUMMARY (mean over reps)")
    print(f"  {'cell':38s} {'n':>2s} {'M1':>6s} {'M2':>7s} "
          f"{'M8':>6s} {'D1':>7s}")
    for key, rs in sorted(cells.items(), key=lambda kv: str(kv[0])):
        def mean(c):
            v = [r[c] for r in rs if r.get(c) is not None]
            return round(sum(v) / len(v), 2) if v else None
        name = "/".join(str(k) for k in key if k is not None)
        print(f"  {name:38s} {len(rs):>2d} {str(mean('M1_completion')):>6s} "
              f"{str(mean('M2_makespan')):>7s} {str(mean('M8_blocked')):>6s} "
              f"{str(mean('D1_travel_m')):>7s}")

    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols + ["provenance_dest_by",
                                                     "prompt_version",
                                                     "bound"],
                               extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"\n[analyze] wrote {a.csv} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
