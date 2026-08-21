"""How much decision density would an availability buffer buy?

The question. Most decisions in a run are taken with one arm idle, so
"which arm" has one answer and there is nothing to judge. A buffer offers
arms that will be free within N ticks as candidates too. Does that create
states with a real choice, and states with a G4 scarcity trap?

This measures it on episodes ALREADY RUN. No Isaac, no model spend.

METHOD. Every consult in the trail carries the tick it was taken at. Every
task in the episode JSON carries exec_start_tick, done_tick and the arm
that executed it, so the tick each busy arm becomes free is reconstructable.
For a buffer of N, an arm busy at tick T is treated as a candidate when it
frees at or before T + N. The state's arm entries are flipped to IDLE
accordingly and the REAL validator is re-run over the result.

WHAT THIS IS NOT. It is a counterfactual on states that arose under the
NO-BUFFER policy. With a buffer the allocator would have made different
choices, so the trajectory would have differed and these exact states would
not have occurred. Read it as an indication of whether the mechanism can
bite, not as a prediction of what a buffered run would produce. Only a real
buffered run answers that, and this exists to decide whether that run is
worth its re-baseline.

Also note episode_buffer_value.py already measured the MAKESPAN value of waiting
for a better arm and found it near zero (2 opportunities in 148 tasks, and
zero on the layout built to favour it). That evidence stands and applies
here: the mechanism is the same. This module asks a different question,
whether the buffer makes decisions well-posed, and the two answers can
legitimately disagree.

Usage:
    python3 analysis/episode/episode_buffer_density.py out/probe_seed_v3_frames/consults.jsonl \\
        out/probe_seed_v3.json 0 100 200 400
"""

import copy
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from analysis.probe_store import legal_options                     # noqa: E402
from analysis.retired.retired_trap_check import classify_decision                  # noqa: E402
from analysis.probe_replay import _consult_entries                 # noqa: E402


def _baskets():
    from ycb_scene import BASKETS
    return BASKETS


def free_ticks(episode_tasks, arm, tick):
    """When the arm executing at `tick` becomes free, or None if idle.

    A task counts as occupying its arm from exec_start_tick until done_tick,
    which is stamped on arrival HOME, the same instant the zone locks are
    released. So done_tick is the tick the arm is genuinely available again.
    """
    best = None
    for t in episode_tasks:
        if t.get("arm") != arm:
            continue
        s, d = t.get("exec_start_tick"), t.get("done_tick")
        if s is None or d is None:
            continue
        if s <= tick < d and (best is None or d < best):
            best = d
    return best


def apply_buffer(probe, episode_tasks, buffer_ticks):
    """A copy of the probe with soon-free arms marked IDLE."""
    out = copy.deepcopy(probe)
    tick = out["provenance"].get("round")
    if tick is None or not buffer_ticks:
        return out, []
    promoted = []
    for a in out["state"].get("arms", []):
        if a.get("state") == "IDLE" or a.get("disabled"):
            continue
        f = free_ticks(episode_tasks, a["name"], tick)
        if f is not None and (f - tick) <= buffer_ticks:
            a["state"] = "IDLE"
            promoted.append((a["name"], f - tick))
    return out, promoted


def measure(trail, episode, buffers=(0, 100, 200, 400), baskets=None):
    baskets = baskets or _baskets()
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
        data = json.load(f)
    tasks = data.get("tasks") or []
    log, _ = _consult_entries((data.get("allocator") or {}).get("log") or [])

    rows = []
    if len(log) != len(probes):
        return {"notes": [f"allocator log has {len(log)} consulted entries "
                          f"against {len(probes)} consults; not aligned"],
                "results": []}

    results = []
    for n in buffers:
        multi = opps = promoted_total = 0
        scored = 0
        for probe, entry in zip(probes, log):
            p, promoted = apply_buffer(probe, tasks, n)
            promoted_total += len(promoted)
            pairs, _ = legal_options(p, baskets)
            by_task = {}
            for tid, a, _k in pairs:
                by_task.setdefault(tid, set()).add(a)
            multi += sum(1 for v in by_task.values() if len(v) >= 2)
            if str(entry.get("result", "")).startswith("valid"):
                scored += 1
                r = classify_decision(p, entry.get("task_id"),
                                      entry.get("arm"), baskets)
                if r and r["verdict"] in ("complied", "stranded"):
                    opps += 1
        results.append({"buffer_ticks": n,
                        "arms_promoted": promoted_total,
                        "tasks_with_choice": multi,
                        "g4_opportunities": opps,
                        "decisions_scored": scored})
    return {"notes": [], "results": results, "consults": len(probes)}


def main(argv=None):
    argv = argv or sys.argv[1:]
    if len(argv) < 2:
        raise SystemExit("usage: python3 analysis/episode/episode_buffer_density.py "
                         "<consults.jsonl> <episode.json> [ticks ...]")
    buffers = [int(x) for x in argv[2:]] or [0, 100, 200, 400]
    rep = measure(argv[0], argv[1], buffers)
    for n in rep["notes"]:
        print("NOTE:", n)
    if not rep["results"]:
        return 1
    print(f"consults: {rep['consults']}")
    print(f"{'buffer':>8} {'promoted':>9} {'tasks w/ choice':>16} "
          f"{'G4 opportunities':>18}")
    for r in rep["results"]:
        print(f"{r['buffer_ticks']:8d} {r['arms_promoted']:9d} "
              f"{r['tasks_with_choice']:16d} {r['g4_opportunities']:18d}")
    print("\nCounterfactual on states that arose WITHOUT a buffer. A buffered "
          "run would have taken different decisions and reached different "
          "states, so read this as whether the mechanism can bite, not as a "
          "prediction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
