"""h_frozen_coord: a coordinator rebuilt from a saved state produces the
SAME validator verdicts as the live one it was built from.

This is the first half of the acceptance test for offline replay, run
against a constructed cell rather than a recorded episode so it can live in
the suite and fail fast. The second half, byte-identity against a real
episode's consults.jsonl, belongs to h_probe_replay.

Method, and the reason it is worth trusting: a LIVE-shaped fake coordinator
is built, the REAL build_state renders it, and the REAL from_state rebuilds
a shim from that render. Then every (task, arm) pair in the cell is pushed
through the REAL validate_decision against BOTH coordinators and the four
returned values are compared, reason strings included. Nothing here
reimplements a rule; the harness only compares two runs of the same code
over two representations of one cell.

The pairs are exhaustive on purpose. A shim can be right on the easy cases
and wrong on exactly the boundary that matters, and this cell places
objects at up to 97% of an arm's reach.

Run:  python3 h_frozen_coord.py
"""

import json
import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.cell import cell_config as C                          # noqa: E402
from core.cell.zones import ZoneMap                             # noqa: E402
from core.decision import state_builder as sb                   # noqa: E402
from core.decision.vlm_allocator import validate_decision       # noqa: E402
from analysis.frozen_coord import (from_state, from_record,     # noqa: E402
                                   idle_arms)
from ycb_objects import register_specs                          # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


# Positions carry FIVE decimal places. The state rounds to two, so if the
# shim ever fell back to the rounded value these would disagree, and the
# soup can sits at 97.4% of ur_w's reach where 5 mm can flip a verdict.
POSITIONS = {
    "ycb_soup_can":    (0.10037, -0.20074),   # ur_w boundary case
    "ycb_power_drill": (0.09961, 0.19952),
    "ycb_bowl":        (-0.30043, 0.45028),   # delicate, Frankas only
    "ycb_large_clamp": (-0.25017, -0.45061),  # 0.122 m, URs only
    "ycb_mug":         (0.30022, 0.50014),
}

for scene_name in POSITIONS:
    register_specs(C.OBJECT_SPECS, scene_name, scene_name[len("ycb_"):])

BASKETS = {"basket_food": {"pos": (-0.70, 0.50)},
           "basket_kitchenware": {"pos": (0.70, 0.50)},
           "basket_tools": {"pos": (-0.70, -0.50)}}

zm = ZoneMap(os.path.join(ROOT, "core", "cell", "reachability", "rasters"))


class LiveScene:
    def __getitem__(self, name):
        x, y = POSITIONS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_live(dead=(), busy=(), statuses=None):
    """A live-shaped coordinator: the thing build_state was written for."""
    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=(name in dead), _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm,
                          state=("MOVING" if name in busy else "IDLE"))
    statuses = statuses or {}
    pool = []
    for i, obj in enumerate(POSITIONS):
        st = statuses.get(i, "queued")
        pool.append(NS(id=i, obj=obj,
                       # one task deliberately has no destination: the
                       # basket is then the model's choice under R7, and
                       # that is the path where the accepted-decision
                       # basket field matters
                       dest=(None if i == 4 else _dest_for(obj)),
                       done=False, failed=False,
                       claimed=(st == "in_progress"),
                       waiting_on=(0 if st == "waiting" else None),
                       attempts=0, dest_by=None))
    return NS(cell=NS(scene=LiveScene(), arms=arms), agents=agents, pool=pool,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))


def _dest_for(obj):
    cat = C.OBJECT_SPECS[obj]["category"]
    return tuple(BASKETS["basket_" + cat]["pos"])


engine = NS(active=list(POSITIONS), applied_log=[])


