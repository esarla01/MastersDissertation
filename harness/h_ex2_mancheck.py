"""h_ex2_mancheck: the control walks every scene and view, grades strictly,
and cannot be fooled by a model that answers one word for everything.

Imports the REAL mancheck module and the REAL prompt builder. No live model
call is made: a fake model_fn stands in, because a harness that needed a
paid endpoint could not run in the suite.

What is pinned, and the failure each one guards:

  1. Every scene yields one check per view, and the true pose comes from
     the REGISTRY entry rather than from anything in the state. In a
     conflict cell the state is deliberately wrong about exactly that, and
     a control graded against the state would confirm the lie.
  2. Null scenes are included. Every null is a lying bottle, so dropping
     them would leave the sample biased toward the pose that is easier to
     see, and the per-view accuracy would be optimistic.
  3. Grading is exact. A reply that buries the word in a sentence scores
     as unparseable, not correct: a chatty model must not look more
     grounded than a terse one.
  4. Unparseable and error are counted separately from wrong. A transport
     failure and a confident misperception are different findings and
     merging them would hide both.
  5. The per-pose split exposes a degenerate answerer. A model that always
     says "lying" scores near half overall, which reads as partial
     competence; the split must show it at 100 and 0.
  6. A wrong but legible answer is NOT retried. Re-asking until the model
     agrees is how a control stops being one.
  7. Rows stream to disk and a resumed run skips what is already ANSWERED,
     so 88 paid calls survive a dropped connection.
  8. A row that ERRORED is retried on resume rather than counted as
     answered. Seven missing-key rows in runs/ex2_q1_cue_gpt_r1.jsonl
     survived two reruns because the resume keyed on the line existing,
     and the summary then reported the remainder as the whole sample.
  9. The retry REPLACES the failure in the summary rather than being
     counted beside it, so n stays equal to the number of checks.

Run:  python3 h_ex2_mancheck.py
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

from experiments.ex2 import mancheck as M                        # noqa: E402
from experiments.ex2 import prompts as P                         # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


def build_captures(tmp):
    """A minimal capture directory the REAL load_scenes can read."""
    recs = []
    # The BLOCK on BOTH of its resting faces, plus one capture of the
    # middle face that the design withdrew on 2026-08-27. That last one is
    # deliberate: 34 such captures are still on disk, and the pin below is
    # that load_scenes SKIPS them rather than loading a scene whose face
    # has no entry in the registry.
    for seq, prim, kind in (("p01_A", "ycb_block_large", "pair"),
                            ("p01_B", "ycb_block_upright", "pair"),
                            ("p01_C", "ycb_block_small", "pair"),
                            ("n01_A", "ycb_block_large", "null")):
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


# 1 and 2: the walk covers every scene and view, truth from the registry.
rows = M.checks(M.load_scenes(TMP, present_ur=False))
check("one check per scene per view, retired faces skipped",
      len(rows) == 6,
      "%d rows: 3 loadable scenes x 2 views. p01_C rests on the withdrawn "
      "middle face and must not appear" % len(rows))
check("the retired-face capture is skipped by name",
      not any(r["seq"] == "p01_C" for r in rows),
      "a capture whose face left the registry would otherwise raise deep "
      "in describe(), one scene at a time and far from the cause")
truth = {(r["seq"], r["view"]): r["true_pose"] for r in rows}
check("true pose read from the registry entry",
      truth[("p01_A", "ex2_cam")] == "large_face"
      and truth[("p01_B", "ex2_cam")] == "small_face",
      str(sorted(set(truth.values()))))

# Checked here as well as in the prompt harness, because this is where a
# mismatch would silently score every correct answer wrong.
faces = {(r["seq"], r["view"]): r["true_face"] for r in rows}
check("the recorded face is the one the probe can be answered with",
      all(faces[(s, "ex2_cam")] == truth[(s, "ex2_cam")]
          for s in ("p01_A", "p01_B")),
      "one vocabulary end to end, so no translation can go wrong")
check("the two faces are two distinct words",
      len({faces[(s, "ex2_cam")] for s in ("p01_A", "p01_B")}) == 2)
check("every face the walk yields is one the model may reply with",
      all(r["true_face"] in M.ANSWERS for r in rows),
      "a truth outside the answer vocabulary scores every trial wrong for "
      "a reason that has nothing to do with the model")
check("null scenes are not dropped",
      any(r["seq"] == "n01_A" for r in rows),
      "%d null rows" % sum(1 for r in rows if r["kind"] == "null"))


# 3: grading is exact, and the prompt asks for exactly these two words.
check("bare word accepted, case and punctuation tolerated",
      M.normalise("small_face") == "small_face"
      and M.normalise(" Large_Face. ") == "large_face")
check("a face the design withdrew is not an accepted answer",
      M.normalise("edge") is None,
      "it is not on offer, so producing it is a compliance failure")
check("word buried in a sentence is unparseable, not correct",
      M.normalise("It is resting on its large_face") is None)
check("a label outside the enum is unparseable",
      M.normalise("tilted") is None and M.normalise("") is None
      and M.normalise("lying") is None)
mc = P.manipulation_check("Zm9v")
mc_text = json.dumps(mc)
check("prompt asks for exactly the words the grader accepts",
      all(f in mc_text for f in M.ANSWERS))
check("chance is derived from the vocabulary, not typed",
      abs(M.CHANCE - 100.0 / len(M.ANSWERS)) < 1e-9
      and abs(M.CHANCE - 50.0) < 1e-9,
      "it was 100/3 until 2026-08-27; a literal left behind would report a "
      "coin as a finding. CHANCE is %.2f" % M.CHANCE)
check("the printed floor says how many ways the choice is",
      "2-way forced choice" in M.format_summary(M.summarise(rows[:1])),
      M.format_summary(M.summarise(rows[:1])))
check("control carries no state, rules or allocation",
      "max_grasp_m" not in mc_text and "assignments" not in mc_text
      and "HARD RULES" not in mc_text)


# 4, 5 and 6: a degenerate answerer is caught by the per-pose split.
calls = {"n": 0}


def always_large(messages, timeout=None, alias=None):
    calls["n"] += 1
    return "large_face"


out = os.path.join(TMP, "degenerate.jsonl")
produced = M.run(TMP, out_path=out, model="fake", model_fn=always_large)
tally = M.summarise(produced)
ex2_all = tally[("ex2_cam", "all")]
ex2_large = tally[("ex2_cam", "large_face")]
ex2_small = tally[("ex2_cam", "small_face")]
check("degenerate model scores its word's base rate, never better",
      ex2_all["correct"] == 2 and ex2_all["n"] == 3,
      "2 of 3 is the share of large_face scenes in this fixture, not a "
      "perception result")
check("per-face split exposes it as 100 and 0",
      ex2_large["correct"] == ex2_large["n"] and ex2_small["correct"] == 0,
      "a model answering one word for everything must not read as partial "
      "perception. With two faces this matters MORE, not less: on a "
      "balanced sample it scores exactly chance and the split is the only "
      "thing that separates it from a coin")
check("a wrong but legible answer is not retried",
      calls["n"] == 6, "%d calls for 6 checks" % calls["n"])


def hedges(messages, timeout=None, alias=None):
    return "I cannot tell from this image."


rows2 = M.run(TMP, out_path=os.path.join(TMP, "hedge.jsonl"),
              model="fake", model_fn=hedges)
t2 = M.summarise(rows2)[("table_cam", "all")]
check("a hedge counts as unparseable, not wrong",
      t2["unparseable"] == 3 and t2["correct"] == 0, str(t2))


def raises(messages, timeout=None, alias=None):
    raise RuntimeError("connection reset")


rows3 = M.run(TMP, out_path=os.path.join(TMP, "err.jsonl"),
              model="fake", model_fn=raises, retry_errors=False)
t3 = M.summarise(rows3)[("ex2_cam", "all")]
check("a transport failure is counted apart from a wrong answer",
      t3["error"] == 3 and t3["unparseable"] == 0, str(t3))


# 7: resume skips what is already written and pays for nothing twice.
calls["n"] = 0
again = M.run(TMP, out_path=out, model="fake", model_fn=always_large)
check("a resumed run makes no further calls", calls["n"] == 0,
      "%d calls on resume" % calls["n"])
check("resume still summarises the whole file", len(again) == 6,
      "%d rows read back" % len(again))

# 8, 9: an errored row is a call that never landed, not an answer.
_ep = os.path.join(TMP, "resume_err.jsonl")
M.run(TMP, out_path=_ep, model="fake", model_fn=raises, retry_errors=False)
calls["n"] = 0
rows4 = M.run(TMP, out_path=_ep, model="fake", model_fn=always_large)
check("a row that errored is retried on resume", calls["n"] == 6,
      "%d retried of 6; skipping them is how a file of key failures "
      "reports itself as a finished run" % calls["n"])
t4 = M.summarise(rows4)[("ex2_cam", "all")]
check("the retry replaces the failure rather than doubling the row",
      t4["n"] == 3 and t4["error"] == 0,
      "%s; the file holds both rows, the summary must hold the later one"
      % t4)
calls["n"] = 0
M.run(TMP, out_path=_ep, model="fake", model_fn=always_large)
check("once answered, those rows are not paid for again", calls["n"] == 0,
      "%d calls on the second resume" % calls["n"])

# 10: a file written by a DIFFERENT probe is refused, not resumed into.
#
# check_id is seq|view|model and carries no vocabulary, so a two-way run
# pointed at a three-way file finds every id present, makes no calls, and
# reports the old answers as new. Every id in the retired
# runs/ex2_q1_cue_*.jsonl collides exactly that way.
check("every row records the vocabulary it was asked in",
      all(r["n_options"] == len(M.ANSWERS) and r["chance_pct"] == M.CHANCE
          for r in produced),
      "a file that records only the answer cannot say what was offered")

_foreign = os.path.join(TMP, "threeway.jsonl")
with open(_foreign, "w") as fh:
    _r = dict(produced[0])
    _r.update({"true_face": "edge", "answer": "edge", "correct": True,
               "n_options": 3, "chance_pct": 100.0 / 3.0})
    fh.write(json.dumps(_r) + "\n")
try:
    M.assert_same_probe(_foreign); _refused = False
except SystemExit:
    _refused = True
check("a file from a differently-sized probe is refused", _refused,
      "resuming into it would make no calls and report its answers as new")

_legacy = os.path.join(TMP, "legacy.jsonl")
with open(_legacy, "w") as fh:
    _r = dict(produced[0])
    _r.update({"true_face": "edge", "answer": "large_face"})
    _r.pop("n_options", None); _r.pop("chance_pct", None)
    fh.write(json.dumps(_r) + "\n")
try:
    M.assert_same_probe(_legacy); _refused = False
except SystemExit:
    _refused = True
check("and so is an UNSTAMPED file that names a face off the enum",
      _refused,
      "rows written before the stamp existed are caught by their "
      "vocabulary instead: every retired three-way run says 'edge'")
try:
    M.assert_same_probe(os.path.join(TMP, "degenerate.jsonl"))
    _ok = True
except SystemExit:
    _ok = False
check("this probe's own file is accepted", _ok)
_calls = {"n": 0}


def _never(messages, timeout=None, alias=None):
    _calls["n"] += 1
    return "large_face"


try:
    M.run(TMP, out_path=_foreign, model="fake", model_fn=_never)
    _stopped = False
except SystemExit:
    _stopped = True
check("run() stops before spending anything on a foreign file",
      _stopped and _calls["n"] == 0, "%d calls made" % _calls["n"])

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
