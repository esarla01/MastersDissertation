"""Harness: PROPOSED-vs-EXECUTED reporting (imports the REAL episode_metrics.py).

Builds an episode with the REAL EpisodeLogger whose decision log contains
a hand-designed set of proposals, then checks episode_metrics.py's model-level
figures against values computed by hand here.

Scenario (spawn positions are the REAL designed ones, so the mandatory
relay set comes from the REAL rasters, not from an assumption):
  task 0 banana  at (0.05, 0.30)   direct for franka_n   -> NOT mandatory
  task 1 mustard at (0.75, -0.25)  east side, food nw    -> MANDATORY relay
  task 2 mustard handover leg (executed by the rule floor)

Decision log:
  A valid_first          task 0 -> franka_n, no pad, no rejections
  B fallback with two rejections:
      1: task 1 -> ur_e, no pad, "cannot reach both ...; a handover pad
         is needed"                        -> cause reach, missed necessity
      2: task 0 -> ur_w VIA center, "arm ur_w is not idle"
                                           -> cause busy_arm, relay proposal
                                              for a task that needs none
  C valid_after_feedback task 1 -> ur_w VIA pad_sw, after one rejection:
      1: task 1 -> franka_s VIA pad_sw, "the object is already at pad
         pad_sw ..."                       -> cause pad_rule, STALE
  D noop

Hand-computed expectations:
  proposals          = 2 accepted + 3 rejected            = 5
  raw validity       = 2 / 5                              = 0.4
  causes             = reach 1, busy_arm 1, pad_rule 1
  model relay set    = {0 (via center), 1 (via pad_sw)}   = {0, 1}
  stale relays       = 1   (the pad_rule one is NOT credited)
  missed necessity   = {1}
  mandatory (raster) = {1}
  model precision    = |{0,1} & {1}| / 2                  = 0.5
  model recall       = 1 / 1                              = 1.0
Run: python3 h_model_relay.py
"""
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from instrumentation.episode_logger import EpisodeLogger   # REAL logger
from analysis.episode import episode_metrics as az                          # REAL pipeline

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


def T(i, obj, arm, claim, done, kind="primary", dest_by="model"):
    return NS(id=i, obj=obj, dest=(-0.70, 0.50), dest_by=dest_by, arm=arm,
              done=done is not None, failed=False, attempts=0, submit_tick=0,
              claim_tick=claim, done_tick=done, kind=kind, waiting_on=None,
              required_zones=[])


POOL = [T(0, "ycb_banana", "franka_n", 10, 400),
        T(1, "ycb_mustard", "ur_w", 900, 1200),
        T(2, "ycb_mustard", "franka_s", 500, 800, kind="handover_leg",
          dest_by="rule")]

OBJECTS = [
    {"name": "ycb_banana", "category": "food", "dist_cm": 2.0,
     "sorted": True, "spawn_xy": [0.05, 0.30]},
    {"name": "ycb_mustard", "category": "food", "dist_cm": 3.0,
     "sorted": True, "spawn_xy": [0.75, -0.25]},
]

LOG = [
    {"round": 1, "result": "valid_first", "task_id": 0, "arm": "franka_n",
     "rejected": [], "arm_by": "model", "dest_by": "model", "via_pad": None,
     "latency_ms": 4000.0, "reason": "delicate, franka_n reaches both"},
    {"round": 500, "result": "fallback", "latency_ms": 7000.0,
     "rejected": [
         {"attempt": 1, "task_id": 1, "arm": "ur_e", "via_pad": None,
          "model_reason": "ur_e can reach both",
          "rejected_because": ("arm ur_e cannot reach both the object and "
                               "destination; a handover pad is needed"),
          "unparseable": False},
         {"attempt": 2, "task_id": 0, "arm": "ur_w", "via_pad": "center",
          "model_reason": "route the banana via the centre pad",
          "rejected_because": "arm ur_w is not idle", "unparseable": False}],
     "last_reason": "arm ur_w is not idle"},
    {"round": 900, "result": "valid_after_feedback", "task_id": 1,
     "arm": "ur_w", "via_pad": "pad_sw", "arm_by": "model",
     "dest_by": "oracle", "latency_ms": 7000.0, "reason": "relay the mustard",
     "rejected": [
         {"attempt": 1, "task_id": 1, "arm": "franka_s", "via_pad": "pad_sw",
          "model_reason": "franka_s can relay it",
          "rejected_because": ("the object is already at pad pad_sw; a "
                               "handover through it would move nothing"),
          "unparseable": False}]},
    {"round": 1000, "result": "noop", "latency_ms": 6000.0,
     "reason": "waiting for ur_w"},
]

