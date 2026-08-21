"""Zone queries over the per-arm reachability rasters. Pure numpy, no Isaac
imports, so it runs and unit-tests anywhere.

Rasters come from reachability/gen_reachability.py as one .npz per arm with
keys mask (H, W bool), xs (W,), ys (H,).
"""

import os

import math
import numpy as np

from core.cell import cell_config as C


class ZoneMap:
    def __init__(self, raster_dir=None):
        raster_dir = raster_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), C.RASTER_DIR
        )
        self.masks = {}
        self.xs = self.ys = None
        for name in C.ARMS:
            data = np.load(os.path.join(raster_dir, f"{name}.npz"))
            self.masks[name] = data["mask"]
            if self.xs is None:
                self.xs, self.ys = data["xs"], data["ys"]

    def _index(self, x, y):
        """Nearest grid cell. searchsorted was wrong here: float error in the
        arange grid made queries on the positive side snap one cell outward
        (e.g. 1.30 landing on the 1.40 edge cell), while the negative side
        snapped inward, so lookups were silently asymmetric east/west."""
        ix = int(np.argmin(np.abs(self.xs - x)))
        iy = int(np.argmin(np.abs(self.ys - y)))
        return iy, ix

    # Measured feasibility deny-list. EMPTY as of 2026-07-19: the single
    # entry (franka_s -> tools basket) was based on a contaminated probe
    # measurement. Arm.tuck() was a no-op for Frankas, so that trial began
    # from a stalled posture; the diagnostic (out/probe_diag.json) shows
    # the same target ARRIVES in 106 ticks from a genuine tuck. The
    # mechanism stays so future MEASURED corrections have a home.
    PROBE_DENY = {}

    def reachable(self, arm, x, y):
        for dx, dy, r in self.PROBE_DENY.get(arm, ()):
            if math.hypot(x - dx, y - dy) <= r:
                return False
        iy, ix = self._index(x, y)
        return bool(self.masks[arm][iy, ix])

    def reachable_arms(self, x, y):
        return [a for a in self.masks if self.reachable(a, x, y)]

    def zone_kind(self, x, y):
        n = len(self.reachable_arms(x, y))
        return {0: "unreachable", 1: "exclusive", 2: "overlap"}.get(n, "contested")

    def validate_pads(self):
        """Every exchange pad must lie inside all of its arms' rasters."""
        return {
            pad: all(self.reachable(a, *spec["pos"]) for a in spec["arms"])
            for pad, spec in C.EXCHANGE_PADS.items()
        }

    def reachability_overlay(self):
        """(H, W) uint8 count of arms reaching each cell (thesis figure)."""
        total = np.zeros_like(next(iter(self.masks.values())), dtype=np.uint8)
        for m in self.masks.values():
            total += m.astype(np.uint8)
        return total


# pixel_to_world (pixel deprojection) removed 2026-07-25: it served the
# retired condition-B pipeline, nothing called it, and it required a depth
# channel the camera does not render. No coordinate extraction from images
# exists anywhere by design (the model returns choices, never coordinates).
