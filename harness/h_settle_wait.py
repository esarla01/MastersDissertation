"""h_settle_wait: the settle-wait policy holds a round only when it should,
never for longer than its cap, and changes nothing when it is off.

Drives a REAL Coordinator with stub arms, so the guard is exercised rather
than read. Nothing here reimplements it.

Why the policy exists. Measured over two episodes, 18 of 21 accepted
decisions were taken with exactly ONE arm idle, so "which arm" had one
answer. Meanwhile every idle-arm subset of size two or more on
decision_rich already offers a scarcity trap. The decision content is in
the cell; the rounds simply do not visit it, because each round drains from
four candidates to one.

What is pinned, and the failure each one guards against:

  1. settle_wait = 0 changes nothing at all. Every episode recorded before
     2026-08-02 must remain reproducible, and if the default moved, every
     existing reference number would silently be against a different
     substrate.
  2. The wait is CAPPED. Without it a round could be held indefinitely and
     the episode would never terminate.
  3. A round with two or more idle arms is never held. It already offers a
     choice, so waiting could only cost makespan.
  4. A DISABLED arm never triggers a wait. It will never reach IDLE, so
     waiting on it would hold every round to the cap forever.
  5. tight and broad differ, and an unknown preset is refused rather than
     defaulted. A run labelled tight that actually waited on broad would be
     invisible in the output.
  6. Agents still tick while the round is held, or the arm being waited for
     could never finish.
  7. Phase names in the presets exist in the real state machine. They are
     string literals scattered through it, so a rename would make the guard
     silently never match.

Run:  python3 h_settle_wait.py
"""

import inspect
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.cell import cell_config as C                          # noqa: E402
from core.control import tasks as T                             # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


class StubAgent:
    """Only what _hold_round reads: a state string and arm.disabled.
    tick() counts calls, which is how "agents still move" is checked."""

    def __init__(self, state="IDLE", disabled=False):
        self.state = state
        self.arm = NS(disabled=disabled)
        self.ticks = 0

    def tick(self):
        self.ticks += 1


def make_coord(states, settle_wait=0, settle_phases="tight", disabled=()):
    """A real Coordinator with _assign and the proximity watch stubbed out,
    so what is measured is the GUARD and nothing else."""
    cell = NS(arms={n: NS(disabled=(n in disabled)) for n in C.ARMS},
              scene={})
    coord = T.Coordinator.__new__(T.Coordinator)
    coord.cell = cell
    # Contended, which is what this policy is about: the settle wait exists
    # to raise the share of rounds taken with two arms idle, and a
    # serialised cell holds every round until all four are.
    coord.serialised = False
    coord.settle_wait = int(settle_wait)
    if settle_phases not in T.SETTLE_PHASES:
        raise ValueError(settle_phases)
    coord.settle_phases = settle_phases
    coord._settle_set = frozenset(T.SETTLE_PHASES[settle_phases])
    coord._settle_waited = 0
    coord._settle_spent = frozenset()
    coord.m_settle = {"waits": 0, "ticks_held": 0, "expired": 0,
                      "paid_off": 0}
    coord.agents = {n: StubAgent(states.get(n, "IDLE"), n in disabled)
                    for n in C.ARMS}
    coord._last_state = {n: coord.agents[n].state for n in C.ARMS}
    coord._phase_entered = {n: {} for n in C.ARMS}
    coord.phase_dwell = []
    coord.assigned = 0
    coord._assign_round = 0
    coord.m = NS(makespan_ticks=0)
    coord.locks = NS(tick=0)
    coord._drain_disabled = lambda: None
    coord._assign = lambda: setattr(coord, "assigned", coord.assigned + 1)
    coord._watch_proximity = lambda: None
    coord.event = lambda *a, **k: None
    return coord


ARMS = list(C.ARMS)
A, B, D, E = ARMS[0], ARMS[1], ARMS[2], ARMS[3]

# ---------------------------------------------------------------------------
# 1. off by default
# ---------------------------------------------------------------------------
c = make_coord({A: "IDLE", B: "SETTLING", D: "TO_PICK", E: "TO_PICK"},
               settle_wait=0)
held = [c._hold_round() for _ in range(5)]
check("settle_wait 0 never holds a round", not any(held), str(held))
check("and records no wait at all", c.m_settle["waits"] == 0)

# ---------------------------------------------------------------------------
# 2. holds, and is capped
# ---------------------------------------------------------------------------
c = make_coord({A: "IDLE", B: "SETTLING", D: "TO_PICK", E: "TO_PICK"},
               settle_wait=3)
held = [c._hold_round() for _ in range(8)]
check("a wait is held for exactly the cap, then released",
      held[:4] == [True, True, True, False], str(held))
check("and does NOT re-arm on the same finishing arms",
      not any(held[4:]),
      "otherwise an arm sitting in a settle phase throttles allocation "
      "to once every cap+1 ticks: " + str(held))

