"""h_ex2_heightcheck: the height probe asks for a number, names no face,
derives its truth from the registry, and separates a perception failure
from a naming one.

Imports the REAL heightcheck module. No live call is made: fake model
functions stand in, because a harness needing a paid endpoint could not
run in the suite.

What is pinned, and the failure each one guards:

  1. NO face word appears in the prompt. The naming step is the thing
     under test, so one leaked face word would put it back and the probe
     would measure nothing mancheck does not already measure.
  2. The three edge lengths DO appear. Nothing in the render carries a
     metric scale, so without them the reply is unscorable and the probe
     would be asking whether a model can guess absolute size from a
     picture of a table.
  3. Truth is DERIVED from the registry, not tabulated. Widening the gap
     between the three heights is an open fix; a hardcoded 130/100/50
     would score the new renders against the old block and look right.
  4. A reply in metres is converted, not discarded. 0.10 is a correct
     perception in the wrong unit and counting it unparseable would file
     a compliance slip as a perception failure.
  5. An ambiguous reply IS unparseable. Two numbers means the grader would
     be choosing, which is the grader deciding what the model saw.
  6. The snapped score reproduces mancheck's three-way call, so the two
     probes can be read on one scale, and the raw number survives beside
     it. A snapped value is never recorded as a face the model uttered.
  7. The signed bias is reported. It is the entire reason this probe
     exists: mancheck showed every error one class flatter but could not
     say whether the model read the block short or named it wrong.
  8. ordering() answers the actual question. Means that separate the two
     flat poses mean the naming failed; means that do not mean the render
     did.
  9. An errored row is retried on resume rather than counted as answered.
 10. The command line builds.

Run:  python3 h_ex2_heightcheck.py
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

from experiments.ex2 import heightcheck as H                     # noqa: E402
from experiments.ex2 import prompts as P                         # noqa: E402
from experiments.ex2 import transforms as T                      # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label
          + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


# The capture fixture is built by the run harness, so every EX2 probe reads
# the same scenes.
_src = open(os.path.join(HERE, "h_ex2_run.py")).read()
_g = {"__name__": "fixture", "__file__": os.path.join(HERE, "h_ex2_run.py")}
try:
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(_src[:_src.index("# --- 3c. REMOVED")],
                     "fixture", "exec"), _g)
except Exception as exc:                                   # noqa: BLE001
    raise SystemExit("could not build the shared capture fixture from "
                     "h_ex2_run.py: %s" % exc)
CAP = _g["CAP"]
TMP = tempfile.mkdtemp()

# 1, 2: what the prompt does and does not contain.
_msgs = H.build("Zm9v")
_text = " ".join(b["text"] for m in _msgs if isinstance(m.get("content"), list)
                 for b in m["content"] if b.get("type") == "text")
_sys = " ".join(m["content"] for m in _msgs
                if isinstance(m.get("content"), str))
_leaked = [f for f in P.RESTING_FACES if f in (_text + _sys).lower()]
check("no face word appears anywhere in the probe", not _leaked,
      "leaked %s; the naming step is what this probe removes" % _leaked)
check("no face word in loose form either",
      not any(w in _text.lower() for w in ("largest face", "smallest face",
                                           "resting face", "which face")),
      _text)
for mm in H.edges_mm():
    check("the prompt states the %d mm edge" % mm, "%d mm" % mm in _text,
          "without a scale the number cannot be scored")
_imgs = [b for m in _msgs if isinstance(m.get("content"), list)
         for b in m["content"] if b.get("type") == "image_url"]
check("exactly one image travels with the question", len(_imgs) == 1,
      "%d image blocks" % len(_imgs))
check("the answer format asks for a number, not a word",
      "one number" in _text.lower() and "millimetre" in _text.lower())

# 3: truth is derived, so a dimension change carries through.
check("heights come from the registry",
      H.edges_mm() == sorted((round(T.DIMS_M["ycb_block"][k] * 1000)
                              for k in ("height", "width", "depth")),
                             reverse=True))
check("the tallest pose is the smallest resting face",
      H.true_height_mm("small_face") == max(H.edges_mm()),
      "%dmm; labels.py: the block STANDS on its smallest face"
      % H.true_height_mm("small_face"))
check("the flattest pose is the largest resting face",
      H.true_height_mm("large_face") == min(H.edges_mm()))
check("the heights are distinct",
      len(set(H.heights_mm())) == len(P.RESTING_FACES), str(H.heights_mm()))
check("the withdrawn middle face has no height",
      H.true_height_mm.__doc__ is not None
      and "edge" not in {f for f in P.RESTING_FACES},
      "0.100 m of vertical extent belonged to the face retired on "
      "2026-08-27; asking for it must raise, not return the middle edge")
_orig = dict(T.DIMS_M["ycb_block"])
try:
    T.DIMS_M["ycb_block"] = {"height": 0.160, "width": 0.090, "depth": 0.035}
    check("a change to DIMS_M carries through to the truth",
          H.true_height_mm("small_face") == 160
          and H.true_height_mm("large_face") == 35,
          "a hardcoded table would score the new render against the old "
          "block and look right")
    check("and through to the prompt", "160 mm" in
          " ".join(b["text"] for m in H.build("x")
                   if isinstance(m.get("content"), list)
                   for b in m["content"] if b.get("type") == "text"))
finally:
    T.DIMS_M["ycb_block"] = _orig
check("the registry is restored after that test",
      H.true_height_mm("small_face") == 130)
try:
    H.true_height_mm("upright")
    _guarded = False
except ValueError:
    _guarded = True
check("a mustard posture is refused, not silently scored", _guarded)

# 4, 5: parsing.
for text, want in (("100", 100.0), ("100mm", 100.0), ("100 mm", 100.0),
                   ("~100", 100.0), ("  130.0 ", 130.0),
                   ("about 100 mm tall", 100.0),
                   ("0.10", 100.0), ("0.13", 130.0),
                   ("100 or 130", None), ("I cannot tell", None),
                   ("0", None), (None, None)):
    got = H.normalise(text)
    check("normalise(%r) -> %s" % (text, want), got == want, "got %s" % got)

# 6: snapping reproduces the three-way call and keeps the raw number.
# The snap targets are the true heights, so these move with DIMS_M. They
# are written against H.heights_mm() rather than as literals, which is what
# stopped them pinning an arithmetic identity when the middle height left.
_lo_h, _hi_h = min(H.heights_mm()), max(H.heights_mm())
_mid = (_lo_h + _hi_h) / 2.0
check("snap goes to the nearest true height",
      (H.snap(_hi_h - 2), H.snap(_lo_h + 2)) == (_hi_h, _lo_h),
      "%s -> %s, %s -> %s" % (_hi_h - 2, H.snap(_hi_h - 2),
                              _lo_h + 2, H.snap(_lo_h + 2)))
check("a reading between classes snaps to the nearer one",
      H.snap(_mid - 10) == _lo_h and H.snap(_mid + 10) == _hi_h,
      "%s->%s %s->%s" % (_mid - 10, H.snap(_mid - 10),
                         _mid + 10, H.snap(_mid + 10)))
check("a tie snaps to the TALLER, never to the flat answer the model "
      "already favours", H.snap(_mid) == _hi_h,
      "%s->%s; with two heights the midpoint is reachable, so the "
      "tie-break is no longer hypothetical" % (_mid, H.snap(_mid)))


def fixed(text):
    def _fn(messages, timeout=None, alias=None):
        return text
    return _fn


rows = H.run(CAP, out_path=os.path.join(TMP, "a.jsonl"), model="fake",
             views=("ex2_cam",), model_fn=fixed("50"))
check("the raw number survives beside the snapped one",
      all(r["said_mm"] == 50.0 and r["snapped_mm"] == 50 for r in rows),
      "mancheck cannot report the raw reading, which is the point")
check("the implied face is derived and named as derived",
      all(r["implied_face"] == "large_face" for r in rows)
      and "implied_face" in rows[0] and "answer" not in rows[0],
      "it must not look like a face the model uttered")

# 7: the signed bias, which is the reading mancheck cannot produce.
_t = H.summarise(rows)
_tall = _t[("ex2_cam", "small_face")]
check("a model reading every block flat shows a negative bias on the "
      "tall pose",
      sum(_tall["said"]) / len(_tall["said"]) - 130 < 0,
      "mean %.0f vs true 130" % (sum(_tall["said"]) / len(_tall["said"])))
check("the summary prints the bias and the true height",
      "bias=" in H.format_summary(_t) and "true=" in H.format_summary(_t))
check("a degenerate answerer is not flattered by the split",
      _t[("ex2_cam", "small_face")]["correct"] == 0
      and _t[("ex2_cam", "large_face")]["correct"] > 0,
      "one number for everything must read as 0 on two faces and 100 on "
      "one, never as partial competence")

# 8: ordering separates a naming failure from a perception one.
#
# Driven by hand-built rows rather than by the shared capture fixture. The
# fixture is small and unbalanced, and this function's whole job is to say
# something about every face, so feeding it the fixture would leave the
# cases that matter untested.
def _rows(**said):
    """said is face -> list of reported mm."""
    return [{"view": "ex2_cam", "true_face": f, "said_mm": float(v),
             "true_height_mm": H.true_height_mm(f)}
            for f, vs in said.items() for v in vs]


_perfect = H.ordering(_rows(small_face=[130, 130], large_face=[50, 50]))
check("a model that reads height perfectly is monotone and separated",
      "reported height is monotone" in _perfect
      and "(separated)" in _perfect, _perfect)

_flat = H.ordering(_rows(small_face=[50, 50], large_face=[50, 50]))
check("a model that reads everything flat is NOT separated",
      "NOT separated" in _flat,
      "this is the verdict that says the render is short rather than the "
      "naming")

# The observed GPT pattern: tall is read short, and the two flat poses are
# read the same. The verdict must be NOT separated even though the overall
# ordering looks almost right.
_same = H.ordering(_rows(small_face=[65, 65], large_face=[65, 65]))
check("two poses read identically are NOT separated",
      "NOT separated" in _same, _same)

# A part-finished run has a face with no rows. That is a gap in the
# sample, not a break in the ordering, and calling it one reported a
# perfect reader as non-monotone.
_gap = H.ordering(_rows(small_face=[130]))
check("a face with no answers is a gap, not a break in the ordering",
      "no rows" in _gap, _gap)
check("and the missing face is named rather than passed over",
      "large_face" in _gap, _gap)
_one = H.ordering(_rows(large_face=[50]))
check("one face alone is reported as not testable",
      "not testable" in _one, _one)

# 9: an errored row is a call that never landed.
def _raises(messages, timeout=None, alias=None):
    raise RuntimeError("connection reset")


_ep = os.path.join(TMP, "err.jsonl")
H.run(CAP, out_path=_ep, model="fake", views=("ex2_cam",),
      model_fn=_raises, retry_errors=False)
_calls = {"n": 0}


def _recovers(messages, timeout=None, alias=None):
    _calls["n"] += 1
    return "100"


again = H.run(CAP, out_path=_ep, model="fake", views=("ex2_cam",),
              model_fn=_recovers)
check("a row that errored is retried on resume", _calls["n"] > 0,
      "%d retried" % _calls["n"])
check("the retry replaces the failure rather than doubling the row",
      H.summarise(again)[("ex2_cam", "all")]["error"] == 0
      and H.summarise(again)[("ex2_cam", "all")]["n"] == len(again))
_calls["n"] = 0
H.run(CAP, out_path=_ep, model="fake", views=("ex2_cam",),
      model_fn=_recovers)
check("a resumed run of good rows makes no calls", _calls["n"] == 0)

# 10: the command line builds.
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
        H.main(["--dry-run", "--probes", CAP])
        _built = True
    except SystemExit as e:
        _built = e.code in (0, None)
    except _argparse.ArgumentError as e:
        _built = False
        print("   argparse rejected the CLI:", e)
finally:
    _argparse.ArgumentParser.add_argument = _orig_add
check("the command line parses without an argparse conflict", _built)
check("no flag is registered more than once",
      not {k: v for k, v in _reg.items() if v > 1},
      str({k: v for k, v in _reg.items() if v > 1}))

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
