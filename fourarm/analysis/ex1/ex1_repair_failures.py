"""repair_failures: give feedback on the rejections a finished run already
recorded, without re-asking the ones that passed.

WHY NOT JUST RE-RUN WITH --repair

A full repair run re-asks attempt 1 for every state. That is the clean
design and it is what probe_replay --repair does. It is also 162 calls per
rung when only about 40 of them can possibly retry.

Re-running ONLY the failed states with a fresh attempt 1 would be cheaper
and WRONG. GPT flickers on roughly 30 percent of grasp-binding states, so
selecting the states that failed and then giving them a new first draw
mixes regression to the mean into the repair rate: some would pass on the
second draw with no feedback involved at all, and the result would
overstate what feedback does.

So this module does not re-ask attempt 1. It rebuilds the exact
conversation that produced the rejection, from the row's own stored reply
and the validator's own stored reason, and asks for attempt 2 onward. One
call per failed state, and the question it answers is the sharp one:
GIVEN that the model got this wrong, does telling it why fix it?

WHAT IS REUSED AND WHAT IS REBUILT

Reused from the row: the raw reply text (verbatim, so the model sees its
own words) and rejected_because (verbatim, so the feedback is the one the
validator actually produced).

Rebuilt from the probe: the prompt, through the same render() the run
used. Not stored in the row, and rebuilding is safer than storing anyway,
since the acceptance test already guarantees a prompt rebuilt from a saved
state is byte-identical to the one that was sent.

Rung, condition and model are read from the row and checked for
consistency across the file, so a repair cannot silently run against a
different configuration than the one it is repairing.

THE LIMITATION TO REPORT

Attempt 1 is not resampled. The repair rate is therefore conditional on
the specific rejections observed in that run rather than on a fresh draw
of them. State it. It is a smaller distortion than the regression artefact
the alternative would introduce, and it is the honest trade for a run that
costs a fifth as many calls.

Usage:

    python3 analysis/ex1/ex1_repair_failures.py --probes probes/ex1_v2.json \\
        --run out/ex1_gpt_L3nw_r3.jsonl --model gpt --attempts 3 \\
        --out out/ex1_gpt_L3nw_repair.jsonl

    python3 analysis/ex1/ex1_repair_failures.py --probes probes/ex1_v2.json \\
        --run out/ex1_gpt_L3nw_r3.jsonl --dry-run
"""

import argparse
import collections
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.decision.state_builder import parse_decision            # noqa: E402
from core.decision.vlm_allocator import (validate_decision,       # noqa: E402
                                         openai_chat)
from analysis.frozen_coord import from_record                     # noqa: E402
from analysis.probe_store import load                             # noqa: E402
from analysis import probe_replay as pr                           # noqa: E402
from experiments.ex1 import anonymise as EX1A                     # noqa: E402


def _one_field(rows, field):
    """The single value of a field across the file, or raise."""
    vals = {r.get(field) for r in rows}
    if len(vals) != 1:
        raise ValueError(
            f"the run file mixes {field} values {sorted(map(str, vals))}. "
            f"A repair must run against one configuration, or the rows it "
            f"writes cannot be attributed to either.")
    return vals.pop()


