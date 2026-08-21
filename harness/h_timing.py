"""Harness: the timing model and the b2 objective/contention switches
(imports the REAL optimal_allocator, rule allocator, zonemap and config).

Four things must hold:

  1. REGRESSION. timing="distance" with objective="minisum" and no
     contention weight must reproduce the historical cost matrix EXACTLY:
     approach + carry metres for direct, + LAMBDA_HANDOVER for a relay.
     Every b2 episode recorded before 2026-07-29 was priced this way, and
     the default must not move by a single digit.
  2. HETEROGENEITY AND THE RETURN LEG. timing="estimate" must price the
     same task differently for a UR and a Franka, in ticks, over the FULL
     journey base -> object -> destination -> home (route_m). The
     coefficients were fitted over a window ending on arrival home, so
     pricing only the one-way path would apply them to a shorter journey
     than they were measured on and under-cost far-homing tasks. Both the
     per-arm difference and the presence of the return leg are pinned.
  3. OBJECTIVE. best_matching_minimax must pick the bottleneck-optimal
     matching on an instance where MiniSum provably picks a different one,
     must maximise cardinality first, and must tie-break deterministically.
  4. SWITCHES. The contention weight is off by default, applies only to
     contended pairs when set, and the instance records objective and
     timing in stats so no episode can be mislabelled.

Run: python3 h_timing.py
"""
import math
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from core.cell import cell_config as C                        # REAL config
from core.cell.zones import ZoneMap                           # REAL rasters
from core.decision import optimal_allocator as oa             # REAL module

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm",
                                "ycb"))
from ycb_objects import register_specs                        # REAL registry

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


# ---------------------------------------------------------------------------
# 0. the TIMING table itself
# ---------------------------------------------------------------------------
check("TIMING has both arm types with positive coefficients",
      set(C.TIMING) == {"franka", "ur10"}
      and all(v["ticks_per_m"] > 0 and v["fixed_ticks"] > 0
              for v in C.TIMING.values()),
      str(C.TIMING))
check("leg_cost is linear in path and legs",
      abs(C.leg_cost("ur_w", 3.0, 2)
          - (C.TIMING["ur10"]["ticks_per_m"] * 3.0
             + C.TIMING["ur10"]["fixed_ticks"] * 2)) < 1e-9)
# Heterogeneity is real, but after the 2026-07-29 per-task refit it lives
# mainly in the per-task overhead, not in travel speed. h_timing_table.py
# pins both ratios; here we only need a franka task to cost more overall.
check("a franka task costs materially more than a ur10 task",
      C.leg_cost("franka_n", 2.5, 1) > 1.5 * C.leg_cost("ur_w", 2.5, 1),
      f"{C.leg_cost('franka_n', 2.5, 1) / C.leg_cost('ur_w', 2.5, 1):.2f}x")

# ---------------------------------------------------------------------------
# 1. minimax matcher, pure-function tests
# ---------------------------------------------------------------------------
T = lambda i: NS(id=i)
tasks = [T(1), T(2)]
arms = ["A", "B"]
feas = {(a, t.id): True for a in arms for t in tasks}
# MiniSum picks {A:1, B:2} (total 11); MiniMax must pick {A:2, B:1}
# (bottleneck 6 beats 10, despite total 12).
cost = {("A", 1): 1.0, ("A", 2): 6.0, ("B", 1): 6.0, ("B", 2): 10.0}
mm = oa.best_matching_minimax(arms, tasks, feas, cost)
ms = oa.best_matching(arms, tasks, feas, cost)
check("minimax picks the bottleneck-optimal matching",
      mm == {2: "A", 1: "B"}, str(mm))
check("on the same instance minisum provably differs",
      ms == {1: "A", 2: "B"} and ms != mm, str(ms))
# cardinality first: an infeasible cell must not shrink the matching
feas2 = dict(feas); feas2[("A", 1)] = False
mm2 = oa.best_matching_minimax(arms, tasks, feas2, cost)
check("minimax maximises cardinality before bottleneck",
      len(mm2) == 2 and mm2[1] == "B", str(mm2))
# deterministic tie-break on total when bottlenecks tie
cost3 = {("A", 1): 5.0, ("A", 2): 5.0, ("B", 1): 5.0, ("B", 2): 1.0}
mm3 = oa.best_matching_minimax(arms, tasks, feas, cost3)
check("bottleneck ties break on total cost, deterministically",
      mm3 == {1: "A", 2: "B"}, str(mm3))
# empty legal set
check("no feasible pair yields an empty matching, not a crash",
      oa.best_matching_minimax(arms, tasks,
                               {k: False for k in feas}, cost) == {})

# ---------------------------------------------------------------------------
# the fake cell for _replan: real specs, real rasters, real rule allocator
# ---------------------------------------------------------------------------
for name in ("soup_can", "power_drill"):
    register_specs(C.OBJECT_SPECS, "ycb_" + name, name)

POS = {"ycb_soup_can": (-0.10, 0.30)}
DEST = (-0.70, 0.50)


class FakeScene:
    def __getitem__(self, name):
        x, y = POS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_coord(contended=frozenset()):
    agents = {n: NS(state="IDLE", arm=NS(disabled=False)) for n in C.ARMS}
    pool = [NS(id=0, obj="ycb_soup_can", dest=DEST, dest_by="oracle",
               done=False, failed=False, claimed=False, waiting_on=None)]
    return NS(cell=NS(scene=FakeScene()), agents=agents, pool=pool,
              locks=NS(is_contended=lambda z, a: z in contended),
              _assign_round=0)


