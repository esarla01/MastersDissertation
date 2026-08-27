"""h_ex2_cue: the minimal three-condition driver reuses the real logic,
scores each condition the right way, and cannot silently skip an error.

Imports the REAL cue module, which in turn imports the real transforms,
legality computation and grader. No live call is made: fake model functions
stand in, because a harness needing a paid endpoint could not run in the
suite.

What is pinned, and the failure each one guards:

  1. It is a DRIVER, not a second implementation. The legality sets and
     the grader come from the modules the rest of EX2 uses. A private copy
     would drift and the two would disagree without either looking wrong.
  2. legal_declared equals legal_true under congruent and dims. Computing
     it from the other pose scored correct assignments as wrong and voided
     a whole 44-trial run before it was caught.
  3. Under conflict the two sets DIFFER, otherwise there is nothing to
     follow and the condition is not doing its job.
  4. Congruent and dims are scored right or wrong; only conflict gets the
     image and state labels. There is no source to prefer when nothing
     disagrees.
  5. Nulls run congruent only, whatever conditions are asked for.
  6. width_belief is reported for conflict alone. Elsewhere the two
     numbers are identical by construction, so any verdict there is an
     artefact rather than a signal.
  7. An errored row is retried on resume rather than counted as answered.
  8. Repeats do not collide.
  9. The command line builds. A duplicate argparse registration once
     passed every other assertion and still crashed on first use.

Run:  python3 h_ex2_cue.py
"""

import argparse as _argparse
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from experiments.ex2 import cue as C                             # noqa: E402
from experiments.ex2 import grade as G                           # noqa: E402
from experiments.ex2 import run as R                             # noqa: E402
from experiments.ex2 import transforms as T                      # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


# The capture fixture is built by the run harness. Reusing it rather than
# writing a second one keeps the two drivers reading the same scenes.
_src = open(os.path.join(HERE, "h_ex2_run.py")).read()
_g = {"__name__": "fixture",
      "__file__": os.path.join(HERE, "h_ex2_run.py")}
_buf = io.StringIO()
try:
    import contextlib
    with contextlib.redirect_stdout(_buf):
        exec(compile(_src[:_src.index("# --- 3c. REMOVED")],
                     "fixture", "exec"), _g)
except Exception as exc:                                   # noqa: BLE001
    raise SystemExit("could not build the shared capture fixture from "
                     "h_ex2_run.py: %s" % exc)
CAP = _g["CAP"]
TMP = tempfile.mkdtemp()


def reply(flip_arm, opening=0.100):
    """A reply in the CURRENT schema: one task, one arm, typed fields.

    The partner argument is gone with the batch round. The prompt queues
    the flip task alone, so a reply naming two tasks would not be in
    schema and the grader would have nothing to compare it against.
    """
    return json.dumps({"task_id": 0, "arm": flip_arm, "basket": "box_1",
                       "opening_needed_m": opening})


def fixed(text):
    def _fn(messages, timeout=None, alias=None):
        return text
    return _fn


# 1. it reuses the real modules rather than reimplementing them.
check("legality comes from the shared run module",
      C.legal_arms is R.legal_arms and C.flip_task_id is R.flip_task_id,
      "a private copy would drift from the rest of EX2")
check("the grader is the shared one", C.G.grade is G.grade)
check("the conditions are the shared ones",
      set(C.CONDITIONS) == set(T.CONDITIONS))

# 2, 3. the declared legal set, per condition.
rows = C.run(CAP, out_path=os.path.join(TMP, "a.jsonl"), models=("fake",),
             kind="pair", model_fn=fixed(reply("ur_e")))
by_cond = {}
for r in rows:
    by_cond.setdefault(r["condition"], []).append(r)

for cond in ("congruent", "dims"):
    same = all(r["legal_declared"] == r["legal_true"] for r in by_cond[cond])
    check("%s: legal_declared equals legal_true" % cond, same,
          "; ".join("%s %s vs %s" % (r["seq"], r["legal_true"],
                                     r["legal_declared"])
                    for r in by_cond[cond]
                    if r["legal_declared"] != r["legal_true"])
          or "identical in every row")

differ = [r for r in by_cond["conflict"]
          if r["legal_declared"] != r["legal_true"]]
check("conflict: the two legal sets differ",
      len(differ) == len(by_cond["conflict"]),
      "%d of %d rows; if they matched there would be nothing to follow"
      % (len(differ), len(by_cond["conflict"])))
