"""Harness: input sufficiency audit (imports the REAL episode_input_audit.py).

Builds an episode plus a matching consults.jsonl in which each rejection
is engineered to land in a KNOWN verdict class, then checks the auditor
assigns exactly those verdicts. Also checks the coherence pass catches a
state whose prose idle list disagrees with arms[].

Engineered cases (consult order):
  1 busy_arm    state shows ur_w TO_PLACE            -> MODEL_ERROR
  2 busy_arm    state shows ur_w IDLE                -> CONTRADICTORY
  3 capability  mug grasp 0.081 > franka 0.08        -> MODEL_ERROR
  4 pad_rule    clamp at_pad=center                  -> MODEL_ERROR
  5 reach       franka_s to a far object             -> MODEL_ERROR
  6 reach       object and basket both inside the
                arm's radius, guard still refused    -> CIRCLE_OK
  7 reach       sorting task, correct basket unreachable,
                another basket reachable, basket NOT logged  -> MODEL_ERROR
  8 reach       same, but the model's basket IS logged and
                is reachable                                 -> CIRCLE_OK
  9 coherence   prose says ur_e idle, arms[] does not
Run: python3 h_input_audit.py
"""
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from instrumentation.episode_logger import EpisodeLogger   # REAL logger
from analysis.episode import episode_input_audit as ia                     # REAL auditor

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


def arm(name, kind, base, reach, state="IDLE", grasp=0.14, delicate_ok=False):
    return {"name": name, "type": kind, "base_xy": base, "reach_m": reach,
            "max_grasp_m": grasp, "payload_kg": 10.0,
            "delicate_ok": delicate_ok, "state": state, "disabled": False,
            "holding": None, "ee_xy": base}


def obj(name, xy, grasp=0.05, at_pad=None, delicate=False, cat="food"):
    return {"name": name, "category": cat, "xy": xy, "zone": "nw",
            "at_pad": at_pad, "grasp_m": grasp, "mass_kg": 0.5,
            "delicate": delicate, "carried_by": None}


BASE_ARMS = [arm("ur_w", "ur10", [-1.05, 0.0], 1.3),
             arm("ur_e", "ur10", [1.05, 0.0], 1.3),
             arm("franka_s", "franka", [0.0, -0.6], 0.855, grasp=0.08),
             arm("franka_n", "franka", [0.0, 0.6], 0.855, grasp=0.08,
                 delicate_ok=True)]
BASKETS = {"basket_food": {"xy": [-0.7, 0.5]},
           "basket_kitchenware": {"xy": [0.7, 0.5]}}
PADS = {"center": {"xy": [0.0, 0.0], "arms": ["ur_w", "ur_e"]}}


def state_for(case):
    arms = [dict(a) for a in BASE_ARMS]
    objs = [obj("ycb_mug", [0.3, 0.55], grasp=0.081, cat="kitchenware"),
            obj("ycb_clamp", [0.0, 0.0], at_pad="center", cat="food"),
            obj("ycb_far", [1.0, -0.5], cat="food"),
            obj("ycb_near", [-0.9, 0.3], cat="food"),
            obj("ycb_gel", [0.82, 0.22], cat="food")]
    tasks = [{"id": 5, "object": "ycb_mug", "dest_xy": None,
              "dest_zone": "unassigned", "status": "queued", "attempts": 0},
             {"id": 9, "object": "ycb_clamp", "dest_xy": [-0.7, -0.5],
              "dest_zone": "sw", "status": "queued", "attempts": 0},
             {"id": 3, "object": "ycb_far", "dest_xy": [-0.7, 0.5],
              "dest_zone": "nw", "status": "queued", "attempts": 0},
             {"id": 1, "object": "ycb_near", "dest_xy": [-0.7, 0.5],
              "dest_zone": "nw", "status": "queued", "attempts": 0},
             {"id": 7, "object": "ycb_gel", "dest_xy": None,
              "dest_zone": "unassigned", "status": "queued", "attempts": 0}]
    if case == "busy":                       # ur_w genuinely occupied
        arms[0]["state"] = "TO_PLACE"
    idle = [a["name"] for a in arms if a["state"] == "IDLE"]
    if case == "incoherent":                 # prose lies about the idle set
        idle = idle + ["ghost_arm"]
    return {"tick": 1, "arms": arms, "objects": objs, "tasks": tasks,
            "baskets": BASKETS, "exchange_pads": PADS,
            "zone_locks": {}, "zone_inbound": {}}, idle


def consult_record(seq, case):
    st, idle = state_for(case)
    text = ("Cell state:\n" + json.dumps(st)
            + "\nIdle arms right now: " + ", ".join(idle) + ".")
    return {"seq": seq, "round": seq, "condition": "A", "image_file": None,
            "messages": [{"role": "system", "content": "s"},
                         {"role": "user",
                          "content": [{"type": "text", "text": text}]}]}


def rej(task_id, armname, why, via_pad=None):
    return {"attempt": 1, "task_id": task_id, "arm": armname,
            "via_pad": via_pad, "model_reason": "because",
            "rejected_because": why, "unparseable": False}


