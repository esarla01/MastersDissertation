"""h_ex2_visibility: the occlusion check measures the block and not the
table, never reads a model reply, and places its cut in open space.

Imports the REAL visibility module and drives it with SYNTHETIC renders
built here, so the pins do not depend on a capture directory that may be
re-rendered.

What is pinned, and the failure each one guards:

  1. It finds the block by the LARGEST CONNECTED region of block colour.
     A bare colour count also collects shadowed table pixels, and at the
     occluded position that noise put it at a third of the median instead
     of a thirtieth -- the difference between a cliff and a judgement.
  2. Each pose is compared against the median of ITS OWN pose. The flat
     pose shows about half the area of the standing one, so one shared
     median would flag every flat capture and hide a real occlusion.
  3. A partly hidden block is caught; a fully visible one is not.
  4. The module never opens a run file. Excluding a position because it
     scored badly is choosing the sample from the answers.
  5. The recorded colour is VALIDATED before anything is measured. Two
     auto-detectors were tried and both silently returned the table, at
     which point every position measures as fully visible and the check
     reports a clean sheet -- the most dangerous failure a precondition
     can have. A stated constant that is checked beats a guess that is
     not, so the guard is the pin.
  6. An incomplete position is reported as incomplete, not as occluded.
     They are different problems with different fixes.
  7. The report states both margins around the cut, so a reader can see
     whether it decided a close call.
  8. The command line builds.

Run:  python3 h_ex2_visibility.py
"""

import argparse as _argparse
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from experiments.ex2 import visibility as V                      # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label
          + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


try:
    from PIL import Image, ImageDraw
except ImportError:
    raise SystemExit("this harness needs Pillow, as the module it tests does")

TMP = tempfile.mkdtemp()
TABLE = (245, 235, 210)      # cream, far from the block colour
BLOCK = (204, 181, 140)      # the sampled tan
ARM = (250, 250, 250)        # near-white, occludes


def render(path, w, h, occlude=0.0, speckle=0):
    """One synthetic capture: a block on a table, optionally part-hidden.

    speckle scatters isolated block-coloured pixels across the table. They
    are what a plain colour count would add to the block's area, and what
    largest-connected must ignore.
    """
    im = Image.new("RGB", (400, 400), TABLE)
    d = ImageDraw.Draw(im)
    x0, y0 = 180, 200
    d.rectangle([x0, y0, x0 + w, y0 + h], fill=BLOCK)
    if occlude:
        d.rectangle([x0, y0, x0 + int(w * occlude), y0 + h], fill=ARM)
    for i in range(speckle):
        d.point((20 + (i * 7) % 140, 30 + (i * 13) % 140), fill=BLOCK)
    im.save(path)


# Three poses per position, the standing one twice the area of the flat one,
# which is the real geometry: 130mm up versus 50mm up over a wider base.
POSES = {"U": (40, 50), "S": (52, 36), "L": (55, 18)}


def build(pos, occlude=0.0, speckle=0, poses=POSES):
    for suf, (w, h) in poses.items():
        render(os.path.join(TMP, "%s_%s.png" % (pos, suf)), w, h,
               occlude=occlude, speckle=speckle)


for i in range(8):
    build("e%02d" % i)
build("e08", occlude=0.90)                 # the occluded one
build("e09", speckle=400)                  # clean block, noisy table
REF = os.path.join(TMP, "e00_U.png")

# 5: the guard, which is what both auto-detectors lacked.
_c = V.sample_block_colour(REF, box=(210, 240, 190, 215))
check("sample_block_colour reads the patch it is given",
      tuple(map(int, _c)) == BLOCK, str(_c))
check("and it requires a box: no magic rectangle to go stale",
      "box" in V.sample_block_colour.__code__.co_varnames[
          :V.sample_block_colour.__code__.co_argcount]
      and V.sample_block_colour.__defaults__ in (None, ()),
      str(V.sample_block_colour.__defaults__))