def repair_row(row, probe, attempts, model_fn, alias, timeout, baskets):
    """Continue one rejected conversation. Returns the repair record."""
    rung, condition = row["rung"], row["condition"]
    messages, _state, mapping = pr.render(probe, rung, condition,
                                          return_map=True)

    out = {
        "provenance": dict(row["provenance"]),
        "rung": rung, "condition": condition,
        "model_alias": alias,
        "repeat_of": row.get("repeat", 1),
        "probe_set_hash": row.get("probe_set_hash"),
        "attempts_allowed": attempts,
        # Attempt 1 is COPIED, never re-asked. These are the fields the
        # rates are conditioned on.
        "attempt1_result": row.get("result"),
        "attempt1_violation": row.get("violation"),
        "attempt1_cause": row.get("violation_cause"),
        "attempt1_task_id": row.get("task_id"),
        "attempt1_arm": row.get("arm"),
        "attempt1_reason": row.get("model_reason"),
        "zero_legal": row.get("zero_legal"),
        "n_legal_pairs": row.get("n_legal_pairs"),
        "accepted_at": None,
        "history": [],
    }
    for c in ("grasp", "reach", "delicate", "payload", "no_route"):
        out["binds_" + c] = row.get("binds_" + c)

    text = row.get("raw")
    why = row.get("rejected_because") or ""
    if not text:
        out["error"] = ("row has no stored reply, so the conversation "
                        "cannot be continued")
        return out

    convo = list(messages)
    for attempt in range(2, attempts + 1):
        fb = pr.REPAIR_FEEDBACK.format(why=why)
        convo = convo + [{"role": "assistant", "content": text},
                         {"role": "user", "content": fb}]
        rec = {"attempt": attempt, "feedback_sent": fb}
        t0 = time.time()
        try:
            try:
                text = model_fn(convo, timeout=timeout, alias=alias)
            except TypeError:
                text = model_fn(convo, timeout=timeout)
            rec["error"] = None
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
            rec["latency_ms"] = round((time.time() - t0) * 1000.0, 1)
            out["history"].append(rec)
            break
        rec["latency_ms"] = round((time.time() - t0) * 1000.0, 1)
        rec["raw"] = text

        d = parse_decision(text)
        rec["decision"] = d
        if d is None:
            rec.update(result="unparseable", violation="PARSE",
                       violation_cause="parse")
            out["history"].append(rec)
            continue
        if mapping is not None:
            d, info = EX1A.deanonymise_decision(d, mapping)
            rec.update(info)
        if d.get("task_id") in (-1, None):
            # Declining after being handed the binding constraint is a
            # different act from declining first, and it ends the loop:
            # there is no rejection left to feed back.
            rec.update(result="noop", model_reason=d.get("reason", ""))
            out["history"].append(rec)
            break

        coord = from_record(probe)     # fresh: the validator writes to it
        ok, _target, _sub, why = validate_decision(dict(d), coord,
                                                   pr.zonemap(), baskets)
        rec.update({
            "result": "valid" if ok else "rejected",
            "task_id": d.get("task_id"), "arm": d.get("arm"),
            "basket": d.get("basket"),
            "model_reason": d.get("reason", ""),
            "rejected_because": why or None,
            # Told exactly why, and proposed it again. A stronger failure
            # than proposing a different wrong pair.
            "repeated_same_pair": (d.get("task_id") == out["attempt1_task_id"]
                                   and d.get("arm") == out["attempt1_arm"]),
        })
        pr._attach_violation(rec, why, d, probe, ok, baskets)
        out["history"].append(rec)
        if ok:
            out["accepted_at"] = attempt
            break
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", required=True)
    ap.add_argument("--run", required=True, help="finished run file")
    ap.add_argument("--out")
    ap.add_argument("--model", help="registry alias; defaults to the run's")
    ap.add_argument("--attempts", type=int, default=3,
                    help="total attempts counting the stored first one")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be repaired, call nothing")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    rows = [json.loads(l) for l in open(args.run) if l.strip()]
    rung = _one_field(rows, "rung")
    condition = _one_field(rows, "condition")
    alias = args.model or _one_field(rows, "model_alias")

    ps = load(args.probes)
    by = {(p["provenance"]["seq"], p["provenance"]["source"]): p
          for p in ps["probes"]}
    want = _one_field(rows, "probe_set_hash")
    if want and ps.get("hash") != want:
        raise SystemExit(
            f"the run was made against probe set {str(want)[:12]} but "
            f"{args.probes} is {str(ps.get('hash'))[:12]}. Repairing "
            f"against a different set would rebuild different prompts.")

    rej = [r for r in rows if r.get("result") == "rejected"]
    if args.limit:
        rej = rej[:args.limit]

    print(f"{args.run}")
    print(f"  rung {rung}  condition {condition}  model {alias}")
    print(f"  {len(rows)} rows, {len(rej)} rejected -> {len(rej)} calls for "
          f"attempt 2" + (f", up to {len(rej) * (args.attempts - 2)} more "
                          f"for later attempts"
                          if args.attempts > 2 else ""))
    c = collections.Counter(r.get("violation_cause") for r in rej)
    print(f"  causes to repair: {dict(c.most_common())}")
    if args.dry_run:
        print("\ndry run: nothing called")
        return 0
    if not args.out:
        ap.error("--out is required unless --dry-run is given")
    if os.path.exists(args.out) and not args.force:
        raise SystemExit(
            f"{args.out} already exists. Refusing to overwrite a paid run "
            f"file; choose a new name or pass --force.")

    baskets = pr._baskets()
    done = []
    with open(args.out, "w") as fh:
        for i, row in enumerate(rej, 1):
            key = (row["provenance"]["seq"], row["provenance"]["source"])
            probe = by.get(key)
            if probe is None:
                print(f"  [{i}/{len(rej)}] SKIP {key}: not in this probe set",
                      file=sys.stderr)
                continue
            out = repair_row(row, probe, args.attempts, openai_chat, alias,
                             args.timeout, baskets)
            done.append(out)
            fh.write(json.dumps(out, default=str) + "\n")
            fh.flush()
            last = (out["history"] or [{}])[-1]
            print(f"  [{i}/{len(rej)}] seq {key[0]} "
                  f"{out['attempt1_cause']} -> "
                  f"{'accepted@%d' % out['accepted_at'] if out['accepted_at'] else last.get('result', 'error')}",
                  file=sys.stderr)

    n = len(done)
    fixed = sum(1 for r in done if r["accepted_at"])
    same = sum(1 for r in done
               if any(h.get("repeated_same_pair") for h in r["history"]))
    noop = sum(1 for r in done
               if any(h.get("result") == "noop" for h in r["history"]))
    print(json.dumps({
        "run": os.path.basename(args.run), "rung": rung, "model": alias,
        "rejections_repaired": n,
        "fixed_by_feedback": fixed,
        "fix_rate_pct": round(100 * fixed / n, 1) if n else None,
        "accepted_at_2": sum(1 for r in done if r["accepted_at"] == 2),
        "accepted_at_3": sum(1 for r in done if r["accepted_at"] == 3),
        "repeated_the_same_pair": same,
        "declined_after_feedback": noop,
        "by_cause": {k: sum(1 for r in done
                            if r["attempt1_cause"] == k and r["accepted_at"])
                     for k in sorted({r["attempt1_cause"] for r in done}
                                     - {None})},
        "of_cause_total": {k: sum(1 for r in done
                                  if r["attempt1_cause"] == k)
                           for k in sorted({r["attempt1_cause"] for r in done}
                                           - {None})},
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
