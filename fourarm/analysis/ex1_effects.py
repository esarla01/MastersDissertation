#!/usr/bin/env python3
"""Effect sizes and intervals for the Experiment 1 results section.

Everything ex1_report.py reports as a bare percentage, reported here as a
contrast with an interval. Six blocks:

    interaction  difference of the two width gaps, the formal test behind
                 "the two removals do not interact"
    refusal      correct-refusal gaps with Newcombe intervals
    franka       Franka-share gaps, the mechanism measure
    reasons      one-sided bound on "no reason string admitted the gap"
    objects      per-object error rates with Wilson intervals
    latency      median and IQR per model and condition

Standard library only, so it is independent of ex1_report.py. Run from
fourarm/:

    python3 analysis/ex1_effects.py
    python3 analysis/ex1_effects.py --block interaction --block refusal
    python3 analysis/ex1_effects.py --csv figures/    # tidy CSV per block
"""

import argparse
import collections
import csv
import json
import math
import os
import re
import statistics
import sys

COND = ["L3", "L3anon", "L3nw", "L1nw"]
NAME = {"L3": "Full Information", "L3anon": "Anonymous",
        "L3nw": "No Width", "L1nw": "No Width + Anon."}
MODELS = ["gemini", "gpt", "qwen"]

# Opportunities per object, from the probe set. An opportunity is an open task
# whose object an idle Franka can reach but cannot grasp.
OPPORTUNITIES = {"ycb_mug": 24, "ycb_mug2": 33, "ycb_meat_can": 135,
                 "ycb_wood_block": 84, "ycb_mustard": 105,
                 "ycb_large_clamp": 138}

MISSING_INFO = re.compile(
    r"(unknown|unstated|not stated|missing|unspecified|no (?:declared )?width"
    r"|not (?:given|provided|specified|declared)|absent)", re.I)


def path(root, model, cond):
    if model == "gpt" and cond == "L1nw":
        return os.path.join(root, "out/ex1_gpt_L1nw_r3b.jsonl")
    suffix = "_r3" if cond in ("L3", "L3anon", "L3nw", "L1nw") else ""
    return os.path.join(root, "out/ex1_%s_%s%s.jsonl" % (model, cond, suffix))


def rows(p):
    with open(p) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, centre - half), 100 * min(1.0, centre + half))


def newcombe(k1, n1, k2, n2, z=1.96):
    """Group 1 minus group 2, Newcombe hybrid-score interval."""
    l1, u1 = (x / 100 for x in wilson(k1, n1, z))
    l2, u2 = (x / 100 for x in wilson(k2, n2, z))
    p1, p2 = k1 / n1, k2 / n2
    d = p1 - p2
    return (100 * d,
            100 * (d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)),
            100 * (d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)))


def legality(rs, grasp=True):
    k = n = 0
    for r in rs:
        if r.get("zero_legal") or bool(r.get("binds_grasp")) != grasp:
            continue
        if r.get("result") not in ("valid", "rejected"):
            continue
        n += 1
        k += r["result"] == "valid"
    return k, n


def refusal(rs):
    k = n = 0
    for r in rs:
        if not r.get("zero_legal"):
            continue
        n += 1
        k += r.get("result") == "noop"
    return k, n


def franka_share(rs):
    k = n = 0
    for r in rs:
        arm = (r.get("decision") or {}).get("arm")
        if not arm:
            continue
        n += 1
        k += arm.startswith("franka")
    return k, n


OUT = collections.defaultdict(list)


def emit(block, **fields):
    OUT[block].append(fields)


# ---------------------------------------------------------------------------


def b_interaction(R):
    """Does the cost of removing the width depend on whether names are there?

    The difference of two independent gaps. The interval is a normal
    approximation from each gap's Newcombe half-width, which is adequate here
    because both gaps are far from 0 and 100.
    """
    print("\ninteraction  (width gap with names) minus (width gap anonymised)")
    for m in MODELS:
        a, b = legality(R[(m, "L3")]), legality(R[(m, "L3nw")])
        c, d = legality(R[(m, "L3anon")]), legality(R[(m, "L1nw")])
        g1 = newcombe(a[0], a[1], b[0], b[1])
        g2 = newcombe(c[0], c[1], d[0], d[1])
        se = math.sqrt(((g1[2] - g1[1]) / 3.92) ** 2 + ((g2[2] - g2[1]) / 3.92) ** 2)
        diff = g1[0] - g2[0]
        lo, hi = diff - 1.96 * se, diff + 1.96 * se
        print("  %-7s names %6.1f   anon %6.1f   interaction %+6.1f [%+.1f, %+.1f]%s"
              % (m, g1[0], g2[0], diff, lo, hi, "" if lo < 0 < hi else "  EXCLUDES ZERO"))
        emit("interaction", model=m, gap_names=round(g1[0], 1),
             gap_anon=round(g2[0], 1), interaction=round(diff, 1),
             lo=round(lo, 1), hi=round(hi, 1))


