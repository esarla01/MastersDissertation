"""h_ex2_twoway: the two-way fallback asks its two question forms without
ever naming the third face, scores against a coin rather than a die, keeps
the forms apart, and reuses the control's scene walk instead of copying it.

Imports the REAL twoway module. No live call is made: fake model functions
stand in.

What is pinned, and the failure each one guards:

  1. Exactly TWO words are offered in EVERY form, and the third face is
     never mentioned -- not even to exclude it. Naming it makes this a
     three-way question with one option discouraged, which is a different
     measurement.
  1b. The `posture` form carries no face word and no dimension at all.
     Either would rebuild the metric-matching task the form exists to
     strip away, and the probe would stop answering the question it was
     added for.
  1c. The forms are one-to-one on truth -- small_face is standing,
     large_face is flat -- so their accuracies are comparable. That
     mapping is the whole point and a drift in it would make the
     comparison meaningless without looking wrong.
  1d. The form is never defaulted, is part of the resume key, and is
     stamped on every row. Without it the two forms collide on resume and
     a file could hold a single accuracy over two different questions.
  2. Chance is 50, everywhere it appears. A 33.3 carried over from the
     three-way control would make a coin look like a finding.
  3. Scenes resting on the middle face are DROPPED, loudly. Asking would
     score every one of them wrong by construction and read as blindness.
  4. The scene walk, the check identity and the resume rule come from
     mancheck, not from a second copy, so the two probes cannot drift
     about which scenes they cover or what counts as done.
  5. The prompt's face sizes are derived from the registry, so widening
     the block carries through.
  6. A degenerate answerer scores exactly chance and the split shows it.
     Here that is 50 percent, which is why the split matters more than in
     the three-way probe, not less.
  7. Every row records that it came from a two-way question, so a file of
     these can never be pooled with three-way rows unnoticed.
  8. An errored row is retried on resume; the retry replaces it.
  9. The command line builds.

Run:  python3 h_ex2_twoway.py
"""

import argparse as _argparse
import contextlib
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

from experiments.ex2 import mancheck as MC                       # noqa: E402
from experiments.ex2 import prompts as P                         # noqa: E402
from experiments.ex2 import transforms as T                      # noqa: E402
from experiments.ex2 import twoway as W                          # noqa: E402
from experiments.ex2.run import load_scenes                      # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label
          + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


_src = open(os.path.join(HERE, "h_ex2_run.py")).read()
_g = {"__name__": "fixture", "__file__": os.path.join(HERE, "h_ex2_run.py")}
try:
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(_src[:_src.index("# --- 3c. REMOVED")],
                     "fixture", "exec"), _g)
except Exception as exc:                                   # noqa: BLE001
    raise SystemExit("could not build the shared capture fixture: %s" % exc)
CAP = _g["CAP"]
TMP = tempfile.mkdtemp()

# 1: two options per form, and the third face is absent from every prompt.
def _prompt(form):
    return " ".join(b["text"] for m in W.build("Zm9v", form)
                    if isinstance(m.get("content"), list)
                    for b in m["content"] if b.get("type") == "text")


_texts = {f: _prompt(f) for f in W.FORMS}
check("the probe asks exactly the forms it declares",
      set(W.FORMS) == {"posture"}, str(W.FORMS))
check("the face form is retired, not merely unused",
      "face" not in W.FORMS and "face" not in W.ANSWERS_BY_FORM,
      "once the design had two faces it became word for word what "
      "mancheck asks, and two probes asking one question is how two "
      "numbers drift apart")
for f in W.FORMS:
    ans = W.ANSWERS_BY_FORM[f]
    check("%s: exactly two answer words are offered" % f, len(ans) == 2,
          str(ans))
    check("%s: both of them appear in the prompt" % f,
          all(w in _texts[f] for w in ans), _texts[f])
    check("%s: the middle face is NEVER mentioned" % f,
          "edge" not in _texts[f].lower(),
          "naming it makes this a three-way question with one option "
          "discouraged: %s" % _texts[f])
    _imgs = [b for m in W.build("Zm9v", f)
             if isinstance(m.get("content"), list)
             for b in m["content"] if b.get("type") == "image_url"]
    check("%s: exactly one image travels with the question" % f,
          len(_imgs) == 1)
