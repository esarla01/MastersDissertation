"""Notebook machinery for the EX2 question notebooks, in one place.

WHY THIS EXISTS. Q1's notebook grew its own loaders, its own share
definition, its own paired-contrast loop and its own spend gate, all as cell
source. Cell 15 then needed the same three exclusion rules as cell 8 and got
them as a comment promising the two copies agreed. Q2 and Q3 would each have
made a third and a fourth copy. A helper written inside a cell cannot be
imported, cannot be tested, and drifts from its twin silently.

These are not estimators. ex2_stats.py holds those, and its reasoning about
which interval belongs where still applies. What lives here is the plumbing
around them: what counts as an answer, what counts as a proposal, which rows
are analysable, and what stands between a keystroke and a paid run.

WHAT IS DELIBERATELY NOT HERE. Anything that is a decision rather than
machinery stays in the notebook cell that makes it: the model set, the rung,
the conditions, the usable-position rule, each spending cell's own cost
arithmetic and its CONFIRM_SPEND line, every verdict tree, and the figure
builder. A reader of the notebook must be able to see what it chose.

DEPENDENCY RULE, enforced by harness/h_ex2_q_common.py rather than trusted.
This module imports the standard library and its sibling ex2_stats, and
nothing else: not experiments.*, not core.*, not anything under notebooks/.
A helper that needs the arm registry stays in the cell or takes the number
it needs as an argument. That is why is_franka is a string test and why
coupling() is told the aperture instead of reading it. The rule keeps the
module importable with only the project root on sys.path, and keeps numpy
out of the analysis path.

Cell 1's sys.modules purge already covers the "analysis.ex2" prefix, so
editing this file and re-running cell 1 picks up the change.

Usage:
    from analysis.ex2.ex2_q_common import (Outputs, answered, load_run,
                                           keep_analysable, share_at)
"""

import csv
import collections
import hashlib
import json
import math
import pathlib


# ---------------------------------------------------------------------------
# Output paths. One object rather than two module globals, so a notebook
# cannot end up with a root and a tables directory that disagree.
# ---------------------------------------------------------------------------

class Outputs:
    """Where a notebook writes, and what it calls its paths in print.

    Constructed once in cell 1 and rebound to bare names:

        OUT = Outputs(ROOT, TABLES, FIGURES)
        rel, write_csv = OUT.rel, OUT.write_csv

    so every call site downstream reads exactly as it did when these were
    closures over notebook globals.
    """

    def __init__(self, root, tables, figures=None):
        self.root = pathlib.Path(root)
        self.tables = pathlib.Path(tables)
        self.figures = None if figures is None else pathlib.Path(figures)

    def rel(self, path):
        """A path relative to the root when it is under it, else as given.

        Output can legitimately sit outside the tree when a cell is
        re-pointed at a scratch directory, and a provenance table must not
        fall over."""
        try:
            return str(pathlib.Path(path).relative_to(self.root))
        except ValueError:
            return str(path)

    def write_csv(self, name, header, rows, dest=None):
        """Write a tidy CSV and return its path. Overwriting a TABLE is
        safe; only run files are protected.

        csv.writer's default dialect terminates lines with CRLF, and every
        table in every chapter carries it. Rewriting this as "\\n".join
        would change every byte of every table at once, which is why the
        harness pins the bytes rather than the rows.
        """
        path = (self.tables if dest is None else pathlib.Path(dest)) / name
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        print("wrote %s  (%d rows)" % (self.rel(path), len(rows)))
        return path


# ---------------------------------------------------------------------------
# Reading run files
# ---------------------------------------------------------------------------