# A DIFFERENT arm reaching a settle phase is a new configuration and does
# earn a fresh wait, so the policy is not disabled by one expiry.
c.agents[D].state = "SETTLING"
check("a new finishing arm re-arms the policy", c._hold_round() is True)
check("the cap is counted as an expiry", c.m_settle["expired"] >= 1,
      str(c.m_settle))
check("ticks held equals the cap", c.m_settle["ticks_held"] >= 3,
      str(c.m_settle))

# ---------------------------------------------------------------------------
# 3. never held when a choice already exists
# ---------------------------------------------------------------------------
c = make_coord({A: "IDLE", B: "IDLE", D: "SETTLING", E: "TO_PICK"},
               settle_wait=200)
check("two idle arms means no hold, however close another is to finishing",
      c._hold_round() is False)

c = make_coord({A: "IDLE", B: "TO_PICK", D: "TO_PICK", E: "TO_PICK"},
               settle_wait=200)
check("nothing finishing means no hold", c._hold_round() is False)

# ---------------------------------------------------------------------------
# 4. a disabled arm never triggers a wait
# ---------------------------------------------------------------------------
c = make_coord({A: "IDLE", B: "SETTLING", D: "TO_PICK", E: "TO_PICK"},
               settle_wait=200, disabled=(B,))
check("a DISABLED arm in a settle phase does not hold the round",
      c._hold_round() is False, "it would never reach IDLE")

# A disabled arm also must not count toward the two-idle exemption.
c = make_coord({A: "IDLE", B: "IDLE", D: "SETTLING", E: "TO_PICK"},
               settle_wait=200, disabled=(B,))
check("a disabled arm does not count as an idle candidate either",
      c._hold_round() is True)

# ---------------------------------------------------------------------------
# 5. presets
# ---------------------------------------------------------------------------
c = make_coord({A: "IDLE", B: "GO_HOME", D: "TO_PICK", E: "TO_PICK"},
               settle_wait=200, settle_phases="tight")
check("tight does NOT wait on GO_HOME (a real travel leg)",
      c._hold_round() is False)
c = make_coord({A: "IDLE", B: "GO_HOME", D: "TO_PICK", E: "TO_PICK"},
               settle_wait=200, settle_phases="broad")
check("broad does wait on GO_HOME", c._hold_round() is True)

check("tight is the conservative subset of broad",
      set(T.SETTLE_PHASES["tight"]) < set(T.SETTLE_PHASES["broad"]),
      str(T.SETTLE_PHASES))

try:
    T.Coordinator(NS(arms={}, scene={}), None, settle_phases="loose")
    check("an unknown preset is refused", False, "no exception")
except ValueError as e:
    check("an unknown preset is refused, not defaulted",
          "loose" in str(e), str(e)[:70])
except Exception as e:
    check("an unknown preset is refused, not defaulted", False,
          f"{type(e).__name__}: {e}")

# ---------------------------------------------------------------------------
# 6. the cell keeps moving while a round is held
# ---------------------------------------------------------------------------
c = make_coord({A: "IDLE", B: "SETTLING", D: "TO_PICK", E: "TO_PICK"},
               settle_wait=3)
for _ in range(3):
    c.tick()
check("agents tick while the round is held",
      all(ag.ticks == 3 for ag in c.agents.values()),
      str({n: ag.ticks for n, ag in c.agents.items()}))
check("and no assignment happened during the hold", c.assigned == 0,
      str(c.assigned))
# THE CLOCK MUST ADVANCE. The first version returned before
# makespan_ticks += 1, so a held tick was invisible to every
# tick-denominated metric: makespan came out 1626 against a true 3158 and
# the phase-dwell medians shrank with the cap. Time passes whether or not
# an allocation happens.
check("the clock advances on a held tick",
      c.m.makespan_ticks == 3, str(c.m.makespan_ticks))

# paid_off is the only number that says the policy achieved its purpose,
# and it read 0 in every run because _hold_round cleared the counter before
# the caller could see it.
c2 = make_coord({A: "IDLE", B: "SETTLING", D: "TO_PICK", E: "TO_PICK"},
                settle_wait=200)
c2._hold_round()
check("a wait is in progress", c2._settle_waited == 1)
c2.agents[B].state = "IDLE"          # the arm we were waiting for arrives
c2._hold_round()
check("a wait that ends with a second idle arm counts as paid off",
      c2.m_settle["paid_off"] == 1, str(c2.m_settle))

c3 = make_coord({A: "IDLE", B: "SETTLING", D: "TO_PICK", E: "TO_PICK"},
                settle_wait=2)
for _ in range(4):
    c3._hold_round()
check("a wait that runs out counts as expired, not paid off",
      c3.m_settle["expired"] == 1 and c3.m_settle["paid_off"] == 0,
      str(c3.m_settle))
c.tick()
check("the round runs once the cap expires", c.assigned == 1, str(c.assigned))

# ---------------------------------------------------------------------------
# 7. the phase names are real
# ---------------------------------------------------------------------------
machine = inspect.getsource(T)
missing = [p for names in T.SETTLE_PHASES.values() for p in names
           if f'"{p}"' not in machine]
check("every phase named in a preset exists in the state machine",
      not missing, str(sorted(set(missing))))

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
