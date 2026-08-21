"""audit_rows: verify a finished run against independently recomputed truth.

WHY THIS EXISTS

Every number in the results chapter rests on the "result" field of a row,
and that field was written by the same validator call that produced the
verdict. Reading rejections one at a time cannot find a systematic scoring
fault, because a fault would look reasonable in every individual case.

So this recomputes the ground truth for every row from the frozen state,
through legal_options, and compares. It answers four questions:

  1. Is every row scored correctly? A proposal recorded as rejected must
     appear in the rejected set for that state, and one recorded as valid
     must appear in the legal set. A mismatch is a harness fault and every
     number from that run is void.

  2. Is the recorded CAUSE right? violation_cause must match the cause
     legal_options assigns to that pair. This is the field the per-type
     tables are built from.

  3. Did the model ever have a legal option it missed? For each rejection,
     how many legal pairs existed. A rejection on a state with no legal
     pair is a different event from one where twelve were available.

  4. Are repeats consistent, and if a model is deterministic, is it
     actually deterministic?

WHAT A DISAGREEMENT WOULD MEAN

The validator is the ground truth for the experiment; this file is a
second opinion computed by a different route (legal_options enumerates
every pair up front, validate_decision judges one pair on demand). They
should never differ. If they do, the pair-level enumeration and the
single-decision path disagree about the cell, and nothing can be reported
until that is resolved.

Usage:

    python3 analysis/ex1/ex1_audit_rows.py --probes probes/ex1_v2.json \\
        out/ex1_gpt_L3_r3.jsonl out/ex1_gpt_L3nw_r3.jsonl ...

    python3 analysis/ex1/ex1_audit_rows.py --probes probes/ex1_v2.json \\
        --rejections out/ex1_gpt_L3nw_r3.jsonl      # list every rejection
"""

import argparse
import collections
import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis.probe_store import load, legal_options          # noqa: E402


def wilson(k, n, z=1.96):
    if not n:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def newcombe(k1, n1, k2, n2, z=1.96):
    """95% CI on a difference of proportions. Needed for a NULL: a gap
    reported without an interval is an absence, not a null."""
    l1, u1 = [x / 100 for x in wilson(k1, n1, z)]
    l2, u2 = [x / 100 for x in wilson(k2, n2, z)]
    p1, p2 = k1 / n1, k2 / n2
    d = p1 - p2
    return (100 * d,
            100 * (d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)),
            100 * (d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)))


def _pct(k, n):
    if not n:
        return "     -"
    lo, hi = wilson(k, n)
    return "%5.1f [%4.1f,%5.1f] n=%-4d" % (100 * k / n, lo, hi, n)


def ground_truth(probes):
    """{(seq, source): (legal set, {pair: cause})} for every probe."""
    out = {}
    for p in probes:
        legal, _per, causes = legal_options(p, with_causes=True)
        out[(p["provenance"]["seq"], p["provenance"]["source"])] = (
            {(t, a) for t, a, _k in legal},
            {(t, a): c for t, a, c in causes})
    return out


def audit(path, gt):
    rows = [json.loads(l) for l in open(path)]
    bad_score, bad_cause, unknown, flagged = [], [], [], []
    for r in rows:
        key = (r["provenance"]["seq"], r["provenance"]["source"])
        if key not in gt:
            unknown.append(r)
            continue
        legal, causes = gt[key]
        if r.get("diagnostic_disagrees"):
            flagged.append(r)
        if r["result"] not in ("valid", "rejected"):
            continue
        pair = (r.get("task_id"), r.get("arm"))
        is_legal = pair in legal
        if (r["result"] == "valid") != is_legal:
            bad_score.append((r, pair, is_legal))
        if r["result"] == "rejected":
            want = causes.get(pair)
            got = r.get("violation_cause")
            # task_state and arm_state rejections have no pair-level cause:
            # legal_options only enumerates OPEN tasks and IDLE arms, so a
            # proposal naming a busy task is outside its universe. That is
            # a real model error, not a mismatch.
            if want is not None and got is not None and want != got:
                bad_cause.append((r, want, got))
    return rows, bad_score, bad_cause, unknown, flagged


