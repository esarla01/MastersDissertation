"""Would an availability buffer have been worth anything? Read-only.

THE QUESTION. Today an arm counts as assignable only once it emits
"arm_idle". An arm five ticks from idle and an arm two thousand ticks from
idle are treated identically, because both are simply "not idle". A buffer
would extend availability to arms still winding down (RETREAT / GO_HOME /
PRE_TUCK / SETTLING), pricing the known remainder into the cost.

Before building that, measure whether it could have helped. This tool
computes, per claim, whether some OTHER arm became idle shortly afterwards
that was BOTH feasible for the task AND cheaper than the arm actually
chosen, and reports the total ticks that could have been saved.

WHAT THE NUMBER IS. An UPPER BOUND on the buffer's value, and deliberately
generous:

  - It assumes the buffer would have picked the better arm every time.
  - It ignores that waiting for an arm delays the task's start, which the
    real cost model would charge for (a partial charge is applied, see
    "net", but arrival is assumed instantaneous at arm_idle).
  - It ignores knock-on effects: taking a different arm changes every
    later round, which can help or hurt.

So a near-zero result is CONCLUSIVE (the buffer cannot help), while a large
result is only suggestive (the buffer might help). That asymmetry is the
point: this tool exists to kill the idea cheaply, not to justify it.

  python3 analysis/episode_buffer_value.py out/fit_b1_decision_rich.json
  python3 analysis/episode_buffer_value.py out/*.json --window 200

--window is how far ahead to look, in ticks. Defaults to 240, which is
above the measured fold time for either arm type (about 75 for a UR, 180
for a Franka), so it covers an arm that had finished its task and was
simply folding when the claim was made.
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ycb"))

from core.cell import cell_config as C                        # noqa: E402
from core.cell.zones import ZoneMap                           # noqa: E402
from ycb_objects import YCB, register_specs                   # noqa: E402
from ycb_scene import BASKETS, CATEGORY_BASKET                # noqa: E402

for _n in YCB:
    register_specs(C.OBJECT_SPECS, "ycb_" + _n, _n)

_ZM = None


def zonemap():
    global _ZM
    if _ZM is None:
        _ZM = ZoneMap()
    return _ZM


def base(n):
    return n[4:] if n.startswith("ycb_") else n


def cost_for(arm, obj, obj_xy, dest_xy):
    """Tick cost of arm doing this task, or None if it cannot.

    Capability and reachability use the same rules the validator applies;
    the route is the full base -> object -> destination -> home journey the
    timing coefficients were fitted over."""
    spec = YCB.get(base(obj))
    if spec is None or obj_xy is None or dest_xy is None:
        return None
    t = C.ARM_TYPES[C.ARMS[arm]["type"]]
    if spec.get("delicate", False) and not t["delicate_ok"]:
        return None
    if spec["grasp_m"] > t["max_grasp_m"] or spec["mass_kg"] > t["payload_kg"]:
        return None
    zm = zonemap()
    if not (zm.reachable(arm, *obj_xy) and zm.reachable(arm, *dest_xy)):
        return None
    return C.leg_cost(arm, C.route_m(arm, obj_xy, dest_xy), 1)


def analyse(path, window):
    ep = json.load(open(path))
    events = ep.get("events", []) or []
    tasks = ep.get("tasks", []) or []
    spawn = {o["name"]: tuple(o["spawn_xy"])
             for o in ep.get("objects", []) or [] if o.get("spawn_xy")}

    # every transition into IDLE, in time order
    idles = sorted(((e.get("tick"), e.get("arm")) for e in events
                    if e.get("type") == "arm_idle"
                    and e.get("tick") is not None and e.get("arm")),
                   key=lambda z: z[0])

    rows, missed = [], 0
    for t in tasks:
        arm, ct = t.get("arm"), t.get("exec_start_tick") or t.get("claim_tick")
        obj, dest = t.get("object"), t.get("dest")
        if arm is None or ct is None or obj is None or dest is None:
            missed += 1
            continue
        oxy = spawn.get(obj)
        if oxy is None:
            missed += 1
            continue
        dxy = tuple(dest)
        chosen = cost_for(arm, obj, oxy, dxy)
        if chosen is None:
            missed += 1
            continue

        # arms that became idle in (ct, ct + window]
        soon = [(tick, a) for tick, a in idles if ct < tick <= ct + window
                and a != arm]
        best = None
        for tick, a in soon:
            c = cost_for(a, obj, oxy, dxy)
            if c is None:
                continue
            wait = tick - ct              # ticks lost waiting for that arm
            net = c + wait                # charge the wait, generously
            if net < chosen and (best is None or net < best[3]):
                best = (a, tick, wait, net)
        if best is not None:
            a, tick, wait, net = best
            rows.append({"task": t.get("id"), "object": base(obj),
                         "chose": arm, "chosen_cost": chosen,
                         "better": a, "in_ticks": wait,
                         "net": net, "saved": chosen - net})
    return ep, rows, missed, len(tasks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="+")
    ap.add_argument("--window", type=int, default=240,
                    help="how far ahead to look for an arm going idle "
                         "(ticks; default 240, above either arm's fold time)")
    ap.add_argument("--show", type=int, default=8,
                    help="how many opportunities to list per episode")
    a = ap.parse_args()

    paths = []
    for pat in a.episodes:
        paths.extend(sorted(glob.glob(pat)) or [pat])

    grand_saved, grand_ops, grand_tasks = 0.0, 0, 0
    print(f"\nlook-ahead window: {a.window} ticks\n")
    print(f"{'episode':<34}{'makespan':>9}{'tasks':>7}{'opps':>6}"
          f"{'ticks saved':>13}{'% makespan':>12}")
    for p in paths:
        try:
            ep, rows, missed, ntasks = analyse(p, a.window)
        except Exception as exc:                       # noqa: BLE001
            print(f"{os.path.basename(p)[:33]:<34}  skipped: {exc}")
            continue
        mk = (ep.get("summary", {}) or {}).get("makespan_ticks") or 0
        saved = sum(r["saved"] for r in rows)
        grand_saved += saved
        grand_ops += len(rows)
        grand_tasks += ntasks
        pct = (100.0 * saved / mk) if mk else 0.0
        print(f"{os.path.basename(p)[:33]:<34}{mk:>9}{ntasks:>7}"
              f"{len(rows):>6}{saved:>13.0f}{pct:>11.1f}%")
        for r in rows[:a.show]:
            print(f"      task {r['task']:>3} {r['object']:<14} chose "
                  f"{r['chose']:<9}({r['chosen_cost']:>5.0f})  "
                  f"{r['better']:<9} free in {r['in_ticks']:>4} "
                  f"-> net {r['net']:>5.0f}  saves {r['saved']:>5.0f}")

    print("\n" + "=" * 72)
    if grand_ops == 0:
        print("VERDICT: no opportunities found.")
        print("Not once did a cheaper feasible arm become available shortly")
        print("after a claim. An availability buffer cannot help in these")
        print("episodes, and the idea can be closed on evidence.")
    else:
        print(f"VERDICT: {grand_ops} opportunities across {grand_tasks} tasks, "
              f"{grand_saved:.0f} ticks total upper bound.")
        print("This is a GENEROUS upper bound: it assumes the buffer picks")
        print("the better arm every time and ignores knock-on effects on")
        print("later rounds. Compare it against the makespan noise floor")
        print("(~160 ticks) before deciding it is worth a prompt-version bump.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
