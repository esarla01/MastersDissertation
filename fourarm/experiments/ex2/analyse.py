"""EX2 analysis: the four diagnostic views, from one instrument.

WHY THIS EXISTS. Every number in this project that came from an ad hoc
query written in a chat window has been wrong at least once: six clamp
assignments that were a task-id mistake, a 24-row cell that was two
duplicated retries, an image-following verdict that was a self
contradiction. The summary tables are produced by solo.py and rescore.py;
these four views were not, and they should be.

It reads results files and makes no calls. Rows are deduplicated by
trial_id with the last write winning, the same rule solo.py's own table
uses, so a retried failure does not count twice.

THE FOUR VIEWS

  reason   What the model REPORTED, grouped so the same scene's repeats
           sit together. The view for reading rather than counting.

           On a current run that is the two typed fields, the opening and,
           at N-D and N-CD, the resting face. On a pre-2026-08-26 file it
           is the prose the model wrote in why.grasp, and the view falls
           back to that so the older results stay readable.

           The question it answered on the prose files: qwen reported
           image_referenced on 66 of 66 replies while width_belief was
           state on 66 of 66. It talked about the picture in every reply
           and never took a number from it. That column no longer exists
           on a current run, by design: the typed schema carries no prose
           to keyword-match, and the reported opening is the measurement.

  odd      Replies whose stated opening is neither candidate value. These
           are the only direct evidence of LOOKING AND MISREADING, as
           opposed to not looking: an opening matching the declared value
           is consistent with never having consulted the image, but a
           third value can only have been derived and derived wrongly.

  stable   Whether a scene gives the same width_belief on every repeat.
           An aggregate of 38 out of 66 can mean 19 scenes always reading
           the image, or 22 scenes reading it two times in three. Those
           are different claims and only this view separates them.

  noop     Trials where no arm was named. A wait is never correct in this
           design, since a legal arm always exists, so choosing one is a
           signal rather than noise.

Usage:
    python3 -m experiments.ex2.analyse --run runs/A_conflict.jsonl \\
        --probes out/ex2_capture --view reason --model qwen --rung N-D
    python3 -m experiments.ex2.analyse --run runs/A_conflict.jsonl --view odd
    python3 -m experiments.ex2.analyse --run runs/A_conflict.jsonl \\
        --view stable
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.cell import cell_config as C                          # noqa: E402
from experiments.ex2.rescore import rescore                     # noqa: E402

# What separates the two readings in view_split: an opening above it needs
# a UR, one below it admits either family. Read from the cell config so it
# cannot drift from the arm the validator actually uses.
FRANKA_APERTURE = C.ARM_TYPES["franka"]["max_grasp_m"]

VIEWS = ("reason", "odd", "stable", "noop", "split", "extract")

# The values the design can produce for a given row: the TRUE opening and,
# in a conflict cell, the DECLARED one. Anything else was derived from the
# picture and derived wrongly.
#
# Read off each row rather than hardcoded. The constants used to be the
# mustard's (0.058, 0.096); the block's are (0.050, 0.100), so a fixed pair
# reported every reply in a block run as off-candidate and every extraction
# fault in a mustard run as fine.
TOL = 0.006


def candidates(row):
    """The opening values this row's own design admits."""
    out = []
    for key in ("true_grasp_m", "declared_grasp_m"):
        v = row.get(key)
        if v is not None:
            out.append(float(v))
    return tuple(out)


def is_candidate(row):
    """Is the extracted opening one of the values this row could produce."""
    w = row.get("believed_width_m")
    cands = candidates(row)
    if w is None or not cands:
        return True
    return any(abs(w - c) <= TOL for c in cands)


def reported(row):
    """What the model reported, in one line, whichever schema it used.

    The typed fields on a current row; the why.grasp prose on a row from a
    pre-2026-08-26 file. Reading only one of the two would print blanks
    for half the results files in the tree.
    """
    bits = []
    if row.get("resting_face"):
        bits.append("face=%s" % row["resting_face"])
    if row.get("opening_needed_m") is not None:
        bits.append("opening=%.3f" % row["opening_needed_m"])
    # Both, when both are there. Returning the typed fields alone dropped
    # the prose on any row that carried a face but no typed opening, which
    # is exactly the row view_extract exists to show in full.
    prose = (row.get("why") or {}).get("grasp") or ""
    if prose:
        bits.append(prose)
    return "  ".join(bits)


def select(rows, model=None, rung=None, preference=None, pose=None,
           condition=None):
    out = rows
    for field, want in (("model", model), ("rung", rung),
                        ("preference", preference), ("true_pose", pose),
                        ("condition", condition)):
        if want:
            out = [r for r in out if r.get(field) == want]
    return out


