"""h_ex2_seecheck: the description probe parses two lines, grades only the
pose, and cannot be fooled by a model that answers one word for everything.

Imports the REAL seecheck module. No live call is made: fake model
functions stand in, because a harness needing a paid endpoint could not run
in the suite.

What is pinned, and the failure each one guards:

  1. Ground truth comes from the REGISTRY entry, not the filename. Only
     p*_B and e*_B are upright; n*_B and m*_B are nulls and lying. Keying
     on the letter would mislabel eleven of forty-four scenes.
  2. The pose is read from the POSE line only. A description mentioning
     the word "upright" while the POSE line says lying must not flip the
     grade, or the free text would contaminate the measure it exists to
     explain.
  3. A missing or malformed POSE line is unparseable, not wrong. Failing a
     format is not failing to see.
  4. The description is recorded even when the pose line is unusable,
     since that is exactly the case worth reading by hand.
  5. Errors are counted apart from wrong answers.
  6. The per-pose split exposes a degenerate answerer: always saying
     "lying" scores near half overall and must show as 100 and 0.
  7. This probe is NOT mancheck. Its prompt asks for a description, so its
     accuracy is not comparable to the terse one, and the two must not
     share a prompt.

Run:  python3 h_ex2_seecheck.py
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

from experiments.ex2 import seecheck as S                        # noqa: E402
from experiments.ex2 import prompts as P                         # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


def build_captures(tmp):
    """Minimal captures the REAL load_scenes can read.

    n01_B is deliberately a LYING bottle whose id ends in _B, which is the
    case a filename rule gets wrong.
    """
    recs = []
    for seq, prim, kind in (("p01_A", "ycb_mustard_lying", "pair"),
                            ("p01_B", "ycb_mustard_upright", "pair"),
                            ("n01_B", "ycb_mustard_lying", "null")):
        images = {"ex2_cam": seq + ".png",
                  "table_cam": seq + "_table_cam.png"}
        for name in images.values():
            with open(os.path.join(tmp, name), "wb") as f:
                f.write(b"\x89PNG-not-a-real-frame")
        recs.append({
            "seq": seq,
            "state": {"objects": [{"name": prim},
                                  {"name": "ycb_large_clamp"}],
                      "tasks": [{"id": 0, "object": prim},
                                {"id": 1, "object": "ycb_large_clamp"}]},
            "positions_exact": {},
            "ex2": {"kind": kind, "images": images}})
    with open(os.path.join(tmp, "consults.jsonl"), "w") as f:
        for rec in recs:
            f.write(json.dumps(rec) + "\n")
    return tmp


TMP = build_captures(tempfile.mkdtemp())
rows = S.probes(S.load_scenes(TMP), S.VIEWS)

# 1. truth from the registry, not the filename
truth = {r["seq"]: r["true_pose"] for r in rows}
check("one probe per scene per view", len(rows) == 6, "%d rows" % len(rows))
check("truth comes from the registry entry, not the _B suffix",
      truth["p01_B"] == "upright" and truth["n01_B"] == "lying",
      "n01_B ends in _B and is a lying null")

# 2, 3, 4. parsing
sees, pose = S.parse("SEES: the cap points up and the label faces me\n"
                     "POSE: upright")
check("both lines are read", pose == "upright" and sees.startswith("the cap"))
sees, pose = S.parse("SEES: it looks upright to me\nPOSE: lying")
check("the pose comes from the POSE line, not the description",
      pose == "lying", "description said upright")
sees, pose = S.parse("SEES: the bottle is on its side\nPOSE: on its side")
check("an unusable POSE line is unparseable, not wrong", pose is None)
check("the description survives an unusable pose line",
      sees == "the bottle is on its side",
      "that row is exactly the one worth reading by hand")
sees, pose = S.parse("I think it is lying down.")
check("prose with no lines at all yields nothing", pose is None
      and sees is None)

# 7. this is not mancheck
check("the description probe does not reuse the terse prompt",
      "SEES" in S.PROMPT
      and "SEES" not in json.dumps(P.manipulation_check("Zm9v")),
      "reasoning aloud can change the answer, so the two are not "
      "comparable and must not share a prompt")
check("the probe carries no state, rules or allocation",
      "max_grasp_m" not in S.PROMPT and "assignments" not in S.PROMPT)

# 5, 6. tallies
calls = {"n": 0}


def always_lying(messages, timeout=None, alias=None):
    calls["n"] += 1
    return "SEES: it rests on its side\nPOSE: lying"


out = os.path.join(TMP, "degenerate.jsonl")
produced = S.run(TMP, out_path=out, models=("fake",), formats=("describe",),
                 views=S.VIEWS, kind=None, model_fn=always_lying)
tally = S.summarise(produced)
check("degenerate model looks middling overall",
      tally[("ex2_cam", "all")]["correct"] == 2)
check("per-pose split exposes it as 100 and 0",
      tally[("ex2_cam", "lying")]["correct"] == 2
      and tally[("ex2_cam", "upright")]["correct"] == 0)
check("a wrong but legible answer is not retried", calls["n"] == 6,
      "%d calls for 6 probes" % calls["n"])


def hedges(messages, timeout=None, alias=None):
    return "SEES: too small to tell\nPOSE: unclear"


t2 = S.summarise(S.run(TMP, out_path=os.path.join(TMP, "h.jsonl"),
                       models=("fake",), formats=("describe",),
                       views=S.VIEWS, kind=None,
                       model_fn=hedges))[("ex2_cam", "all")]
check("a hedge is unparseable, not wrong, and keeps its description",
      t2["unparseable"] == 3 and t2["correct"] == 0 and t2["described"] == 3,
      str(t2))


def raises(messages, timeout=None, alias=None):
    raise RuntimeError("connection reset")


t3 = S.summarise(S.run(TMP, out_path=os.path.join(TMP, "e.jsonl"),
                       models=("fake",), formats=("describe",),
                       views=S.VIEWS, kind=None,
                       model_fn=raises))[("ex2_cam", "all")]
check("a transport failure is counted apart from a wrong answer",
      t3["error"] == 3 and t3["unparseable"] == 0, str(t3))

calls["n"] = 0
again = S.run(TMP, out_path=out, models=("fake",),
              formats=("describe",), views=S.VIEWS, kind=None,
              model_fn=always_lying)
check("a resumed run makes no further calls", calls["n"] == 0)
check("resume still summarises the whole file", len(again) == 6)

# 8. the default sample is BALANCED, which is what dropping nulls buys.
_pairs = S.probes(S.load_scenes(TMP), ("ex2_cam",), kind=S.DEFAULT_KIND)
_poses = [r["true_pose"] for r in _pairs]
check("the default kind drops the nulls",
      all(r["kind"] == "pair" for r in _pairs), "%d scenes" % len(_pairs))
check("pairs give equal numbers of each pose",
      _poses.count("lying") == _poses.count("upright"),
      "%d lying, %d upright" % (_poses.count("lying"),
                                _poses.count("upright")))
_all = S.probes(S.load_scenes(TMP), ("ex2_cam",), kind=None)
check("without the filter the sample is lopsided toward lying",
      [r["true_pose"] for r in _all].count("lying") > _poses.count("lying"),
      "which is why an overall accuracy on the full set is weighted")
check("the default view is the oblique camera alone",
      S.DEFAULT_VIEWS == ("ex2_cam",),
      "the overhead camera scored 0 of 11 upright and has no cue to probe")
check("both models run by default", len(S.DEFAULT_MODELS) == 2,
      str(S.DEFAULT_MODELS))

# 9. the table reports each model and pose separately.
_tbl = S.table([
    {"seq": "s1", "repeat": 0, "model": "a", "view": "ex2_cam",
     "true_pose": "lying", "pose": "lying", "correct": True},
    {"seq": "s2", "repeat": 0, "model": "a", "view": "ex2_cam",
     "true_pose": "upright", "pose": "lying", "correct": False},
    {"seq": "s3", "repeat": 0, "model": "b", "view": "ex2_cam",
     "true_pose": "upright", "pose": None, "correct": None},
])
check("the table has a row per model", "a" in _tbl and "b" in _tbl)
check("an unparseable row is excluded from accuracy, not scored wrong",
      "0/0" in _tbl or "nan" in _tbl.lower(), _tbl.splitlines()[-1])


# 10. the two reply formats are separate measurements, not one refined.
check("the terse format reuses the REAL manipulation_check prompt",
      json.dumps(S.messages_for("Zm9v", "terse"))
      == json.dumps(P.manipulation_check("Zm9v")),
      "a second copy would drift from the probe that already has results")
check("the describe format is a different prompt",
      json.dumps(S.messages_for("Zm9v", "describe"))
      != json.dumps(S.messages_for("Zm9v", "terse")))
try:
    S.messages_for("Zm9v", "chatty")
    check("an unknown format raises", False, "no exception")
except ValueError as e:
    check("an unknown format raises rather than defaulting",
          "chatty" in str(e), str(e)[:55])
check("a terse reply is parsed as a bare word with no description",
      S.parse("lying", "terse") == (None, "lying"))
check("terse prose is unparseable, not scored wrong",
      S.parse("It is lying down.", "terse")[1] is None,
      "failing a format is not failing to see")

# 11. an ERRORED row is retried on resume, not treated as answered.
_err_out = os.path.join(TMP, "errthenok.jsonl")
S.run(TMP, out_path=_err_out, models=("fake",), formats=("describe",),
      views=("ex2_cam",), kind=None, model_fn=raises)
_calls = {"n": 0}


def _recovers(messages, timeout=None, alias=None):
    _calls["n"] += 1
    return "SEES: on its side\nPOSE: lying"


S.run(TMP, out_path=_err_out, models=("fake",), formats=("describe",),
      views=("ex2_cam",), kind=None, model_fn=_recovers)
check("a row that errored is retried on resume",
      _calls["n"] == 3,
      "%d retried; skipping them is how a whole missing-key run "
      "re-reported itself as complete having made no calls" % _calls["n"])
_final = [json.loads(x) for x in open(_err_out) if x.strip()]
_ids = [r["probe_id"] for r in _final]
check("the retried answer replaces the error in the table, not doubles it",
      len(set(_ids)) == 3 and len(_final) == 6,
      "6 rows written, 3 distinct probes, later wins")


# 12. the interval maths, which a reader will check.
_lo, _hi = S.wilson(4, 11)
check("wilson matches the published value for 4 of 11",
      abs(_lo - 15.2) < 0.2 and abs(_hi - 64.6) < 0.2,
      "%.1f-%.1f" % (_lo, _hi))
for _c, _n in ((0, 11), (11, 11), (1, 22)):
    _lo, _hi = S.wilson(_c, _n)
    check("wilson stays inside 0 to 100 at the ends (%d/%d)" % (_c, _n),
          0.0 <= _lo <= _hi <= 100.0, "%.1f-%.1f" % (_lo, _hi))
check("wilson of an empty cell is not a number, not zero",
      S.wilson(0, 0) != S.wilson(0, 1),
      "an empty cell must not read as a confident zero")
_lo, _hi = S.wilson(5, 22)
check("an overhead-sized cell excludes chance",
      _hi < S.CHANCE, "5/22 upper bound %.1f is under %.0f" % (_hi, S.CHANCE))

# 13. repeats collapse to ONE verdict per image before the interval.
check("an image's repeats are settled by majority",
      S.majority(["lying", "lying", "upright"]) == "lying")
check("a tied image is unusable, not silently resolved",
      S.majority(["lying", "upright"]) is None,
      "picking one would invent a verdict the model never settled on")
check("an image with no usable answer is unusable",
      S.majority([None, None]) is None)

_reps = [{"model": "m", "format": "terse", "view": "v", "seq": "s1",
          "true_pose": "lying", "pose": p, "correct": p == "lying",
          "repeat": i + 1}
         for i, p in enumerate(["lying", "lying", "upright"])]
_st = S.cell_stats(_reps)
check("three repeats of one image count as ONE image, not three",
      _st["images"] == 1 and _st["correct"] == 1,
      "pooling them would report an interval far tighter than the "
      "evidence supports")
check("the run spread is reported per repeat", len(_st["spread"]) == 3,
      str([round(x) for x in _st["spread"]]))

# 14. repeats do not collide on resume.
_calls = {"n": 0}


def _counting(messages, timeout=None, alias=None):
    _calls["n"] += 1
    return "lying"


_rp = os.path.join(TMP, "repeats.jsonl")
S.run(TMP, out_path=_rp, models=("fake",), formats=("terse",),
      views=("ex2_cam",), kind=None, repeats=3, model_fn=_counting)
check("each repeat is its own call, not deduplicated away",
      _calls["n"] == 9, "%d calls for 3 scenes x 3 repeats" % _calls["n"])
_calls["n"] = 0
S.run(TMP, out_path=_rp, models=("fake",), formats=("terse",),
      views=("ex2_cam",), kind=None, repeats=3, model_fn=_counting)
check("a resumed repeat run makes no further calls", _calls["n"] == 0)


# 15. the COMMAND LINE builds. The harness drives run() directly, so a
# duplicate argparse registration passed every assertion above and still
# crashed on the first real invocation. Parsing is cheap; exercise it.
import argparse as _ap  # noqa: E402

_seen = {}
_orig = _ap.ArgumentParser.add_argument


def _record(self, *args, **kw):
    for a in args:
        if isinstance(a, str) and a.startswith("--"):
            _seen[a] = _seen.get(a, 0) + 1
    return _orig(self, *args, **kw)


_ap.ArgumentParser.add_argument = _record
try:
    _parsed = S.main.__globals__["argparse"]  # noqa: F841
    _ns = None
    try:
        S.main(["--dry-run", "--probes", TMP, "--repeats", "2"])
        _built = True
    except SystemExit as e:
        _built = (e.code in (0, None))
    except _ap.ArgumentError as e:
        _built = False
        print("   argparse rejected the CLI:", e)
finally:
    _ap.ArgumentParser.add_argument = _orig

check("the command line parses without an argparse conflict", _built,
      "every flag must be registered exactly once")
_dupes = {k: v for k, v in _seen.items() if v > 1}
check("no flag is registered more than once", not _dupes, str(_dupes))
check("--repeats reaches the parser", "--repeats" in _seen)


print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)