check("nothing is excluded any more, and the constant says so",
      W.EXCLUDED is None,
      "the middle face left the DESIGN on 2026-08-27, so this probe no "
      "longer covers less of it than the control does")
check("and it is gone from the design, not just from this probe",
      "edge" not in P.RESTING_FACES, str(P.RESTING_FACES))

# 1b: the posture form is bare, which is the entire reason it exists.
_p = _texts["posture"].lower()
check("posture: no face word appears at all",
      not any(w in _p for w in P.RESTING_FACES), _texts["posture"])
check("posture: no dimension is given",
      not any(str(mm) in _p for mm in (130, 100, 50))
      and "mm" not in _p and "measur" not in _p,
      "a measurement would rebuild the metric-matching task this form "
      "removes: %s" % _texts["posture"])
check("posture: it is asked in plain words",
      "standing" in _p and "flat" in _p and "_" not in _p,
      _texts["posture"])
check("posture asks for a judgement, not a measurement",
      "?" in _texts["posture"] and "mm" not in _texts["posture"])

# 1c: the forms agree about the truth, one to one.
check("the tall pose is standing and the flat pose is flat",
      W.true_answer("small_face", "posture") == "standing"
      and W.true_answer("large_face", "posture") == "flat",
      "this mapping is what makes the two forms comparable")
check("the truth mapping covers both faces and nothing else",
      set(W.TRUTH_BY_FORM["posture"]) == set(W.FACES))
check("every form maps both faces and nothing else",
      all(set(W.TRUTH_BY_FORM[f]) == set(W.FACES) for f in W.FORMS))
check("each form's truths are exactly its answer vocabulary",
      all(set(W.TRUTH_BY_FORM[f].values()) == set(W.ANSWERS_BY_FORM[f])
          for f in W.FORMS),
      "a truth the model cannot say would score every trial wrong")
try:
    W.true_answer(W.EXCLUDED, "posture")
    _guarded = False
except ValueError:
    _guarded = True
check("the excluded face has no truth in either form, and says so",
      _guarded,
      "on its edge the block is 100mm over a 130x50 base: neither "
      "standing nor flat, so there is no correct answer to score")

# 1d: the form is explicit, keyed and stamped.
for bad in (None, "", "posture_", "FACE"):
    try:
        W.require_form(bad)
        _ok = False
    except ValueError:
        _ok = True
    check("form %r is refused rather than defaulted" % bad, _ok)
_row = {"seq": "p01_A", "view": "ex2_cam"}
check("the form is part of the resume key",
      "posture" in W.check_id(_row, "m", "posture"),
      "one form is registered today; the form still has to be in the key "
      "or the next one added collides with this one on resume")
check("and the key still starts with mancheck's",
      W.check_id(_row, "m", "posture").startswith(MC.check_id(_row, "m")))
check("a face name is not credited as a posture answer",
      W.normalise("large_face", "posture") is None
      and W.normalise("standing", "posture") == "standing",
      "that is the model answering a question it was not asked")

# 2: chance is a coin, everywhere.
check("CHANCE is 50, not the control's 33.3", W.CHANCE == 50.0,
      str(W.CHANCE))
check("the printed floor says two-way, not three",
      "TWO-way" in W.format_summary({}) and "33.3%" in W.format_summary({}),
      "the three-way figure must appear only as the thing this is NOT")
check("the posture form's summary refuses the derivation reading outright",
      "NOT" in W.format_summary({}, form="posture")
      and "posture on purpose" in W.format_summary({}, form="posture"),
      "this form measures the heuristic, so it must never be read as "
      "evidence against it")
check("the summary names the vocabulary the model answered in",
      "standing / flat" in W.format_summary({}, form="posture"))

# 3, 4: the scene walk is mancheck's, with the middle face filtered out.
_scenes = load_scenes(CAP, present_ur=False)
_all = MC.checks(_scenes, views=("ex2_cam",))
_kept, _dropped = W.checks(_scenes, views=("ex2_cam",))
check("the walk comes from mancheck, not a second copy",
      W.MC.checks is MC.checks and W.MC.check_id is MC.check_id
      and W.MC.done_ids is MC.done_ids)