with tempfile.TemporaryDirectory() as d:
    m = NS(makespan_ticks=1200, requeued=0,
           completed={"ur_w": 1, "franka_n": 1, "franka_s": 1, "ur_e": 0},
           blocked={"ur_w": 10, "ur_e": 0, "franka_n": 5, "franka_s": 3})
    m.pad_wait = {"pad_sw": 4}
    coord = NS(m=m, locks=NS(ledger=[]), pool=POOL,
               agents={a: None for a in m.blocked},
               cell=NS(arms={a: NS(travel_m=3.0) for a in m.blocked}))
    alloc = NS(stats={"calls": 6, "valid_first": 1,
                      "valid_after_feedback": 1, "fallback": 1, "noop": 1,
                      "errors": 0, "rule_assigned": 1, "oracle_resolved": 1,
                      "unnecessary_pad": 0, "region_mismatches": 0,
                      "latency_ms_total": 24000.0},
               log=LOG)
    EpisodeLogger(out_dir=d, seed=0, layout="designed", allocator="vlm1",
                  condition="A", disruptions="none",
                  prompt_version="2026-07-25d").finish(
        coord, alloc=alloc, objects=OBJECTS, verdict="PASS",
        filename="ep.json",
        extra_metrics={"sorted_correct": 2, "sorted_total": 2})
    ep = json.load(open(os.path.join(d, "ep.json")))

# ground truth from the REAL rasters, asserted rather than assumed
mand = az.mandatory_task_ids(ep)
check("mandatory relay set from the real rasters is {1}",
      mand == {1}, str(mand))

p = az.proposal_layer(ep, mandatory=mand)
check("proposal count", p["P_proposals"] == 5, str(p["P_proposals"]))
check("accepted split",
      p["P_accepted_first"] == 1 and p["P_accepted_after_feedback"] == 1,
      f"{p['P_accepted_first']}/{p['P_accepted_after_feedback']}")
check("rejected count", p["P_rejected"] == 3, str(p["P_rejected"]))
check("raw validity 0.4", p["P_raw_validity"] == 0.4,
      str(p["P_raw_validity"]))
check("rejection causes classified",
      p["P_rejected_by_cause"] == {"reach": 1, "busy_arm": 1, "pad_rule": 1},
      str(p["P_rejected_by_cause"]))
check("model relay proposals are {0, 1}",
      p["P_relay_proposals"] == [0, 1], str(p["P_relay_proposals"]))
check("stale relay NOT credited (pad_rule counted separately)",
      p["P_stale_relay_proposals"] == 1, str(p["P_stale_relay_proposals"]))
check("missed necessity {1}", p["P_missed_necessity"] == [1],
      str(p["P_missed_necessity"]))
check("model relay precision 0.5",
      p["P_relay_precision_model"] == 0.5, str(p["P_relay_precision_model"]))
check("model relay recall 1.0",
      p["P_relay_recall_model"] == 1.0, str(p["P_relay_recall_model"]))
check("noops counted, not treated as proposals",
      p["P_noops"] == 1 and p["P_proposals"] == 5)

# the two layers stay separate: EXECUTED relay figures are system level
full = az.episode_metrics(ep, cycles_by_arm=az.observed_cycles([ep]))
check("EXECUTED relay recall is system level (1.0 here)",
      full["M7_relay_recall"] == 1.0, str(full.get("M7_relay_recall")))
check("both layers present and distinct",
      full["M6_relay_precision"] == 1.0
      and full["P_relay_precision_model"] == 0.5,
      f"executed={full.get('M6_relay_precision')} "
      f"model={full.get('P_relay_precision_model')}")

# episodes with no decision log (b1) must not grow P_ fields
b1 = dict(ep)
b1["allocator"] = {}
check("classical episodes carry no PROPOSED layer",
      "P_proposals" not in az.episode_metrics(b1))

# unparseable replies are flagged, not silently dropped
p2 = az.proposal_layer({"allocator": {"log": [
    {"round": 1, "result": "fallback", "rejected": [
        {"attempt": 1, "task_id": None, "arm": None, "via_pad": None,
         "model_reason": "", "rejected_because": "reply was not valid JSON",
         "unparseable": True}]}]}}, mandatory=set())
check("unparseable classified",
      p2["P_rejected_by_cause"] == {"unparseable": 1},
      str(p2["P_rejected_by_cause"]))

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