def answered(path):
    """How many rows in a run file are real ANSWERS.

    Not lines. A row that errored is a call that never landed, and a file
    of them counts to the full sample and skips the run: that is how the
    seven key-failure rows in ex2_q1_cue_gpt_r1.jsonl survived two reruns.
    An unparseable reply IS an answer for this purpose -- it is a real
    observation about the model and re-asking would be re-asking until the
    model complies -- except in the allocation runners, which record it as
    a trial that produced nothing and retry it themselves.

    Handles both reply shapes so the same guard works in every spending
    cell: the perception probes carry "answer", the allocation runners
    carry "outcome"."""
    if not pathlib.Path(path).exists():
        return 0
    n = 0
    for line in open(path):
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("error") is not None:
            continue
        if r.get("answer") is None and r.get("outcome") in (None, "unparseable"):
            continue
        n += 1
    return n


def load_run(path, condition, models):
    """Rows from one run file, filtered to `models`, plus what was skipped.

    FILTERED TO MODELS, NOT DELETED FROM THE FILE. A run file accumulates:
    solo.run appends and de-duplicates on trial_id, which carries the
    model, so a file keeps every model ever run into it. That is the right
    behaviour for a record and the wrong one for a denominator. gpt at
    reasoning_effort low was in the Q1 design until 2026-08-27 and left 136
    trials in the congruent file; the analysis cells loop over MODELS and
    never saw them, but the diagnostics counted them, so they described a
    model the chapter does not report. Filtering here rather than deleting
    the rows keeps the low-effort record intact and readable.

    What is skipped is RETURNED, never dropped in silence, so the caller
    can print it: a model missing from MODELS by accident and a model
    excluded on purpose look identical in the output otherwise.

    A `condition` already on the row wins over the argument, including when
    it is None, because the row is the record and the argument is only a
    default for files written before the field existed.
    """
    if not pathlib.Path(path).exists():
        print("MISSING %s" % path)
        return [], collections.Counter()
    seen = {}
    for line in open(path):
        if line.strip():
            r = json.loads(line)
            seen[r.get("trial_id")] = r        # last write wins, as solo does
    rows, skipped = [], collections.Counter()
    for r in seen.values():
        if r.get("model") not in models:
            skipped[r.get("model")] += 1
            continue
        r["condition"] = r.get("condition", condition)
        r["position"] = r["seq"].rsplit("_", 1)[0]
        r["face"] = r["true_pose"]
        rows.append(r)
    return rows, skipped


def keep_analysable(rows, usable):
    """The three exclusions, in one place because they are applied twice.

    Drops a transport error (the call never landed), drops an unparseable
    reply (no decision to score), and restricts to the positions that carry
    the contrast. Nothing else.

    IT DOES NOT DROP A DECLINE. A row with no arm is a real decision and it
    is the numerator of the wait table; it is excluded from the Franka-share
    DENOMINATOR later, at the point where proposals are counted. Dropping it
    here would move the share table and the wait table in the same direction
    at once, which would read as a result.
    """
    return [r for r in rows if not r.get("error")
            and r.get("outcome") != "unparseable"
            and r["position"] in usable]


def run_meta(path):
    """(rows, prompt versions, models) for a run file, for provenance."""
    if not pathlib.Path(path).exists():
        return 0, "", ""
    rows = [json.loads(l) for l in open(path) if l.strip()]
    vers = sorted({r.get("ex2_prompt_version") for r in rows
                   if r.get("ex2_prompt_version")})
    mods = sorted({r.get("model") for r in rows if r.get("model")})
    return len(rows), ";".join(vers), ";".join(mods)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance_row(role, path, out, *, today, default_version,
                   model_string=None):
    """One row of a provenance table: role, path, rows, hash, version.

    `today` is REQUIRED and never read from the clock inside this function.
    The provenance table is the trail from a number in the chapter back to
    the file it came from, and a table that changes when nothing changed
    cannot be diffed, cannot be regenerated, and cannot be checked by a
    reader a month later.
    """
    p = pathlib.Path(path)
    if not p.exists():
        return [role, out.rel(p), 0, "MISSING", "", "", today]
    n, vers, mods = run_meta(p)
    return [role, out.rel(p), n, sha256(p), vers or default_version,
            mods if model_string is None else model_string, today]


