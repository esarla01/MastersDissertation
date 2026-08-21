"""h_violations: every rejection the validator can produce classifies to
exactly one code, and no code is unreachable.

Imports the REAL validator and drives it with real states through the
frozen coordinator. Nothing here restates a rule.

Why this harness exists. EX1 reports a legality rate, but the finding is in
the composition of the illegal proposals: capability errors versus
instruction-following errors versus unreachable objects. Before 2026-08-01
those were inline f-strings and per-class counts meant matching text at
analysis time. Two bugs in this project came from exactly that kind of
matching, so messages and classification now come from one table and this
harness holds them together.

What is pinned:

  1. Round trip. Every template builds a message that classifies back to
     its own code, and to no other. Ambiguity here would silently misfile
     violations into the wrong bucket.
  2. No unreachable codes. Every code except the two that need a degenerate
     cell is provoked from a real validator call, so a code that can never
     fire is caught rather than sitting in a results table at zero forever.
  3. Wording is frozen. The strings must stay byte-identical to the inline
     versions they replaced, because probe_seed_v2 and every trail after it
     recorded them and the offline replay acceptance test compares reason
     strings.
  4. An unrecognised reason returns None, not a guess.
  5. Every code maps to a prompt rule, so a results table can report
     against the ladder.

Run:  python3 h_violations.py
"""

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
from core.decision.vlm_allocator import (VIOLATIONS,            # noqa: E402
                                         VIOLATION_RULE,
                                         classify, _reason,
                                         validate_decision)
from analysis.frozen_coord import from_record                   # noqa: E402
from ycb_objects import register_specs                          # noqa: E402
from ycb_scene import BASKETS                                   # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


# The exact strings as they stood before the table existed. If one of these
# changes, trails already recorded stop classifying and the acceptance test
# stops comparing like with like.
FROZEN = {
    "PARSE": "reply was not valid JSON",
    "TASK_UNKNOWN": "task 7 does not exist",
    "TASK_FINISHED": "task 7 is already finished",
    "TASK_BUSY": "task 7 is already being handled",
    "ARM_UNKNOWN": "unknown arm ur_w",
    "ARM_NOT_IDLE": "arm ur_w is not idle",
    "CAPABILITY": "arm ur_w cannot grasp object ycb_mug",
    "NO_BASKETS": "task has no destination and no baskets exist",
    "BASKET_MISSING": "task 7 needs a basket choice; options: ['a', 'b']",
    "REACH_OBJECT": "arm ur_w cannot reach the object",
    "NO_ROUTE": ("arm ur_w cannot reach both the object and destination, "
                 "and no handover route exists with it on the first leg"),
}

FIELDS = {"tid": 7, "arm": "ur_w", "obj": "ycb_mug", "options": ["a", "b"]}

# ---------------------------------------------------------------------------
# 1. round trip and wording
# ---------------------------------------------------------------------------
check("the frozen list covers every code",
      set(FROZEN) == set(VIOLATIONS),
      str(set(VIOLATIONS) ^ set(FROZEN)))

bad_round, bad_word = [], []
for code in VIOLATIONS:
    msg = _reason(code, **FIELDS)
    if msg != FROZEN[code]:
        bad_word.append((code, msg, FROZEN[code]))
    got, _ = classify(msg)
    if got != code:
        bad_round.append((code, got, msg))
check("every message classifies back to its own code", not bad_round,
      str(bad_round[:2]))
check("wording is byte-identical to the pre-table strings", not bad_word,
      str(bad_word[:2]))

# Ambiguity: no message may match a code other than its own.
cross = []
for code in VIOLATIONS:
    msg = _reason(code, **FIELDS)
    hits = [c for c in VIOLATIONS if classify(msg)[0] == c]
    if hits != [code]:
        cross.append((code, hits))
check("no message is ambiguous between codes", not cross, str(cross[:2]))

check("an unrecognised reason returns None, not a guess",
      classify("the gripper is sad today") == (None, {})
      and classify("") == (None, {}))
check("every code maps to a prompt rule (PARSE excepted)",
      all(c in VIOLATION_RULE for c in VIOLATIONS)
      and VIOLATION_RULE["CAPABILITY"] == "R3"
      and VIOLATION_RULE["REACH_OBJECT"] == "R4"
      and VIOLATION_RULE["NO_ROUTE"] == "R5",
      str(VIOLATION_RULE))

# ---------------------------------------------------------------------------
# 2. provoke the codes through the REAL validator
# ---------------------------------------------------------------------------
POSITIONS = {
    "ycb_mug":         (0.30022, 0.50014),    # 0.081 m, URs only
    "ycb_bowl":        (0.05011, 0.02037),    # delicate, Frankas only, and
                                              # sitting ON the centre pad, so
                                              # a handover through it would
                                              # move nothing
    "ycb_wood_block":  (-1.05017, -0.35061),  # far west, ur_e cannot reach
    "ycb_large_clamp": (-0.25017, -0.45061),
}
for scene_name in POSITIONS:
    register_specs(C.OBJECT_SPECS, scene_name, scene_name[len("ycb_"):])

zm = ZoneMap(os.path.join(ROOT, "core", "cell", "reachability", "rasters"))