for bad, why in ((TABLE, "the table"), ((0, 255, 0), "nothing at all")):
    try:
        V.validate_colour([REF], block_rgb=bad)
        _ok = False
    except SystemExit:
        _ok = True
    check("a colour matching %s is refused, not silently used" % why, _ok,
          "every position would measure as fully visible and the check "
          "would report a clean sheet")
check("the recorded colour passes its own guard",
      V.validate_colour([REF], block_rgb=BLOCK) is True)

counts = V.measure(TMP, prefix="e", reference="e00", block_rgb=BLOCK)
usable, occluded, detail = V.verdict(counts)

# 1, 3: the occluded position is caught.
check("a 90 percent hidden block is flagged", occluded == ["e08"],
      "occluded=%s" % occluded)
check("every fully visible position is retained",
      len(usable) == 9 and "e08" not in usable, str(usable))
check("the pose that is hidden is named",
      detail["e08"]["worst"] < 0.2, str(detail["e08"]["worst"]))

# 1: speckle must not rescue a block, nor inflate a clean one.
check("scattered same-coloured pixels do not count as block",
      abs(detail["e09"]["worst"] - detail["e00"]["worst"]) < 0.02,
      "a plain colour count would score e09 higher than e00 on 400 stray "
      "pixels: %.3f vs %.3f" % (detail["e09"]["worst"],
                                detail["e00"]["worst"]))
build("e10", occlude=0.90, speckle=2000)
counts2 = V.measure(TMP, prefix="e", reference="e00", block_rgb=BLOCK)
_, occ2, det2 = V.verdict(counts2)
check("an occluded block is not rescued by table noise", "e10" in occ2,
      "%.3f; largest-connected is what makes this a measurement of the "
      "block" % det2["e10"]["worst"])

# 2: per-pose medians, not one shared median.
check("the flat pose is not flagged for being smaller than the standing "
      "one",
      all(detail[p]["ratios"]["L"] > 0.9 for p in usable),
      "L is a third the area of U by construction; a shared median would "
      "call every one of them occluded")

# 6: incomplete is its own verdict.
render(os.path.join(TMP, "e11_U.png"), 40, 50)
_, occ3, det3 = V.verdict(V.measure(TMP, prefix="e", reference="e00",
                                    block_rgb=BLOCK))
check("a position missing poses is INCOMPLETE, not occluded",
      "e11" not in occ3 and det3["e11"]["worst"] is None,
      "different problems, different fixes")
check("and it is not counted usable either",
      "e11" not in V.verdict(V.measure(TMP, prefix="e", reference="e00",
                                       block_rgb=BLOCK))[0])

# 4: it never reads a reply.
_src = open(os.path.join(ROOT, "experiments", "ex2",
                         "visibility.py")).read()
check("the module never opens a run file or a reply field",
      not any(w in _src for w in ("runs/", '"answer"', "'answer'",
                                  '"correct"', "'correct'", "jsonl")),
      "excluding a position for scoring badly is choosing the sample from "
      "the answers")

# 7: the report shows both margins.
_rep = V.report(detail, usable, occluded)
check("the report states the worst excluded and the best retained",
      "worst excluded" in _rep and "best retained" in _rep, _rep)
check("and says the verdict is blind to model replies",
      "never a model reply" in _rep)

# 8: the command line.
_reg = {}
_orig = _argparse.ArgumentParser.add_argument


def _record(self, *args, **kw):
    for a in args:
        if isinstance(a, str) and a.startswith("--"):
            _reg[a] = _reg.get(a, 0) + 1
    return _orig(self, *args, **kw)


_argparse.ArgumentParser.add_argument = _record
try:
    try:
        V.main(["--probes", TMP, "--prefix", "e", "--reference", "e00",
                "--block-rgb", "%d,%d,%d" % BLOCK])
        _built = True
    except SystemExit as e:
        _built = e.code in (0, None)
    except _argparse.ArgumentError:
        _built = False
finally:
    _argparse.ArgumentParser.add_argument = _orig
check("the command line parses and runs", _built)
check("no flag is registered more than once",
      not {k: v for k, v in _reg.items() if v > 1})

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