# ---------------------------------------------------------------------------
# The endpoint: who was proposed, and how often
# ---------------------------------------------------------------------------

def is_franka(arm):
    """Is this arm a Franka. A string test on purpose: see the dependency
    rule in the module docstring."""
    return bool(arm) and arm.startswith("franka")


def is_ur(arm):
    return bool(arm) and arm.startswith("ur")


def share_counts(rows, pick=is_franka):
    """(k, n) where n is PROPOSALS, not trials.

    A declined trial is not a proposal and is not in the denominator. Three
    trials with one decline and one Franka is 50 percent, not 33.
    """
    props = [r for r in rows if r.get("arm")]
    return sum(1 for r in props if pick(r["arm"])), len(props)


def share_at(rows, pick=is_franka):
    """Percentage of proposals naming the picked arm family, or None.

    None rather than 0.0 when nothing was proposed. A cell where every
    trial declined has no share, and a 0.0 there would be averaged in as a
    real zero by whatever consumes it.
    """
    k, n = share_counts(rows, pick)
    return None if not n else 100.0 * k / n


def paired_diffs(rows, positions, face_a, face_b, pick=is_franka):
    """[(position, diff or None)] in the order of `positions`.

    PAIRED WITHIN POSITION. The unit of analysis is the position, so the
    difference is taken inside a position and the positions are then
    averaged. Pooling first would throw the pairing away and answer a
    different question with a wider interval.

    Returning pairs rather than a bare list is what lets one walk feed both
    the by-position table and the interval, in one order, so the two cannot
    disagree about which position is which.
    """
    out = []
    for pos in positions:
        at = [r for r in rows if r["position"] == pos]
        sa = share_at([r for r in at if r["face"] == face_a], pick)
        sb = share_at([r for r in at if r["face"] == face_b], pick)
        out.append((pos, None if (sa is None or sb is None) else sa - sb))
    return out


def paired_delta(pairs_a, pairs_b):
    """Position-wise a - b over two paired_diffs results.

    The Q3 quantity: how much a rung moved the contrast, relative to the
    same model's N0 contrast at the same positions. It is a difference of
    paired differences, so it stays paired at BOTH levels -- the position is
    still the unit, and a position missing from either side contributes
    nothing rather than being treated as a zero.

    Second-order quantities are wide. At 32 positions the interval on one of
    these is roughly 30 points whatever the data, so a cell must say in
    advance that small ladder effects are not resolvable rather than report
    a wide interval and let a reader infer a null from it.
    """
    b = dict(pairs_b)
    out = []
    for pos, da in pairs_a:
        db = b.get(pos)
        out.append((pos, None if (da is None or db is None) else da - db))
    return out


def full_flip_count(diffs, magnitude=100.0, tol=1e-9):
    """(k, n) positions showing the complete flip, over positions with data.

    WHY THIS EXISTS. When every position gives the same difference the
    standard deviation is zero and paired_mean_ci returns a ZERO-WIDTH
    interval. That is a degeneracy of the t interval on a saturated cell,
    not precision, and printed as "+100.0 [100.0, 100.0]" it reads as a
    certainty no sample of 32 can support. The honest quantity is the count
    of positions that flipped, with a Wilson interval on it.

    Report this alongside the mean whenever the interval collapses.
    """
    have = [d for d in diffs if d is not None]
    return (sum(1 for d in have if abs(abs(d) - magnitude) <= tol), len(have))


# ---------------------------------------------------------------------------
# The corrected coupling statistic
# ---------------------------------------------------------------------------

