"""Pre-screen EX2 block positions against the SAME masks the validator uses,
exactly as ycb/ex2_block.txt's header promises. Pure numpy (ZoneMap has no
Isaac imports), so it runs under isaac's python without launching the app.

Rules, taken verbatim from the ex2_block.txt header:
  1. the object cell is reachable by franka_n AND by the nearer UR
     (ur_w for a west position, ur_e for an east one);
  2. object and clamp are clear of every arm base by >= 0.25 m;
  3. object and clamp are clear of every basket wall (footprint-aware);
  4. the clamp cell is ur_w-reachable (idle ur_w must deliver the tool);
  5. the object sits OUT of the central-x band the oblique ex2_cam / franka_s
     occlude: west x <= -0.25, east x >= +0.15.

Run:  /isaac-sim/python.sh ycb/screen_ex2_block.py            (audits ex2_block.txt)
      /isaac-sim/python.sh ycb/screen_ex2_block.py --scan     (proposes new cells)
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cell import cell_config as C
from core.cell.zones import ZoneMap

ARM_BASE_CLEAR = 0.25          # rule 2
BASKET_HALF = C.BASKET_WALL_HALF   # 0.22, the walled square half-extent
# largest horizontal half-extent the block ever presents (lying, 0.130 face)
BLOCK_HALF = max(C.OBJECT_SPECS.get("block_large", {"footprint_m": 0.130})
                 .get("footprint_m", 0.130),
                 0.130) / 2.0
CLAMP_HALF = 0.165 / 2.0       # large_clamp footprint_m / 2
WEST_MAX_X = -0.25             # rule 5, west band edge
EAST_MIN_X = +0.15             # rule 5, east band edge

ZM = ZoneMap()
BASES = {n: (s["pos"][0], s["pos"][1]) for n, s in C.ARMS.items()}
BASKETS = {"food": (-0.70, 0.50), "kitchenware": (0.70, 0.50),
           "tools": (-0.70, -0.50)}


def clears_bases(x, y):
    return all(math.hypot(x - bx, y - by) >= ARM_BASE_CLEAR
               for bx, by in BASES.values())


def clears_baskets(x, y, half):
    """Object of half-extent `half` centred at (x,y) does not overlap any
    walled basket square (Chebyshev gap to the square >= half)."""
    for bx, by in BASKETS.values():
        gap = max(abs(x - bx) - BASKET_HALF, abs(y - by) - BASKET_HALF)
        if gap < half:
            return False
    return True


def on_table(x, y, half):
    return (abs(x) + half <= C.TABLE_HALF_X and abs(y) + half <= C.TABLE_HALF_Y)


def screen(side, ox, oy, cx, cy, verbose=False):
    """Return (ok, reasons[]) for one candidate. side in {'w','e'}."""
    near_ur = "ur_w" if side == "w" else "ur_e"
    r = []
    if side == "w" and ox > WEST_MAX_X:
        r.append(f"object x {ox:+.3f} in central band (need <= {WEST_MAX_X})")
    if side == "e" and ox < EAST_MIN_X:
        r.append(f"object x {ox:+.3f} in central band (need >= {EAST_MIN_X})")
    if not ZM.reachable("franka_n", ox, oy):
        r.append("object not franka_n-reachable")
    if not ZM.reachable(near_ur, ox, oy):
        r.append(f"object not {near_ur}-reachable")
    if not ZM.reachable("ur_w", cx, cy):
        r.append("clamp not ur_w-reachable")
    if not clears_bases(ox, oy):
        r.append("object within 0.25 m of an arm base")
    if not clears_bases(cx, cy):
        r.append("clamp within 0.25 m of an arm base")
    if not clears_baskets(ox, oy, BLOCK_HALF):
        r.append("object overlaps a basket wall")
    if not clears_baskets(cx, cy, CLAMP_HALF):
        r.append("clamp overlaps a basket wall")
    if not on_table(ox, oy, BLOCK_HALF):
        r.append("object off table")
    if not on_table(cx, cy, CLAMP_HALF):
        r.append("clamp off table")
    # object and clamp must not collide with each other
    if math.hypot(ox - cx, oy - cy) < (BLOCK_HALF + CLAMP_HALF + 0.03):
        r.append("object and clamp footprints overlap")
    return (not r), r


def audit(spec_path):
    ok = bad = 0
    for raw in open(spec_path):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        kind, pid = parts[0], parts[1]
        ox, oy = map(float, parts[2].split(","))
        cx, cy = map(float, parts[3].split(","))
        side = pid[0]
        good, reasons = screen(side, ox, oy, cx, cy)
        if good:
            ok += 1
        else:
            bad += 1
            print(f"  FAIL {pid}: " + "; ".join(reasons))
    print(f"[audit] {spec_path}: {ok} pass, {bad} fail")
    return bad == 0


def scan():
    """Enumerate a grid of legal (object, clamp) candidates per side.

    The clamp is placed at a proven, reused clamp cell rather than searched:
    west positions reuse (+0.125,-0.210) (ur_w-reachable, central-south, used
    by most west lines); east positions reuse (-0.700,+0.150). Only the object
    cell is scanned, which is what a new position actually varies."""
    clamp = {"w": (0.125, -0.210), "e": (-0.700, 0.150)}
    step = 0.025
    for side in ("w", "e"):
        cx, cy = clamp[side]
        found = []
        xs = ([round(-0.75 + i * step, 3) for i in range(int(0.55 / step) + 1)]
              if side == "w" else
              [round(0.15 + i * step, 3) for i in range(int(0.60 / step) + 1)])
        ys = [round(-0.20 + i * step, 3) for i in range(int(0.80 / step) + 1)]
        for ox in xs:
            for oy in ys:
                good, _ = screen(side, ox, oy, cx, cy)
                if good:
                    found.append((ox, oy))
        print(f"[scan {side}] clamp ({cx:+.3f},{cy:+.3f}): "
              f"{len(found)} legal object cells")
        # print a spread-out sample for the human to choose from
        for ox, oy in found[:: max(1, len(found) // 20)]:
            print(f"    {side}? object ({ox:+.3f},{oy:+.3f})  "
                  f"clamp ({cx:+.3f},{cy:+.3f})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--spec", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ex2_block.txt"))
    ap.add_argument("--check", nargs=5, metavar=("SIDE", "OX", "OY", "CX", "CY"),
                    help="screen one candidate: side ox oy cx cy")
    a = ap.parse_args()
    if a.check:
        side, ox, oy, cx, cy = (a.check[0], *map(float, a.check[1:]))
        good, reasons = screen(side, ox, oy, cx, cy)
        print("PASS" if good else "FAIL: " + "; ".join(reasons))
    elif a.scan:
        scan()
    else:
        audit(a.spec)
