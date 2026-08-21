"""h_pad_router: the pad router extraction did not change b1, and the new
entry point honours its candidate list.

Context. Until 2026-08-01 the exchange-pad routing logic lived inside
rule_based_allocate and was not callable from anywhere else. The VLM head
therefore had to name a pad itself, which gave it a degree of freedom the
classical heads do not have and made a frozen-state comparison a comparison
of two different questions. route_via_pad is that logic lifted out
unchanged, so the VLM head can choose the arm and delegate the pad exactly
as b1 does.

Two things are checked.

1. b1 is unchanged. A 1980-scenario sweep (44 object placements drawn from
   four frozen layouts x 15 idle-arm subsets x 3 disabled sets) is hashed
   and compared with the digest recorded from the pre-extraction file,
   md5 54d1589278c6b4772d6b4ca91ac4fa24. Twelve of those scenarios are also
   spelled out in full, so a failure says WHICH case moved rather than only
   that something did. The sweep covers all three outcomes: 768 direct, 394
   pad-routed, 818 no-allocation.

2. route_via_pad honours its candidate list. The VLM head will call it with
   exactly one arm, the one the model named, so the router must either
   return that arm or return nothing. It must never substitute a different
   first-leg arm, because that would silently overwrite the model's decision
   and make the audit trail wrong.

Regenerating the digest. It is a function of the four frozen layout tables,
the YCB registry rows those layouts use, ARMS, EXCHANGE_PADS, PAD_SKIP_RADIUS
and can_grasp. Changing any of those legitimately changes the digest: in
particular, accepting the Q1 grasp-threshold question (franka max_grasp_m
0.080 to 0.085) will. Regenerate deliberately, never to make a red harness
go green.

Run:  python3 h_pad_router.py
      python3 h_pad_router.py --dump /tmp/sweep.json   (for diffing)
"""

import hashlib
import itertools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.cell import cell_config as C                        # noqa: E402
from core.cell.zones import ZoneMap                           # noqa: E402
from core.control.tasks import (rule_based_allocate,          # noqa: E402
                                route_via_pad, Task)
from ycb_objects import YCB, register_specs                   # noqa: E402
from ycb_scene import BASKETS, CATEGORY_BASKET                # noqa: E402
import layouts as L                                           # noqa: E402

SWEEP_LAYOUTS = ("decision_rich", "relay_heavy", "designed", "contention")
# REGENERATED 2026-08-02, deliberately, for a capability change and not to
# turn a red harness green. The mustard's grasp_m was corrected from 0.058
# to 0.096, its true lying width, measured by run_ycb_probe. That puts it
# over the Franka's 0.080 limit, so it is UR-only where it used to be
# graspable by all four arms, and every b1 decision involving it moves.
#
#   before  direct 768  pad_routed 394  none 818
#   after   direct 756  pad_routed 346  none 878
#
# The shift is in the expected direction for a PERMISSIVENESS fix: fewer
# direct and fewer routed, more no-allocation. Nothing that was refused
# before is accepted now.
SWEEP_DIGEST = ("146aefc2db14498fd4d65653d1dd4f5e"
                "92febaaf85309a4d791b1cbf65964267")
SWEEP_SHAPE = {"rows": 1980, "direct": 756, "pad_routed": 346, "none": 878}

# Twelve scenarios spelled out, so a digest failure can be localised.
# Recorded from the pre-extraction file, not from the new one.
EXPECTED = [
    ("decision_rich", "soup_can", ["ur_e"], [],
     "ur_e", [0.0, 0.0], [0.0, 0.0]),
    ("decision_rich", "soup_can", ["franka_s"], [],
     "franka_s", [-0.42, -0.28], [-0.42, -0.28]),
    ("decision_rich", "power_drill", ["ur_e"], [],
     "ur_e", [0.0, 0.0], [0.0, 0.0]),
    ("relay_heavy", "soup_can", ["ur_w", "ur_e", "franka_s", "franka_n"], [],
     "ur_e", [0.0, 0.0], [0.0, 0.0]),
    ("relay_heavy", "banana", ["ur_w", "ur_e", "franka_s", "franka_n"], [],
     "franka_s", [0.0, 0.0], [0.0, 0.0]),
    # Was franka_s via pad_sw. With the mustard UR-only, franka_s can no
    # longer take the first leg and ur_e routes via the centre pad instead.
    ("relay_heavy", "mustard", ["ur_w", "ur_e", "franka_s", "franka_n"], [],
     "ur_e", [0.0, 0.0], [0.0, 0.0]),
    ("decision_rich", "soup_can", ["ur_w", "ur_e"], [],
     "ur_w", [-0.7, 0.5], None),
    ("decision_rich", "soup_can", ["ur_w", "ur_e"], ["franka_s"],
     "ur_w", [-0.7, 0.5], None),
    ("relay_heavy", "large_clamp",
     ["ur_w", "ur_e", "franka_s", "franka_n"], ["ur_w"],
     None, None, None),
    ("designed", "large_clamp",
     ["ur_w", "ur_e", "franka_s", "franka_n"], ["ur_w"],
     None, None, None),
    ("contention", "meat_can",
     ["ur_w", "ur_e", "franka_s", "franka_n"], ["ur_w"],
     None, None, None),
    ("decision_rich", "soup_can", ["ur_e"], ["ur_w"],
     "ur_e", [0.0, 0.0], [0.0, 0.0]),
]

