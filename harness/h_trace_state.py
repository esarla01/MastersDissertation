"""Harness: trace viewer state blocks (imports the REAL trace_episode).

Builds an episode with the REAL logger (tasks with known lifecycles, a
lock ledger, a vlm decision log) plus a fake audit trail directory, then
checks reconstruct() and the printed trace:
  1. At a mid-episode round: the busy arm shows its task/object/zones,
     idle set is the complement, queued/parked classified correctly
     (waiting_on gates parked vs queued), done count right.
  2. Lock ledger replay: held zone at that round, released later;
     reservations tracked.
  3. "model saw" line appears from consults.jsonl and shows the model's
     idle set, enabling execution-vs-model-view cross-checks.
  4. Multiple episode files in one invocation both get traced.
Run: python3 h_trace_state.py
"""
import io
import json
import os
import sys
import tempfile
import types
import contextlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from instrumentation.episode_logger import EpisodeLogger   # REAL logger
from analysis.episode import episode_trace as tr                    # REAL viewer

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


def task(i, obj, arm, sub, claim, done_t, kind="primary", waiting=None):
    return NS(id=i, obj=obj, dest=(0.1, 0.2), dest_by="given", arm=arm,
              done=done_t is not None, failed=False, attempts=0,
              submit_tick=sub, claim_tick=claim, done_tick=done_t,
              kind=kind, waiting_on=waiting, required_zones=["nw"])


POOL = [
    task(0, "ycb_soup_can", "ur_w", 0, 10, 300),       # done before r=500
    task(1, "ycb_banana", "franka_n", 0, 400, 900),    # busy at r=500
    task(2, "ycb_gelatin_box", None, 0, None, None,    # parked on leg 3
         waiting=3),
    task(3, "ycb_gelatin_box", None, 0, None, None,    # queued leg
         kind="handover_leg"),
    task(4, "ycb_mug", None, 0, None, None),           # queued
]
IDLE_EVENTS = [   # schema v3 availability ledger
    {"tick": 330, "type": "arm_idle", "arm": "ur_w"},   # folded, assignable
    # franka_n finishes task 1 at 900 but no arm_idle before tick 500
]
LEDGER = [
    {"tick": 5, "action": "acquire", "zone": "nw", "arm": "ur_w"},
    {"tick": 300, "action": "release", "zone": "nw", "arm": "ur_w"},
    {"tick": 400, "action": "acquire", "zone": "center", "arm": "franka_n"},
    {"tick": 450, "action": "reserve", "zone": "ne", "arm": "ur_e"},
    {"tick": 900, "action": "release", "zone": "center", "arm": "franka_n"},
]
LOG = [
    {"round": 500, "result": "fallback", "latency_ms": 6000.0,
     "rejected": [{"attempt": 1, "task_id": 4, "arm": "franka_s",
                   "via_pad": None, "model_reason": "closest",
                   "rejected_because": "arm franka_s cannot grasp object",
                   "unparseable": False}],
     "last_reason": "arm franka_s cannot grasp object"},
    {"round": 500, "result": "rule_assigned", "task_id": 4,
     "arm": "ur_e", "arm_by": "rule", "dest_by": "oracle"},
    {"round": 500, "result": "noop", "latency_ms": 5000.0,
     "reason": "waiting for ur_w"},
]

