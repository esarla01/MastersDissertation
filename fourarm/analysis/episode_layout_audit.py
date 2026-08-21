"""Layout auditor: is there anything to decide in this layout?

Read-only. Answers, before a single episode is spent, the question the
step3 diagnostics forced: how much allocation CHOICE does a layout contain,
and how CONSEQUENTIAL is it in ticks? Measured on the designed layout, mean
capable-and-reaching arms per object was 1.09 and seven multi-idle b2
rounds offered exactly one feasible cell: almost every decision was forced,
which is why minimax was inert and the random floor matched b1 at seed 0.

For each object it reports the arms that are capable of it AND reach it AND
reach its category basket (the true single-arm feasible set the allocators
see), each with its leg_cost in ticks. Layout summary:

  A1 mean feasible arms per object   (choice EXISTS; target >= 2.0)
  A2 objects with >= 2 feasible arms (where the choice lives)
  A3 median cost spread, best vs worst feasible arm, ticks
                                     (choice MATTERS; target > noise ~160)
  A4 relay-required objects          (feasible set empty; scarcity's limit)
  A5 static trap count               (scarce arm attractive for shared work)
  A6 per-arm pickable / completable census (the franka_s question)

These are the tier-validity numbers scope revision 4 promises: "tier
validity is demonstrated, not assumed". Chance legality per tier is
A1-derived: feasible pairs / (arms x objects).

Usage:
  python3 analysis/episode_layout_audit.py                  # all frozen layouts
  python3 analysis/episode_layout_audit.py --layout L2_BALANCED
  python3 analysis/episode_layout_audit.py --episode out/step3_b2_default.json

The episode mode audits the layout an episode ACTUALLY ran (spawn_xy),
so drifted spawns and frozen tables can be compared.

Trap definition (static form of the scope's): a scarce task T_s has exactly
one feasible arm A; a shared task T_h has >= 2 feasible arms including A;
and A is the CHEAPEST feasible arm for T_h, so a greedy allocator is pulled
to spend A on T_h and strand T_s. Counted per (T_s, T_h) pair.
"""
import argparse
import json
import math
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ycb"))

from core.cell import cell_config as C                        # noqa: E402
from core.cell.zones import ZoneMap                           # noqa: E402
from ycb_objects import YCB, register_specs                   # noqa: E402
from ycb_scene import BASKETS, CATEGORY_BASKET                # noqa: E402
import layouts as L                                           # noqa: E402


def base(n):
    return n[4:] if n.startswith("ycb_") else n


def feasible_set(zm, obj, xy):
    """Arms capable of obj that reach BOTH xy and obj's basket, with the
    leg_cost of doing the whole task, sorted cheapest first."""
    spec = YCB[base(obj)]
    bx, by = BASKETS[CATEGORY_BASKET[spec["category"]]]["pos"]
    out = []
    for a in C.ARMS:
        t = C.ARM_TYPES[C.ARMS[a]["type"]]
        if spec.get("delicate", False) and not t["delicate_ok"]:
            continue
        if spec["grasp_m"] > t["max_grasp_m"] or spec["mass_kg"] > t["payload_kg"]:
            continue
        if not (zm.reachable(a, xy[0], xy[1]) and zm.reachable(a, bx, by)):
            continue
        # Full round trip including the return home, matching the span the
        # timing coefficients were fitted over and what the allocator now
        # prices. Auditing a one-way path would rank arms on a journey no
        # arm actually makes.
        out.append((a, C.leg_cost(a, C.route_m(a, xy, (bx, by)), 1)))
    return sorted(out, key=lambda p: p[1])


def audit(name, positions):
    zm = ZoneMap()
    for obj in positions:
        register_specs(C.OBJECT_SPECS, "ycb_" + base(obj), base(obj))

    rows = {}
    for obj, xy in positions.items():
        rows[obj] = feasible_set(zm, obj, xy)

    print(f"\n===== {name} =====")
    print(f"{'object':14s}{'feasible arms (leg_cost ticks, cheapest first)'}")
    for obj, fs in rows.items():
        pretty = ", ".join(f"{a} {c:.0f}" for a, c in fs) or "NONE (relay required)"
        print(f"{base(obj):14s}{pretty}")

    n = len(rows)
    counts = [len(fs) for fs in rows.values()]
    multi = [o for o, fs in rows.items() if len(fs) >= 2]
    relay = [o for o, fs in rows.items() if not fs]
    spreads = [fs[-1][1] - fs[0][1] for fs in rows.values() if len(fs) >= 2]

    # A5 static traps: scarce task's only arm is the CHEAPEST arm of a
    # multi-choice task, so greed is pulled toward stranding the scarce one
    traps = []
    for ts, fs_s in rows.items():
        if len(fs_s) != 1:
            continue
        scarce_arm = fs_s[0][0]
        for th, fs_h in rows.items():
            if th == ts or len(fs_h) < 2:
                continue
            if fs_h[0][0] == scarce_arm:
                traps.append((base(ts), base(th), scarce_arm))

    # A6 the completion census (who could EVER finish each object)
    per_arm = {a: 0 for a in C.ARMS}
    for obj, fs in rows.items():
        for a, _ in fs:
            per_arm[a] += 1

    print(f"\nA1 mean feasible arms/object : {sum(counts) / n:.2f}"
          f"   (target >= 2.0; designed measured 1.09 at spawn)")
    print(f"A2 objects with a real choice: {len(multi)}/{n}  "
          f"{sorted(base(o) for o in multi)}")
    med = statistics.median(spreads) if spreads else 0.0
    print(f"A3 median cost spread        : {med:.0f} ticks over "
          f"{len(spreads)} choice objects   (noise floor ~160)")
    print(f"A4 relay-required            : {len(relay)}  "
          f"{sorted(base(o) for o in relay)}")
    print(f"A5 static traps              : {len(traps)}  "
          + "; ".join(f"{s}<-{h}@{a}" for s, h, a in traps[:6]))
    print(f"A6 single-arm completions    : "
          + ", ".join(f"{a}:{k}" for a, k in per_arm.items()))
    print(f"   chance legality           : "
          f"{sum(counts) / (n * len(C.ARMS)):.2f}")
    return {"mean_feasible": sum(counts) / n, "choice_objects": len(multi),
            "median_spread": med, "relay": len(relay), "traps": len(traps)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layout", help="one frozen layout name (default: all)")
    ap.add_argument("--episode", help="audit an episode JSON's spawn_xy "
                                      "instead of a frozen table")
    a = ap.parse_args()

    if a.episode:
        ep = json.load(open(a.episode))
        positions = {o["name"]: tuple(o["spawn_xy"])
                     for o in ep.get("objects", [])}
        audit(os.path.basename(a.episode), positions)
        return 0

    table = {a.layout: L.LAYOUTS[a.layout]} if a.layout else L.LAYOUTS
    for name, positions in table.items():
        audit(name, positions)
    return 0


if __name__ == "__main__":
    sys.exit(main())
