"""h_ex2_q_common: the notebook machinery computes the right denominators,
keeps the right rows, and refuses to spend on anything but an exact match.

Imports the REAL module. Nothing here reimplements a helper, and nothing
makes a network call or reads a run file from the tree, so the whole file is
free to run.

WHY THIS FILE EXISTS. ex2_stats.py computes numbers that are wrong in visible
ways: an interval outside 0 to 100 announces itself. This module computes
DENOMINATORS and GATES, which are wrong in invisible ones. A share taken over
trials instead of proposals is a plausible number that is quietly too low. A
spend gate that accepts a string costs money. And where Q1 had a second copy
of each rule inside a cell to disagree with, Q2 and Q3 will have none.

What is pinned, and the failure each one guards:

  1. answered() counts ANSWERS, not lines. A file of errored rows counts to
     the full sample and skips the run: that is how seven key-failure rows
     in ex2_q1_cue_gpt_r1.jsonl survived two reruns.
  2. load_run() dedupes on trial_id, filters to the models asked for, and
     REPORTS what it skipped. 136 low-effort gpt trials sat in the congruent
     file describing a model the chapter does not report.
  3. keep_analysable() drops errors, unparseables and out-of-sample
     positions and NOTHING ELSE. A decline survives: it is the wait table's
     numerator. Dropping it here would move the share table and the wait
     table together, which reads as a result.
  4. The share denominator is PROPOSALS. Three trials, one decline, one
     franka is 50 percent, not 33.
  5. share_at returns None, never 0.0, on an empty cell, so paired_mean_ci
     drops it rather than averaging in a zero that was never observed.
  6. paired_diffs pairs WITHIN position and preserves the caller's order.
     A dataset whose pooled difference is zero and whose within-position
     difference is 100 must read 100.
  7. write_csv writes CRLF. Every table in every chapter carries it, so a
     tidy-up to "\n".join would change every byte of all three notebooks'
     output at once.
  8. spend_gate proceeds on an exact int only, and refuses when the factors
     stop multiplying to it. That second check is what catches a rebound
     REPEATS at the gate rather than in a file a third the size it should be.
  9. coupling() is two-directional. The statistic it replaces asked only
     whether the arm could span the reported opening, which a UR always can.
 10. The dependency rule, enforced rather than documented.

Run:  python3 h_ex2_q_common.py
"""

import io
import json
import math
import os
import contextlib
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analysis.ex2.ex2_q_common import (           # noqa: E402
    Outputs, answered, coupling, fmt, full_flip_count, is_franka,
    keep_analysable, load_run, paired_delta, paired_diffs, pct, share_at,
    share_counts, spend_gate)
from analysis.ex2.ex2_stats import paired_mean_ci  # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


