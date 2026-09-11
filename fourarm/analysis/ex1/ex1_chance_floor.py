"""The chance floor: what a model would score without reasoning.

A legality rate means nothing on its own. If a model scores 55 percent at
L1-nowidth, that is real work if random picking scores 20 and no work at
all if random picking scores 52. This computes the reference lines, from
the frozen states alone, with no model calls and no cost.

ONE FLOOR FOR THE WHOLE SPINE

The states are identical at every rung; only the prompt changes. So the
odds of a random pick being legal are the same everywhere and one line
sits under L3, L3-nowidth and L1-nowidth alike. Reporting a floor per rung
would imply the states moved.

THE FOUR NUMBERS

uniform        Every (open task, idle arm) equally likely. The floor for a
               model that has understood the answer format and nothing
               else.

per cause      The same floor restricted to states where a given
               constraint binds at least one pair. The grasp subset has
               its own floor, and it is the one the primary endpoint is
               read against. A pooled floor would be read against a
               subset, which is the wrong comparison.

width-blind    The score of a chooser that gets reach, payload, delicacy
               and routing right and guesses only at width. This is the
               most useful line on the spine, because the distance between
               it and the uniform floor is exactly what width knowledge is
               worth in this cell. A model at L3-nowidth landing here has
               lost its width knowledge and kept everything else.

refusal        Reported SEPARATELY, never pooled. On a state with no legal
               pair the correct answer is to decline, so this is a floor
               for a different question and averaging it into the legality
               floor would drag it below what a picking model faces.

               Declining is an ACTION, not the absence of one. R5 licenses
               waiting and replay_one records a noop as its own third
               result, so a random agent's action space is every (task,
               arm) pair PLUS one decline. On a zero-legal state that gives
               a correct-refusal floor of 1/(pairs+1), which is far from
               zero: refusal states carry few pairs, median 4, so the
               decline slot is a large share of the space. Without this
               line the 36 refusal probes have no baseline and nothing can
               be said about them.

TWO ENDPOINTS, TWO FLOORS

Legality is scored on trials where the model PROPOSED something, because a
noop is neither valid nor rejected. Its floor is therefore conditional on
proposing, and adding a decline option does not change a rate that
excludes declines. That is the headline legality number.

Correct refusal is scored on the 36 zero-legal states and its floor is the
decline probability. The unconditional variants of both are printed beside
them for completeness.

The two trade off and must be read as a pair. An agent that declines with
probability p scores p on refusal states and (1-p) times the conditional
floor on picking states, so a model cannot be praised for one without its
cost in the other being checked. Uniform-over-(pairs+1) is ONE point on
that curve, chosen because it needs no free parameter, and it is stated as
an assumption rather than a fact about how models behave.

HOW WIDTH-BLIND IS COMPUTED

Not by reimplementing the rule. Both arm types' max_grasp_m is raised so
that width can never bind, and the REAL validator is run again through
legal_options. Whatever it accepts then is exactly the option set of a
chooser for whom width is invisible. The limits are restored in a finally
block, and the result is asserted to be a superset of the true legal set,
because a chooser that ignores a constraint can only ever gain options.

WHAT IS CHECKED BEFORE ANY NUMBER IS PRINTED

The recomputed legal count is compared against the n_legal_pairs already
stored in each probe's derived block. A mismatch means this script and the
frozen set disagree about the ground truth, and nothing is reported.
Three extractor rules on EX2 each produced false findings before this kind
of check was routine.

Usage:

    python3 analysis/ex1/ex1_chance_floor.py --probes probes/ex1_v2.json
    python3 analysis/ex1/ex1_chance_floor.py --probes probes/ex1_v2.json \\
        --out out/ex1_chance_floor.json
"""

import argparse
import collections
import json
import os
import statistics
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.cell import cell_config as C                        # noqa: E402
from harvest.probe_store import load, legal_options          # noqa: E402

CAUSES = ("grasp", "reach", "delicate", "payload", "no_route")

# Larger than any object in the cell by two orders of magnitude, so the
# comparison spec["grasp_m"] > t["max_grasp_m"] can never be true.
_WIDE = 99.0