def view_reason(rows, limit=None):
    """What the model reported, grouped by scene so repeats sit together.

    Printed rather than counted. The keyword classifier already says
    whether the image was mentioned and the arithmetic says which width
    was used; what neither can say is what the sentence actually claims,
    and that is the open question for qwen's talks-about-it-never-uses-it
    cells.
    """
    out = []
    key = lambda r: (r.get("model"), r.get("preference"), r.get("rung"),
                     r["true_pose"], r["seq"], r.get("repeat", 1))
    shown = 0
    last = None
    for r in sorted(rows, key=key):
        group = key(r)[:5]
        if last is not None and group[:4] != last[:4]:
            out.append("")
        last = group
        why = reported(r)
        out.append("%-6s %-6s %-7s %-8s r%s %-8s arm=%-9s %-6s %-16s %s"
                   % (r.get("model"), r.get("preference"), r.get("rung"),
                      r["seq"], r.get("repeat", 1), r["true_pose"],
                      r.get("arm") or "none", r.get("width_belief"),
                      r.get("reasoning"), why[:70]))
        shown += 1
        if limit and shown >= limit:
            out.append("... truncated at %d rows" % limit)
            break
    return "\n".join(out)


def view_odd(rows):
    """Stated openings that are neither candidate value for their own row.

    The only direct evidence of looking and misreading. A declared-value
    match is consistent with never having consulted the image; a third
    value is not.
    """
    odd = [r for r in rows
           if r.get("believed_width_m") is not None and not is_candidate(r)]
    out = ["%d replies stated an opening that is neither candidate value "
           "for their own row" % len(odd)]
    if not odd:
        out.append("  none. Every stated opening in this file is one of the "
                   "values already present, so the model is SELECTING "
                   "between given numbers rather than measuring anything.")
        return "\n".join(out)
    for r in sorted(odd, key=lambda x: (x.get("model"), x.get("rung"),
                                        x["seq"])):
        why = reported(r)
        out.append("  %-6s %-6s %-7s %-8s %-8s stated=%.3f arm=%-9s %s"
                   % (r.get("model"), r.get("preference"), r.get("rung"),
                      r["seq"], r["true_pose"], r["believed_width_m"],
                      r.get("arm") or "none", why[:60]))
    return "\n".join(out)


def view_stable(rows):
    """Per-scene consistency of width_belief across repeats.

    An aggregate of 38 of 66 can mean 19 scenes that always read the image
    or 22 that read it twice in three. Those are different claims about
    whether source selection is a property of the scene or of the sample,
    and the aggregate cannot tell them apart.
    """
    cells = {}
    for r in rows:
        key = (r.get("model"), r.get("preference"), r.get("rung"))
        cells.setdefault(key, {}).setdefault(r["seq"], []).append(
            r.get("width_belief"))
    head = ("%-6s %-6s %-7s %-7s %-9s %-9s %s"
            % ("model", "pref", "rung", "scenes", "always-im", "always-st",
               "flips"))
    out = [head, "-" * len(head)]
    for key in sorted(cells, key=str):
        scenes = cells[key]
        always_im = [s for s, v in scenes.items() if set(v) == {"image"}]
        always_st = [s for s, v in scenes.items() if set(v) == {"state"}]
        flips = [s for s, v in scenes.items() if len(set(v)) > 1]
        out.append("%-6s %-6s %-7s %-7d %-9d %-9d %d  %s"
                   % (key[0], key[1], key[2], len(scenes), len(always_im),
                      len(always_st), len(flips),
                      " ".join(sorted(flips))))
    return "\n".join(out)


def view_extract(rows):
    """Every reply whose extracted opening is not a candidate value.

    A VALIDATION view, not a result, and one that matters much less than
    it used to. On a current run the opening is a TYPED field and no
    extractor stands between the reply and the number, so an off-candidate
    value is a model fault. On a pre-2026-08-26 file the number was mined
    out of prose: three extractor rules failed there, each on a sentence
    shape the previous test cases did not contain, and each time the
    faults were reported as findings before being caught.

    Run this on every prose results file before quoting any width-derived
    number. It prints the FULL report, untruncated, so a fault is visible
    rather than inferred.
    """
    odd = [r for r in rows
           if r.get("believed_width_m") is not None and not is_candidate(r)]
    typed = sum(1 for r in odd if r.get("opening_needed_m") is not None)
    out = ["%d of %d replies reported an opening that is neither candidate "
           "value for their own row" % (len(odd), len(rows))]
    if not odd:
        out.append("  none. Every reported opening is a candidate value, so "
                   "the model is selecting between the supplied numbers "
                   "rather than measuring anything.")
        return "\n".join(out)
    out.append("  %d of those came from the TYPED field, so they are model "
               "faults, not extraction faults." % typed)
    out.append("  CHECK THE REST against their prose before treating them "
               "as model failures.")
    for r in odd:
        out.append("")
        out.append("  %-5s %-6s %-7s %-9s %-8s true=%-8s arm=%-9s "
                   "extracted=%s"
                   % (r.get("model"), r.get("preference"), r.get("rung"),
                      r.get("condition"), r.get("seq"), r.get("true_pose"),
                      r.get("arm"), r.get("believed_width_m")))
        out.append("      %s" % reported(r))
    return "\n".join(out)