fails = []


def check(cond, label, detail=""):
    print(("PASS " if cond else "FAIL ") + label + (f": {detail}" if detail
                                                    else ""))
    if not cond:
        fails.append(label)


def dest_of(obj):
    return tuple(BASKETS[CATEGORY_BASKET[YCB[obj]["category"]]]["pos"])


def rnd(xy):
    return [round(v, 6) for v in xy] if xy else None


def sweep(zm):
    """Every (placement, idle subset, disabled set) through the REAL b1."""
    arms = list(C.ARMS)
    idle_sets = []
    for r in range(1, len(arms) + 1):
        idle_sets.extend(itertools.combinations(arms, r))

    rows = []
    for lname in SWEEP_LAYOUTS:
        for obj, xy in L.LAYOUTS[lname].items():
            for idle in idle_sets:
                for dis in ((), ("franka_s",), ("ur_w",)):
                    t = Task(obj="ycb_" + obj, dest=dest_of(obj))
                    arm, target, sub = rule_based_allocate(
                        t, tuple(xy), list(idle), zm, dis)
                    rows.append({
                        "layout": lname, "obj": obj, "xy": list(xy),
                        "idle": list(idle), "disabled": list(dis),
                        "arm": arm,
                        "target": rnd(target),
                        "sub_dest": rnd(sub.dest) if sub else None,
                        "sub_obj": sub.obj if sub else None,
                    })
    return rows


def main():
    zm = ZoneMap()
    for n in YCB:
        register_specs(C.OBJECT_SPECS, "ycb_" + n, n)

    rows = sweep(zm)

    if "--dump" in sys.argv:
        path = sys.argv[sys.argv.index("--dump") + 1]
        json.dump(rows, open(path, "w"), indent=1)
        print(f"[dump] wrote {len(rows)} rows to {path}")

    shape = {
        "rows": len(rows),
        "direct": sum(1 for r in rows if r["arm"] and not r["sub_dest"]),
        "pad_routed": sum(1 for r in rows if r["sub_dest"]),
        "none": sum(1 for r in rows if not r["arm"]),
    }
    check(shape == SWEEP_SHAPE, "sweep shape unchanged", str(shape))

    blob = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode()).hexdigest()
    check(digest == SWEEP_DIGEST, "b1 sweep digest unchanged",
          digest[:16] + " vs " + SWEEP_DIGEST[:16])

    # Named cases, so a digest miss can be localised.
    index = {(r["layout"], r["obj"], tuple(r["idle"]), tuple(r["disabled"])): r
             for r in rows}
    for lname, obj, idle, dis, e_arm, e_target, e_sub in EXPECTED:
        got = index[(lname, obj, tuple(idle), tuple(dis))]
        ok = (got["arm"] == e_arm and got["target"] == e_target
              and got["sub_dest"] == e_sub)
        check(ok, f"case {lname}/{obj} idle={list(idle)} disabled={list(dis)}",
              f"arm={got['arm']} target={got['target']} "
              f"sub={got['sub_dest']}")

    # route_via_pad must respect its candidate list. This is the contract
    # the VLM head depends on: it passes exactly the arm the model named.
    single_ok = True
    single_seen = 0
    for lname in SWEEP_LAYOUTS:
        for obj, xy in L.LAYOUTS[lname].items():
            for a in C.ARMS:
                t = Task(obj="ycb_" + obj, dest=dest_of(obj))
                arm, target, sub = route_via_pad(t, tuple(xy), [a], zm, ())
                if arm is None:
                    continue
                single_seen += 1
                if arm != a or sub is None or target is None:
                    single_ok = False
    check(single_ok, "route_via_pad returns only the named candidate",
          f"{single_seen} single-candidate routes")
    check(single_seen > 0, "single-candidate routing exercised",
          f"{single_seen} routes found")

    # An empty candidate list can never produce an allocation.
    empty_ok = all(
        route_via_pad(Task(obj="ycb_" + obj, dest=dest_of(obj)),
                      tuple(xy), [], zm, ()) == (None, None, None)
        for obj, xy in L.LAYOUTS["relay_heavy"].items())
    check(empty_ok, "empty candidate list yields no allocation")

    # A capable arm that b1 would have chosen for the first leg is still
    # chosen when handed to route_via_pad on its own, so delegation and the
    # rule path agree wherever they overlap.
    agree = 0
    for r in rows:
        if not r["sub_dest"]:
            continue
        t = Task(obj="ycb_" + r["obj"], dest=dest_of(r["obj"]))
        arm, target, sub = route_via_pad(t, tuple(r["xy"]), [r["arm"]], zm,
                                         tuple(r["disabled"]))
        if arm == r["arm"] and rnd(target) == r["sub_dest"]:
            agree += 1
    check(agree == shape["pad_routed"],
          "delegated route matches b1's own route",
          f"{agree}/{shape['pad_routed']}")

    print("\nRESULT: " + ("ALL PASS" if not fails
                          else f"{len(fails)} FAILURE(S): {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