with tempfile.TemporaryDirectory() as d:
    m = NS(makespan_ticks=1000, requeued=0,
           completed={"ur_w": 1, "franka_n": 1},
           blocked={"ur_w": 0, "ur_e": 0, "franka_n": 0, "franka_s": 0})
    coord = NS(m=m, locks=NS(ledger=LEDGER), pool=POOL,
               sim_events=IDLE_EVENTS,
               agents={a: None for a in m.blocked},
               cell=NS(arms={a: NS(travel_m=1.0) for a in m.blocked}))
    alloc = NS(stats={"noop": 1, "calls": 1}, log=LOG)
    EpisodeLogger(out_dir=d, seed=0, layout="designed", allocator="vlm2",
                  condition="V").finish(coord, alloc=alloc, verdict="PASS",
                                        filename="vlm2_x.json",
                                        extra_metrics={"sorted_correct": 5,
                                                       "sorted_total": 5})
    # audit trail with the model's view at round 500
    fdir = os.path.join(d, "vlm2_x_frames")
    os.makedirs(fdir)
    state_json = json.dumps({
        "arms": [{"name": "ur_e", "state": "IDLE", "disabled": False},
                 {"name": "franka_n", "state": "TO_PLACE",
                  "disabled": False}],
        "tasks": [{"id": 4, "object": "ycb_mug", "status": "queued"}],
        "zone_locks": {"center": "franka_n"}})
    rec = {"seq": 1, "round": 500, "condition": "V", "image_file": "x.png",
           "messages": [{"role": "system", "content": "s"},
                        {"role": "user", "content": [
                            {"type": "text",
                             "text": "Cell state:\n" + state_json
                                     + "\nIdle arms right now: ur_e."}]}]}
    with open(os.path.join(fdir, "consults.jsonl"), "w") as f:
        f.write(json.dumps(rec) + "\n")

    ep = json.load(open(os.path.join(d, "vlm2_x.json")))

    s = tr.reconstruct(ep, 500)
    check("busy arm identified",
          [t["id"] for t in s["busy"]] == [1], str([t["id"] for t in s["busy"]]))
    check("availability from the v3 ledger, not task records",
          s["status"] == {"ur_w": "IDLE", "franka_n": "BUSY",
                          "ur_e": "IDLE", "franka_s": "IDLE"},
          str(s["status"]))
    s310 = tr.reconstruct(ep, 310)
    check("done but not yet folded shows RESETTING (not assignable)",
          s310["status"]["ur_w"] == "RESETTING", str(s310["status"]))
    s340 = tr.reconstruct(ep, 340)
    check("assignable only after the arm_idle event",
          s340["status"]["ur_w"] == "IDLE", str(s340["status"]))
    legacy = dict(ep); legacy["events"] = [e for e in ep["events"]
                                           if e.get("type") != "arm_idle"]
    check("v2 episode (no ledger) is flagged, not guessed silently",
          tr.reconstruct(legacy, 310)["status"]["ur_w"] == "IDLE?"
          and tr.reconstruct(legacy, 310)["have_ledger"] is False)
    check("queued vs parked split on waiting_on",
          [t["id"] for t in s["queued"]] == [3, 4]
          and [t["id"] for t in s["parked"]] == [2],
          f"queued={[t['id'] for t in s['queued']]} "
          f"parked={[t['id'] for t in s['parked']]}")
    check("done count", s["done"] == 1, str(s["done"]))
    check("ledger replay: center held, nw released, ne reserved",
          s["held"] == {"center": "franka_n"}
          and s["resv"] == {"ne": ["ur_e"]},
          f"held={s['held']} resv={s['resv']}")

    av = tr.load_audit_views(os.path.join(d, "vlm2_x.json"))
    check("audit views parsed in consult order",
          len(av) == 1 and av[0]["idle"] == ["ur_e"]
          and av[0]["queued_ids"] == [4] and av[0]["seq"] == 1, str(av))

    buf = io.StringIO()
    sys.argv = ["episode_trace.py", os.path.join(d, "vlm2_x.json"),
                os.path.join(d, "vlm2_x.json"), "--rounds-only"]
    with contextlib.redirect_stdout(buf):
        tr.main()
    out = buf.getvalue()
    check("distinct BEFORE and AFTER blocks",
          "STATE BEFORE" in out and "STATE AFTER" in out
          and out.index("STATE BEFORE") < out.index("DECISIONS")
          < out.index("STATE AFTER"))
    check("per-decision model-saw line printed",
          "model saw: idle=['ur_e']" in out
          and out.index("model saw") < out.index("waiting because"))
    check("busy arm line shows task and object",
          "BUSY  task  1 banana" in out, "")
    check("rejected proposal rendered with task, arm and cause",
          "REJECTED attempt 1: proposed task 4 (mug) -> franka_s" in out
          and "rejected because: arm franka_s cannot grasp object" in out)
    check("fallback states the consequence",
          "FALLBACK to rule floor after 1 rejected attempt(s)" in out)
    check("rule assignment named",
          "-> RULE ASSIGNED task 4 (mug) to ur_e" in out)
    check("acceptance uses ASSIGN wording where applicable",
          "NOOP: deliberate wait" in out)
    check("multi-file: two traces in one run",
          out.count("======== 1 HEADER") == 2)

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
