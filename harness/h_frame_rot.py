"""Harness: north-up frame rotation (imports the REAL grab_frame_b64).

Feeds the REAL state_builder.grab_frame_b64 a synthetic raw frame via a
fake scene/camera chain, decodes the PNG it returns, and checks the
rotation is exactly 90 degrees clockwise.

The raw camera frame is east-up, north-left (verified against the
scene_cfg table_cam quaternion, 90 deg about world Y). In raw-frame pixel
terms that means: row 0 = EAST edge, column 0 = NORTH edge. After a 90 deg
clockwise rotation the encoded image must have row 0 = NORTH edge and
last column = EAST edge, i.e. north-up, east-right.

Synthetic frame (4x4, distinct corner colours):
  raw[0, 0]   = RED    (east-north corner of the world, i.e. NE)
  raw[0, 3]   = GREEN  (east-south corner, SE)
  raw[3, 0]   = BLUE   (west-north corner, NW)
  raw[3, 3]   = YELLOW (west-south corner, SW)
After CW rotation (north-up, east-right):
  out[0, 3] (top-right)    = NE = RED
  out[3, 3] (bottom-right) = SE = GREEN
  out[0, 0] (top-left)     = NW = BLUE
  out[3, 0] (bottom-left)  = SW = YELLOW

Run: python3 h_frame_rot.py
"""
import base64
import io
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from core.decision import state_builder as sb   # REAL module

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


RED, GREEN, BLUE, YELLOW = ((255, 0, 0), (0, 255, 0),
                            (0, 0, 255), (255, 255, 0))
raw = np.zeros((4, 4, 3), dtype=np.uint8)
raw[0, 0], raw[0, 3] = RED, GREEN
raw[3, 0], raw[3, 3] = BLUE, YELLOW


class _Chain:
    """Mimics tensor.detach().cpu().numpy() on the raw array."""
    def __init__(self, arr):
        self._a = arr

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._a


class FakeCam:
    def __init__(self, arr):
        self.data = type("D", (), {})()
        self.data.output = {"rgb": [_Chain(arr)]}


class FakeScene(dict):
    pass


scene = FakeScene()
scene["table_cam"] = FakeCam(raw)

b64 = sb.grab_frame_b64(scene)
from PIL import Image
out = np.asarray(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB"))

check("output is 4x4 RGB", out.shape == (4, 4, 3), str(out.shape))
check("NE corner (red) at top-right", tuple(out[0, 3]) == RED, str(out[0, 3]))
check("SE corner (green) at bottom-right", tuple(out[3, 3]) == GREEN)
check("NW corner (blue) at top-left", tuple(out[0, 0]) == BLUE)
check("SW corner (yellow) at bottom-left", tuple(out[3, 0]) == YELLOW)
check("rotation is exactly rot90 CW",
      np.array_equal(out, np.rot90(raw, k=-1)))

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