check("conflict declares the opposite pose",
      all(r["declared_pose"] != r["true_pose"] for r in by_cond["conflict"]))
check("dims declares no pose at all",
      all(r["declared_pose"] is None for r in by_cond["dims"]),
      "naming it would let the model pick the right dimension unseen")

# 4. scoring vocabulary per condition.
#
# grade() reads image-versus-state off the two legal sets. Under congruent
# and dims those sets are identical, so a legal arm can only land in
# "uninformative" and an illegal one in "illegal_both": the source labels
# are unreachable there by construction, which is the point. Only conflict
# can produce them.
_belief = {"follows_image", "follows_state"}
for cond in ("congruent", "dims"):
    check("%s cannot be scored image or state" % cond,
          all(r["outcome"] not in _belief for r in by_cond[cond]),
          "nothing disagrees, so there is no source to prefer: got %s"
          % sorted({r["outcome"] for r in by_cond[cond]}))
check("every outcome is one the single-assignment grader declares",
      all(r["outcome"] in G.OUTCOMES for r in rows),
      str(sorted({r["outcome"] for r in rows})))
check("the typed opening reaches the row",
      all(r["opening_needed_m"] == 0.100 for r in rows),
      "no extractor stands between the reply and the measurement")

# 5. nulls, whatever is asked for.
_null_rows = C.run(CAP, out_path=os.path.join(TMP, "n.jsonl"),
                   models=("fake",), kind=None,
                   conditions=C.CONDITIONS, model_fn=fixed(reply("ur_e")))
_nulls = [r for r in _null_rows if r["seq"].startswith("n")]
check("nulls run congruent only even when all conditions are asked for",
      _nulls and all(r["condition"] == "congruent" for r in _nulls),
      "%d null rows, conditions %s"
      % (len(_nulls), sorted({r["condition"] for r in _nulls})))

# 6. width_belief is a conflict-only reading.
_tbl = C.table(rows)
check("the table reports width belief under conflict",
      "width" in _tbl and "conflict" in _tbl)
_cong_wb = {r["width_belief"] for r in by_cond["congruent"]}
check("congruent width belief is a tie, never an image win",
      "image" not in _cong_wb,
      "both sources state the same number, so %s" % sorted(_cong_wb))

# 7. an errored row is retried, not treated as answered.
def _raises(messages, timeout=None, alias=None):
    raise RuntimeError("connection reset")


_ep = os.path.join(TMP, "err.jsonl")
C.run(CAP, out_path=_ep, models=("fake",), kind="pair", pair="p01",
      conditions=("congruent",), model_fn=_raises)
_calls = {"n": 0}


def _recovers(messages, timeout=None, alias=None):
    _calls["n"] += 1
    return reply("ur_e")


C.run(CAP, out_path=_ep, models=("fake",), kind="pair", pair="p01",
      conditions=("congruent",), model_fn=_recovers)
check("a row that errored is retried on resume", _calls["n"] > 0,
      "%d retried; skipping them is how a run of failed rows once "
      "re-reported itself as complete" % _calls["n"])
_calls["n"] = 0
C.run(CAP, out_path=_ep, models=("fake",), kind="pair", pair="p01",
      conditions=("congruent",), model_fn=_recovers)
check("a resumed run of good rows makes no calls", _calls["n"] == 0)

# 8. repeats are distinct trials.
_calls["n"] = 0
_rp = os.path.join(TMP, "rep.jsonl")
C.run(CAP, out_path=_rp, models=("fake",), kind="pair", pair="p01",
      conditions=("congruent",), repeats=3, model_fn=_recovers)
_seen = [json.loads(x)["trial_id"] for x in open(_rp) if x.strip()]
check("each repeat is its own trial id",
      len(set(_seen)) == len(_seen) and len(_seen) == _calls["n"],
      "%d calls, %d distinct ids" % (_calls["n"], len(set(_seen))))

# 9. the command line builds.
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
        C.main(["--dry-run", "--probes", CAP])
        _built = True
    except SystemExit as e:
        _built = e.code in (0, None)
    except _argparse.ArgumentError as e:
        _built = False
        print("   argparse rejected the CLI:", e)
finally:
    _argparse.ArgumentParser.add_argument = _orig

check("the command line parses without an argparse conflict", _built)
_dupes = {k: v for k, v in _reg.items() if v > 1}
check("no flag is registered more than once", not _dupes, str(_dupes))

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)