def summarise(name, rows, gt):
    p = [r for r in rows if not r["zero_legal"]]
    z = [r for r in rows if r["zero_legal"]]
    prop = [r for r in p if r["result"] in ("valid", "rejected")]
    g = [r for r in prop if r["binds_grasp"]]
    ng = [r for r in prop if not r["binds_grasp"]]
    by = collections.defaultdict(list)
    for r in rows:
        by[(r["provenance"]["seq"], r["provenance"]["source"])].append(
            r["result"])
    full = [v for v in by.values() if len(v) > 1]
    reps = max((r.get("n_repeats") or 1) for r in rows)

    print("\n%s" % name)
    print("  rows %-5d states %-4d repeats %d" % (len(rows), len(by), reps))
    print("  legality, grasp-binding   %s" % _pct(
        sum(1 for r in g if r["result"] == "valid"), len(g)))
    print("  legality, no grasp bind   %s" % _pct(
        sum(1 for r in ng if r["result"] == "valid"), len(ng)))
    print("  correct refusal           %s" % _pct(
        sum(1 for r in z if r["result"] == "noop"), len(z)))
    print("  declines on picking       %s" % _pct(
        sum(1 for r in p if r["result"] == "noop"), len(p)))
    if full:
        print("  outcome consistency       %s" % _pct(
            sum(1 for v in full if len(set(v)) == 1), len(full)))
    c = collections.Counter(r.get("violation_cause") for r in rows
                            if r.get("violation_cause"))
    if c:
        print("  causes                    %s" % dict(c.most_common()))
    obj = collections.Counter((r.get("violation_fields") or {}).get("obj")
                              for r in rows
                              if r.get("violation_cause") == "grasp")
    if obj:
        print("  grasp errors by object    %s" % dict(obj.most_common()))
    return {"grasp_k": sum(1 for r in g if r["result"] == "valid"),
            "grasp_n": len(g),
            "ref_k": sum(1 for r in z if r["result"] == "noop"),
            "ref_n": len(z)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", required=True)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--rejections", metavar="RUN",
                    help="list every rejection in one run and stop")
    args = ap.parse_args(argv)

    ps = load(args.probes)
    print("%s  hash %s  n %d" % (args.probes, ps.get("hash", "")[:16],
                                 len(ps["probes"])))
    gt = ground_truth(ps["probes"])

    if args.rejections:
        rows = [json.loads(l) for l in open(args.rejections)]
        rej = [r for r in rows if r["result"] == "rejected"]
        print("\n%d rejections in %s" % (len(rej), args.rejections))
        for r in rej:
            key = (r["provenance"]["seq"], r["provenance"]["source"])
            legal, causes = gt[key]
            pair = (r.get("task_id"), r.get("arm"))
            print("\n  seq %-4s r%-2s  task %-3s -> %-9s  %s" % (
                r["provenance"]["seq"], r.get("repeat", 1),
                r.get("task_id"), r.get("arm"), r.get("violation_cause")))
            print("    legal pairs on this state: %d %s" % (
                len(legal), sorted(legal)[:6]))
            print("    independent cause for the chosen pair: %s" %
                  causes.get(pair, "NOT IN REJECTED SET"))
            print("    validator: %s" % (r.get("rejected_because") or "")[:110])
            print("    model    : %s" % (r.get("model_reason") or "")[:110])
        return 0

    fails = 0
    stats = {}
    for path in args.runs:
        if not os.path.exists(path):
            print("\n%s  MISSING" % path)
            fails += 1
            continue
        rows, bad_score, bad_cause, unknown, flagged = audit(path, gt)
        name = os.path.basename(path)
        print("\n" + "=" * 62)
        print("VERIFY  %s" % name)
        ok = True
        if unknown:
            print("  FAIL  %d rows reference a probe not in this set "
                  "(wrong probe set?)" % len(unknown))
            ok = False
        if bad_score:
            print("  FAIL  %d rows scored against independent truth" %
                  len(bad_score))
            for r, pair, is_legal in bad_score[:3]:
                print("        seq %s r%s pair %s recorded %s, independently %s"
                      % (r["provenance"]["seq"], r.get("repeat"), pair,
                         r["result"], "legal" if is_legal else "illegal"))
            ok = False
        if bad_cause:
            print("  FAIL  %d rows carry a cause that disagrees" %
                  len(bad_cause))
            for r, want, got in bad_cause[:3]:
                print("        seq %s pair (%s,%s) recorded %s, independently %s"
                      % (r["provenance"]["seq"], r.get("task_id"),
                         r.get("arm"), got, want))
            ok = False
        if flagged:
            print("  FAIL  %d rows had diagnostic_disagrees set at run time"
                  % len(flagged))
            ok = False
        if ok:
            print("  PASS  every row agrees with independently recomputed "
                  "truth (%d rows)" % len(rows))
        else:
            fails += 1
        stats[name] = summarise("  " + name, rows, gt)

    # Gaps between consecutive runs, with intervals.
    names = [os.path.basename(p) for p in args.runs if os.path.exists(p)]
    if len(names) > 1:
        print("\n" + "=" * 62)
        print("GAPS, legality on the grasp-binding subset")
        for a, b in zip(names, names[1:]):
            sa, sb = stats[a], stats[b]
            if not (sa["grasp_n"] and sb["grasp_n"]):
                continue
            d, lo, hi = newcombe(sa["grasp_k"], sa["grasp_n"],
                                 sb["grasp_k"], sb["grasp_n"])
            flag = "" if (lo > 0 or hi < 0) else "   (interval spans zero)"
            print("  %-28s -> %-28s %6.1f pts [%5.1f,%5.1f]%s" % (
                a[:28], b[:28], d, lo, hi, flag))
        print("\nGAPS, correct refusal")
        for a, b in zip(names, names[1:]):
            sa, sb = stats[a], stats[b]
            if not (sa["ref_n"] and sb["ref_n"]):
                continue
            d, lo, hi = newcombe(sa["ref_k"], sa["ref_n"],
                                 sb["ref_k"], sb["ref_n"])
            flag = "" if (lo > 0 or hi < 0) else "   (interval spans zero)"
            print("  %-28s -> %-28s %6.1f pts [%5.1f,%5.1f]%s" % (
                a[:28], b[:28], d, lo, hi, flag))

    print("\nRESULT: " + ("ALL RUNS VERIFY" if not fails
                          else "%d RUN(S) FAILED" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
