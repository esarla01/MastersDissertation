"""Harness for STEP 2 ONLY: the TIMING table and leg_cost in cell_config.

Step 2 is a pure addition: no other module reads TIMING yet, so the only
things to verify are the table itself and the cost function's arithmetic.
(The b2 switches that consume it are step 3 and have their own harness,
h_timing.py, which will NOT run until step 3's optimal_allocator is in
place. Do not run h_timing.py yet.)

Checks:
  1. Both arm types present, all coefficients positive (a negative
     coefficient was the failure mode of the underfed calibration fit).
  2. leg_cost is exactly linear in path and legs, per type.
  3. The calibrated heterogeneity is intact, and is the RIGHT shape: the
     Franka is only ~1.4x slower per metre, while its per-task overhead is
     ~3.8x. An earlier misspecified fit claimed 3.67x per metre; both facts
     are pinned so that story cannot quietly return.
  4. Implied end-effector speeds are physical. This is the guard the first
     fit failed while scoring R2 0.99.
  5. Every arm in ARMS maps to a type the table covers.
  6. route_m spans base -> object -> destination -> HOME, the same journey
     the coefficients were fitted over, reading HOME_XY rather than
     assuming home is the arm base (it is about 0.30 m inward).

Run: python3 h_timing_table.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from core.cell import cell_config as C                        # REAL config

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


check("TIMING covers exactly the two arm types",
      set(C.TIMING) == {"franka", "ur10"}, str(set(C.TIMING)))
check("all coefficients positive",
      all(v["ticks_per_m"] > 0 and v["fixed_ticks"] > 0
          for v in C.TIMING.values()), str(C.TIMING))
check("every arm's type is priced",
      all(C.ARMS[a]["type"] in C.TIMING for a in C.ARMS),
      str({a: C.ARMS[a]["type"] for a in C.ARMS}))

for arm, typ in (("ur_w", "ur10"), ("franka_n", "franka")):
    t = C.TIMING[typ]
    want = t["ticks_per_m"] * 2.5 + t["fixed_ticks"] * 3
    check(f"leg_cost linear for {arm}",
          abs(C.leg_cost(arm, 2.5, 3) - want) < 1e-9,
          f"{C.leg_cost(arm, 2.5, 3)} vs {want}")
check("leg_cost defaults to one leg",
      C.leg_cost("ur_e", 1.0) == C.leg_cost("ur_e", 1.0, 1))

# The heterogeneity is REAL but it is not mostly speed. The 2026-07-29
# per-task refit puts the Franka at 1.38x the UR per metre, while its
# per-task overhead is 3.8x (314 vs 83 ticks). The earlier 3.67x per-metre
# figure came from a misspecified fit. Pin BOTH facts so a future edit
# cannot quietly restore the wrong story.
ratio_m = C.TIMING["franka"]["ticks_per_m"] / C.TIMING["ur10"]["ticks_per_m"]
ratio_f = C.TIMING["franka"]["fixed_ticks"] / C.TIMING["ur10"]["fixed_ticks"]
check("per-metre gap is modest (the Franka is not much slower at moving)",
      1.15 < ratio_m < 1.8, f"{ratio_m:.2f}x")
check("per-task overhead is the real gap (slow to pick up, not to carry)",
      ratio_f > 2.5 and ratio_f > ratio_m, f"{ratio_f:.2f}x")

# the fitted values themselves, pinned: a silent edit to the table would
# de-calibrate every estimate-mode episode without failing anything else
check("table carries the 2026-07-29 PER-TASK refit verbatim",
      C.TIMING == {"franka": {"ticks_per_m": 97.2, "fixed_ticks": 314.2},
                   "ur10": {"ticks_per_m": 70.4, "fixed_ticks": 82.9}},
      str(C.TIMING))
# The guard that the first fit failed: implied EE speed must be physical.
for _typ, _v in C.TIMING.items():
    _speed = 1.0 / (_v["ticks_per_m"] * C.SIM_DT)
    check(f"{_typ} implied EE speed is physical (0.15-4.0 m/s)",
          0.15 <= _speed <= 4.0, f"{_speed:.2f} m/s")

# route_m: the FULL journey the coefficients were fitted over
check("route_m sums base -> object -> destination -> home",
      abs(C.route_m("ur_w", (0.0, 0.0), (-0.7, 0.5))
          - (math.hypot(0.0 - C.ARMS["ur_w"]["pos"][0],
                        0.0 - C.ARMS["ur_w"]["pos"][1])
             + math.hypot(-0.7, 0.5)
             + math.hypot(C.HOME_XY["ur_w"][0] + 0.7,
                          C.HOME_XY["ur_w"][1] - 0.5))) < 1e-9)
check("home is NOT the base (about 0.30 m inward), so the return leg is "
      "read from HOME_XY rather than assumed",
      all(0.2 < math.hypot(C.HOME_XY[a][0] - C.ARMS[a]["pos"][0],
                           C.HOME_XY[a][1] - C.ARMS[a]["pos"][1]) < 0.4
          for a in C.ARMS))
check("the return leg makes a far-homing task cost strictly more",
      C.route_m("ur_w", (0.0, 0.0), (-0.7, 0.5))
      > math.hypot(0.0 - C.ARMS["ur_w"]["pos"][0], 0.0)
      + math.hypot(-0.7, 0.5))

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