class LiveScene:
    def __getitem__(self, name):
        x, y = POSITIONS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_live(busy=(), statuses=None, dests=None):
    """dests fixes a destination on a task, which is what lets NO_ROUTE
    fire: while dest is None the model picks the basket under R7, and in
    this cell some basket is always routable, so the destination constraint
    never binds. Once a destination is fixed, it binds."""
    statuses = statuses or {}
    dests = dests or {}
    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=False, _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm,
                          state=("MOVING" if name in busy else "IDLE"))
    pool = []
    for i, obj in enumerate(POSITIONS):
        st = statuses.get(i, "queued")
        pool.append(NS(id=i, obj=obj, dest=dests.get(i), done=False,
                       failed=False,
                       claimed=(st == "claimed"),
                       waiting_on=(0 if st == "waiting" else None),
                       attempts=0, dest_by=None))
    return NS(cell=NS(scene=LiveScene(), arms=arms), agents=agents, pool=pool,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))


engine = NS(active=list(POSITIONS), applied_log=[])
EXACT = {k: list(v) for k, v in POSITIONS.items()}


def record(**kw):
    st = sb.build_state(make_live(**kw), engine, tick=1, baskets=BASKETS,
                        zonemap=zm)
    return {"state": st, "positions_exact": EXACT}


def verdict(decision, baskets=BASKETS, **kw):
    return validate_decision(decision, from_record(record(**kw)), zm, baskets)


seen = {}


def provoke(label, decision, expect, baskets=BASKETS, **kw):
    ok, _, _, why = verdict(decision, baskets, **kw)
    code, _ = classify(why)
    seen[expect] = seen.get(expect, 0) + (1 if code == expect else 0)
    check(f"{label} -> {expect}", (not ok) and code == expect,
          f"ok={ok} code={code} why={why!r}")


provoke("a task id that is not in the pool",
        {"task_id": 99, "arm": "ur_w", "basket": "basket_kitchenware"},
        "TASK_UNKNOWN")
provoke("a task already claimed",
        {"task_id": 0, "arm": "ur_w", "basket": "basket_kitchenware"},
        "TASK_BUSY", statuses={0: "claimed"})
provoke("a task parked behind a handover leg",
        {"task_id": 1, "arm": "franka_n", "basket": "basket_kitchenware"},
        "TASK_BUSY", statuses={1: "waiting"})
provoke("an arm that does not exist",
        {"task_id": 0, "arm": "ur_north", "basket": "basket_kitchenware"},
        "ARM_UNKNOWN")
provoke("an arm that is busy",
        {"task_id": 0, "arm": "ur_e", "basket": "basket_kitchenware"},
        "ARM_NOT_IDLE", busy=("ur_e",))
provoke("a Franka on an 0.081 m mug",
        {"task_id": 0, "arm": "franka_n", "basket": "basket_kitchenware"},
        "CAPABILITY")
provoke("a UR on a delicate bowl",
        {"task_id": 1, "arm": "ur_w", "basket": "basket_kitchenware"},
        "CAPABILITY")
provoke("ur_e on an object in the far west",
        {"task_id": 2, "arm": "ur_e", "basket": "basket_tools"},
        "REACH_OBJECT")
provoke("no basket named on a sorting task",
        {"task_id": 0, "arm": "ur_e", "basket": None},
        "BASKET_MISSING")
provoke("a basket that does not exist",
        {"task_id": 0, "arm": "ur_e", "basket": "basket_cutlery"},
        "BASKET_MISSING")
provoke("a sorting task with no baskets configured at all",
        {"task_id": 0, "arm": "ur_e", "basket": "basket_kitchenware"},
        "NO_BASKETS", baskets={})

ok, _, _, why = validate_decision(None, from_record(record()), zm, BASKETS)
check("a reply that is not JSON -> PARSE",
      (not ok) and classify(why)[0] == "PARSE", f"{why!r}")

# NO_ROUTE needs a task whose destination is ALREADY FIXED. An earlier
# version of this harness asserted the code was structurally unprovokable,
# on the reasoning that some basket is always routable. That was wrong, and
# the live episode disproved it: probe_seed_v2 produced two NO_ROUTE
# rejections. The gap was that every task here was born destination-less,
# where R7 lets the model pick a reachable basket. Once a destination is
# fixed, the constraint binds.
#
# The case: the bowl is delicate, so only the Frankas can grasp it, and it
# sits on the centre pad, which is the ONLY pad both Frankas reach. Routing
# through the pad an object already occupies is refused as a liveness rule,
# and no other pad both progresses toward the kitchenware basket and is
# reachable by a finisher. So franka_s can pick it up and there is no way
# to get it delivered.
provoke("a delicate object on the only shared pad, destination fixed",
        {"task_id": 1, "arm": "franka_s"},
        "NO_ROUTE", dests={1: (0.70, 0.50)})

# TASK_FINISHED remains unprovokable through a saved state, because
# build_state filters done and failed tasks out entirely, so no frozen
# state can contain one. Recorded rather than left as a silent gap.
covered = set(seen) | {"PARSE"}
uncovered = set(VIOLATIONS) - covered
check("only TASK_FINISHED is untested by a live validator call, and it is "
      "unreachable from any saved state",
      uncovered == {"TASK_FINISHED"}, str(sorted(uncovered)))

# ---------------------------------------------------------------------------
# 3. a valid decision produces no violation
# ---------------------------------------------------------------------------
ok, target, sub, why = verdict({"task_id": 0, "arm": "ur_e",
                                "basket": "basket_kitchenware"})
check("an accepted decision has an empty reason and no code",
      ok and why == "" and classify(why) == (None, {}),
      f"ok={ok} why={why!r}")

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
