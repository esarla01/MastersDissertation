"""explain_route: why a handover was or was not available, pad by pad.

A NO_ROUTE rejection says "arm X cannot reach both the object and the
destination, and no handover route exists with it on the first leg". That
sentence is true but opaque. This prints the router's actual working: one
row per exchange pad, one column per condition, and a mark against the
condition that failed.

THE FOUR CONDITIONS A PAD MUST SATISFY

  not-on-pad   the object is not already sitting on this pad
  progress     the pad is at least 0.05 m closer to the destination than
               the object is now. Without this rule the router ping-ponged
               the gelatin box between centre and pad_ne four times.
  first leg    the NAMED arm reaches both the object and the pad
  second leg   some arm, idle or not, can grasp the object and reaches
               both the pad and the destination

All four, on the same pad. If no pad satisfies all four, the proposal is
rejected.

WHY THE NAMED ARM ONLY

rule_based_allocate passes every idle capable arm as a first-leg
candidate, because it is choosing the arm. The validator passes only the
arm the model named, because the model has already chosen and R5 states the
consequence: the cell arranges the handover using YOUR arm for the first
leg. Passing all arms would accept a proposal by silently substituting a
different first-leg arm, and the model's answer would stop being the thing
being scored. This tool prints both, so the difference is visible rather
than argued about.

Usage:

    python3 analysis/ex1_explain_route.py --probes probes/ex1_v2.json \\
        --seq 7 --task 2 --arm franka_s

    python3 analysis/ex1_explain_route.py --probes probes/ex1_v2.json \\
        --from-run out/ex1_gpt_L3nw_r3.jsonl        # every NO_ROUTE in it
"""

import argparse
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.cell import cell_config as C                        # noqa: E402
from analysis.frozen_coord import from_record                 # noqa: E402
from analysis.probe_store import load                         # noqa: E402
from analysis.probe_replay import zonemap                     # noqa: E402

YES, NO = "yes", " NO"