def normalise(v):
    """Compare verdicts by CONTENT, not by object identity.

    A routed verdict returns a real core.control.tasks.Task for the pad leg,
    and Task ids come from a global counter, so two runs of the same
    decision produce subtasks that differ in id alone. Comparing raw tuples
    would report every routed verdict as a mismatch and hide any real one in
    the noise. Everything that carries meaning is kept: the outcome, the
    target, the subtask's object, destination and provenance, and the reason
    string.
    """
    if v[0] == "EXC":
        return v
    ok, target, sub, why = v
    sub_sig = None if sub is None else (sub.obj, tuple(sub.dest), sub.dest_by)
    return (ok, None if target is None else tuple(target), sub_sig, why)


def verdicts(coord, decisions):
    """Every decision through the REAL validator. Fresh coord per call is
    the caller's job: validate_decision mutates task.dest on success."""
    out = []
    for d in decisions:
        try:
            out.append(normalise(validate_decision(dict(d), coord, zm,
                                                   BASKETS)))
        except Exception as e:                      # compared, not hidden
            out.append(("EXC", f"{type(e).__name__}: {e}"))
    return out


def all_decisions(coord):
    """Exhaustive (task, arm) pairs, plus a basket for the destination-less
    task, plus a decision naming an unknown arm and one naming an unknown
    task, so the rejection paths are compared too."""
    ds = []
    for t in coord.pool:
        for a in list(C.ARMS) + ["not_an_arm"]:
            if t.dest is None:
                for b in list(BASKETS) + [None, "basket_nope"]:
                    ds.append({"task_id": t.id, "arm": a, "basket": b})
            else:
                ds.append({"task_id": t.id, "arm": a, "basket": None})
    ds.append({"task_id": 999, "arm": "ur_w", "basket": None})
    ds.append({"task_id": -1, "arm": None, "basket": None})
    return ds


# ---------------------------------------------------------------------------
# 1. live vs rebuilt, over several cell configurations
# ---------------------------------------------------------------------------
SCENARIOS = [
    ("all idle", {}),
    ("ur_w disabled", {"dead": ("ur_w",)}),
    ("both frankas disabled", {"dead": ("franka_n", "franka_s")}),
    ("ur_e busy", {"busy": ("ur_e",)}),
    ("one claimed, one waiting", {"statuses": {1: "in_progress",
                                              2: "waiting"}}),
    ("three busy, one idle", {"busy": ("ur_e", "franka_n", "franka_s")}),
]

total_pairs = 0
for label, kw in SCENARIOS:
    live = make_live(**kw)
    state = sb.build_state(live, engine, tick=1, baskets=BASKETS, zonemap=zm)
    exact = {k: list(v) for k, v in POSITIONS.items()}

    decisions = all_decisions(live)
    total_pairs += len(decisions)

    got_live = verdicts(make_live(**kw), decisions)
    got_frozen = verdicts(from_state(state, exact), decisions)

    diffs = [(d, l, f) for d, l, f in zip(decisions, got_live, got_frozen)
             if l != f]
    check(f"rebuilt verdicts match live: {label}", not diffs,
          f"{len(diffs)}/{len(decisions)} differ; first: {diffs[:1]}")

check("the comparison was not vacuous", total_pairs > 100,
      f"{total_pairs} decisions compared")

# The comparison is only worth anything if it covered all three outcomes.
live = make_live()
state = sb.build_state(live, engine, tick=1, baskets=BASKETS, zonemap=zm)
res = verdicts(from_state(state, {k: list(v) for k, v in POSITIONS.items()}),
               all_decisions(live))
n_ok = sum(1 for r in res if r[0] is True)
n_no = sum(1 for r in res if r[0] is False)
n_routed = sum(1 for r in res if r[0] is True and r[2] is not None)
check("accepted, rejected and ROUTED outcomes all occurred",
      n_ok and n_no and n_routed,
      f"accepted={n_ok} rejected={n_no} routed={n_routed}")

