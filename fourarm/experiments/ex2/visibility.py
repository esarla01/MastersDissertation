"""EX2 step 0: is the flip object actually VISIBLE in the render.

WHY THIS EXISTS. The Q1 notebook already excludes positions with cause,
but on ONE criterion: whether the arm legality carries the aperture
contrast. A position can carry the full contrast and still have the block
hidden behind the Franka, and nothing in the pipeline noticed. Position
e10 is such a case. Its block presents 45 visible pixels standing and 224
lying, against medians of 1518 and 720, and GPT answered its two posture
trials INVERTED -- the only two it got wrong out of twenty.

Legality and visibility are independent properties and both are
preconditions. A perception result from a picture that does not show the
object is not a result about the model.

WHY IT IS COMPUTED FROM PIXELS ALONE. Excluding a position BECAUSE it
scored badly is choosing the sample from the answers. This module never
sees a model reply. It takes the renders, measures how much of the block
each one shows, and returns the verdict; whether that verdict happens to
agree with a run's failures is then a finding rather than a construction.
Run it before the calls, not after.

HOW THE BLOCK IS FOUND. By colour, sampled from a capture where the block
is plainly unoccluded, then the LARGEST CONNECTED region of that colour.
Connectivity is what makes it a measurement of the block: a bare colour
count also collects shadowed table pixels inside the tolerance, and at the
occluded position that noise was enough to put it at 34 percent of the
median rather than 3, which is the difference between a cliff and a
judgement call.

THE THRESHOLD IS A CLIFF, NOT A TUNING. Across the seventeen captured
positions the worst-visible pose runs 0.60 to 1.14 of its pose median,
and then one position at 0.03. Any cut between 0.05 and 0.55 excludes the
same single position. The default sits in the middle of that gap and the
report prints both margins, so a reader can see the cut was not placed
against a close call.

Usage:
    python3 -m experiments.ex2.visibility --probes out/ex2_capture_block
    python3 -m experiments.ex2.visibility --probes out/ex2_capture_block \\
        --prefix e --min-ratio 0.5
"""

import argparse
import collections
import glob
import os
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# A position must show at least this fraction of the median visible block
# area, in EVERY pose, to be usable. See the module docstring: the observed
# gap runs from 0.03 to 0.60, so this sits in open space.
MIN_RATIO = 0.50

# Summed absolute RGB distance from the sampled block colour. Tight enough
# that the cream table (about 165 away) never enters.
TOLERANCE = 40


def _np():
    """numpy, PIL and scipy, imported late.

    They are not needed to run EX2, only to check a capture, and a hard
    import would make the whole experiments package fail to load on a
    machine that never renders anything.
    """
    try:
        import numpy as np
        from PIL import Image
        from scipy import ndimage
    except ImportError as exc:                          # noqa: BLE001
        raise SystemExit(
            "the visibility check needs numpy, Pillow and scipy: %s. It is "
            "the only part of EX2 that reads pixels; everything else runs "
            "without them." % exc)
    return np, Image, ndimage


# The block's colour, sampled once from out/ex2_capture_block/e08_U.png at
# the block's centre and recorded here with its provenance.
#
# Stated rather than auto-detected, deliberately. Two auto-detectors were
# tried -- a fixed sampling box, and the modal colour of the region that
# changes between poses -- and BOTH silently returned the table instead of
# the block, at which point every position measures as fully visible and
# the check passes while testing nothing. A wrong constant that is
# CHECKED is safer than a clever guess that is not, so the number is here
# and validate_colour below refuses to proceed if it stops matching a
# block.
BLOCK_RGB = (204.0, 181.0, 140.0)


def sample_block_colour(path, box):
    """The block's RGB from a patch known to be block. Both arguments
    required: a default box is a magic rectangle tuned to one framing, and
    it returns the table the moment the camera moves. Use this to
    RE-DERIVE BLOCK_RGB after recolouring or re-rendering, then paste the
    result above and rerun the harness."""
    np, Image, _ = _np()
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    y0, y1, x0, x1 = box
    return tuple(float(v) for v in
                 np.median(a[y0:y1, x0:x1].reshape(-1, 3), axis=0))


