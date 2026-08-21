"""Does the model follow G4, the scarce-arm rule?

G4 in the prompt reads: "Protect scarce arms: if the arm you are about to
use is the only one that could serve another queued task, prefer an
alternative for this one." It is the trap rule, and EX3 is built on the
assumption that it is live guidance rather than decoration.

This module answers that from episodes you have already run. No model
spend, no simulator, no new episodes.

WHAT COUNTS AS AN OPPORTUNITY. A decision is a G4 opportunity when, on the
state the model actually saw:

  1. the task it chose had TWO OR MORE legal arms, so a choice existed;
  2. at least one of those arms was SCARCE, meaning some other open task
     could be served by that arm and by no other idle arm; and
  3. at least one was SAFE, meaning not uniquely needed elsewhere.

Both must be present. If every option was scarce the model could not
comply, and if none was, complying was free. Neither case tests anything,
so both are excluded and counted separately.

Choosing a safe arm is compliance. Choosing a scarce one strands the other
task until an arm frees up.

THE CHANCE FLOOR IS COMPUTED, NOT ASSUMED. For each opportunity, a model
picking uniformly among the legal arms would comply with probability
safe/total. Summing those gives the rate to beat. Without it a measured
70% is uninterpretable, because if 70% of options were safe anyway then
70% is exactly what indifference looks like.

WHAT THIS DOES NOT MEASURE. Only accepted decisions are scored: a rejected
proposal never became an allocation, and a noop allocated nothing. It also
takes the state at face value, so an arm that is about to free up counts as
busy, which is what the model was shown.

Usage:
    python3 analysis/retired_trap_check.py out/probe_seed_v3_frames/consults.jsonl \\
        out/probe_seed_v3.json
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis.frozen_coord import from_record                      # noqa: E402
from analysis.probe_store import legal_options                     # noqa: E402
from analysis.probe_replay import _consult_entries                 # noqa: E402


def _baskets():
    from ycb_scene import BASKETS
    return BASKETS


def classify_decision(probe, task_id, arm, baskets=None):
    """One accepted decision against G4.

    Returns a dict with the verdict and everything needed to audit it, or
    None when the decision is not a G4 opportunity at all.
    """
    baskets = baskets or _baskets()
    pairs, _ = legal_options(probe, baskets)

    by_task = {}
    for tid, a, _kind in pairs:
        by_task.setdefault(tid, set()).add(a)

    options = sorted(by_task.get(task_id, set()))
    if len(options) < 2:
        return {"verdict": "no_choice", "task_id": task_id, "arm": arm,
                "options": options}

    # An arm is SCARCE when some OTHER open task can be served by it and by
    # no other idle arm. Spending it strands that task.
    scarce = {}
    for a in options:
        for other, arms_for_other in by_task.items():
            if other == task_id:
                continue
            if arms_for_other == {a}:
                scarce.setdefault(a, []).append(other)
    safe = [a for a in options if a not in scarce]

    if not scarce:
        return {"verdict": "no_scarcity", "task_id": task_id, "arm": arm,
                "options": options}
    if not safe:
        return {"verdict": "all_scarce", "task_id": task_id, "arm": arm,
                "options": options, "scarce": {k: v for k, v in
                                               scarce.items()}}

    return {"verdict": "complied" if arm in safe else "stranded",
            "task_id": task_id, "arm": arm, "options": options,
            "safe": safe, "scarce": {k: v for k, v in scarce.items()},
            "stranded_tasks": scarce.get(arm, []),
            # what indifference would have scored on THIS decision
            "chance": len(safe) / len(options)}


def check_episode(trail, episode, baskets=None):
    baskets = baskets or _baskets()
    frames_dir = os.path.dirname(os.path.abspath(trail))

    probes = []
    with open(trail) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            probes.append({"state": rec["state"],
                           "positions_exact": rec.get("positions_exact"),
                           "frame_path": None,
                           "provenance": {"seq": rec.get("seq"),
                                          "round": rec.get("round")}})

    with open(episode) as f:
        raw = (json.load(f).get("allocator") or {}).get("log") or []
    log, _ = _consult_entries(raw)

    report = {"trail": trail, "episode": episode, "consults": len(probes),
              "rows": [], "notes": []}
    if len(log) != len(probes):
        report["notes"].append(
            f"allocator log has {len(log)} consulted entries against "
            f"{len(probes)} consults, so they cannot be aligned. Are the two "
            f"files from the same run?")
        return report

    for probe, entry in zip(probes, log):
        if not str(entry.get("result", "")).startswith("valid"):
            continue
        row = classify_decision(probe, entry.get("task_id"),
                                entry.get("arm"), baskets)
        if row is None:
            continue
        row["seq"] = probe["provenance"]["seq"]
        row["round"] = probe["provenance"]["round"]
        row["model_reason"] = entry.get("reason", "")
        report["rows"].append(row)

    opps = [r for r in report["rows"]
            if r["verdict"] in ("complied", "stranded")]
    complied = [r for r in opps if r["verdict"] == "complied"]
    report["summary"] = {
        "accepted_decisions": len(report["rows"]),
        "no_choice": sum(1 for r in report["rows"]
                         if r["verdict"] == "no_choice"),
        "no_scarcity": sum(1 for r in report["rows"]
                           if r["verdict"] == "no_scarcity"),
        "all_scarce": sum(1 for r in report["rows"]
                          if r["verdict"] == "all_scarce"),
        "g4_opportunities": len(opps),
        "complied": len(complied),
        "stranded": len(opps) - len(complied),
        "compliance_rate": (len(complied) / len(opps)) if opps else None,
        # the rate indifference would have produced on these same decisions
        "chance_rate": (sum(r["chance"] for r in opps) / len(opps))
                       if opps else None,
    }
    return report


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) != 2:
        raise SystemExit("usage: python3 analysis/retired_trap_check.py "
                         "<consults.jsonl> <episode.json>")
    rep = check_episode(argv[0], argv[1])
    for n in rep["notes"]:
        print("NOTE:", n)
    s = rep.get("summary")
    if not s:
        return 1
    print(json.dumps(s, indent=1))
    if s["g4_opportunities"]:
        print("\nper opportunity:")
        for r in rep["rows"]:
            if r["verdict"] in ("complied", "stranded"):
                print(f"  seq {r['seq']:3d} round {r['round']:5d} "
                      f"{r['verdict']:9s} task {r['task_id']} -> {r['arm']} "
                      f"| options {r['options']} safe {r['safe']} "
                      f"| strands {r['stranded_tasks']} "
                      f"| chance {r['chance']:.2f}")
                print(f"        reason: {r['model_reason'][:90]}")
    else:
        print("\nNo G4 opportunity arose in this episode. That is a fact "
              "about the CELL, not about the model: either the chosen tasks "
              "had one legal arm, or no arm was uniquely needed elsewhere. "
              "Counts above say which.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