# ---------------------------------------------------------------------------
# 2. exact positions are used, and rounded ones are refused
# ---------------------------------------------------------------------------
live = make_live()
state = sb.build_state(live, engine, tick=1, baskets=BASKETS, zonemap=zm)
check("the state itself is rounded to 2 dp",
      state["objects"][0]["xy"] == [round(POSITIONS["ycb_soup_can"][0], 2),
                                    round(POSITIONS["ycb_soup_can"][1], 2)],
      str(state["objects"][0]["xy"]))

fc = from_state(state, {k: list(v) for k, v in POSITIONS.items()})
px = fc.cell.scene["ycb_soup_can"].data.root_pos_w[0]
check("the shim carries the UNROUNDED position",
      (px[0], px[1]) == POSITIONS["ycb_soup_can"], f"{px[0]}, {px[1]}")

for bad, why in ((None, "None"), ({}, "empty dict")):
    try:
        from_state(state, bad)
        check(f"positions_exact={why} is refused", False, "no exception")
    except ValueError as e:
        check(f"positions_exact={why} is refused, not guessed",
              "rounded" in str(e), str(e)[:70])

try:
    partial = {k: list(v) for k, v in POSITIONS.items()
               if k != "ycb_soup_can"}
    from_state(state, partial)
    check("a missing object is refused", False, "no exception")
except ValueError as e:
    check("a missing object is refused and NAMED",
          "ycb_soup_can" in str(e), str(e)[:80])

# ---------------------------------------------------------------------------
# 3. status decoding round-trips, and an impossible status is refused
# ---------------------------------------------------------------------------
live = make_live(statuses={1: "in_progress", 2: "waiting"})
state = sb.build_state(live, engine, tick=1, baskets=BASKETS, zonemap=zm)
fc = from_state(state, {k: list(v) for k, v in POSITIONS.items()})
by_id = {t.id: t for t in fc.pool}
check("in_progress decodes back to claimed",
      by_id[1].claimed and by_id[1].waiting_on is None, repr(by_id[1]))
check("waiting_on_<id> decodes back to the id",
      by_id[2].waiting_on == 0 and not by_id[2].claimed, repr(by_id[2]))
check("queued decodes to neither",
      not by_id[0].claimed and by_id[0].waiting_on is None, repr(by_id[0]))

bogus = json.loads(json.dumps(state))
bogus["tasks"][0]["status"] = "done"
try:
    from_state(bogus, {k: list(v) for k, v in POSITIONS.items()})
    check("an impossible status is refused", False, "no exception")
except ValueError as e:
    check("an impossible status is refused rather than guessed",
          "done" in str(e), str(e)[:70])

# ---------------------------------------------------------------------------
# 4. the scene behaves like the live one, and idle_arms matches
# ---------------------------------------------------------------------------
try:
    fc.cell.scene["ycb_nothing"]
    check("an unknown object raises KeyError", False, "no exception")
except KeyError:
    check("an unknown object raises KeyError, as the live scene does", True)

live = make_live(dead=("ur_w",), busy=("ur_e",))
state = sb.build_state(live, engine, tick=1, baskets=BASKETS, zonemap=zm)
fc = from_state(state, {k: list(v) for k, v in POSITIONS.items()})
want = [n for n, ag in live.agents.items()
        if ag.state == "IDLE" and not ag.arm.disabled]
check("idle_arms reproduces the Coordinator's own predicate",
      idle_arms(fc) == want, f"{idle_arms(fc)} vs {want}")

# ---------------------------------------------------------------------------
# 5. from_record, and the refusal to replay a pre-2026-08-01 record
# ---------------------------------------------------------------------------
# Section 5 onward needs an ALL IDLE cell: the scenario above left ur_w
# disabled and ur_e busy, and a basket-choice decision by a busy arm would
# be refused under R2 for reasons that have nothing to do with the shim.
state = sb.build_state(make_live(), engine, tick=1, baskets=BASKETS,
                       zonemap=zm)
