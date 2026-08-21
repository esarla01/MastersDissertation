"""Is each arm's measured reachable set a clean annulus?

The prompt tells the model one number per arm (reach_m) and the model can
only judge reachability as distance(base, point) <= reach_m. The cell does
not work that way: gen_reachability.py marks a cell reachable only when
0.15 < d < reach*0.98 AND the IK solver converged there. So the stated
radius overstates the truth, and IK failures may punch holes that no radius
can express.

This script answers one question per arm, offline, from the raster files:

  r_safe = the largest radius r for which EVERY grid cell with
           0.15 < d < r is actually reachable.

If r_safe is close to reach*0.98 the set is a clean annulus and a
conservative radius in the prompt is sound. If r_safe collapses well below
it, the set is holey, no radius can represent it, and a conservative radius
would give false confidence.

Reports the inner dead-zone edge and the radial distribution of holes too,
so the shape of the envelope can be described rather than assumed.

Run: python3 analysis/cell_reach_envelope.py
     python3 analysis/cell_reach_envelope.py --inner 0.15
"""
import argparse
import ast
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cell import cell_config as C          # noqa: E402  REAL config
from core.cell.zones import ZoneMap             # noqa: E402  REAL loader


def envelope(zm, name, inner):
    """Per-arm radial audit of the REAL raster. Returns a dict."""
    pos = C.ARMS[name]["pos"]          # (x, y, z) of the arm base
    bx, by = float(pos[0]), float(pos[1])
    reach = C.ARM_TYPES[C.ARMS[name]["type"]]["reach"]
    mask = zm.masks[name]

    cells = []                                   # (d, reachable) per grid cell
    for iy, y in enumerate(zm.ys):
        for ix, x in enumerate(zm.xs):
            d = math.hypot(float(x) - bx, float(y) - by)
            cells.append((d, bool(mask[iy, ix])))
    cells.sort()

    # r_safe: walk outward from the inner bound, stop at the first gap
    r_safe = inner
    for d, ok in cells:
        if d <= inner:
            continue
        if not ok:
            break
        r_safe = d

    reachable_d = [d for d, ok in cells if ok]
    band = [(d, ok) for d, ok in cells if inner < d < reach * 0.98]
    holes = [d for d, ok in band if not ok]

    return {"arm": name, "type": C.ARMS[name]["type"], "base": (bx, by),
            "reach_nominal": reach, "reach_098": reach * 0.98,
            "r_safe": r_safe,
            "d_min_reachable": min(reachable_d) if reachable_d else None,
            "d_max_reachable": max(reachable_d) if reachable_d else None,
            "n_reachable": len(reachable_d), "n_cells": len(cells),
            "band_cells": len(band), "holes": holes}