def coupling(rows, franka_max, tol=1e-9):
    """Does the arm named agree with the opening reported, BOTH ways.

    WHAT WAS WRONG WITH THE OLD ONE. It asked only whether the named arm
    could span the reported opening. A UR opens to 0.140 and every opening
    in this design is 0.050 or 0.100, so every reply naming a UR passed
    automatically and only Franka choices were ever tested. It read 100
    percent everywhere, and a statistic at ceiling whenever the safe arm is
    chosen cannot tell "the arm follows the report" from "the model always
    picks the wide arm".

    Agreement is two-directional. An opening at or below the Franka
    aperture should give a Franka, because a Franka is what the preference
    asks for and it fits. An opening above it must give a UR. So there are
    two ways to disagree and they mean different things:

      over_reach   said wide, chose a Franka. The arm cannot close on the
                   opening the model itself reported. This is
                   grade.self_contradicted, arithmetic rather than
                   judgement.
      over_cautious said narrow, chose a UR. Nothing was violated, but the
                   arm does not follow the report either: the model
                   reported an opening a Franka fits and did not use one.
                   Nothing counted this before.

    Returns (agree, n, over_reach, over_cautious) over replies that named an
    arm AND reported an opening. Rows missing either are not counted, since
    there is nothing to couple.

    `franka_max` is passed in rather than read from the arm registry: see
    the dependency rule in the module docstring.
    """
    agree = over_reach = over_cautious = 0
    n = 0
    for r in rows:
        arm, op = r.get("arm"), r.get("opening_needed_m")
        if not arm or op is None:
            continue
        n += 1
        fits_franka = op <= franka_max + tol
        if fits_franka and is_franka(arm):
            agree += 1
        elif not fits_franka and not is_franka(arm):
            agree += 1
        elif not fits_franka and is_franka(arm):
            over_reach += 1
        else:
            over_cautious += 1
    return agree, n, over_reach, over_cautious


# ---------------------------------------------------------------------------
# Spending
# ---------------------------------------------------------------------------

def spend_gate(n_calls, confirm, out_path=None, factors=None):
    """Print the cost, and say whether the cell may proceed.

    Returns True only when `confirm` is exactly the integer `n_calls`. A
    string, a float, a None and an off-by-one all refuse, because this
    function is the only thing between a stray keystroke and a paid run.

    `factors` is a sequence of (name, count) whose product must equal
    n_calls. It catches the failure where a later cell rebinds REPEATS and
    the cost arithmetic silently describes a smaller run than the design
    asks for: caught at the gate rather than discovered afterwards in a
    file that is a third the size it should be.
    """
    if factors:
        product = 1
        for _, count in factors:
            product *= count
        if product != n_calls:
            raise AssertionError(
                "the cost does not multiply: %s = %d, but n_calls is %d. "
                "Something has rebound one of these since it was set."
                % (" x ".join("%s %d" % (k, v) for k, v in factors),
                   product, n_calls))
    have = None
    if out_path is not None:
        have = answered(out_path)
        print("already answered: %d of %d in %s"
              % (have, n_calls, pathlib.Path(out_path).name))
    print("set CONFIRM_SPEND = %d in this cell to proceed" % n_calls)
    if type(confirm) is not int or confirm != n_calls:
        print("\nnot confirmed; no calls made.")
        return False
    if have is not None and have >= n_calls:
        print("\ncomplete already; nothing to do.")
        return False
    return True


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def pct(k, n):
    """100 k / n, or NaN when the cell is empty.

    NaN rather than 0.0, for the reason wilson() returns NaN at n = 0: a
    cell with no observations is not a confident zero, and one printed as
    0.0 has been read as a finding before.
    """
    return float("nan") if not n else 100.0 * k / n


def fmt(x, spec="%.1f", na="NA"):
    """Format a number for a table, rendering None and NaN as "NA"."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return na
    return spec % x


def show(header, rows):
    """Print a table without pandas, which is not installed everywhere."""
    cols = [str(h) for h in header]
    data = [[("" if c is None else str(c)) for c in r] for r in rows]
    w = [max(len(cols[i]), *(len(r[i]) for r in data)) if data else len(cols[i])
         for i in range(len(cols))]
    print("  ".join(c.ljust(w[i]) for i, c in enumerate(cols)))
    print("  ".join("-" * w[i] for i in range(len(cols))))
    for r in data:
        print("  ".join(r[i].ljust(w[i]) for i in range(len(cols))))
