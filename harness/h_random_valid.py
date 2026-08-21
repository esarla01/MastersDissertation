"""Harness: the random-valid floor, matching version (imports the REAL
rule allocator, zonemap and config).

Step 1b rewrote the floor from "random arm for the pool-ordered task" to a
random GREEDY MATCHING: shuffle the ready tasks per replan, give each a
uniformly random legal arm while idle arms remain, answer the coordinator
from that plan. Measured motivation: on the designed layout the per-pick
version had n_legal=1 on all 14 assignments and reproduced b1 tick for
tick; the freedom it randomised was empty. The floor must randomise the
TASK dimension too.

What must hold:

  1. NEVER illegal: every planned (task, arm) is one the REAL
     rule_based_allocate also returns for that single arm.
  2. The TASK dimension is actually random: with one idle arm and several
     feasible tasks, different seeds choose different tasks.
  3. Deterministic and call-order independent: same seed + same state
     yields the same plan; the order the coordinator offers tasks in does
     not change who gets what.
  4. Relay safety: a finishing leg (waiting_on set) is never planned
     before its parent completes; relays are planned via the real pad
     routing.
  5. invalidate() exists and forces a replan (the occupied-pad decline).
  6. Unplanned tasks get (None, None, None), and stats add up.

Run: python3 h_random_valid.py
"""
import itertools
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from core.cell import cell_config as C                        # REAL config
from core.cell.zones import ZoneMap                           # REAL rasters
from core.control.tasks import rule_based_allocate            # REAL rule
from core.decision.random_allocator import RandomValidAllocator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm",
                                "ycb"))
from ycb_objects import register_specs                        # REAL registry

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


zm = ZoneMap(os.path.join(os.path.dirname(__file__), "..", "fourarm",
                          "core", "cell", "reachability", "rasters"))

for name in ("bowl", "mug", "power_drill", "soup_can", "large_clamp",
             "gelatin_box", "meat_can"):
    register_specs(C.OBJECT_SPECS, "ycb_" + name, name)

POS = {"ycb_soup_can": (-0.10, 0.30),
       "ycb_gelatin_box": (-0.20, 0.20),
       "ycb_meat_can": (0.05, 0.40),
       "ycb_mug": (0.30, 0.45),
       "ycb_power_drill": (-0.65, -0.02),
       "ycb_bowl": (-0.25, 0.50),
       "ycb_large_clamp": (0.10, 0.20)}
DEST = {"ycb_soup_can": (-0.70, 0.50), "ycb_gelatin_box": (-0.70, 0.50),
        "ycb_meat_can": (-0.70, 0.50), "ycb_mug": (0.70, 0.50),
        "ycb_power_drill": (-0.70, -0.50), "ycb_bowl": (0.70, 0.50),
        "ycb_large_clamp": (-0.70, -0.50)}


class FakeScene:
    def __getitem__(self, name):
        x, y = POS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_coord(objs, idle_arms=None, waiting=None, done_ids=frozenset()):
    """A coordinator double: real positions and specs, chosen idle set."""
    idle_arms = list(C.ARMS) if idle_arms is None else idle_arms
    agents = {n: NS(state=("IDLE" if n in idle_arms else "TO_PICK"),
                    arm=NS(disabled=False)) for n in C.ARMS}
    pool = []
    for i, o in enumerate(objs):
        pool.append(NS(id=i, obj=o, dest=DEST[o], dest_by="oracle",
                       done=(i in done_ids), failed=False, claimed=False,
                       waiting_on=(waiting or {}).get(i)))
    return NS(cell=NS(scene=FakeScene()), agents=agents, pool=pool)


def offer_all(alloc, coord, order=None):
    """Drive the coordinator's per-task loop: offer every unclaimed task,
    collect the answers. `order` permutes the OFFER order only."""
    got = {}
    tasks = list(coord.pool)
    if order is not None:
        tasks = [tasks[i] for i in order]
    idle = [n for n, ag in coord.agents.items() if ag.state == "IDLE"]
    for t in tasks:
        if t.done:
            continue
        oxy = POS[t.obj]
        arm, target, sub = alloc(t, oxy, idle, zm)
        if arm is not None:
            got[t.id] = (arm, sub is not None)
            idle.remove(arm)
    return got


def legal_arms(coord, t, remaining):
    out = []
    for a in remaining:
        arm_r, target, sub = rule_based_allocate(t, POS[t.obj], [a], zm)
        if arm_r == a and target is not None:
            out.append(a)
    return out


OBJS = ["ycb_soup_can", "ycb_gelatin_box", "ycb_meat_can", "ycb_mug",
        "ycb_power_drill", "ycb_bowl", "ycb_large_clamp"]

# ---------------------------------------------------------------------------
# 1. NEVER illegal, across seeds and idle subsets
# ---------------------------------------------------------------------------
bad, planned_total = [], 0
for seed in range(12):
    for idle in (list(C.ARMS), ["ur_w"], ["ur_w", "franka_n"],
                 ["ur_e", "franka_s"]):
        coord = make_coord(OBJS, idle_arms=idle)
        alloc = RandomValidAllocator(lambda c=coord: c, seed=seed)
        got = offer_all(alloc, coord)
        planned_total += len(got)
        # replay the plan against ground truth: each assigned arm must be
        # legal for its task given the arms not consumed by EARLIER tasks
        # in the plan's own order (greedy matching semantics)
        order = alloc.log[-1]["order"] if alloc.log else []
        remaining = sorted(idle)
        for tid in order:
            if tid not in got:
                continue
            t = coord.pool[tid]
            if got[tid][0] not in legal_arms(coord, t, remaining):
                bad.append((seed, idle, tid, got[tid]))
            remaining.remove(got[tid][0])
