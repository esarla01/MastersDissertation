"""ex1_report: one pass over every run file, everything needed to write up.

Reads whatever run files exist, infers model and rung from the ROWS rather
than the filenames, and prints a report compact enough to read in one go.

Sections:

  0  inventory and integrity      what is on disk, and whether it verifies
  1  the spine, per model         legality by binding cause, refusal,
                                  declines, consistency, with Wilson CIs
  2  gaps                         adjacent rungs, Newcombe CIs
  3  per-scene majority           stable-right / stable-wrong / flickering
  4  violation composition        first-recorded against all-broken
  5  grasp errors by object       ordered by how far the object exceeds
                                  the Franka aperture
  6  arm choice                   which arm each model reaches for
  7  declines                     coded by reason, and whether any error
                                  admits the information was missing
  8  off-spine                    L2 and L4
  9  cost and latency

Every rate carries its denominator. Nothing is pooled across models or
across rungs. Where a number cannot be computed the cell says so rather
than showing zero.

Usage:

    python3 analysis/ex1_report.py --probes probes/ex1_v2.json out/ex1_*.jsonl
"""

import argparse
import collections
import json
import math
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis.probe_store import load, legal_options              # noqa: E402

SPINE = ("L3", "L3-nowidth", "L1-nowidth")
OFF = ("L4", "L2")
APERTURE = 0.080


def wilson(k, n, z=1.96):
    if not n:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def newcombe(k1, n1, k2, n2, z=1.96):
    l1, u1 = [x / 100 for x in wilson(k1, n1, z)]
    l2, u2 = [x / 100 for x in wilson(k2, n2, z)]
    p1, p2 = k1 / n1, k2 / n2
    d = p1 - p2
    return (100 * d,
            100 * (d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)),
            100 * (d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)))


def rate(k, n):
    if not n:
        return "      -        "
    lo, hi = wilson(k, n)
    return "%5.1f [%4.1f,%5.1f] %-4d" % (100 * k / n, lo, hi, n)


