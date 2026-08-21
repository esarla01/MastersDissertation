"""Harness: the FROZEN logging contract (imports the REAL modules).

Guards the locked schema. It must keep passing for every future change:
additive only, never rename, never remove.

  1. M9: the REAL Coordinator._assign pad-block branch increments
     m.pad_wait per tick, keyed by pad NAME; the REAL logger publishes
     pad_wait_by_pad and pad_wait_ticks_total.
  2. The logger emits every locked top-level section and metric key.
  3. Old-shaped coordinators (no pad_wait, no cell) still log cleanly:
     the getattr guards hold.
  4. The disruption engine fires on the SECONDS clock and its events
     carry the fields M10/M12 need.
Run: python3 h_logging_lock.py
"""
import json
import os
import sys
import tempfile
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

# torch stub (established pattern): disruptions imports it for teleports
_torch = types.ModuleType("torch")
_torch.tensor = lambda x, **k: np.asarray(x, dtype=float)
_torch.norm = lambda x: float(np.linalg.norm(np.asarray(x)))
_torch.float32 = np.float32
sys.modules.setdefault("torch", _torch)

from core.control.tasks import Metrics                     # REAL dataclass
from core.control import disruptions as dis                # REAL engine parts
from instrumentation.episode_logger import EpisodeLogger   # REAL logger

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


# 1. Metrics carries pad_wait and it is per-instance (no shared default)
m1, m2 = Metrics(), Metrics()
m1.pad_wait["center"] = 3
check("Metrics.pad_wait exists and is per-instance",
      m1.pad_wait == {"center": 3} and m2.pad_wait == {},
      f"{m1.pad_wait} {m2.pad_wait}")

# 2. logger publishes the locked sections and keys
task = NS(id=0, obj="ycb_mug", dest=(0.1, 0.2), dest_by="model", arm="ur_w",
          done=True, failed=False, attempts=0, submit_tick=0, claim_tick=5,
          done_tick=50, kind="primary", waiting_on=None, required_zones=["ne"])
m = Metrics(blocked={"ur_w": 7}, completed={"ur_w": 1}, requeued=0,
            makespan_ticks=100, contended_claims=1)
m.pad_wait.update({"center": 12, "pad_sw": 3})
coord = NS(m=m, locks=NS(ledger=[{"tick": 1, "action": "acquire",
                                  "zone": "ne", "arm": "ur_w"}]),
           pool=[task], agents={"ur_w": None},
           sim_events=[{"tick": 40, "type": "disruption", "kind": "displace",
                        "object": "ycb_mug", "x": 0.3, "y": 0.2},
                       {"tick": 60, "type": "arm_idle", "arm": "ur_w"}],
           cell=NS(arms={"ur_w": NS(travel_m=2.5)}))
alloc = NS(stats={"calls": 1, "valid_first": 1, "fallback": 0, "noop": 0,
                  "errors": 0, "rule_assigned": 0, "region_mismatches": 0,
                  "unnecessary_pad": 0, "latency_ms_total": 100.0},
           log=[{"round": 1, "result": "valid_first", "task_id": 0,
                 "arm": "ur_w", "rejected": [], "arm_by": "model",
                 "dest_by": "model", "reason": "r", "latency_ms": 100.0},
                {"round": 2, "result": "noop", "latency_ms": 50.0,
                 "attempt": 2, "reason": "waiting for ur_w",
                 "rejected": [{"attempt": 1, "task_id": 0, "arm": "ur_e",
                               "via_pad": None, "basket": "basket_food",
                               "model_reason": "closest",
                               "rejected_because": "arm ur_e is not idle",
                               "unparseable": False}]}])

with tempfile.TemporaryDirectory() as d:
    EpisodeLogger(out_dir=d, seed=0, layout="designed", allocator="vlm1",
                  condition="A", disruptions="mixed",
                  prompt_version="2026-07-25d").finish(
        coord, alloc=alloc, verdict="PASS", filename="ep.json",
        objects=[{"name": "ycb_mug", "category": "kitchenware",
                  "dist_cm": 2.0, "sorted": True, "spawn_xy": [0.3, 0.5]}],
        extra_metrics={"sorted_correct": 1, "sorted_total": 1})
    ep = json.load(open(os.path.join(d, "ep.json")))

LOCKED_SECTIONS = ("meta", "summary", "objects", "per_arm", "tasks",
                   "events", "locks", "metrics", "allocator")
check("all locked top-level sections present",
      all(s in ep for s in LOCKED_SECTIONS),
      str([s for s in LOCKED_SECTIONS if s not in ep]))

LOCKED_META = ("seed", "layout", "allocator", "condition", "disruptions",
               "prompt_version", "schema_version", "verdict")
check("locked meta keys present",
      all(k in ep["meta"] for k in LOCKED_META),
      str([k for k in LOCKED_META if k not in ep["meta"]]))

LOCKED_SUMMARY = ("verdict", "sorted", "makespan_ticks", "tasks_done",
                  "tasks_failed", "requeued", "contended_claims",
                  "blocked_ticks_total", "events_summary")