def view_split(rows):
    """Arm family crossed with stated width. Splits "uninformative".

    A UR is legal under BOTH poses, so naming one cannot be scored on the
    arm axis and the grader calls it uninformative. That is a fact about
    the arm, not about the trial: crossed with the width the model stated,
    the same rows separate cleanly.

    Take a conflict trial whose TRUE opening is over the Franka aperture,
    under the Franka preference. The text claims the narrower opening and
    the guidance pulls toward franka_n, so naming a UR goes against both.
    Why it did so is in the opening the model reported:

      wide + UR       read the picture, found the Franka too small, and
                      overrode the preference. Image use that the arm
                      column cannot show.
      narrow + UR     believed the text, which says the Franka fits, and
                      declined it anyway. Not perception: the guidance was
                      simply not followed.
      narrow + Franka followed the text and the preference together.
      wide + Franka   states an opening its own arm cannot span.

    When the TRUE opening is under the aperture the text claims the wider
    one, so the readings invert: a Franka choice needs the image, and a UR
    choice is what the text implies.

    Split on the GEOMETRY, not on a pose name. The mustard had two poses
    and the block has three, and only two of the block's three are over
    the aperture, so a split on ("lying", "upright") matched no block row
    at all and printed an empty view.
    """
    notes_wide = {
        ("image", "UR"): "read the image, overrode the preference",
        ("state", "UR"): "believed the text, declined the Franka anyway",
        ("state", "franka"): "followed the text and the preference",
        ("image", "franka"): "states an opening that arm cannot span",
    }
    notes_narrow = {
        ("image", "franka"): "read the image, used the wider arm set",
        ("state", "UR"): "followed the text, which claims the wider opening",
        ("image", "UR"): "read the image but took the safer arm",
        ("state", "franka"): "states an opening that arm cannot span",
    }
    out = []
    cells = {}
    for r in rows:
        cells.setdefault((r.get("model"), r.get("preference"),
                          r.get("rung")), []).append(r)
    for key in sorted(cells, key=str):
        out.append("=" * 74)
        out.append("%s / %s / %s" % key)
        for band in ("over aperture", "under aperture"):
            pr = [r for r in cells[key]
                  if r.get("true_grasp_m") is not None
                  and ((r["true_grasp_m"] > FRANKA_APERTURE)
                       == (band == "over aperture"))]
            if not pr:
                continue
            tally = {}
            for r in pr:
                arm = r.get("arm")
                fam = ("none" if not arm else
                       "franka" if arm.startswith("franka") else "UR")
                k = (r.get("width_belief"), fam)
                tally[k] = tally.get(k, 0) + 1
            notes = (notes_wide if band == "over aperture" else notes_narrow)
            out.append("  %-15s n=%d" % (band, len(pr)))
            for k in sorted(tally, key=str):
                out.append("    width=%-6s arm=%-7s %3d   %s"
                           % (k[0], k[1], tally[k], notes.get(k, "")))
    return "\n".join(out)


def view_noop(rows):
    """Trials where no arm was named.

    A legal arm exists in every scene, so a wait is never correct here and
    choosing one is a signal rather than noise.
    """
    noops = [r for r in rows if not r.get("arm")]
    out = ["%d trials named no arm" % len(noops)]
    for r in sorted(noops, key=lambda x: (x.get("model"), x.get("rung"),
                                          x["seq"])):
        why = reported(r) or json.dumps(r.get("why"))
        out.append("  %-6s %-6s %-7s %-8s %-8s outcome=%-14s %s"
                   % (r.get("model"), r.get("preference"), r.get("rung"),
                      r["seq"], r["true_pose"], r.get("outcome"), why[:110]))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--probes", default="out/ex2_capture")
    ap.add_argument("--view", default="stable", choices=VIEWS)
    ap.add_argument("--model", default=None)
    ap.add_argument("--rung", default=None)
    ap.add_argument("--preference", default=None)
    ap.add_argument("--pose", default=None,
                    help="filter on the resting face: small_face, "
                         "edge or large_face")
    ap.add_argument("--condition", default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)

    rows = rescore(a.run, a.probes)
    rows = select(rows, a.model, a.rung, a.preference, a.pose, a.condition)
    print("%d trials after filtering" % len(rows))
    print()
    if a.view == "reason":
        print(view_reason(rows, a.limit))
    elif a.view == "odd":
        print(view_odd(rows))
    elif a.view == "stable":
        print(view_stable(rows))
    elif a.view == "split":
        print(view_split(rows))
    elif a.view == "extract":
        print(view_extract(rows))
    else:
        print(view_noop(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())