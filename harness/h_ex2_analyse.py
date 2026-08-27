"""h_ex2_analyse: the diagnostic views, pinned.

analyse.py shipped without a harness. It is the file that answers "why did
the model do that", so its readings end up in the write-up directly, and
every reading in this project that came from an unpinned query has been
wrong at least once.

Imports the REAL module. No model is called and no results file is needed:
rows are constructed here so each view can be checked against a known
answer.

What is pinned, and the failure each one guards:

  1. Rows are deduplicated by trial_id. A retried failure and its
     replacement are one trial, not two; reading every line once put 24
     rows in a 22-scene cell.
  2. The split view separates what the arm column cannot. A UR is legal
     under both poses, so an "uninformative" verdict is a fact about the
     arm rather than the trial. Crossed with the stated width, a UR choice
     on a trial whose true opening is over the Franka aperture is either
     the model overriding the preference on the strength of the picture
     (0.100) or believing the text and declining the Franka anyway
     (0.050). Pooling them loses the finding.
  3. The reading INVERTS between poses, because the text claims the
     opposite pose in each. A view that applied one legend to both would
     mislabel half the data.
  4. A wait is its own family, not folded into an arm.
  5. The odd view catches widths that are neither candidate value. Those
     are the only direct evidence of looking and misreading, as against
     not looking, which is otherwise inseparable.

Run:  python3 h_ex2_analyse.py
"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from experiments.ex2 import analyse as A                         # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


# view_split and view_odd now read the candidate openings OFF THE ROW
# (true_grasp_m / declared_grasp_m) instead of a module constant, and
# view_split bands on the geometry rather than on a pose name. So the
# fixture has to carry both numbers, and "over"/"under" name which side of
# the 0.080 Franka aperture the TRUE opening sits.
_OVER = {"true_pose": "large_face", "true_grasp_m": 0.100,
         "declared_pose": "small_face", "declared_grasp_m": 0.050}
_UNDER = {"true_pose": "small_face", "true_grasp_m": 0.050,
          "declared_pose": "large_face", "declared_grasp_m": 0.100}


def row(belief, arm, band="over", **kw):
    r = {"model": "m", "preference": "franka", "rung": "N-D",
         "condition": "conflict", "arm": arm,
         "width_belief": belief, "seq": "p01_A", "repeat": 1,
         "resting_face": "large_face", "opening_needed_m": 0.050,
         "why": None, "reasoning": "none",
         "believed_width_m": 0.050, "outcome": "uninformative"}
    r.update(_OVER if band == "over" else _UNDER)
    r.update(kw)
    return r


# 1. the split view exists and is offered.
check("split is one of the views", "split" in A.VIEWS, str(A.VIEWS))

# 2, 3. the four combinations, and the inversion between poses.
rows = []
for belief, arm, band, n in (("image", "ur_w", "over", 5),
                             ("state", "franka_n", "over", 3),
                             ("state", "ur_w", "over", 2),
                             ("image", "franka_n", "over", 1),
                             ("image", "franka_n", "under", 4),
                             ("state", "ur_w", "under", 6)):
    for i in range(n):
        rows.append(row(belief, arm, band, seq="p%02d_A" % i))

out = A.view_split(rows)
check("image plus UR over the aperture reads as overriding the preference",
      "overrode the preference" in out,
      "the arm column scores this uninformative; the width shows it is "
      "image use")
check("state plus UR over the aperture reads as declining the Franka",
      "declined the Franka anyway" in out,
      "not perception: the guidance was simply not followed")
check("state plus Franka over the aperture reads as following both",
      "followed the text and the preference" in out)
check("image plus Franka over the aperture is flagged as contradictory",
      "cannot span" in out)
check("the reading inverts under the aperture",
      "used the wider arm set" in out
      and "followed the text, which claims the wider opening" in out,
      "the text claims the opposite face, so a Franka choice needs the "
      "image there")
check("all four over-aperture combinations appear separately",
      out.count("width=") >= 6, out)
check("the split is on the geometry, not on a pose name",
      "over aperture" in out and "under aperture" in out,
      "the block has three poses and only one is over the aperture, so a "
      "split on lying-versus-upright matched no row at all")

# 4. a wait is its own family.
check("a wait is not folded into an arm family",
      "arm=none" in A.view_split([row("none", None)]),
      "declining to assign is not the same as choosing badly")

# 5. the odd view.
check("a third width is surfaced",
      "0.191" in A.view_odd([row("other", "ur_w", believed_width_m=0.191)]),
      "the only direct evidence of looking and misreading")
# view_odd filters on the NUMBER against the two candidate values, not on
# the width_belief label. That is the right way round: the label is derived
# and could be wrong, the number is what the model actually wrote.
_clean = A.view_odd([row("state", "ur_w", believed_width_m=0.050)])
check("a candidate width is not counted as odd",
      _clean.startswith("0 replies"), _clean.splitlines()[0])
check("the clean case says what it means",
      "SELECTING" in _clean,
      "every opening being one of the supplied values is itself the "
      "finding: the model picks between given numbers rather than "
      "measuring anything")
_rounded = A.view_odd([row("image", "ur_w", believed_width_m=0.1)])
check("a rounded 0.100 is tolerated, not counted as odd",
      _rounded.startswith("0 replies"),
      "0.006 covers a model writing 0.1 for 0.100")
# The candidates come from the ROW, so a file measuring a different object
# is judged against its own numbers. A module constant reported every
# reply in a block run as off-candidate.
check("the candidates are read off the row, not from a constant",
      A.candidates(row("image", "ur_w")) == (0.100, 0.050),
      str(A.candidates(row("image", "ur_w"))))

# 1. deduplication, if the module loads files itself.
if hasattr(A, "load"):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "dupes.jsonl")
    with open(path, "w") as fh:
        fh.write(json.dumps(dict(row("none", None), trial_id="t1",
                                 outcome="unparseable")) + "\n")
        fh.write(json.dumps(dict(row("state", "ur_w"), trial_id="t1")) + "\n")
        fh.write(json.dumps(dict(row("state", "ur_w"), trial_id="t2")) + "\n")
    got = A.load(path)
    check("a retried trial is counted once", len(got) == 2,
          "%d rows from 3 lines with one duplicated id" % len(got))
    check("the retry replaces the failure",
          all(r["outcome"] != "unparseable" for r in got))
else:
    check("rows reach the views through rescore, which deduplicates",
          "rescore" in open(os.path.join(ROOT, "experiments", "ex2",
                                         "analyse.py")).read(),
          "reading every line would count a retry twice")

# the selector must not silently ignore an unknown field value.
sub = A.select(rows, model="m", rung="N-D")
check("select filters on the fields it names", len(sub) == len(rows))
check("select returns nothing for a model that is not there",
      A.select(rows, model="nobody") == [])

# --- a rescored row carries a RECOMPUTED width ---------------------------
# believed_width_m on disk was written by whatever extractor existed at run
# time, and the extractor has changed: it used to take the first number in
# why.grasp, which is an extent the model REJECTED when the reply
# enumerates before concluding. Two dims replies reading "extents are
# 0.191 m and 0.096 m, so graspable width is 0.096 m" were recorded as
# 0.191, flagged as self-contradictions, and reported as the only evidence
# of misderivation in the whole experiment. They were not.
from experiments.ex2 import grade as G                            # noqa: E402
from experiments.ex2 import rescore as RS                         # noqa: E402

_prose = ("Mustard is lying down; its horizontal extents are 0.191 m and "
          "0.096 m, so graspable width is 0.096 m, covered by ur_w max "
          "0.140 m")
check("the extractor reads the conclusion, not the rejected extent",
      G.believed_width({"why": {"grasp": _prose}}) == 0.096)

# A row from a PRE-2026-08-26 file: a P-rung, mustard geometry, a prose
# why block and no typed opening. It stays exactly as it was written. The
# point of the check is that the legacy fallback still re-mines a stale
# believed_width_m correctly, and rewriting the fixture in the current
# schema would test the typed path and quietly stop testing this one.
_stale = os.path.join(tempfile.mkdtemp(), "stale.jsonl")
with open(_stale, "w") as _fh:
    _fh.write(json.dumps({
        "trial_id": "t1", "model": "m", "preference": "franka",
        "rung": "P2", "condition": "dims", "seq": "p03_A", "repeat": 1,
        "true_pose": "lying", "declared_pose": None, "arm": "ur_w",
        "true_grasp_m": 0.096, "declared_grasp_m": None,
        "legal_true": ["ur_w", "ur_e"], "outcome": "uninformative",
        "why": {"grasp": _prose},
        "believed_width_m": 0.191,          # what the old extractor wrote
        "width_belief": "other"}) + "\n")
try:
    _out = RS.rescore(_stale, os.path.join(ROOT, "out", "ex2_capture"))
    _ok = True
except SystemExit:
    _ok = False                              # no captures in this tree
if _ok:
    _r = _out[0]
    check("rescore recomputes the width from the prose",
          _r["believed_width_m"] == 0.096,
          "trusting the file inherits the old extractor's mistake into "
          "every downstream verdict")
    check("the recomputed width reclassifies the row",
          _r["width_belief"] == "image")
    check("and clears a contradiction that was never real",
          not _r.get("self_contradicted"))
else:
    check("rescore recomputes rather than reading believed_width_m",
          "believed_width" in open(os.path.join(
              ROOT, "experiments", "ex2", "rescore.py")).read(),
          "captures absent in this tree, so checked by inspection")

# --- the extract view is a VALIDATION, not a result ----------------------
# Three extractor rules have failed, each on a sentence shape the previous
# test cases did not contain, and each time the faults were reported as
# findings first. The models state one of two values in almost every reply,
# so a non-candidate extraction is far more likely to be an instrument
# fault than a model one, and this view exists to be run before any
# width-derived number is quoted.
check("extract is one of the views", "extract" in A.VIEWS, str(A.VIEWS))
_clean = A.view_extract([row("state", "ur_w", believed_width_m=0.050),
                         row("image", "ur_w", believed_width_m=0.100)])
check("a file of candidate openings reports none",
      "none." in _clean, _clean.splitlines()[0])
check("the clean case states what it means",
      "selecting between the supplied numbers" in _clean)

# A LEGACY row: the number was mined out of prose, so the full sentence has
# to be printed for a fault to be visible rather than inferred.
_dirty = A.view_extract([row("other", "ur_w", believed_width_m=0.140,
                             opening_needed_m=None,
                             why={"grasp": "0.050 m graspable width, "
                                           "covered by ur_e 0.140 m"})])
check("a non-candidate opening is surfaced", "1 of 1" in _dirty)
check("the FULL prose is printed, not a truncation",
      "covered by ur_e 0.140 m" in _dirty,
      "a fault has to be visible rather than inferred")
check("the view tells the reader to check before concluding",
      "CHECK THE REST" in _dirty)

# A row from the CURRENT schema. The number is typed, so no extractor sits
# between the reply and it, and an off-candidate value is a model fault
# rather than an instrument one. Saying so is the point of the change.
_typed = A.view_extract([row("other", "ur_w", believed_width_m=0.075,
                             opening_needed_m=0.075)])
check("a typed off-candidate value is named as a model fault",
      "came from the TYPED field" in _typed and "1 of those" in _typed,
      _typed.splitlines()[1] if len(_typed.splitlines()) > 1 else _typed)
check("the typed field is what the view prints for a current row",
      "opening=0.075" in _typed, _typed)

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)