zm = ZoneMap(os.path.join(os.path.dirname(__file__), "..", "fourarm",
                          "core", "cell", "reachability", "rasters"))


def matrix(alloc, coord):
    alloc._replan(coord, zm)
    return alloc.log[-1]["matrix"]


# ---------------------------------------------------------------------------
# 2. REGRESSION: distance mode reproduces the historical pricing exactly
# ---------------------------------------------------------------------------
coord = make_coord()
dflt = oa.OptimalAllocator(lambda: coord, verify=False)
m_dist = matrix(dflt, coord)
ox, oy = POS["ycb_soup_can"]
expect, paths = {}, {}
for a in C.ARMS:
    from core.control.tasks import rule_based_allocate
    arm_r, target, sub = rule_based_allocate(coord.pool[0], (ox, oy), [a], zm)
    if arm_r != a or target is None:
        continue
    d = math.hypot(ox - C.ARMS[a]["pos"][0], oy - C.ARMS[a]["pos"][1])
    if sub is None:
        c = d + math.hypot(DEST[0] - ox, DEST[1] - oy)
    else:
        c = (d + math.hypot(target[0] - ox, target[1] - oy)
             + math.hypot(DEST[0] - target[0], DEST[1] - target[1])
             + oa.LAMBDA_HANDOVER)
    expect[f"{a}|0"] = round(c + oa.TIE_EPS * 0, 3)
    paths[f"{a}|0"] = c                    # UNROUNDED metres: the estimate
                                           # check multiplies by ~70 ticks/m,
                                           # which amplifies display rounding
                                           # past any sane tolerance
check("defaults are unchanged: distance mode matches the historical "
      "formula cell for cell", m_dist == expect,
      f"got {m_dist} want {expect}")
check("defaults recorded honestly in stats",
      dflt.stats["objective"] == "minisum"
      and dflt.stats["timing"] == "distance"
      and dflt.stats["lambda_contention"] == 0.0)

# ---------------------------------------------------------------------------
# 3. HETEROGENEITY: estimate mode prices in ticks, per arm type
# ---------------------------------------------------------------------------
coord2 = make_coord()
est = oa.OptimalAllocator(lambda: coord2, verify=False, timing="estimate")
m_est = matrix(est, coord2)
mismatch = []
for key, got in m_est.items():
    a = key.split("|")[0]
    # Direct route for every arm here (soup_can is shared and central). The
    # tick price is the FULL round trip that the coefficients were fitted
    # over: base -> object -> destination -> home, via route_m.
    want = round(C.leg_cost(a, C.route_m(a, (ox, oy), DEST), 1), 3)
    if abs(got - want) > 0.01:
        mismatch.append((key, got, want))
check("estimate mode prices every pair at leg_cost(arm, route_m(...), 1)",
      not mismatch and set(m_est) == set(expect), str(mismatch[:3]))
# The Step D defect, pinned: pricing only the one-way path would make a
# far-homing task look as cheap as a nearby one. Every pair must cost
# strictly more than its one-way price.
oneway = {k: round(C.leg_cost(k.split("|")[0], paths[k], 1), 3)
          for k in m_est}
check("the RETURN LEG is priced (every pair beats its one-way price)",
      all(m_est[k] > oneway[k] + 1.0 for k in m_est),
      str({k: (oneway[k], m_est[k]) for k in list(m_est)[:2]}))
ur_key = next(k for k in m_est if k.startswith("ur_"))
fr_key = next((k for k in m_est if k.startswith("franka_")), None)
if fr_key:
    ur_m = expect[ur_key]
    fr_m = expect[fr_key]
    check("the same task is priced DIFFERENTLY per arm type in ticks "
          "(heterogeneity the distance matrix cannot express)",
          abs((m_est[fr_key] / m_est[ur_key])
              - (fr_m / ur_m)) > 0.10,
          f"tick ratio {m_est[fr_key] / m_est[ur_key]:.2f} vs metre ratio "
          f"{fr_m / ur_m:.2f}")

# ---------------------------------------------------------------------------
# 4. contention switch
# ---------------------------------------------------------------------------
from core.cell.locks import zone_of
obj_zone = zone_of(ox, oy)
coord3 = make_coord(contended=frozenset({obj_zone}))
blind = oa.OptimalAllocator(lambda: coord3, verify=False)
m_blind = matrix(blind, coord3)
check("contention weight 0.0 by default: contended zones change nothing",
      m_blind == expect, str(m_blind))
coord4 = make_coord(contended=frozenset({obj_zone}))
aware = oa.OptimalAllocator(lambda: coord4, verify=False,
                            lambda_contention=0.5)
m_aware = matrix(aware, coord4)
check("lambda_contention surcharges every pair touching a contended zone",
      all(abs(m_aware[k] - (expect[k] + 0.5)) < 0.01 for k in expect),
      str(m_aware))

# ---------------------------------------------------------------------------
# 5. objective switch is validated and wired through _replan
# ---------------------------------------------------------------------------
coord5 = make_coord()
mmx = oa.OptimalAllocator(lambda: coord5, verify=False, objective="minimax")
mmx._replan(coord5, zm)
check("minimax mode runs through _replan and records itself",
      mmx.stats["objective"] == "minimax" and len(mmx._plan) == 1,
      str(mmx._plan))
try:
    oa.OptimalAllocator(lambda: None, objective="fastest")
    check("unknown objective rejected", False)
except ValueError:
    check("unknown objective rejected", True)
try:
    oa.OptimalAllocator(lambda: None, timing="wallclock")
    check("unknown timing mode rejected", False)
except ValueError:
    check("unknown timing mode rejected", True)

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
