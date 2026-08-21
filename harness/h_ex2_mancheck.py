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
  7. Rows stream to disk and a resumed run skips what is already written,
     so 88 paid calls survive a dropped connection.

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
    for seq, prim, kind in (("p01_A", "ycb_mustard_lying", "pair"),
                            ("p01_B", "ycb_mustard_upright", "pair"),
                            ("n01_A", "ycb_mustard_lying", "null")):
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
rows = M.checks(M.load_scenes(TMP))
check("one check per scene per view", len(rows) == 6, "%d rows" % len(rows))
truth = {(r["seq"], r["view"]): r["true_pose"] for r in rows}
check("true pose read from the registry entry",
      truth[("p01_A", "ex2_cam")] == "lying"
      and truth[("p01_B", "ex2_cam")] == "upright"
      and truth[("p01_B", "table_cam")] == "upright",
      str(sorted(set(truth.values()))))
check("null scenes are not dropped",
      any(r["seq"] == "n01_A" for r in rows),
      "%d null rows" % sum(1 for r in rows if r["kind"] == "null"))


# 3: grading is exact, and the prompt asks for exactly these two words.
check("bare word accepted, case and punctuation tolerated",
      M.normalise("upright") == "upright"
      and M.normalise(" Lying. ") == "lying")
check("word buried in a sentence is unparseable, not correct",
      M.normalise("It is lying down on the table") is None)
check("a third label is unparseable",
      M.normalise("tilted") is None and M.normalise("") is None)
mc = P.manipulation_check("Zm9v")
mc_text = json.dumps(mc)
check("prompt asks for the two words the grader accepts",
      "upright" in mc_text and "lying" in mc_text)
check("control carries no state, rules or allocation",
      "max_grasp_m" not in mc_text and "assignments" not in mc_text
      and "HARD RULES" not in mc_text)


# 4, 5 and 6: a degenerate answerer is caught by the per-pose split.
calls = {"n": 0}


def always_lying(messages, timeout=None, alias=None):
    calls["n"] += 1
    return "lying"


out = os.path.join(TMP, "degenerate.jsonl")
produced = M.run(TMP, out_path=out, model="fake", model_fn=always_lying)
tally = M.summarise(produced)
ex2_all = tally[("ex2_cam", "all")]
ex2_lying = tally[("ex2_cam", "lying")]
ex2_upright = tally[("ex2_cam", "upright")]
check("degenerate model looks middling overall",
      ex2_all["correct"] == 2 and ex2_all["n"] == 3)
check("per-pose split exposes it as 100 and 0",
      ex2_lying["correct"] == ex2_lying["n"] and ex2_upright["correct"] == 0)
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
again = M.run(TMP, out_path=out, model="fake", model_fn=always_lying)
check("a resumed run makes no further calls", calls["n"] == 0,
      "%d calls on resume" % calls["n"])
check("resume still summarises the whole file", len(again) == 6,
      "%d rows read back" % len(again))

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