check("locked summary keys present",
      all(k in ep["summary"] for k in LOCKED_SUMMARY),
      str([k for k in LOCKED_SUMMARY if k not in ep["summary"]]))

LOCKED_TASK = ("id", "object", "dest", "dest_by", "arm", "done", "failed",
               "attempts", "submit_tick", "claim_tick", "done_tick",
               "wait_ticks", "kind", "waiting_on", "required_zones")
check("locked task keys present",
      all(k in ep["tasks"][0] for k in LOCKED_TASK),
      str([k for k in LOCKED_TASK if k not in ep["tasks"][0]]))

check("per_arm carries legs, blocked, travel (D1)",
      ep["per_arm"]["ur_w"] == {"completed_legs": 1, "blocked_ticks": 7,
                                "travel_m": 2.5}, str(ep["per_arm"]))
check("M9 published: by pad and total",
      ep["metrics"]["pad_wait_by_pad"] == {"center": 12, "pad_sw": 3}
      and ep["metrics"]["pad_wait_ticks_total"] == 15,
      str(ep["metrics"].get("pad_wait_by_pad")))
check("D1 total published",
      ep["metrics"]["travel_m_total"] == 2.5)
check("objects carry spawn_xy (M3/M6/M7 ground truth)",
      ep["objects"][0]["spawn_xy"] == [0.3, 0.5])
check("locks: ledger and by_zone rollup",
      ep["locks"]["ledger"] and "ne" in ep["locks"]["by_zone"])
check("allocator: stats and decision log with rejected[]",
      "stats" in ep["allocator"]
      and ep["allocator"]["log"][0]["rejected"] == [])
# v4: a noop carries the attempt it answered on and any refused proposal
noop_entry = [e for e in ep["allocator"]["log"] if e.get("result") == "noop"]
check("v4 noop entry keeps rejected[] and attempt",
      noop_entry and "rejected" in noop_entry[0]
      and noop_entry[0].get("attempt") == 2, str(noop_entry))
check("v4 rejected[] carries the named basket",
      noop_entry and noop_entry[0]["rejected"][0].get("basket")
      == "basket_food", str(noop_entry))
check("disruption event kept with object + coordinates (M10)",
      any(e.get("type") == "disruption" and e.get("object") == "ycb_mug"
          for e in ep["events"]))
check("schema_version is 4 (noop rejections; basket in rejected[])",
      ep["meta"]["schema_version"] == 4, str(ep["meta"]["schema_version"]))
check("arm_idle availability events survive to the JSON",
      any(e.get("type") == "arm_idle" and e.get("arm") == "ur_w"
          for e in ep["events"]))

# 3. old-shaped coordinator still logs (guards hold)
old = NS(m=NS(makespan_ticks=10, requeued=0, completed={}, blocked={}),
         locks=NS(ledger=[]), pool=[], agents={})
with tempfile.TemporaryDirectory() as d:
    EpisodeLogger(out_dir=d, allocator="b1").finish(old, filename="old.json")
    old_ep = json.load(open(os.path.join(d, "old.json")))
check("legacy coordinator logs without pad_wait/travel keys",
      "pad_wait_by_pad" not in old_ep["metrics"]
      and "travel_m_total" not in old_ep["metrics"])

# 4. disruption schedule fires on the SECONDS clock, INSIDE the episode
#
#    The old schedule hardcoded absolute seconds: disable_arm at t = 30.0 s
#    is tick 3600 at 120 Hz, while measured episodes end near 2450 ticks.
#    Every D3 and mixed run ever recorded had an arm-failure disruption
#    that never fired. Times are now fractions of a horizon, so the test
#    is not "are they seconds" but "does every event land in the run".
HORIZON_S = 20.0                       # ~2400 ticks, a measured episode
sched = dis.make_schedule(seed=0, profile="mixed", horizon_s=HORIZON_S)
check("mixed profile schedules events", len(sched) >= 4, str(len(sched)))
check("EVERY event fires inside the episode",
      sched and max(e.t for e in sched) < HORIZON_S,
      f"last event at {max(e.t for e in sched):.1f}s of {HORIZON_S}s")
check("the arm failure in particular fires (it never did before)",
      any(e.kind == "disable_arm" and e.t < HORIZON_S for e in sched),
      str([(e.kind, round(e.t, 1)) for e in sched]))
check("times scale with the horizon",
      max(e.t for e in dis.make_schedule(seed=0, profile="mixed",
                                         horizon_s=40.0))
      == 2 * max(e.t for e in sched))
check("D4 names a category of the RUNNING scene, not a cube colour",
      all("food" in e.params["command"] or "kitchenware" in e.params["command"]
          or "tools" in e.params["command"]
          for e in dis.make_schedule(seed=0, profile="D4",
                                     categories=["food", "kitchenware",
                                                 "tools"])),
      str([e.params for e in dis.make_schedule(seed=0, profile="D4",
                                               categories=["food"])]))
check("none profile is empty (baselines unaffected)",
      dis.make_schedule(seed=0, profile="none") == [])

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