def key(rows):
    """(model, rung) from the rows, not the filename."""
    m = {r.get("model_alias") for r in rows}
    g = {r.get("rung") for r in rows}
    return (sorted(m)[0] if len(m) == 1 else "MIXED:" + ",".join(map(str, m)),
            sorted(g)[0] if len(g) == 1 else "MIXED")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", required=True)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the independent re-scoring (slow on many files)")
    args = ap.parse_args(argv)

    ps = load(args.probes)
    widths = {}
    for p in ps["probes"]:
        for o in p["state"]["objects"]:
            if o.get("grasp_m") is not None:
                widths[o["name"]] = o["grasp_m"]

    gt = None
    if not args.no_verify:
        gt = {}
        for p in ps["probes"]:
            legal, _per, causes = legal_options(p, with_causes=True)
            gt[(p["provenance"]["seq"], p["provenance"]["source"])] = (
                {(t, a) for t, a, _k in legal},
                {(t, a): c for t, a, c in causes})

    data = {}
    print("=" * 78)
    print("0  INVENTORY AND INTEGRITY")
    print("=" * 78)
    print("  %-34s %-7s %-11s %5s %4s %5s %s"
          % ("file", "model", "rung", "rows", "rep", "state", "verify"))
    for path in sorted(args.runs):
        if not os.path.exists(path):
            print("  %-34s MISSING" % os.path.basename(path)[:34])
            continue
        rows = [json.loads(l) for l in open(path) if l.strip()]
        if not rows:
            print("  %-34s EMPTY" % os.path.basename(path)[:34])
            continue
        m, g = key(rows)
        reps = max((r.get("n_repeats") or 1) for r in rows)
        nstates = len({(r["provenance"]["seq"], r["provenance"]["source"])
                       for r in rows})
        verdict = "skipped"
        if gt is not None:
            bad = 0
            for r in rows:
                k = (r["provenance"]["seq"], r["provenance"]["source"])
                if k not in gt or r.get("result") not in ("valid", "rejected"):
                    continue
                if (r.get("result") == "valid") != ((r.get("task_id"),
                                                 r.get("arm")) in gt[k][0]):
                    bad += 1
            flag = sum(1 for r in rows if r.get("diagnostic_disagrees"))
            # A row with no "result" never got that far: the model call
            # raised. It is not a decision and must not be counted as one,
            # but it must be visible, because a rate whose denominator
            # quietly shrank is worse than a missing one.
            nores = sum(1 for r in rows if "result" not in r)
            verdict = "OK" if not bad and not flag else \
                      "FAIL %d scored, %d flagged" % (bad, flag)
            if nores:
                verdict += "  %d ERRORED (no result)" % nores
        print("  %-34s %-7s %-11s %5d %4d %5d %s"
              % (os.path.basename(path)[:34], m, g, len(rows), reps,
                 nstates, verdict))
        data[(m, g)] = rows

    models = sorted({m for m, _ in data})

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("1  THE SPINE   legality is conditioned on binding cause")
    print("   floors: grasp 30.5, all-picking 35.5, refusal 22.0;"
          " width-blind grasp 74.9")
    print("=" * 78)
    stats = {}
    for m in models:
        print("\n  %s" % m.upper())
        print("    %-11s %-21s %-21s %-21s %-21s"
              % ("rung", "legality grasp-bind", "legality no-grasp",
                 "correct refusal", "declines on picking"))
        for g in SPINE:
            rows = data.get((m, g))
            if not rows:
                print("    %-11s  [not run]" % g)
                continue
            p = [r for r in rows if not r.get("zero_legal")]
            z = [r for r in rows if r.get("zero_legal")]
            prop = [r for r in p if r.get("result") in ("valid", "rejected")]
            gb = [r for r in prop if r.get("binds_grasp")]
            ng = [r for r in prop if not r.get("binds_grasp")]
            stats[(m, g)] = {
                "gk": sum(1 for r in gb if r.get("result") == "valid"),
                "gn": len(gb),
                "zk": sum(1 for r in z if r.get("result") == "noop"),
                "zn": len(z),
                "pk": sum(1 for r in prop if r.get("result") == "valid"),
                "pn": len(prop)}
            print("    %-11s %-21s %-21s %-21s %-21s" % (
                g,
                rate(stats[(m, g)]["gk"], len(gb)),
                rate(sum(1 for r in ng if r.get("result") == "valid"), len(ng)),
                rate(stats[(m, g)]["zk"], len(z)),
                rate(sum(1 for r in p if r.get("result") == "noop"), len(p))))

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("2  GAPS   adjacent spine rungs, Newcombe 95% CI")
    print("=" * 78)
    for m in models:
        print("\n  %s" % m.upper())
        for a, b in zip(SPINE, SPINE[1:]):
            sa, sb = stats.get((m, a)), stats.get((m, b))
            if not sa or not sb or not sa["gn"] or not sb["gn"]:
                print("    %-11s -> %-11s  [incomplete]" % (a, b))
                continue
            d, lo, hi = newcombe(sa["gk"], sa["gn"], sb["gk"], sb["gn"])
            note = "" if (lo > 0 or hi < 0) else "   CI SPANS ZERO"
            print("    %-11s -> %-11s legality %6.1f pts [%5.1f,%5.1f]%s"
                  % (a, b, d, lo, hi, note))
            d, lo, hi = newcombe(sa["zk"], sa["zn"], sb["zk"], sb["zn"])
            note = "" if (lo > 0 or hi < 0) else "   CI SPANS ZERO"
            print("    %-11s -> %-11s refusal  %6.1f pts [%5.1f,%5.1f]%s"
                  % ("", "", d, lo, hi, note))

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("3  PER-SCENE MAJORITY   unit of analysis, as in EX2")
    print("=" * 78)
    for m in models:
        print("\n  %s" % m.upper())
        print("    %-11s %6s %6s %6s %7s  %s"
              % ("rung", "stable+", "stable-", "flick", "n", "majority legal"))
        for g in SPINE:
            rows = data.get((m, g))
            if not rows:
                continue
            by = collections.defaultdict(list)
            for r in rows:
                by[(r["provenance"]["seq"],
                    r["provenance"]["source"])].append(r)
            sr = sw = fl = 0
            mk = mn = 0
            for v in by.values():
                if v[0].get("zero_legal"):
                    continue
                res = [x.get("result") for x in v]
                if len(set(res)) == 1:
                    if res[0] == "valid":
                        sr += 1
                    else:
                        sw += 1
                else:
                    fl += 1
                if any(x.get("binds_grasp") for x in v):
                    mn += 1
                    if sum(1 for x in res if x == "valid") * 2 > len(res):
                        mk += 1
            print("    %-11s %6d %6d %6d %7d  %s"
                  % (g, sr, sw, fl, sr + sw + fl, rate(mk, mn)))

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("4  VIOLATION COMPOSITION   first-recorded / every constraint broken")
    print("=" * 78)
    for m in models:
        print("\n  %s" % m.upper())
        for g in SPINE + OFF:
            rows = data.get((m, g))
            if not rows:
                continue
            first = collections.Counter(r.get("violation_cause") for r in rows
                                        if r.get("violation_cause"))
            allb = collections.Counter(c for r in rows
                                       for c in (r.get("violation_all") or []))
            print("    %-11s first %s" % (g, dict(first.most_common())))
            print("    %-11s all   %s" % ("", dict(allb.most_common())))

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("5  GRASP ERRORS BY OBJECT   Franka aperture %.3f m" % APERTURE)
    print("=" * 78)
    objs = sorted(widths, key=lambda o: -widths[o])
    for m in models:
        cols = [g for g in SPINE if (m, g) in data]
        if not cols:
            continue
        print("\n  %s" % m.upper())
        print("    %-20s %8s %8s  %s"
              % ("object", "width", "excess", "  ".join("%-11s" % c
                                                        for c in cols)))
        for o in objs:
            counts = []
            for g in cols:
                c = collections.Counter(
                    (r.get("violation_fields") or {}).get("obj")
                    for r in data[(m, g)]
                    if r.get("violation_cause") == "grasp")
                counts.append(c.get(o, 0))
            if not any(counts):
                continue
            print("    %-20s %8.3f %+8.3f  %s"
                  % (o, widths[o], widths[o] - APERTURE,
                     "  ".join("%-11d" % n for n in counts)))

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("6  ARM CHOICE   among proposals that named an arm")
    print("=" * 78)
    for m in models:
        print("\n  %s" % m.upper())
        for g in SPINE + OFF:
            rows = data.get((m, g))
            if not rows:
                continue
            c = collections.Counter(r.get("arm") for r in rows
                                    if r.get("result") in ("valid", "rejected"))
            tot = sum(c.values())
            fr = sum(v for k, v in c.items() if k and k.startswith("franka"))
            print("    %-11s %s   franka share %.0f%%"
                  % (g, dict(c.most_common()),
                     100 * fr / tot if tot else 0))

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("7  DECLINES AND WHAT THE REASONS SAY")
    print("=" * 78)
    PAT = {"zone": r"zone|lock|inbound|contend",
           "wait-arm": r"wait(ing)? for \w+|free up|becomes? (free|available)",
           "unknown": r"unknown|cannot determine|not (given|stated|provided|"
                      r"specified)|no width|unclear|insufficient|missing",
           "infeasible": r"no (idle )?arm|nothing (is )?feasible|none can|"
                         r"no feasible|cannot be assigned"}
    for m in models:
        print("\n  %s" % m.upper())
        for g in SPINE:
            rows = data.get((m, g))
            if not rows:
                continue
            pn = [r for r in rows
                  if not r.get("zero_legal") and r.get("result") == "noop"]
            c = collections.Counter()
            for r in pn:
                t = (r.get("model_reason") or "").lower()
                hit = tuple(k for k, p in PAT.items() if re.search(p, t))
                c[hit or ("other",)] += 1
            err = [r for r in rows if r.get("violation_cause") == "grasp"]
            adm = sum(1 for r in err
                      if re.search(PAT["unknown"],
                                   (r.get("model_reason") or "").lower()))
            print("    %-11s declines-on-picking %-4d  %s"
                  % (g, len(pn), dict(c.most_common(4))))
            print("    %-11s grasp errors %-4d of which the reason admits "
                  "missing information: %d" % ("", len(err), adm))

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("8  OFF-SPINE   L4 obedience control, L2 rules withheld")
    print("=" * 78)
    print("  %-7s %-5s %-21s %-21s %-21s"
          % ("model", "rung", "legality grasp-bind", "correct refusal",
             "declines on picking"))
    for m in models:
        for g in OFF:
            rows = data.get((m, g))
            if not rows:
                continue
            p = [r for r in rows if not r.get("zero_legal")]
            z = [r for r in rows if r.get("zero_legal")]
            prop = [r for r in p if r.get("result") in ("valid", "rejected")]
            gb = [r for r in prop if r.get("binds_grasp")]
            print("  %-7s %-5s %-21s %-21s %-21s" % (
                m, g,
                rate(sum(1 for r in gb if r.get("result") == "valid"), len(gb)),
                rate(sum(1 for r in z if r.get("result") == "noop"), len(z)),
                rate(sum(1 for r in p if r.get("result") == "noop"), len(p))))

    # ---------------------------------------------------------------
    print("\n" + "=" * 78)
    print("9  LATENCY AND ERRORS")
    print("=" * 78)
    print("  %-7s %-11s %8s %8s %8s %7s %8s"
          % ("model", "rung", "median s", "p90 s", "max s", "errors",
             "unparse"))
    for m in models:
        for g in SPINE + OFF:
            rows = data.get((m, g))
            if not rows:
                continue
            lat = sorted(r["latency_ms"] for r in rows if r.get("latency_ms"))
            if not lat:
                continue
            print("  %-7s %-11s %8.1f %8.1f %8.1f %7d %8d" % (
                m, g, lat[len(lat) // 2] / 1000,
                lat[int(len(lat) * 0.9)] / 1000, lat[-1] / 1000,
                sum(1 for r in rows if r.get("error")),
                sum(1 for r in rows if r.get("result") == "unparseable")))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())