fc = from_state(state, {k: list(v) for k, v in POSITIONS.items()})
rec = {"state": state,
       "positions_exact": {k: list(v) for k, v in POSITIONS.items()}}
check("from_record builds the same pool as from_state",
      [t.id for t in from_record(rec).pool] == [t.id for t in fc.pool])

try:
    from_record({"positions_exact": {"a": [0, 0]}})
    check("a record with no state is refused", False, "no exception")
except ValueError as e:
    check("a record with no state is refused with the reason",
          "state" in str(e), str(e)[:70])

# ---------------------------------------------------------------------------
# 5b. object physics must come from the STATE, not from a pre-registered
#     global that only a harness happens to have set up
# ---------------------------------------------------------------------------
# cell_config.can_grasp falls back to a small cube for unknown objects, and
# OBJECT_SPECS is populated when the SCENE is built, which an offline
# process never does. Every harness in this suite calls register_specs at
# import, so all of them agreed with themselves while the real replay path
# treated a 0.122 m clamp as graspable by a Franka. The acceptance test
# against a live episode is what exposed it on 2026-08-02.
#
# This check deletes the registrations first, so it fails against the old
# code and passes against the new.
_saved_specs = {k: C.OBJECT_SPECS.pop(k) for k in list(POSITIONS)
                if k in C.OBJECT_SPECS}
check("the fixture really did register specs (otherwise this proves nothing)",
      len(_saved_specs) == len(POSITIONS), str(list(_saved_specs)))
check("with specs removed, can_grasp is wrongly permissive",
      C.can_grasp("franka_s", "ycb_large_clamp") is True)

fc_cold = from_record(rec)
check("from_record re-registers object physics out of the saved state",
      C.can_grasp("franka_s", "ycb_large_clamp") is False
      and C.can_grasp("ur_w", "ycb_large_clamp") is True)
ok_cold, _, _, why_cold = validate_decision(
    {"task_id": 3, "arm": "franka_s", "basket": "basket_tools"},
    from_record(rec), zm, BASKETS)
check("a cold process rejects the clamp on CAPABILITY, as the live cell did",
      not ok_cold and "cannot grasp" in (why_cold or ""), str(why_cold))

# A state that cannot supply the physics must refuse rather than default.
thin = json.loads(json.dumps(state))
for o in thin["objects"]:
    o.pop("grasp_m", None)
try:
    from_state(thin, {k: list(v) for k, v in POSITIONS.items()})
    check("a state with no grasp_m is refused", False, "no exception")
except ValueError as e:
    check("a state with no grasp_m is refused rather than defaulted",
          "grasp_m" in str(e), str(e)[:80])

# A conflicting spec must raise rather than overwrite silently.
conflicting = json.loads(json.dumps(state))
for o in conflicting["objects"]:
    if o["name"] == "ycb_large_clamp":
        o["grasp_m"] = 0.050
try:
    from_state(conflicting, {k: list(v) for k, v in POSITIONS.items()})
    check("a conflicting spec is refused", False, "no exception")
except ValueError as e:
    check("a conflicting spec is refused rather than overwritten",
          "already registered" in str(e), str(e)[:80])

# ---------------------------------------------------------------------------
# 6. single use: validate_decision mutates, so a shim must not be reused
# ---------------------------------------------------------------------------
fresh = from_record(rec)
t4 = [t for t in fresh.pool if t.id == 4][0]
check("a destination-less task starts with dest None", t4.dest is None)
ok, _, _, why = validate_decision(
    {"task_id": 4, "arm": "ur_e", "basket": "basket_kitchenware"},
    fresh, zm, BASKETS)
check("a valid basket choice persists onto the task",
      ok and t4.dest is not None and t4.dest_by == "model",
      f"ok={ok} dest={t4.dest} by={t4.dest_by} why={why}")
check("and from_record hands back a FRESH one each call",
      [t for t in from_record(rec).pool if t.id == 4][0].dest is None)

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)