def validate_colour(paths, block_rgb=BLOCK_RGB, tolerance=TOLERANCE):
    """Refuse a colour that is not measuring a block.

    This is the guard that both auto-detectors needed and did not have. A
    colour that has drifted onto the table matches an enormous, frame-
    spanning region; one that matches nothing leaves an empty mask. Either
    way every position scores the same and the occlusion check reports a
    clean sheet, which is the most dangerous possible failure for a
    precondition. So the mask on the reference position must look like an
    object: present, a small fraction of the frame, and mostly one
    connected piece.

    `paths` are the poses of a position where the block is plainly
    unoccluded.
    """
    np, Image, ndimage = _np()
    problems = []
    for path in paths:
        a = np.asarray(Image.open(path).convert("RGB")).astype(int)
        mask = np.abs(a - np.array(block_rgb)).sum(2) < tolerance
        frac = mask.sum() / mask.size
        if frac == 0:
            problems.append("%s: nothing matches the colour"
                            % os.path.basename(path))
            continue
        if frac > 0.05:
            problems.append("%s: %.1f%% of the frame matches, which is a "
                            "surface and not an object"
                            % (os.path.basename(path), 100 * frac))
            continue
        lab, n = ndimage.label(mask)
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        if sizes.max() / mask.sum() < 0.5:
            problems.append("%s: the matching pixels are scattered, the "
                            "largest piece is only %.0f%% of them"
                            % (os.path.basename(path),
                               100 * sizes.max() / mask.sum()))
    if problems:
        raise SystemExit(
            "the block colour %s is not measuring a block in the reference "
            "position:\n  %s\nRe-derive it with sample_block_colour() from "
            "a patch that is block, update BLOCK_RGB, and rerun "
            "h_ex2_visibility.py." % (tuple(block_rgb), "\n  ".join(problems)))
    return True


def visible_px(path, block_rgb, tolerance=TOLERANCE):
    """Pixels in the LARGEST connected block-coloured region of a render.

    Largest-connected rather than a plain count, because scattered table
    pixels inside the tolerance are not the block and counting them hides
    an occlusion behind noise.
    """
    np, Image, ndimage = _np()
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    mask = np.abs(a - block_rgb).sum(2) < tolerance
    lab, n = ndimage.label(mask)
    if n == 0:
        return 0
    return int(ndimage.sum(mask, lab, range(1, n + 1)).max())


def measure(capture_dir, prefix="e", reference=None, block_rgb=BLOCK_RGB):
    """{position: {pose_suffix: visible_px}} for every position found.

    `reference` names a POSITION used to validate the colour before
    anything is measured, and it must be one where the block is plainly
    unoccluded -- validating against a hidden block would accept a colour
    that matches whatever is in front of it. It defaults to the position
    with the most block-coloured pixels, which is the least occluded one
    by construction.
    """
    paths = sorted(glob.glob(os.path.join(capture_dir, "%s*.png" % prefix)))
    if not paths:
        raise SystemExit("no %s*.png renders in %s" % (prefix, capture_dir))
    by_pos = collections.defaultdict(list)
    for p in paths:
        by_pos[os.path.basename(p)[:-4][:-2]].append(p)

    out = collections.defaultdict(dict)
    for p in paths:
        seq = os.path.basename(p)[:-4]
        out[seq[:-2]][seq[-1]] = visible_px(p, block_rgb)
    out = dict(out)

    ref = reference or max(out, key=lambda k: max(out[k].values()))
    if ref not in by_pos:
        raise SystemExit("reference position %r has no %s*.png renders in "
                         "%s" % (ref, prefix, capture_dir))
    validate_colour(sorted(by_pos[ref]), block_rgb=block_rgb)
    return out