def b_refusal(R):
    print("\nrefusal  correct refusal, Full Information to No Width")
    for m in MODELS:
        a, b = refusal(R[(m, "L3")]), refusal(R[(m, "L3nw")])
        d, lo, hi = newcombe(a[0], a[1], b[0], b[1])
        print("  %-7s %5.1f -> %5.1f   fall %+6.1f [%.1f, %.1f]  n=%d"
              % (m, 100 * a[0] / a[1], 100 * b[0] / b[1], d, lo, hi, a[1]))
        emit("refusal", model=m, full=round(100 * a[0] / a[1], 1),
             nowidth=round(100 * b[0] / b[1], 1), fall=round(d, 1),
             lo=round(lo, 1), hi=round(hi, 1))


def b_franka(R):
    print("\nfranka  share of proposals naming a Franka, Full Information to No Width")
    for m in MODELS:
        a, b = franka_share(R[(m, "L3")]), franka_share(R[(m, "L3nw")])
        d, lo, hi = newcombe(b[0], b[1], a[0], a[1])
        print("  %-7s %5.1f -> %5.1f   rise %+6.1f [%.1f, %.1f]"
              % (m, 100 * a[0] / a[1], 100 * b[0] / b[1], d, lo, hi))
        emit("franka", model=m, full=round(100 * a[0] / a[1], 1),
             nowidth=round(100 * b[0] / b[1], 1), rise=round(d, 1),
             lo=round(lo, 1), hi=round(hi, 1))


def b_reasons(R):
    """A count of zero is not the same as an absence. Bound it."""
    print("\nreasons  grasp-violation reasons admitting the width was missing")
    total = hits = 0
    for m in MODELS:
        for c in ("L3nw", "L1nw"):
            for r in R[(m, c)]:
                if r.get("violation_cause") == "grasp":
                    total += 1
                    hits += bool(MISSING_INFO.search(r.get("model_reason") or ""))
    lo, hi = wilson(hits, total)
    print("  %d of %d matched" % (hits, total))
    print("  95%% upper bound  Wilson %.2f%%   rule of three %.2f%%"
          % (hi, 100 * 3 / total))
    emit("reasons", matched=hits, total=total, wilson_upper=round(hi, 2),
         rule_of_three_upper=round(100 * 3 / total, 2))


def b_objects(R):
    print("\nobjects  grasp errors per opportunity at No Width, Wilson intervals")
    for m in MODELS:
        counts = collections.Counter()
        for r in R[(m, "L3nw")]:
            if r.get("violation_cause") == "grasp":
                obj = (r.get("violation_fields") or {}).get("obj")
                if obj:
                    counts[obj] += 1
        print("  %s" % m)
        for obj, opps in OPPORTUNITIES.items():
            k = counts[obj]
            lo, hi = wilson(k, opps)
            print("    %-18s %3d/%3d = %5.1f [%.1f, %.1f]"
                  % (obj, k, opps, 100 * k / opps, lo, hi))
            emit("objects", model=m, object=obj, errors=k, opportunities=opps,
                 rate=round(100 * k / opps, 1), lo=round(lo, 1), hi=round(hi, 1))
        # The width-ordering violation the chapter rests an argument on.
        a, b = counts["ycb_meat_can"], counts["ycb_wood_block"]
        d, lo, hi = newcombe(a, OPPORTUNITIES["ycb_meat_can"],
                             b, OPPORTUNITIES["ycb_wood_block"])
        print("    meat can (0.084) minus wood block (0.090): %+.1f [%.1f, %.1f]%s"
              % (d, lo, hi, "  EXCLUDES ZERO" if not lo < 0 < hi else ""))
        emit("ordering", model=m, contrast="meat_can_minus_wood_block",
             diff=round(d, 1), lo=round(lo, 1), hi=round(hi, 1))


def b_latency(R):
    print("\nlatency  seconds per call, median and interquartile range")
    for m in MODELS:
        for c in COND:
            v = sorted(r["latency_ms"] / 1000 for r in R[(m, c)] if r.get("latency_ms"))
            if not v:
                continue
            q1, q3 = statistics.quantiles(v, n=4)[0], statistics.quantiles(v, n=4)[2]
            print("  %-7s %-20s median %5.1f  IQR [%.1f, %.1f]  n=%d"
                  % (m, NAME[c], statistics.median(v), q1, q3, len(v)))
            emit("latency", model=m, condition=NAME[c],
                 median=round(statistics.median(v), 1),
                 q1=round(q1, 1), q3=round(q3, 1), n=len(v))


BLOCKS = {"interaction": b_interaction, "refusal": b_refusal,
          "franka": b_franka, "reasons": b_reasons,
          "objects": b_objects, "latency": b_latency}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="path to the fourarm package")
    ap.add_argument("--block", action="append", choices=sorted(BLOCKS),
                    help="run one block only, repeatable")
    ap.add_argument("--csv", metavar="DIR",
                    help="also write one tidy CSV per block into DIR")
    args = ap.parse_args()

    R = {(m, c): rows(path(args.root, m, c)) for m in MODELS for c in COND}
    for name in (args.block or list(BLOCKS)):
        BLOCKS[name](R)

    if args.csv:
        os.makedirs(args.csv, exist_ok=True)
        for block, records in OUT.items():
            dest = os.path.join(args.csv, "ex1_%s.csv" % block)
            with open(dest, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(records[0]))
                w.writeheader()
                w.writerows(records)
            print("wrote %s  (%d rows)" % (dest, len(records)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
