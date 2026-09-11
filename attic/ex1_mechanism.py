"""ex1_mechanism: two questions the summary tables cannot answer.

A. GRASP ERRORS PER OPPORTUNITY, not per run.

   Section 5 of ex1_report ranks objects by raw error count. That ranking
   can be an artefact. An object is only mis-graspable when it sits in an
   open task with a Franka that is idle and can reach it, and objects do
   not appear in that situation equally often. If the clamp offers twice
   the opportunities of the wood block it collects twice the errors even
   if the models treat them identically.

   So this counts, per object:

     opportunities   (state, repeat) cells where the object had an open
                     task and at least one idle Franka could reach it but
                     not grasp it, i.e. a Franka choice was AVAILABLE and
                     WRONG
     errors          times a model actually made that choice
     rate            errors / opportunities

   The rate is what distinguishes a model substituting mass for width from
   one that is simply asked about heavy objects less often. Gemini spares
   the wood block, the heaviest object at 1.58 kg, almost entirely, while
   GPT does not. Either that survives normalisation and is a real
   difference in what the two models fall back on, or it does not and
   there is nothing to explain.

B. DID QWEN'S NAMED ARM APPEAR IN THE IDLE LIST?

   Qwen produces arm_state rejections 67 times at L3 and 36 times at L4,
   where the legal set is handed over outright. The prompt ends with a
   plain sentence: "Idle arms right now: ur_w, ur_e, franka_s, franka_n."

   If the named arm is absent from that sentence, the failure involves no
   reasoning at all: the model was told which arms were available and
   named one that was not. That belongs in the write-up as an
   instruction-following finding, reported separately from legality, and
   it is the reason Qwen's spine results need a caveat: L4 exists to
   establish that a model can follow a supplied list, and Qwen fails it.

   If the named arm IS in the list and the validator still rejected it,
   that is a far more serious problem, because the prompt and the
   validator would disagree about the cell. Not expected, since every row
   verified, but it has to be ruled out rather than assumed.

Usage:

    python3 analysis/ex1_mechanism.py --probes probes/ex1_v2.json \\
        out/ex1_gpt_L3nw_r3.jsonl out/ex1_gemini_L3nw_r3.jsonl ...
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

from core.cell import cell_config as C                            # noqa: E402
from harvest.frozen_coord import from_record, idle_arms          # noqa: E402
from harvest.probe_store import load                             # noqa: E402
from harvest import probe_replay as pr                           # noqa: E402

IDLE_RE = re.compile(r"Idle arms right now:\s*([^.\n]*)")


def wilson(k, n, z=1.96):
    if not n:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def opportunities(probes):
    """{(seq, source): {object: n_franka_choices_that_would_be_wrong}}.

    An opportunity is an open task whose object at least one IDLE Franka
    can reach but cannot grasp. That is exactly the situation in which a
    width-blind model can err, and it is the correct denominator.
    """
    zm = pr.zonemap()
    out = {}
    for p in probes:
        coord = from_record(p)
        idle = set(idle_arms(coord))
        franka = [a for a in idle if a.startswith("franka")]
        per = collections.Counter()
        for t in coord.pool:
            if t.done or t.failed or t.claimed or t.waiting_on is not None:
                continue
            q = coord.cell.scene[t.obj].data.root_pos_w[0]
            oxy = (float(q[0]), float(q[1]))
            for a in franka:
                if zm.reachable(a, *oxy) and not C.can_grasp(a, t.obj):
                    per[t.obj] += 1
                    break     # one opportunity per (task, state), not per arm
        out[(p["provenance"]["seq"], p["provenance"]["source"])] = per
    return out


def analysis_a(files, probes, widths, masses):
    opp = opportunities(probes)
    print("=" * 78)
    print("A  GRASP ERRORS PER OPPORTUNITY")
    print("   opportunity = open task whose object an idle Franka can reach")
    print("   but cannot grasp, counted once per (task, state, repeat)")
    print("=" * 78)
    for path in files:
        rows = [json.loads(l) for l in open(path) if l.strip()]
        if not rows:
            continue
        model = sorted({r.get("model_alias") for r in rows})[0]
        rung = sorted({r.get("rung") for r in rows})[0]
        err = collections.Counter()
        den = collections.Counter()
        for r in rows:
            k = (r["provenance"]["seq"], r["provenance"]["source"])
            for obj, n in opp.get(k, {}).items():
                den[obj] += n
            if r.get("violation_cause") == "grasp":
                o = (r.get("violation_fields") or {}).get("obj")
                if o:
                    err[o] += 1
        print("\n  %s  %s" % (model.upper(), rung))
        print("    %-20s %7s %7s %7s %7s   %s"
              % ("object", "width", "mass", "errors", "opps", "rate%"))
        for o in sorted(den, key=lambda x: -widths.get(x, 0)):
            n, k = den[o], err.get(o, 0)
            lo, hi = wilson(k, n)
            print("    %-20s %7.3f %7.3f %7d %7d   %5.1f [%4.1f,%5.1f]"
                  % (o, widths.get(o, 0), masses.get(o, 0), k, n,
                     100 * k / n if n else 0, lo or 0, hi or 0))


def analysis_b(files, probes):
    """Was the arm the model named in the idle sentence it was shown?"""
    print("\n" + "=" * 78)
    print("B  ARM_STATE FAILURES: WAS THE NAMED ARM IN THE IDLE LIST?")
    print("=" * 78)
    by = {(p["provenance"]["seq"], p["provenance"]["source"]): p
          for p in probes}
    cache = {}
    print("  %-7s %-11s %7s %9s %9s  %s"
          % ("model", "rung", "arm_st", "not idle", "WAS idle", "note"))
    for path in files:
        rows = [json.loads(l) for l in open(path) if l.strip()]
        if not rows:
            continue
        model = sorted({r.get("model_alias") for r in rows})[0]
        rung = sorted({r.get("rung") for r in rows})[0]
        bad = [r for r in rows if r.get("violation_cause") == "arm_state"]
        absent = present = 0
        examples = []
        for r in bad:
            k = (r["provenance"]["seq"], r["provenance"]["source"])
            ck = (k, rung, r.get("condition", "A"))
            if ck not in cache:
                msgs, _ = pr.render(by[k], rung, r.get("condition", "A"))
                txt = "".join(
                    b.get("text", "") for m in msgs
                    if isinstance(m.get("content"), list)
                    for b in m["content"] if b.get("type") == "text")
                m = IDLE_RE.search(txt)
                cache[ck] = ({a.strip() for a in m.group(1).split(",")}
                             if m else None)
            idle = cache[ck]
            if idle is None:
                continue
            if r.get("arm") in idle:
                present += 1
                if len(examples) < 3:
                    examples.append((k[0], r.get("arm"), sorted(idle)))
            else:
                absent += 1
        note = ""
        if present:
            note = "%d NAMED AN ARM THE PROMPT LISTED AS IDLE" % present
        print("  %-7s %-11s %7d %9d %9d  %s"
              % (model, rung, len(bad), absent, present, note))
        for e in examples:
            print("        seq %s named %s; prompt listed %s" % e)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", required=True)
    ap.add_argument("runs", nargs="+")
    args = ap.parse_args(argv)

    ps = load(args.probes)
    widths, masses = {}, {}
    for p in ps["probes"]:
        for o in p["state"]["objects"]:
            if o.get("grasp_m") is not None:
                widths[o["name"]] = o["grasp_m"]
            if o.get("mass_kg") is not None:
                masses[o["name"]] = o["mass_kg"]

    files = [f for f in sorted(args.runs) if os.path.exists(f)]
    analysis_a(files, ps["probes"], widths, masses)
    analysis_b(files, ps["probes"])
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