def _legal_set(probe):
    """(legal pairs, rejected pairs with causes) from the real validator."""
    pairs, _per_task, causes = legal_options(probe, with_causes=True)
    return {(t, a) for t, a, _k in pairs}, {(t, a): c for t, a, c in causes}


def _legal_set_width_blind(probe):
    """The legal set when width can never bind.

    Raises both arm types' max_grasp_m and re-runs the SAME validator, so
    nothing here restates a rule. Restored in finally: a leaked limit would
    silently make every later number in the process wrong.
    """
    saved = {k: C.ARM_TYPES[k]["max_grasp_m"] for k in C.ARM_TYPES}
    try:
        for k in C.ARM_TYPES:
            C.ARM_TYPES[k]["max_grasp_m"] = _WIDE
        pairs, _per_task = legal_options(probe)
        return {(t, a) for t, a, _k in pairs}
    finally:
        for k, v in saved.items():
            C.ARM_TYPES[k]["max_grasp_m"] = v


def floors_for(probe):
    """Per-state floors, or None if the state has no (task, arm) pair.

    Returns a dict with the pair counts, the uniform floor, the
    width-blind reference, and the binding causes present on this state.
    """
    legal, rejected = _legal_set(probe)
    n_pairs = len(legal) + len(rejected)
    if n_pairs == 0:
        return None

    blind = _legal_set_width_blind(probe)
    if not legal <= blind:
        raise ValueError(
            f"width-blind legal set is not a superset of the true one on "
            f"{probe['provenance'].get('seq')}: ignoring a constraint can "
            f"only add options, so this means the limits were not restored "
            f"or legal_options is not deterministic.")

    d = probe.get("derived") or {}
    stored = d.get("n_legal_pairs")
    if stored is not None and stored != len(legal):
        raise ValueError(
            f"recomputed {len(legal)} legal pairs but the frozen set stores "
            f"{stored} on seq {probe['provenance'].get('seq')}. This script "
            f"and the probe set disagree about the ground truth, so no "
            f"number from either can be reported.")

    causes = {c for c in rejected.values()}
    return {
        "seq": probe["provenance"].get("seq"),
        "source": probe["provenance"].get("source"),
        "n_pairs": n_pairs,
        "n_legal": len(legal),
        "n_legal_width_blind": len(blind),
        # A random picker over every pair.
        "uniform": len(legal) / n_pairs,
        # A picker that has excluded everything except width. Undefined
        # when width blindness opens no options at all, which happens when
        # width binds nothing on this state.
        "width_blind": (len(legal) / len(blind)) if blind else None,
        # Declining treated as one action alongside every pair.
        "p_decline": 1.0 / (n_pairs + 1),
        # Legality when a wrongly-taken decline counts against the model.
        "uniform_unconditional": len(legal) / (n_pairs + 1),
        "zero_legal": len(legal) == 0,
        "binds": sorted(causes & set(CAUSES)),
        "other_causes": sorted(causes - set(CAUSES)),
    }


def _agg(rows, key="uniform"):
    """Per-state mean and pooled rate.

    Per-state mean is the headline: each state is ONE decision the model
    is asked to make, so states weigh equally regardless of how many pairs
    they happen to offer. Pooled is reported beside it because a large gap
    between the two means the floor depends on state size, which is worth
    knowing before any rung is read against it.
    """
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return None
    out = {"n_states": len(vals), "mean": statistics.mean(vals)}
    if len(vals) > 1:
        out["sd"] = statistics.stdev(vals)
        out["min"] = min(vals)
        out["max"] = max(vals)
    if key == "uniform":
        num = sum(r["n_legal"] for r in rows)
        den = sum(r["n_pairs"] for r in rows)
        out["pooled"] = num / den if den else None
    return out


