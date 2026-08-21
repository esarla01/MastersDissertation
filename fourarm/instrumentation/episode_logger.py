"""Episode logger: one machine-readable JSON file per run.

Terminal output does not survive 300 experiment runs; files do. Every run
writes a single JSON containing: run identity (seed, allocator, condition,
prompt version, date), final metrics, the allocator's full decision log,
and each task's life story (submitted / claimed / done ticks, provenance
of arm and destination choices).

Usage:
    logger = EpisodeLogger(seed=0, allocator="vlm", condition="A",
                           prompt_version="2026-07-11")
    ... run the episode ...
    path = logger.finish(coord, alloc=alloc,
                         extra_metrics={"sorted_correct": 8, "total": 8})
"""

import json
import os
import time


class EpisodeLogger:
    def __init__(self, out_dir="out", **meta):
        self.out_dir = out_dir
        self.meta = dict(meta)
        self.meta.setdefault("started_utc",
                             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self.events = []                 # optional free-form notes

    def note(self, **entry):
        """Record a free-form event (e.g. an applied disruption)."""
        self.events.append(entry)

    @staticmethod
    def _task_record(t):
        wait = (t.claim_tick - t.submit_tick
                if t.claim_tick is not None and t.submit_tick is not None
                else None)
        return {
            "id": t.id, "object": t.obj,
            "dest": list(t.dest) if t.dest is not None else None,
            "dest_by": t.dest_by,
            "arm": getattr(t, "arm", None),
            "done": t.done, "failed": t.failed, "attempts": t.attempts,
            "submit_tick": t.submit_tick, "claim_tick": t.claim_tick,
            "done_tick": t.done_tick, "wait_ticks": wait,
            # per-task execution window (additive, 2026-07-29): the span the
            # timing model must be calibrated against. getattr-guarded so
            # older Task objects and any non-standard caller still log.
            "exec_start_tick": getattr(t, "exec_start_tick", None),
            "travel_leg_m": getattr(t, "travel_leg_m", None),
            "blocked_ticks": getattr(t, "blocked_ticks", None),
            "kind": getattr(t, "kind", "primary"),
            "waiting_on": getattr(t, "waiting_on", None),
            "required_zones": list(getattr(t, "required_zones", [])),
        }

    def finish(self, coord, alloc=None, extra_metrics=None, filename=None,
               objects=None, verdict=None):
        """Write the episode JSON (schema v2).

        Sections: meta (identity + verdict), summary (the run at a
        glance), objects (per-object final result), per_arm, tasks (life
        stories incl. kind and waiting_on), events (typed, tick-sorted
        timeline), locks (by_zone rollup + full ledger), metrics
        (quality numbers), allocator (stats + decision log).

        objects: optional list of {"name","category","dist_cm","sorted"}.
        verdict: optional "PASS"/"CHECK" string from the run script.
        All new arguments are optional: cube-era call sites work
        unchanged and simply omit the sections.
        """
        extra = dict(extra_metrics or {})
        tasks = [self._task_record(t) for t in coord.pool]
        waits = [t["wait_ticks"] for t in tasks if t["wait_ticks"] is not None]

        # ---- events: one tick-sorted typed timeline -----------------------
        events = list(getattr(coord, "sim_events", []))
        events += list(getattr(coord, "prox_events", []))
        events += self.events
        events.sort(key=lambda e: e.get("tick", 0))
        counts = {}
        for e in events:
            counts[e.get("type", "note")] = counts.get(e.get("type", "note"), 0) + 1

        # ---- summary: the run at a glance ---------------------------------
        summary = {
            "verdict": verdict,
            "sorted": (f"{extra['sorted_correct']}/{extra['sorted_total']}"
                       if "sorted_correct" in extra else None),
            "makespan_ticks": coord.m.makespan_ticks,
            "tasks_done": sum(1 for t in coord.pool if t.done),
            "tasks_failed": sum(1 for t in coord.pool if t.failed),
            "requeued": coord.m.requeued,
            "contended_claims": getattr(coord.m, "contended_claims", 0),
            "blocked_ticks_total": sum(coord.m.blocked.values()),
            "events_summary": counts,
        }

        # ---- per-arm rollup (joins the old parallel dicts) ----------------
        # Arms from coord.agents are included even with zero completed and
        # zero blocked, so D1 travel is reported for every arm.
        arm_names = (set(coord.m.completed) | set(coord.m.blocked)
                     | set(getattr(coord, "agents", {})))
        per_arm = {a: {"completed_legs": coord.m.completed.get(a, 0),
                       "blocked_ticks": coord.m.blocked.get(a, 0)}
                   for a in arm_names}
        cell_arms = getattr(getattr(coord, "cell", None), "arms", None) or {}
        for a in per_arm:                    # D1: getattr-guarded, additive
            travel = getattr(cell_arms.get(a), "travel_m", None)
            if travel is not None:
                per_arm[a]["travel_m"] = round(travel, 4)

        # ---- locks: rollup over the untouched ledger ----------------------
        ledger = coord.locks.ledger if hasattr(coord.locks, "ledger") else []
        by_zone = {}
        for e in ledger:
            z = by_zone.setdefault(e["zone"], {"acquires": 0, "reserves": 0})
            if e["action"] == "acquire":
                z["acquires"] += 1
            elif e["action"] == "reserve":
                z["reserves"] += 1

        # ---- quality metrics ----------------------------------------------
        metrics = {
            "wait_ticks_mean": (sum(waits) / len(waits)) if waits else None,
            "wait_ticks_max": max(waits) if waits else None,
        }
        for k, v in extra.items():
            if k not in ("sorted_correct", "sorted_total"):
                metrics[k] = v
        metrics["sorted_correct"] = extra.get("sorted_correct")
        metrics["sorted_total"] = extra.get("sorted_total")
        if alloc is not None and alloc.stats.get("calls"):
            metrics["model_latency_ms_mean"] = round(
                alloc.stats.get("latency_ms_total", 0.0)
                / alloc.stats["calls"], 1)
        if hasattr(coord, "min_pair_dist") and coord.min_pair_dist:
            metrics["min_arm_distance_m"] = dict(coord.min_pair_dist)
        travels = [v["travel_m"] for v in per_arm.values()
                   if "travel_m" in v]
        if travels:                          # D1 rollup, absent when unwired
            metrics["travel_m_total"] = round(sum(travels), 4)
        pad_wait = getattr(coord.m, "pad_wait", None)   # M9, getattr-guarded
        if pad_wait is not None:
            metrics["pad_wait_by_pad"] = dict(pad_wait)
            metrics["pad_wait_ticks_total"] = sum(pad_wait.values())

        meta = dict(self.meta)
        meta["schema_version"] = 4    # v4: rejected[] on noops; basket in rejected[]
        # Settle-wait policy, stamped so no episode can be mislabelled: it
        # changes the SUBSTRATE every allocator runs on, so pooling a
        # settle_wait=0 episode with a settle_wait=200 one would compare
        # two different cells. getattr-guarded, as new attributes must be.
        sw = getattr(coord, "settle_wait", 0)
        meta["settle_wait"] = sw
        meta["settle_phases"] = getattr(coord, "settle_phases", None)
        if sw:
            metrics["settle"] = dict(getattr(coord, "m_settle", {}))
        dwell = getattr(coord, "phase_dwell", None)
        if dwell:
            metrics["phase_dwell"] = list(dwell)
        meta["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime())
        if verdict is not None:
            meta["verdict"] = verdict

        data = {"meta": meta, "summary": summary}
        if objects is not None:
            data["objects"] = objects
        data.update({"per_arm": per_arm, "tasks": tasks, "events": events,
                     "locks": {"by_zone": by_zone, "ledger": ledger},
                     "metrics": metrics})
        if alloc is not None:
            data["allocator"] = {"stats": dict(alloc.stats),
                                 "log": list(alloc.log)}
        os.makedirs(self.out_dir, exist_ok=True)
        if filename is None:
            tag = self.meta.get("allocator", "run")
            stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
            filename = f"episode_{tag}_{stamp}.json"
        path = os.path.join(self.out_dir, filename)
        with open(path, "w") as f:
            json.dump(data, f, indent=1)
        print(f"[log] episode written to {path}")
        return path