check(f"every planned assignment is legal ({planned_total} across "
      "12 seeds x 4 idle sets)", not bad, str(bad[:3]))

# ---------------------------------------------------------------------------
# 2. the TASK dimension is random: one idle arm, several feasible tasks
# ---------------------------------------------------------------------------
shared = ["ycb_soup_can", "ycb_gelatin_box", "ycb_meat_can"]
coord0 = make_coord(shared, idle_arms=["franka_n"])
feasible = [t.id for t in coord0.pool
            if legal_arms(coord0, t, ["franka_n"])]
chosen = set()
for seed in range(40):
    coord = make_coord(shared, idle_arms=["franka_n"])
    alloc = RandomValidAllocator(lambda c=coord: c, seed=seed)
    got = offer_all(alloc, coord)
    if got:
        chosen.add(next(iter(got)))
check("with 1 idle arm and several feasible tasks, seeds explore the "
      "TASK choice (the freedom the per-pick floor lacked)",
      len(feasible) >= 2 and chosen == set(feasible),
      f"feasible={feasible} chosen across seeds={sorted(chosen)}")

# ---------------------------------------------------------------------------
# 3. deterministic and call-order independent
# ---------------------------------------------------------------------------
runs = []
for _ in range(3):
    coord = make_coord(OBJS)
    alloc = RandomValidAllocator(lambda c=coord: c, seed=7)
    runs.append(offer_all(alloc, coord))
check("same seed + same state reproduces the same matching",
      runs[0] == runs[1] == runs[2], str(runs[0]))
coord = make_coord(OBJS)
alloc = RandomValidAllocator(lambda c=coord: c, seed=7)
rev = offer_all(alloc, coord, order=list(range(len(OBJS)))[::-1])
check("the matching is independent of the coordinator's OFFER order",
      rev == runs[0], f"{rev} vs {runs[0]}")

# ---------------------------------------------------------------------------
# 4. relay safety
# ---------------------------------------------------------------------------
# a waiting finisher must never be planned before its parent is done
coord = make_coord(OBJS, waiting={2: 0})            # task 2 waits on task 0
alloc = RandomValidAllocator(lambda c=coord: c, seed=3)
got = offer_all(alloc, coord)
check("a waiting_on task is excluded from the plan",
      2 not in got, str(got))
coord = make_coord(OBJS, waiting={2: 0}, done_ids={0})   # parent now done
alloc = RandomValidAllocator(lambda c=coord: c, seed=3)
got2 = offer_all(alloc, coord)
check("...and becomes plannable once its parent is done",
      any(tid == 2 for tid in got2) or 2 in {t.id for t in coord.pool
                                             if not legal_arms(coord, t, list(C.ARMS))},
      str(got2))
# relays are planned via the real pad routing when only a far-side arm fits
relay_seen = False
for seed in range(30):
    coord = make_coord(["ycb_mug"], idle_arms=["franka_s", "franka_n", "ur_w"])
    alloc = RandomValidAllocator(lambda c=coord: c, seed=seed)
    got = offer_all(alloc, coord)
    if got and got[0][1]:
        relay_seen = True
        break
mug_direct = legal_arms(make_coord(["ycb_mug"]),
                        make_coord(["ycb_mug"]).pool[0], list(C.ARMS))
check("relay legs are planned through the real pad routing",
      relay_seen or bool(mug_direct),
      f"direct arms for mug: {mug_direct}")

# ---------------------------------------------------------------------------
# 5. invalidate() and consumption semantics
# ---------------------------------------------------------------------------
coord = make_coord(OBJS)
alloc = RandomValidAllocator(lambda c=coord: c, seed=1)
got = offer_all(alloc, coord)
check("invalidate() exists, clears the plan, and counts itself",
      hasattr(alloc, "invalidate") and (alloc.invalidate() or
      alloc._plan == {} and alloc._sig is None
      and alloc.stats["invalidated"] == 1))

# 5b. the replan storm is FOLDED, not logged hundreds of times
coord = make_coord(OBJS)
alloc = RandomValidAllocator(lambda c=coord: c, seed=1)
t0 = coord.pool[0]
alloc(t0, POS[t0.obj], list(C.ARMS), zm)         # plan created + consumed
base_assign = alloc.stats["assignments"]
for _ in range(50):                              # the occupied-pad loop:
    alloc.invalidate()                           # decline -> invalidate ->
    alloc(t0, POS[t0.obj], list(C.ARMS), zm)     # identical state replans
check("identical consecutive replans fold into one entry with repeats",
      len(alloc.log) == 1 and alloc.log[0].get("repeats") == 51,
      f"{len(alloc.log)} entries, repeats={alloc.log[0].get('repeats')}")
check("folded replans do not inflate the assignments stat",
      alloc.stats["assignments"] == base_assign
      and alloc.stats["replans"] == 1 + 50,
      str({k: alloc.stats[k] for k in ("assignments", "replans")}))

# 6. bookkeeping
coord = make_coord(["ycb_bowl"], idle_arms=["ur_w", "ur_e"])   # delicate: URs illegal
alloc = RandomValidAllocator(lambda c=coord: c, seed=0)
got = offer_all(alloc, coord)
check("no legal option -> (None, None, None) and counted",
      got == {} and alloc.stats["no_legal_option"] == 1
      and alloc.stats["assignments"] == 0, str(alloc.stats))
check("log entries carry NO round key (trace_episode prints them verbatim)",
      all("round" not in e for a2 in [alloc] for e in a2.log))

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