def verdict(counts, min_ratio=MIN_RATIO):
    """(usable, occluded, detail) from the measurements.

    Each pose is compared against the MEDIAN OF ITS OWN POSE across
    positions, never against the other poses. The three poses present
    genuinely different areas -- the flat one shows about half what the
    standing one does -- so one shared median would flag every flat
    capture and hide a real occlusion among them.
    """
    poses = sorted({p for v in counts.values() for p in v})
    complete = {k: v for k, v in counts.items() if set(v) == set(poses)}
    if not complete:
        raise SystemExit("no position has all of %s" % poses)
    med = {p: statistics.median(v[p] for v in complete.values())
           for p in poses}
    detail = {}
    for pos, v in complete.items():
        ratios = {p: (v[p] / med[p]) if med[p] else 0.0 for p in poses}
        detail[pos] = {"px": v, "ratios": ratios,
                       "worst": min(ratios.values()),
                       "worst_pose": min(ratios, key=ratios.get)}
    usable = sorted(p for p, d in detail.items() if d["worst"] >= min_ratio)
    occluded = sorted(p for p, d in detail.items() if d["worst"] < min_ratio)
    incomplete = sorted(set(counts) - set(complete))
    for pos in incomplete:
        detail[pos] = {"px": counts[pos], "ratios": {}, "worst": None,
                       "worst_pose": None}
    return usable, occluded, detail


def report(detail, usable, occluded, min_ratio=MIN_RATIO):
    lines = ["%-6s %s   %8s  %s"
             % ("pos", "  ".join("%7s" % p for p in
                                 sorted(next(iter(detail.values()))["px"])),
                "worst", "verdict")]
    ranked = sorted((d["worst"] if d["worst"] is not None else -1, p)
                    for p, d in detail.items())
    for _, pos in ranked:
        d = detail[pos]
        if d["worst"] is None:
            lines.append("%-6s %s   %8s  INCOMPLETE"
                         % (pos, "  ".join("%7s" % d["px"].get(p, "-")
                                           for p in sorted(d["px"])), "-"))
            continue
        lines.append("%-6s %s   %8.2f  %s"
                     % (pos, "  ".join("%7d" % d["px"][p]
                                       for p in sorted(d["px"])),
                        d["worst"],
                        "OCCLUDED (%s)" % d["worst_pose"]
                        if pos in occluded else "ok"))
    worst_ok = min((detail[p]["worst"] for p in usable), default=None)
    best_bad = max((detail[p]["worst"] for p in occluded), default=None)
    lines.append("")
    lines.append("cut at %.2f of the pose median, in every pose."
                 % min_ratio)
    if best_bad is not None and worst_ok is not None:
        lines.append("worst excluded %.2f, best retained %.2f: the cut sits "
                     "in open space, so it is not deciding a close call."
                     % (best_bad, worst_ok))
    lines.append("%d usable, %d occluded: %s"
                 % (len(usable), len(occluded), ", ".join(occluded) or "none"))
    lines.append("this reads pixels only and never a model reply, so a "
                 "position is not excluded for having scored badly.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probes", default="out/ex2_capture_block")
    ap.add_argument("--prefix", default="e",
                    help="render filename prefix, e.g. e or w")
    ap.add_argument("--min-ratio", type=float, default=MIN_RATIO)
    ap.add_argument("--reference", default=None,
                    help="a POSITION id used to validate the block colour, "
                         "e.g. e08. Must be one where the block is plainly "
                         "unoccluded. Defaults to the least occluded.")
    ap.add_argument("--block-rgb", default=None,
                    help="override the recorded block colour, as R,G,B")
    a = ap.parse_args(argv)
    rgb = (tuple(float(x) for x in a.block_rgb.split(","))
           if a.block_rgb else BLOCK_RGB)
    counts = measure(a.probes, prefix=a.prefix, reference=a.reference,
                     block_rgb=rgb)
    usable, occluded, detail = verdict(counts, min_ratio=a.min_ratio)
    print(report(detail, usable, occluded, min_ratio=a.min_ratio))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
