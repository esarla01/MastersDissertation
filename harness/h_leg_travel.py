"""Harness: per-task execution window (imports the REAL Task and logger).

WHY THIS EXISTS. The timing model was fitted against per-EPISODE travel
while its target, productive ticks, spans only claim..done. Measurement and
predictor described different spans, so the regression buried the
difference in its constants and the fitted UR coefficient implied an
end-effector speed of 6.3 m/s, which is not physical. Two new fields close
the gap: exec_start_tick (the LAST claim) and travel_leg_m (metres covered
between that claim and done_tick).

What must hold:

  1. The fields exist on Task, default to None, and reach the episode JSON
     through the REAL EpisodeLogger record builder.
  2. travel_leg_m is a DIFFERENCE on the executing arm's odometer, not an
     episode total: distance accrued before the claim must not appear in it.
  3. ABORT CASE. A task claimed, aborted, and re-claimed by a DIFFERENT arm
     must report the second arm's distance only. A delta straddling two
     arms would be meaningless, and this is the case that motivated
     stamping on every claim rather than only the first.
  4. exec_start_tick tracks the LAST claim while claim_tick keeps its
     first-claim-only meaning, so wait-time accounting is unchanged.
  5. Nothing is required: an arm without a travel_m odometer logs None
     rather than raising, matching how episode_logger already treats D1.

The harness drives the REAL ArmAgent.claim and the REAL _go_home completion
path with a fake arm and fake locks, so the fields are exercised where they
are actually written, not simulated.

Run: python3 h_leg_travel.py
"""
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from core.control.tasks import Task, ArmAgent          # REAL task + agent
from instrumentation.episode_logger import EpisodeLogger  # REAL logger

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


class FakeArm:
    """Minimal arm: an odometer and the calls claim/_go_home make."""

    def __init__(self, name, travel=0.0):
        self.name = name
        self.travel_m = travel
        self.disabled = False
        self._carried = None

    def clear_goal(self):
        pass

    def set_goal(self, x, y, z):
        # _go_home commands the PRE_TUCK rise after stamping done; the
        # harness only cares that the stamp happened, not where it flies
        pass

    def error(self):
        return 0.0


class FakeLocks:
    def __init__(self):
        self.reserved = []

    def is_contended(self, z, a):
        return False

    def reserve(self, z, a):
        self.reserved.append((z, a))

    def release_all(self, a):
        pass


class FakeScene:
    def __getitem__(self, name):
        return NS(data=NS(root_pos_w=np.array([[0.1, 0.2, 0.9]], dtype=float)))


def make_agent(arm, metrics):
    """An ArmAgent with the collaborators claim()/_go_home() touch."""
    ag = ArmAgent.__new__(ArmAgent)          # bypass __init__'s sim wiring
    ag.arm = arm
    ag.scene = FakeScene()
    ag.locks = FakeLocks()
    ag.m = metrics
    ag.task = None
    ag.target = None
    ag.state = "IDLE"
    ag._timer = 0
    ag._place_at = None
    ag._blocked = 0
    ag._hover_z = lambda: 1.0
    return ag


def metrics():
    return NS(makespan_ticks=0, contended_claims=0,
              completed={"ur_w": 0, "ur_e": 0, "franka_s": 0, "franka_n": 0},
              blocked={}, requeued=0)


# ---------------------------------------------------------------------------
# 1. fields exist and default to None
# ---------------------------------------------------------------------------
t0 = Task(obj="ycb_soup_can", dest=(-0.7, 0.5))
check("Task carries exec_start_tick and travel_leg_m, defaulting to None",
      t0.exec_start_tick is None and t0.travel_leg_m is None
      and t0._travel_at_claim is None)

# ---------------------------------------------------------------------------
# 2. travel_leg_m is a DIFFERENCE, not an episode total
# ---------------------------------------------------------------------------
m = metrics()
arm = FakeArm("ur_w", travel=40.0)           # 40 m already flown this episode
ag = make_agent(arm, m)
task = Task(obj="ycb_soup_can", dest=(-0.7, 0.5))

m.makespan_ticks = 500
ag.claim(task, (-0.7, 0.5))
check("claim stamps exec_start_tick and the odometer cursor",
      task.exec_start_tick == 500 and task._travel_at_claim == 40.0,
      f"{task.exec_start_tick}, {task._travel_at_claim}")
check("claim_tick keeps its own first-claim meaning",
      task.claim_tick == 500)

arm.travel_m = 42.5                           # 2.5 m during this task
m.makespan_ticks = 800
ag._arrived = lambda: True                    # force the completion branch
ag._go_home()
check("travel_leg_m is the in-window difference, not the episode total",
      abs(task.travel_leg_m - 2.5) < 1e-6, str(task.travel_leg_m))
check("done_tick closes the same window exec_start_tick opened",
      task.done_tick == 800 and task.exec_start_tick == 500)
check("the window is non-empty and consistent",
      task.done_tick > task.exec_start_tick and task.travel_leg_m > 0)