def _pct(x):
    return "     -" if x is None else f"{100 * x:6.1f}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", required=True)
    ap.add_argument("--out", help="write the full result as JSON")
    ap.add_argument("--limit", type=int, help="first N probes, for a smoke run")
    args = ap.parse_args(argv)

    ps = load(args.probes)
    probes = ps["probes"][:args.limit] if args.limit else ps["probes"]
    print(f"{args.probes}")
    print(f"  hash {ps.get('hash', '')[:16]}  n {len(probes)}")

    rows, skipped = [], 0
    for i, p in enumerate(probes, 1):
        r = floors_for(p)
        if r is None:
            skipped += 1
            continue
        rows.append(r)
        if i % 25 == 0:
            print(f"  ... {i}/{len(probes)}", flush=True)

    picking = [r for r in rows if not r["zero_legal"]]
    refusal = [r for r in rows if r["zero_legal"]]

    print(f"\n  states with pairs   {len(rows)}")
    print(f"  states with none    {skipped}")
    print(f"  picking states      {len(picking)}")
    print(f"  refusal states      {len(refusal)}")

    result = {
        "probe_set": os.path.basename(args.probes),
        "probe_set_hash": ps.get("hash"),
        "n_states": len(rows),
        "n_picking": len(picking),
        "n_refusal": len(refusal),
        "uniform": _agg(picking, "uniform"),
        "width_blind": _agg(picking, "width_blind"),
        "by_cause": {},
        "per_state": rows,
    }
    for c in CAUSES:
        sub = [r for r in picking if c in r["binds"]]
        if sub:
            result["by_cause"][c] = {
                "n_states": len(sub),
                "uniform": _agg(sub, "uniform"),
                "width_blind": _agg(sub, "width_blind"),
            }

    print("\n                            states  uniform%  width-blind%")
    u, w = result["uniform"], result["width_blind"]
    print(f"  all picking states        {len(picking):6d}  "
          f"{_pct(u['mean'] if u else None)}    "
          f"{_pct(w['mean'] if w else None)}")
    for c in CAUSES:
        b = result["by_cause"].get(c)
        if not b:
            continue
        print(f"  binds {c:<20} {b['n_states']:6d}  "
              f"{_pct(b['uniform']['mean'])}    "
              f"{_pct(b['width_blind']['mean'] if b['width_blind'] else None)}")

    if u:
        print(f"\n  uniform pooled            {_pct(u['pooled'])}"
              f"   (per-state mean {_pct(u['mean'])})")

    # ---- declining as an action ------------------------------------------
    result["refusal"] = {
        "n_states": len(refusal),
        # THE headline for the refusal probes. Compare a model's
        # correct-decline rate on the zero-legal states against this.
        "correct_refusal_floor": _agg(refusal, "p_decline"),
        "median_pairs": (statistics.median([r["n_pairs"] for r in refusal])
                         if refusal else None),
    }
    result["unconditional"] = {
        "legality": _agg(picking, "uniform_unconditional"),
        "wrong_decline": _agg(picking, "p_decline"),
    }

    print("\n  DECLINING AS AN ACTION")
    print("  Random agent over every (task, arm) pair PLUS one decline.")
    rf = result["refusal"]["correct_refusal_floor"]
    print(f"    correct-refusal floor, {len(refusal)} zero-legal states  "
          f"{_pct(rf['mean'] if rf else None)}")
    ul = result["unconditional"]["legality"]
    wd = result["unconditional"]["wrong_decline"]
    print(f"    legality if wrong declines count against  "
          f"{_pct(ul['mean'] if ul else None)}")
    print(f"    rate of wrongly declining                 "
          f"{_pct(wd['mean'] if wd else None)}")
    print("  Read these two as a pair: an agent declining with probability "
          "p\n  scores p on refusal states and (1-p) x the conditional "
          "floor on\n  picking states, so neither can be judged alone.")

    odd = collections.Counter(c for r in rows for c in r["other_causes"])
    if odd:
        print(f"\n  UNSPLIT CAUSES SEEN: {dict(odd)}")
        print("  capability_unsplit means the validator rejected on "
              "capability\n  but the three sub-limits all passed, which is a "
              "real disagreement\n  between probe_store and cell_config.")

    if args.out:
        d = os.path.dirname(os.path.abspath(args.out))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(result, f, indent=1)
        print(f"\nWROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())