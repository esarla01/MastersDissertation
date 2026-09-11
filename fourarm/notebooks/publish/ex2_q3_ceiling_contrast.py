#!/usr/bin/env python3
"""Compute the dims N-ACD ceiling contrast, which notebook cell 9e prints but
does not save. Uses the pipeline's own helpers so the numbers match cell 9e
exactly; USABLE is read from the pipeline's own inventory table.

Writes tab_ex2_q3_ceiling_contrast.csv into the live Q3 tables directory.
"""
import csv, os, sys, hashlib

# The fourarm package: the directory holding runs/ and tables/. Resolved
# from this file rather than hardcoded, which pinned it to one machine.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from analysis.ex2.ex2_q_common import (load_run, keep_analysable,
                                       paired_diffs, paired_delta)
from analysis.ex2.ex2_stats import paired_mean_ci

TABLES = os.path.join(ROOT, "tables", "ex2_q3")
RUNS = os.path.join(ROOT, "runs")
MODELS = ("gpt_hi", "gemini", "claude_md")

# The positions that carry the contrast, from the pipeline's inventory table
# rather than typed here, so this cannot drift from the rest of Q3.
with open(os.path.join(TABLES, "tab_ex2_q3_inventory.csv")) as f:
    USABLE = [r["position"] for r in csv.DictReader(f)
              if r["usable"] == "True"]
assert len(USABLE) == 32, USABLE

FILES = {
    "N-ACD": os.path.join(RUNS, "ex2_q3_dims_N-ACD.jsonl"),
    "N-CD": os.path.join(RUNS, "ex2_q3_dims_N-CD.jsonl"),
    "N0": os.path.join(RUNS, "ex2_q1_dims_N0.jsonl"),
}


def rows_for(rung, model):
    r, _ = load_run(FILES[rung], "dims", MODELS)
    r = [x for x in r if x.get("rung") == rung]
    return [x for x in keep_analysable(r, USABLE) if x["model"] == model]


def diffs(rung, model):
    return paired_diffs(rows_for(rung, model), USABLE,
                        "small_face", "large_face")


def f(v):
    return "" if v != v else "%.1f" % v


out = []
for m in MODELS:
    a = diffs("N-ACD", m)
    mean, lo, hi, npos = paired_mean_ci([d for _, d in a])
    row = {"model": m, "rung": "N-ACD", "n_positions": npos,
           "contrast_pts": f(mean), "contrast_lo": f(lo), "contrast_hi": f(hi)}
    for base in ("N-CD", "N0"):
        b = diffs(base, m)
        dm, dlo, dhi, dn = paired_mean_ci(
            [d for _, d in paired_delta(a, b)])
        row["delta_vs_%s_pts" % base] = f(dm)
        row["delta_vs_%s_lo" % base] = f(dlo)
        row["delta_vs_%s_hi" % base] = f(dhi)
        row["n_positions_vs_%s" % base] = dn
    n_trials = len(rows_for("N-ACD", m))
    row["n_trials"] = n_trials
    out.append(row)
    print("%-10s N-ACD %6s [%6s, %6s]   vs N-CD %6s [%6s, %6s]   "
          "vs N0 %6s [%6s, %6s]   n=%d"
          % (m, row["contrast_pts"], row["contrast_lo"], row["contrast_hi"],
             row["delta_vs_N-CD_pts"], row["delta_vs_N-CD_lo"],
             row["delta_vs_N-CD_hi"], row["delta_vs_N0_pts"],
             row["delta_vs_N0_lo"], row["delta_vs_N0_hi"], n_trials))

cols = ["model", "rung", "n_trials", "n_positions", "contrast_pts",
        "contrast_lo", "contrast_hi",
        "n_positions_vs_N-CD", "delta_vs_N-CD_pts", "delta_vs_N-CD_lo",
        "delta_vs_N-CD_hi",
        "n_positions_vs_N0", "delta_vs_N0_pts", "delta_vs_N0_lo",
        "delta_vs_N0_hi"]
dest = os.path.join(TABLES, "tab_ex2_q3_ceiling_contrast.csv")
with open(dest, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    for r in out:
        w.writerow(r)
print("\nwrote", dest)

# Provenance for the one run file this table adds, in the same shape as
# tab_ex2_q3_provenance.csv, so the ceiling is traceable like everything else.
p = FILES["N-ACD"]
n_rows = sum(1 for l in open(p) if l.strip())
sha = hashlib.sha256(open(p, "rb").read()).hexdigest()
print("provenance  runs/%s  rows=%d  sha256=%s"
      % (os.path.basename(p), n_rows, sha))