# ---------------------------------------------------------------------------
# 3. ABORT: re-claimed by a DIFFERENT arm, only the finisher's distance
# ---------------------------------------------------------------------------
m2 = metrics()
a1 = FakeArm("ur_w", travel=10.0)
a2 = FakeArm("franka_n", travel=99.0)         # a very different odometer
ag1, ag2 = make_agent(a1, m2), make_agent(a2, m2)
t = Task(obj="ycb_bowl", dest=(0.7, 0.5))

m2.makespan_ticks = 100
ag1.claim(t, (0.7, 0.5))                      # first claim, ur_w
a1.travel_m = 13.0                            # 3 m before it aborts
first_claim = t.claim_tick

m2.makespan_ticks = 400
ag2.claim(t, (0.7, 0.5))                      # re-claim by franka_n
a2.travel_m = 99.75                           # 0.75 m to finish
m2.makespan_ticks = 600
ag2._arrived = lambda: True
ag2._go_home()

check("re-claim moves exec_start_tick but NOT claim_tick",
      t.claim_tick == first_claim == 100 and t.exec_start_tick == 400,
      f"claim_tick={t.claim_tick} exec_start={t.exec_start_tick}")
check("abort case: only the FINISHING arm's distance is reported",
      abs(t.travel_leg_m - 0.75) < 1e-6, str(t.travel_leg_m))
check("the straddling delta (which would be meaningless) is NOT reported",
      abs(t.travel_leg_m - (99.75 - 10.0)) > 1.0)

# ---------------------------------------------------------------------------
# 3b. BLOCKED TICKS per task (Step A2). The agent's own _blocked counter is
#     a CONSECUTIVE run that resets on every successful acquire, because it
#     exists to time out a stuck arm. The calibration needs the CUMULATIVE
#     total for the task, so the two must not be confused.
# ---------------------------------------------------------------------------
class CountingLocks(FakeLocks):
    """Refuses the first `deny` acquires, then grants."""

    def __init__(self, deny):
        super().__init__()
        self.left = deny

    def acquire(self, z, a):
        if self.left > 0:
            self.left -= 1
            return False
        return True


m4 = metrics()
m4.blocked = {"ur_w": 0}
a4 = FakeArm("ur_w", travel=0.0)
ag4 = make_agent(a4, m4)
ag4.locks = CountingLocks(deny=7)
t4 = Task(obj="ycb_soup_can", dest=(-0.7, 0.5))
ag4.locks.is_contended = lambda z, a: False
ag4.claim(t4, (-0.7, 0.5))
check("blocked_ticks starts at 0 on claim", t4.blocked_ticks == 0)
for _ in range(10):
    ag4._need("center")
check("blocked_ticks accumulates one per denied acquire",
      t4.blocked_ticks == 7, str(t4.blocked_ticks))
check("the agent's _blocked is a CONSECUTIVE run and reset on success, so "
      "it is NOT the per-task total",
      ag4._blocked == 0 and t4.blocked_ticks == 7,
      f"_blocked={ag4._blocked} task={t4.blocked_ticks}")
check("per-arm and per-task counters agree on a single-task arm",
      m4.blocked["ur_w"] == t4.blocked_ticks)

# a re-claim resets the per-task total (that waiting belonged to the
# aborted attempt), matching travel_leg_m and exec_start_tick semantics
ag4.claim(t4, (-0.7, 0.5))
check("re-claim resets blocked_ticks to 0", t4.blocked_ticks == 0)

# blocking with no task in hand must not raise
ag4.task = None
ag4.locks.left = 2
ag4._need("center")
check("blocking with no task in hand is safe", True)

# ---------------------------------------------------------------------------
# 4. reaches the episode JSON through the REAL logger
# ---------------------------------------------------------------------------
rec = EpisodeLogger._task_record(task)
check("logger emits all three new fields",
      rec.get("exec_start_tick") == 500
      and abs(rec.get("travel_leg_m") - 2.5) < 1e-6
      and rec.get("blocked_ticks") == 0, str(rec)[:200])
check("existing task fields are untouched",
      rec["claim_tick"] == 500 and rec["done_tick"] == 800
      and rec["arm"] == "ur_w" and rec["done"] is True)

# ---------------------------------------------------------------------------
# 5. nothing is required: no odometer -> None, no exception
# ---------------------------------------------------------------------------
m3 = metrics()
bare = FakeArm("ur_e")
del bare.travel_m                             # an arm without D1 wired
ag3 = make_agent(bare, m3)
t3 = Task(obj="ycb_mug", dest=(0.7, 0.5))
m3.makespan_ticks = 10
ag3.claim(t3, (0.7, 0.5))
m3.makespan_ticks = 20
ag3._arrived = lambda: True
ag3._go_home()
check("an arm with no odometer logs None instead of raising",
      t3.travel_leg_m is None and t3.exec_start_tick == 10)
check("and the logger still records it",
      EpisodeLogger._task_record(t3).get("travel_leg_m") is None)

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