def explain(probe, task_id, arm, zm):
    coord = from_record(probe)
    task = next((t for t in coord.pool if t.id == task_id), None)
    if task is None:
        print(f"  task {task_id} is not in this state's pool")
        return
    p = coord.cell.scene[task.obj].data.root_pos_w[0]
    oxy = (float(p[0]), float(p[1]))
    dest = task.dest
    dead = {a for a in C.ARMS
            if a in coord.agents and coord.agents[a].arm.disabled}

    print(f"\n  task {task_id}: {task.obj}")
    print(f"    object at   ({oxy[0]:+.2f}, {oxy[1]:+.2f})")
    print(f"    destination ({dest[0]:+.2f}, {dest[1]:+.2f})")
    print(f"    named arm   {arm}")
    print()
    print(f"    can {arm} grasp it?          "
          f"{YES if C.can_grasp(arm, task.obj) else NO}")
    print(f"    can {arm} reach the object?  "
          f"{YES if zm.reachable(arm, *oxy) else NO}")
    print(f"    can {arm} reach the dest?    "
          f"{YES if zm.reachable(arm, *dest) else NO}")
    if zm.reachable(arm, *dest):
        print("\n    -> reaches both ends, so no handover is needed and the "
              "proposal is legal on this rule.")
        return

    print("\n    It cannot deliver, so the cell looks for a handover pad.")
    d_dest = math.hypot(oxy[0] - dest[0], oxy[1] - dest[1])
    print(f"    Object is currently {d_dest:.2f} m from the destination; a "
          f"pad must get it below {d_dest - 0.05:.2f} m.")
    print()
    print("    %-9s %7s  %-9s %-9s %-9s %-9s  %s" % (
        "pad", "to dest", "not-on-pad", "progress", "first leg", "second leg",
        "verdict"))

    any_ok = False
    all_first = {}
    for pad, spec in C.EXCHANGE_PADS.items():
        px, py = spec["pos"]
        on_pad = math.hypot(oxy[0] - px, oxy[1] - py) < C.PAD_SKIP_RADIUS
        pad_to_dest = math.hypot(px - dest[0], py - dest[1])
        progresses = pad_to_dest < d_dest - 0.05
        first_ok = (zm.reachable(arm, *oxy) and zm.reachable(arm, px, py))
        second = [a for a in C.ARMS
                  if a not in dead and C.can_grasp(a, task.obj)
                  and zm.reachable(a, px, py) and zm.reachable(a, *dest)]
        second_ok = bool(second)
        # Who COULD have carried the first leg, for the note below.
        all_first[pad] = [a for a in C.ARMS
                          if a not in dead and C.can_grasp(a, task.obj)
                          and zm.reachable(a, *oxy) and zm.reachable(a, px, py)]
        ok = (not on_pad) and progresses and first_ok and second_ok
        any_ok = any_ok or ok
        print("    %-9s %6.2fm  %-9s %-9s %-9s %-9s  %s" % (
            pad, pad_to_dest,
            NO if on_pad else YES,
            YES if progresses else NO,
            YES if first_ok else NO,
            YES if second_ok else NO,
            "USABLE" if ok else "no"))

    print()
    if any_ok:
        print("    -> at least one pad works, so this proposal is LEGAL.")
        return
    print("    -> no pad satisfies all four, so the proposal is rejected "
          "as NO_ROUTE.")

    # The most useful diagnostic: would another first-leg arm have worked?
    alt = sorted({a for pad, arms in all_first.items() for a in arms
                  if a != arm
                  and math.hypot(C.EXCHANGE_PADS[pad]["pos"][0] - dest[0],
                                 C.EXCHANGE_PADS[pad]["pos"][1] - dest[1])
                  < d_dest - 0.05})
    if alt:
        print(f"    NOTE: {', '.join(alt)} could have carried a first leg "
              f"here. The rule allocator would have found that, because it "
              f"chooses the arm. The validator does not, because the model "
              f"already chose {arm} and R5 says the cell uses YOUR arm for "
              f"the first leg.")
    else:
        print("    NOTE: no arm at all could carry a first leg here, so this "
              "task cannot start in this state whatever arm is named.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", required=True)
    ap.add_argument("--seq", type=int)
    ap.add_argument("--source")
    ap.add_argument("--task", type=int)
    ap.add_argument("--arm")
    ap.add_argument("--from-run", help="explain every NO_ROUTE in a run file")
    args = ap.parse_args(argv)

    ps = load(args.probes)
    zm = zonemap()
    by = {(p["provenance"]["seq"], p["provenance"]["source"]): p
          for p in ps["probes"]}

    if args.from_run:
        rows = [json.loads(l) for l in open(args.from_run)]
        seen = set()
        cases = []
        for r in rows:
            if r.get("violation_cause") != "no_route":
                continue
            k = (r["provenance"]["seq"], r["provenance"]["source"],
                 r.get("task_id"), r.get("arm"))
            if k in seen:
                continue
            seen.add(k)
            cases.append(r)
        print("%d distinct NO_ROUTE cases in %s"
              % (len(cases), os.path.basename(args.from_run)))
        for r in cases:
            print("\n" + "=" * 66)
            print("seq %s  (%s)" % (r["provenance"]["seq"],
                                    r["provenance"]["source"]))
            print("  model said: %s" % (r.get("model_reason") or "")[:150])
            explain(by[(r["provenance"]["seq"], r["provenance"]["source"])],
                    r["task_id"], r["arm"], zm)
        return 0

    if args.seq is None or args.task is None or not args.arm:
        ap.error("give --seq, --task and --arm, or --from-run")
    match = [k for k in by if k[0] == args.seq
             and (args.source is None or k[1] == args.source)]
    if not match:
        ap.error(f"no probe with seq {args.seq}")
    if len(match) > 1:
        ap.error(f"seq {args.seq} appears in {[k[1] for k in match]}; "
                 f"add --source")
    print("=" * 66)
    print("seq %s  (%s)" % match[0])
    explain(by[match[0]], args.task, args.arm, zm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