LOG = [
    {"round": 1, "result": "fallback", "latency_ms": 1.0,
     "rejected": [rej(3, "ur_w", "arm ur_w is not idle")]},          # MODEL
    {"round": 2, "result": "fallback", "latency_ms": 1.0,
     "rejected": [rej(3, "ur_w", "arm ur_w is not idle")]},          # CONTRA
    {"round": 3, "result": "fallback", "latency_ms": 1.0,
     "rejected": [rej(5, "franka_s", "arm franka_s cannot grasp object "
                                     "ycb_mug")]},                   # MODEL
    {"round": 4, "result": "fallback", "latency_ms": 1.0,
     "rejected": [rej(9, "ur_e", "the object is already at pad center; a "
                                 "handover through it would move nothing",
                      via_pad="center")]},                           # MODEL
    {"round": 5, "result": "fallback", "latency_ms": 1.0,
     "rejected": [rej(3, "franka_s", "arm franka_s cannot reach both the "
                                     "object and destination; a handover "
                                     "pad is needed")]},             # MODEL
    {"round": 6, "result": "fallback", "latency_ms": 1.0,
     "rejected": [rej(1, "ur_w", "arm ur_w cannot reach both the object "
                                 "and destination; a handover pad is "
                                 "needed")]},                        # CIRCLE_OK
    {"round": 7, "result": "fallback", "latency_ms": 1.0,
     "rejected": [rej(7, "ur_e", "arm ur_e cannot reach both the object "
                                 "and destination; a handover pad is "
                                 "needed")]},        # v3 file: no basket
    {"round": 8, "result": "fallback", "latency_ms": 1.0,
     "rejected": [dict(rej(7, "ur_e", "arm ur_e cannot reach both the "
                                      "object and destination; a handover "
                                      "pad is needed"),
                       basket="basket_kitchenware")]},   # v4 file
    {"round": 9, "result": "noop", "latency_ms": 1.0, "reason": "waiting"},
]
CASES = ["busy", "clean", "clean", "clean", "clean", "clean", "clean",
         "clean", "incoherent"]

with tempfile.TemporaryDirectory() as d:
    m = NS(makespan_ticks=100, requeued=0, completed={"ur_w": 1},
           blocked={"ur_w": 0, "ur_e": 0, "franka_n": 0, "franka_s": 0})
    m.pad_wait = {}
    coord = NS(m=m, locks=NS(ledger=[]), pool=[], agents={},
               cell=NS(arms={}))
    alloc = NS(stats={"calls": 7}, log=LOG)
    EpisodeLogger(out_dir=d, seed=0, layout="designed", allocator="vlm1",
                  condition="A").finish(coord, alloc=alloc, verdict="PASS",
                                        filename="vlm1_a.json")
    fdir = os.path.join(d, "vlm1_a_frames")
    os.makedirs(fdir)
    with open(os.path.join(fdir, "consults.jsonl"), "w") as f:
        for i, case in enumerate(CASES, 1):
            f.write(json.dumps(consult_record(i, case)) + "\n")

    path = os.path.join(d, "vlm1_a.json")
    consults = ia.load_consults(path)
    check("consult trail parsed", len(consults) == 9, str(len(consults)))

    ep = json.load(open(path))
    entries = [e for e in ep["allocator"]["log"]
               if e.get("result") in ia.CONSULT_RESULTS]
    got = []
    for i, e in enumerate(entries):
        for r in (e.get("rejected") or []):
            cause = ia.classify(r)
            got.append((cause,) + ia.AUDITORS[cause](r, consults[i]["state"]))

    want = [("busy_arm", "MODEL_ERROR"), ("busy_arm", "CONTRADICTORY"),
            ("capability", "MODEL_ERROR"), ("pad_rule", "MODEL_ERROR"),
            ("reach", "MODEL_ERROR"), ("reach", "CIRCLE_OK"),
            # sorting task, basket NOT recorded: the category-correct
            # basket is unreachable even though another basket is, so
            # this is the model's error, not an unfair rejection
            ("reach", "MODEL_ERROR"),
            # same geometry, but the model NAMED a reachable basket, so
            # the recorded basket takes precedence over the category
            ("reach", "CIRCLE_OK")]
    for i, (w_cause, w_verdict) in enumerate(want):
        check(f"case {i+1} {w_cause} -> {w_verdict}",
              got[i][0] == w_cause and got[i][1] == w_verdict,
              f"got {got[i][0]}/{got[i][1]}: {got[i][2]}")

    check("unlogged basket falls back to the CATEGORY-correct one",
          "category-correct basket basket_food" in got[6][2], got[6][2])
    check("a logged basket overrides the category assumption",
          "basket_kitchenware" in got[7][2], got[7][2])
    # 2026-07-28: the enriched state has NO reach_m, so a circle-only auditor
    # crashed with KeyError on every reach rejection. reach_ok_arms must be
    # used when the point carries it, and the circle kept for the 25d lineage.
    enriched_arm = {"name": "franka_s", "base_xy": [0.0, -0.6]}     # no reach_m
    enriched_obj = {"name": "ycb_far", "xy": [1.0, -0.5],
                    "reach_ok_arms": ["ur_e"]}
    check("reach audit uses reach_ok_arms when the point carries it",
          ia._reaches(enriched_arm, enriched_obj["xy"], enriched_obj) is False)
    check("and says yes when the arm IS listed",
          ia._reaches({"name": "ur_e", "base_xy": [1.15, 0.0]},
                      enriched_obj["xy"], enriched_obj) is True)
    check("falls back to the circle for the frozen 25d lineage",
          ia._reaches({"name": "ur_e", "base_xy": [1.15, 0.0],
                       "reach_m": 1.3},
                      [1.0, -0.5], {"xy": [1.0, -0.5]}) is True)
    check("undecidable rather than a crash when neither is present",
          ia._reaches(enriched_arm, [1.0, -0.5], None) is None)

    check("classifier knows the pad-leg reach string",
          ia.classify({"rejected_because":
                       "arm ur_e cannot reach object and pad pad_sw"})
          == "reach")

    probs = ia.coherence(consults)
    check("coherence catches the lying idle sentence",
          len(probs) == 1 and probs[0][0] == 9, str(probs))

    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ia.audit_episode(path)
    out = buf.getvalue()
    check("summary separates model from our inputs",
          "attributable to the model: 5 of 8" in out
          and "attributable to our inputs: 3 of 8" in out, out[-400:])

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