def quiet(fn, *a, **k):
    """Run something that prints, and give back only its return value."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def jsonl(rows):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def row(tid, model="gpt", seq="e00_U", face="small_face", arm="franka_n",
        **kw):
    r = {"trial_id": tid, "model": model, "seq": seq, "true_pose": face,
         "arm": arm, "outcome": "follows_image", "error": None}
    r.update(kw)
    return r


# ---------------------------------------------------------------------------
# 1. answered
# ---------------------------------------------------------------------------
p = jsonl([{"answer": "small_face", "error": None},
           {"answer": "large_face", "error": "HTTPError: 429"},
           {"outcome": "follows_image", "error": None},
           {"outcome": "unparseable", "error": None},
           {"answer": None, "outcome": None, "error": None}])
check("answered counts answers, not lines", answered(p) == 2,
      "5 lines, 2 real answers: one errored, one unparseable with no answer, "
      "one empty. A file of errored rows counting to the sample is how a "
      "rerun silently skips.")
check("answered on a missing file is 0, not an exception",
      answered(p + ".nope") == 0,
      "a spend gate has to run before the first call")
os.unlink(p)

# A retry and a re-run at a higher repeat count both append a second row for
# a trial that is already answered. Counting rows there compares a row total
# against a trial total, and the gate calls a cell complete while trials are
# still missing: ex2_q1_congruent_face_N0.jsonl reported 677 of 612 while
# holding 455 of the 612, and claude_md never got repeats 2 and 3.
p = jsonl([{"trial_id": "s1|c|m|franka|N0|V|r1", "outcome": "unparseable",
            "error": None},
           {"trial_id": "s1|c|m|franka|N0|V|r1", "outcome": "follows_image",
            "error": None},
           {"trial_id": "s1|c|m|franka|N0|V|r1", "outcome": "follows_state",
            "error": None},
           {"trial_id": "s2|c|m|franka|N0|V|r1", "outcome": "uninformative",
            "error": None}])
check("answered counts DISTINCT trials, not rows", answered(p) == 2,
      "4 lines over 2 trial ids, one of them answered three times. Counting "
      "rows would say 3 and a spend gate would stop short of the sample.")
os.unlink(p)


# ---------------------------------------------------------------------------
# 2. load_run
# ---------------------------------------------------------------------------
p = jsonl([row("t1", model="gpt_hi"),
           row("t1", model="gpt_hi", arm="ur_e"),      # same id, later wins
           row("t2", model="gpt"),                     # not in the design
           row("t3", model="gemini", seq="w05_L", face="large_face")])
rows, skipped = quiet(load_run, p, "dims", ("gpt_hi", "gemini"))
check("load_run dedupes on trial_id, last write wins",
      len(rows) == 2 and [r["arm"] for r in rows if r["trial_id"] == "t1"] == ["ur_e"],
      "reading every line once put 24 rows in a 22-scene cell")
check("load_run filters to the models asked for",
      {r["model"] for r in rows} == {"gpt_hi", "gemini"})
check("load_run reports what it skipped, per model", dict(skipped) == {"gpt": 1},
      "a model missing by accident and one excluded on purpose look the same "
      "in the output otherwise")
check("load_run derives position from seq and face from true_pose",
      sorted((r["position"], r["face"]) for r in rows)
      == [("e00", "small_face"), ("w05", "large_face")])

p2 = jsonl([row("t1", condition="conflict"), row("t2")])
rows2, _ = quiet(load_run, p2, "dims", ("gpt",))
check("a condition already on the row wins over the argument",
      sorted(r["condition"] for r in rows2) == ["conflict", "dims"])
check("load_run on a missing file returns empty, not an exception",
      quiet(load_run, p + ".nope", "dims", ("gpt",)) == ([], __import__(
          "collections").Counter()))
os.unlink(p)
os.unlink(p2)


# ---------------------------------------------------------------------------
# 3. keep_analysable
# ---------------------------------------------------------------------------
base = [dict(row("a"), position="e00"),
        dict(row("b", arm=None), position="e00", outcome="noop"),
        dict(row("c"), position="e00", error="HTTPError: 429"),
        dict(row("d"), position="e00", outcome="unparseable"),
        dict(row("e"), position="e02")]
kept = keep_analysable(base, ("e00",))
check("keep_analysable drops errors, unparseables and other positions",
      sorted(r["trial_id"] for r in kept) == ["a", "b"])
check("keep_analysable KEEPS a decline", any(r["arm"] is None for r in kept),
      "a declined row is the wait table's numerator; dropping it here would "
      "move the share table and the wait table in the same direction")


# ---------------------------------------------------------------------------
# 4 and 5. the share
# ---------------------------------------------------------------------------
cell = [row("a", arm="franka_n"), row("b", arm=None), row("c", arm="ur_e")]
check("the share denominator is proposals, not trials",
      share_counts(cell) == (1, 2) and abs(share_at(cell) - 50.0) < 1e-9,
      "three trials, one decline, one franka is 50 percent, not 33.3")
check("share_at on an all-declined cell is None, never 0.0",
      share_at([row("a", arm=None)]) is None,
      "paired_mean_ci drops a None; a 0.0 would be averaged in as a real "
      "zero difference that was never observed")
check("is_franka is a family test, not an identity",
      is_franka("franka_n") and is_franka("franka_s") and not is_franka("ur_e")
      and not is_franka(None))


# ---------------------------------------------------------------------------
# 6. paired_diffs
# ---------------------------------------------------------------------------
# Pooled over everything this is 50 against 50, a difference of zero. Within
# position it is +100 at p1 and -100 at p2. The pairing is the whole point.
mixed = [dict(row("1", arm="franka_n"), position="p1", face="small_face"),
         dict(row("2", arm="ur_e"), position="p1", face="large_face"),
         dict(row("3", arm="ur_e"), position="p2", face="small_face"),
         dict(row("4", arm="franka_n"), position="p2", face="large_face")]
got = paired_diffs(mixed, ["p1", "p2"], "small_face", "large_face")
check("paired_diffs pairs within position",
      [d for _, d in got] == [100.0, -100.0],
      "pooled this is 50 against 50, a difference of zero; the pairing is "
      "what the design bought")
check("paired_diffs preserves the caller's position order",
      [q for q, _ in paired_diffs(mixed, ["p2", "p1"], "small_face",
                                  "large_face")] == ["p2", "p1"],
      "the by-position CSV's row order is a function of USABLE, not of dict "
      "iteration order")
check("paired_diffs returns None for a position with no data",
      paired_diffs(mixed, ["p9"], "small_face", "large_face") == [("p9", None)])
_m, _lo, _hi, _n = paired_mean_ci([d for _, d in got])
check("a None position does not drag the mean toward zero",
      paired_mean_ci([100.0, None, 100.0])[0] == 100.0)

# paired_delta: the Q3 second-order quantity
A = [("p1", 100.0), ("p2", 0.0), ("p3", 50.0), ("p4", None)]
B = [("p1", 40.0), ("p2", 0.0), ("p3", None), ("p4", 10.0)]
check("paired_delta subtracts position by position",
      paired_delta(A, B) == [("p1", 60.0), ("p2", 0.0), ("p3", None),
                             ("p4", None)],
      "a position missing from EITHER side contributes nothing; treating it "
      "as a zero would pull a ladder effect toward no effect")
check("paired_delta keeps the left side's order and length",
      [q for q, _ in paired_delta(A, B)] == ["p1", "p2", "p3", "p4"])
check("paired_delta on a position absent from the right is None",
      paired_delta([("z", 1.0)], []) == [("z", None)])

sat = [100.0, 100.0, 100.0, None]
check("full_flip_count counts positions at the full flip, over those with data",
      full_flip_count(sat) == (3, 3),
      "a saturated cell has zero variance, so paired_mean_ci returns a "
      "zero-width interval that reads as impossible precision; this is the "
      "quantity to quote instead")
check("full_flip_count counts a reversal as a flip too",
      full_flip_count([100.0, -100.0, 0.0]) == (2, 3),
      "magnitude, not direction: the direction is already in the mean")


# ---------------------------------------------------------------------------
# 7. write_csv bytes
# ---------------------------------------------------------------------------
d = tempfile.mkdtemp()
out = Outputs(d, d)
quiet(out.write_csv, "t.csv", ["a", "b"], [["1", "franka, preference satisfied"]])
raw = open(os.path.join(d, "t.csv"), "rb").read()
check("write_csv terminates lines with CRLF",
      raw == b'a,b\r\n1,"franka, preference satisfied"\r\n',
      "every table in every chapter carries it: %r" % raw)
check("Outputs.rel returns a path relative to the root",
      out.rel(os.path.join(d, "x", "y.csv")) == os.path.join("x", "y.csv"))
check("Outputs.rel returns a path outside the root unchanged, not an error",
      out.rel("/nowhere/y.csv") == "/nowhere/y.csv",
      "a cell can legitimately be pointed at a scratch directory and a "
      "provenance table must not fall over")


# ---------------------------------------------------------------------------
# 8. spend_gate. This is the money.
# ---------------------------------------------------------------------------
check("spend_gate proceeds on an exact int", quiet(spend_gate, 180, 180) is True)
check("spend_gate refuses None", quiet(spend_gate, 180, None) is False)
check("spend_gate refuses off by one",
      not quiet(spend_gate, 180, 179) and not quiet(spend_gate, 180, 181))
check("spend_gate refuses the STRING form",
      quiet(spend_gate, 180, "180") is False,
      "a pasted number is still not a confirmation")
check("spend_gate refuses a bool", quiet(spend_gate, 1, True) is False,
      "True == 1 in Python, so an exact type check is what refuses it")
full = jsonl([{"answer": "x", "error": None}] * 5)
check("spend_gate refuses when the file already holds the whole sample",
      quiet(spend_gate, 5, 5, full) is False)
check("spend_gate proceeds when the file is short",
      quiet(spend_gate, 6, 6, full) is True)
os.unlink(full)

_raised = False
try:
    quiet(spend_gate, 612, 612,
          factors=(("scenes", 68), ("models", 3), ("repeats", 1)))
except AssertionError:
    _raised = True
check("spend_gate refuses when the factors do not multiply to the total",
      _raised,
      "68 x 3 x 1 is 204, not 612. This is the rebound-REPEATS failure, "
      "caught at the gate instead of in a file a third the size")
check("spend_gate accepts factors that do multiply",
      quiet(spend_gate, 612, 612,
            factors=(("scenes", 68), ("models", 3), ("repeats", 3))) is True)


# ---------------------------------------------------------------------------
# 9. coupling, the corrected statistic
# ---------------------------------------------------------------------------
FRANKA_MAX = 0.080
# The failure the old statistic could not see: a model that reports the
# narrow opening and then names the wide arm anyway. Under "can the arm span
# it" every one of these passed.
cautious = [row("a", arm="ur_e", opening_needed_m=0.050) for _ in range(4)]
agree, n, over_reach, over_cautious = coupling(cautious, FRANKA_MAX)
check("coupling counts an over-cautious reply as a disagreement",
      (agree, n, over_reach, over_cautious) == (0, 4, 0, 4),
      "the old statistic scored these 4 of 4 agreeing, because a UR spans "
      "everything, which is why it read 100 percent everywhere")
reach = [row("a", arm="franka_n", opening_needed_m=0.100)]
check("coupling counts an over-reaching reply, in the other direction",
      coupling(reach, FRANKA_MAX) == (0, 1, 1, 0),
      "said wide, chose an arm that cannot close on it")
good = [row("a", arm="franka_n", opening_needed_m=0.050),
        row("b", arm="ur_e", opening_needed_m=0.100)]
check("coupling counts agreement in both directions",
      coupling(good, FRANKA_MAX) == (2, 2, 0, 0))
check("coupling ignores a row with no arm or no opening",
      coupling([row("a", arm=None, opening_needed_m=0.05),
                row("b", opening_needed_m=None)], FRANKA_MAX)[1] == 0,
      "there is nothing to couple")


# ---------------------------------------------------------------------------
# 10. formatting, which is CSV bytes
# ---------------------------------------------------------------------------
check("fmt renders None and NaN as NA, never as 0.0",
      fmt(None) == "NA" and fmt(float("nan")) == "NA")
check("fmt is exactly %.1f",
      (fmt(94.45), fmt(0.0), fmt(100.0), fmt(-12.34)) ==
      ("94.5" if "%.1f" % 94.45 == "94.5" else "%.1f" % 94.45,
       "0.0", "100.0", "-12.3"),
      "these strings are CSV bytes")
check("pct on an empty cell is NaN, not 0.0", math.isnan(pct(0, 0)),
      "a cell with no observations is not a confident zero, and one printed "
      "as 0.0 has been read as a finding before")
check("pct is the plain percentage", pct(1, 2) == 50.0)


# ---------------------------------------------------------------------------
# 11. the dependency rule, enforced rather than documented
# ---------------------------------------------------------------------------
probe = ("import sys; sys.path.insert(0, %r);"
         "import analysis.ex2.ex2_q_common;"
         "bad=[m for m in sys.modules if m.split('.')[0] in "
         "('experiments','core','numpy','pandas','ycb_objects') "
         "or m.startswith('notebooks')];"
         "print(sorted(bad))" % ROOT)
res = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                     text=True)
check("the module imports with only the project root on sys.path",
      res.returncode == 0, res.stderr.strip()[-200:])
check("it pulls in no experiments, core, notebooks, numpy or pandas",
      res.stdout.strip() == "[]", res.stdout.strip(),)


print("\nRESULT: " + ("ALL PASS" if not fails
                      else "%d FAILURE(S): %s" % (len(fails), fails)))
sys.exit(1 if fails else 0)