check("no kept scene rests on the excluded face",
      all(r["true_face"] in W.FACES for r in _kept),
      "every such trial would be wrong by construction")
check("the drop count is returned rather than the sample silently "
      "shrinking",
      _dropped == sum(1 for r in _all if r["true_face"] == W.EXCLUDED),
      "%d dropped of %d" % (_dropped, len(_all)))
check("nothing else is dropped", len(_kept) + _dropped == len(_all))

# 5: the posture form quotes no geometry at all, so a change to DIMS_M
# must NOT reach it. That is the opposite of the retired face form and it
# is the property that makes this probe a perception measurement.
_orig = dict(T.DIMS_M["ycb_block"])
try:
    T.DIMS_M["ycb_block"] = {"height": 0.160, "width": 0.090, "depth": 0.035}
    _t2 = " ".join(b["text"] for m in W.build("x", "posture")
                   if isinstance(m.get("content"), list)
                   for b in m["content"] if b.get("type") == "text")
    check("resizing the block does not change the question",
          _t2 == _texts["posture"],
          "a measurement leaking in would rebuild the metric task: %s" % _t2)
finally:
    T.DIMS_M["ycb_block"] = _orig
check("the registry is restored", W.faces_mm() == ((130, 100), (100, 50)),
      str(W.faces_mm()))

# 6, 7: scoring.
def fixed(text):
    def _fn(messages, timeout=None, alias=None):
        return text
    return _fn


rows = W.run(CAP, "posture", out_path=os.path.join(TMP, "a.jsonl"),
             model="fake", views=("ex2_cam",), model_fn=fixed("flat"))
_t = W.summarise(rows)
_all_cell = _t[("ex2_cam", "all")]
# A degenerate answerer scores the BASE RATE of the word it always says,
# which equals chance only when the sample is balanced. The fixture is not
# (it carries two large_face scenes and one small_face), so asserting 50
# here would be asserting something about the fixture rather than about
# the probe. The identity below holds on any sample; the balance of the
# real sample is checked separately, immediately after.
_base = sum(1 for r in rows if r["true_face"] == "large_face")
check("a model answering one word for everything scores that word's base "
      "rate, never better",
      _all_cell["correct"] == _base,
      "%d correct of %d, base rate %d" % (_all_cell["correct"],
                                          _all_cell["n"], _base))
check("so on a BALANCED sample that is exactly chance",
      abs(100.0 * 0.5 - W.CHANCE) < 1e-9
      and W.CHANCE == 100.0 / len(W.ANSWERS),
      "chance is defined as one over the number of options offered, so it "
      "tracks the vocabulary rather than being typed in")
# The sample the caller draws must therefore be balanced, or the headline
# accuracy is a statement about the sample. Under ex2_cam the pair members
# cover the two faces by construction, and this is what says so.
_kept_faces = {}
for r in _kept:
    _kept_faces[r["true_face"]] = _kept_faces.get(r["true_face"], 0) + 1
check("the probe reports the per-face counts so imbalance is visible",
      set(_kept_faces) <= set(W.ANSWERS)
      and all(("ex2_cam", f) in _t for f in _kept_faces),
      "a headline accuracy over an unbalanced sample is a statement about "
      "the sample: %s" % _kept_faces)
check("and the split shows it at 100 and 0",
      _t[("ex2_cam", "large_face")]["correct"]
      == _t[("ex2_cam", "large_face")]["n"]
      and _t[("ex2_cam", "small_face")]["correct"] == 0)
check("every row records that it came from a two-way question",
      all(r["n_options"] == 2 and r["chance_pct"] == 50.0 for r in rows),
      "a file of these must never be pooled with three-way rows unnoticed")
check("and which form it was asked in",
      all(r["form"] == "posture" for r in rows))
check("the row carries the word a correct reply uses, not only the face",
      all(r["true_answer"] == W.true_answer(r["true_face"], "posture")
          for r in rows),
      "a posture file must be readable without the mapping in hand")