def layout_check(zm, points=None):
    """Does the gap between the two tests touch any point that MATTERS?

    A hole only harms the experiment if an object, basket or exchange pad
    sits in one. This compares the circle test the prompt supports against
    the raster the cell honours, at every such point. Run it again for any
    new layout: a hole that is harmless in the designed layout may not be
    in a random one, and a disruption can displace an object into one.
    """
    if points is None:
        points = {}
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Read the REAL literals out of the REAL source files. Importing
        # them would drag in isaaclab, so this script would only run under
        # the Isaac interpreter. The values are the ones the sim uses.
        for rel, var in ((os.path.join("ycb", "run_ycb_sort.py"), "DESIGNED"),
                         (os.path.join("ycb", "ycb_scene.py"), "BASKETS")):
            path = os.path.join(root, rel)
            try:
                tree = ast.parse(open(path).read())
                val = next(ast.literal_eval(node.value)
                           for node in tree.body
                           if isinstance(node, ast.Assign)
                           and any(getattr(t, "id", None) == var
                                   for t in node.targets))
            except Exception as exc:
                print(f"\n[layout] could not read {var} from {rel}: {exc}")
                continue
            for k, v in val.items():
                xy = v["pos"] if isinstance(v, dict) else v
                points[k] = (float(xy[0]), float(xy[1]))
    for k, v in C.EXCHANGE_PADS.items():
        points[k] = (v["pos"][0], v["pos"][1])

    print("\nLAYOUT CHECK (circle test the prompt supports vs the cell)")
    bad = []
    for name, (x, y) in sorted(points.items()):
        for arm in C.ARMS:
            pos = C.ARMS[arm]["pos"]
            reach = C.ARM_TYPES[C.ARMS[arm]["type"]]["reach"]
            d = math.hypot(x - pos[0], y - pos[1])
            if (d <= reach) != zm.reachable(arm, x, y):
                bad.append((name, arm, d, d <= reach))
    total = len(points) * len(C.ARMS)
    if not bad:
        print(f"  {total} point-arm pairs over {len(points)} points: "
              f"NO disagreement. The radius the model is given and the "
              f"envelope the cell enforces agree everywhere that matters "
              f"in this layout.")
    else:
        print(f"  {len(bad)} of {total} point-arm pairs DISAGREE:")
        for name, arm, d, circ in bad:
            says = "circle says yes, cell says no" if circ else \
                   "circle says no, cell says yes"
            print(f"    {name:22s} {arm:10s} d={d:.3f}  {says}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inner", type=float, default=0.15,
                    help="inner dead-zone bound used by gen_reachability")
    ap.add_argument("--rasters", default=None)
    a = ap.parse_args()

    rdir = a.rasters or os.path.join(os.path.dirname(__file__), "..",
                                     "core", "cell", "reachability",
                                     "rasters")
    zm = ZoneMap(rdir)
    res = float(zm.xs[1] - zm.xs[0]) if len(zm.xs) > 1 else float("nan")
    print(f"\nraster grid {len(zm.xs)} x {len(zm.ys)} at {res:.3f} m/cell "
          f"(cell_config RASTER_RESOLUTION = {C.RASTER_RESOLUTION})")
    if abs(res - C.RASTER_RESOLUTION) > 1e-9:
        print("  NOTE these rasters were NOT built at the configured "
              "resolution; r_safe is quantised to the grid above.")

    rows = [envelope(zm, n, a.inner) for n in C.ARMS]

    print(f"\n{'arm':10s} {'type':8s} {'nominal':>8s} {'0.98x':>8s} "
          f"{'r_safe':>8s} {'shortfall':>10s} {'holes':>6s} {'of band':>8s}")
    for r in rows:
        short = r["reach_098"] - r["r_safe"]
        print(f"{r['arm']:10s} {r['type']:8s} {r['reach_nominal']:>8.3f} "
              f"{r['reach_098']:>8.3f} {r['r_safe']:>8.3f} "
              f"{short:>10.3f} {len(r['holes']):>6d} {r['band_cells']:>8d}")

    print("\nINNER EDGE (the dead zone the prompt never mentions)")
    for r in rows:
        print(f"  {r['arm']:10s} closest reachable cell "
              f"{r['d_min_reachable']:.3f} m from base, "
              f"furthest {r['d_max_reachable']:.3f} m")

    print("\nHOLES (reachable by the radius rule, refused by the cell)")
    for r in rows:
        if not r["holes"]:
            print(f"  {r['arm']:10s} none: the set is a clean annulus")
            continue
        h = sorted(r["holes"])
        print(f"  {r['arm']:10s} {len(h)} of {r['band_cells']} band cells "
              f"({100.0 * len(h) / max(r['band_cells'], 1):.1f}%), "
              f"radii {h[0]:.3f} to {h[-1]:.3f} m")
        edges = np.linspace(a.inner, r["reach_098"], 6)
        counts, _ = np.histogram(h, bins=edges)
        spans = " ".join(f"[{edges[i]:.2f},{edges[i+1]:.2f}):{counts[i]}"
                         for i in range(len(counts)))
        print(f"             {spans}")

    layout_check(zm)

    print("\nVERDICT")
    for r in rows:
        short = r["reach_098"] - r["r_safe"]
        if not r["holes"]:
            print(f"  {r['arm']:10s} SOUND. A conservative radius of "
                  f"{r['r_safe']:.3f} m (with an inner bound of "
                  f"{a.inner:.2f} m) never overstates the cell.")
        elif short <= 2 * res:
            print(f"  {r['arm']:10s} SOUND WITHIN A CELL. Holes sit at the "
                  f"outer edge only; {r['r_safe']:.3f} m is safe.")
        else:
            print(f"  {r['arm']:10s} HOLEY. A sound radius would be "
                  f"{r['r_safe']:.3f} m, {short:.3f} m inside the boundary, "
                  f"discarding usable workspace. A radius cannot represent "
                  f"this envelope.")
    print()


if __name__ == "__main__":
    main()