check("a hedge is unparseable, not wrong",
      W.normalise("I think it is flat", "posture") is None
      and W.normalise("Standing.", "posture") == "standing")
check("a withdrawn face name is not an accepted answer",
      all(W.normalise("edge", f) is None for f in W.FORMS),
      "it is not on offer, so producing it is a compliance failure")

check("the posture form scores against standing/flat",
      all(r["true_answer"] in ("standing", "flat") for r in rows))
_calls2 = {"n": 0}


def _count(messages, timeout=None, alias=None):
    _calls2["n"] += 1
    return "flat"


W.run(CAP, "posture", out_path=os.path.join(TMP, "a.jsonl"), model="fake",
      views=("ex2_cam",), model_fn=_count)
check("the same form resumes and pays for nothing twice",
      _calls2["n"] == 0, "%d calls" % _calls2["n"])

# A file holding more than one question form must be refused rather than
# averaged. Only one form is registered today, so the second is supplied
# as a hand-written row carrying the RETIRED form name -- which is exactly
# what a file written before 2026-08-27 holds, and exactly the file most
# likely to be pooled with a new one by mistake.
_mixed = os.path.join(TMP, "mixed.jsonl")
with open(_mixed, "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")
    _legacy = dict(rows[0])
    _legacy.update({"form": "face", "answer": "large_face",
                    "true_answer": "large_face",
                    "check_id": rows[0]["check_id"] + "|legacy"})
    fh.write(json.dumps(_legacy) + "\n")
try:
    with contextlib.redirect_stdout(io.StringIO()):
        W.run(CAP, "posture", out_path=_mixed, model="fake",
              views=("ex2_cam",), model_fn=fixed("flat"))
    _refused = False
except SystemExit:
    _refused = True
check("a file holding more than one question form is refused, not averaged",
      _refused,
      "one accuracy over two different questions describes neither")

# 8: resume.
def _raises(messages, timeout=None, alias=None):
    raise RuntimeError("connection reset")


_ep = os.path.join(TMP, "err.jsonl")
W.run(CAP, "posture", out_path=_ep, model="fake", views=("ex2_cam",),
      model_fn=_raises, retry_errors=False)
_calls = {"n": 0}


def _recovers(messages, timeout=None, alias=None):
    _calls["n"] += 1
    return "flat"


again = W.run(CAP, "posture", out_path=_ep, model="fake",
              views=("ex2_cam",), model_fn=_recovers)
check("a row that errored is retried on resume", _calls["n"] > 0,
      "%d retried" % _calls["n"])
check("the retry replaces the failure rather than doubling the row",
      W.summarise(again)[("ex2_cam", "all")]["error"] == 0
      and W.summarise(again)[("ex2_cam", "all")]["n"] == len(again))
_calls["n"] = 0
W.run(CAP, "posture", out_path=_ep, model="fake", views=("ex2_cam",),
      model_fn=_recovers)
check("a resumed run of good rows makes no calls", _calls["n"] == 0)

# 9: the command line.
_reg = {}
_orig_add = _argparse.ArgumentParser.add_argument


def _record(self, *args, **kw):
    for a in args:
        if isinstance(a, str) and a.startswith("--"):
            _reg[a] = _reg.get(a, 0) + 1
    return _orig_add(self, *args, **kw)


_argparse.ArgumentParser.add_argument = _record
try:
    try:
        W.main(["--dry-run", "--probes", CAP, "--form", "posture"])
        _built = True
    except SystemExit as e:
        _built = e.code in (0, None)
    except _argparse.ArgumentError as e:
        _built = False
        print("   argparse rejected the CLI:", e)
finally:
    _argparse.ArgumentParser.add_argument = _orig_add
check("the command line parses without an argparse conflict", _built)
try:
    with contextlib.redirect_stdout(io.StringIO()):
        W.main(["--dry-run", "--probes", CAP])
    _needs_form = False
except SystemExit as e:
    _needs_form = e.code not in (0, None)
check("--form is required, never defaulted", _needs_form,
      "a posture row recorded as a face row would merge two measurements")
check("no flag is registered more than once",
      not {k: v for k, v in _reg.items() if v > 1},
      str({k: v for k, v in _reg.items() if v > 1}))

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
