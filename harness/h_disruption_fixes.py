"""Harness: the seven robustness fixes (imports the REAL modules).

Every one of these was a latent fault that could not fire in an
undisrupted episode, which is exactly why none of them was caught by the
existing suite. They are pinned here so they cannot come back.

  H4  a DISABLED arm must not count as a handover finisher, and must not
      count as a direct deliverer that suppresses a needed handover.
      Three sites: the validator, the patient floor, the rule.
  M4  a disabled arm must not emit arm_idle. abort() parks it in IDLE, so
      the availability ledger claimed a frozen arm had become available.
  M3  permanence must be re-tested over time, not once. It used to sit
      inside a once-only warning guard, so a task that was merely blocked
      the first time was never re-examined and an object displaced out of
      reach later never failed its task.
  H3  a handover declined for an occupied pad must invalidate the
      allocator's cached decision, or the leg is never re-offered.
  H2  a noop must not be able to freeze the cell. The re-consult gate
      keys on (idle, ready), which a noop leaves unchanged.
  D-time  every disruption event must fire inside the tick budget.
  D-body  displacement must pick an unsorted object and land it somewhere
      a capable arm can still serve; spawn must report pool exhaustion
      rather than firing inertly.

Run: python3 h_disruption_fixes.py
"""
import math
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

_torch = types.ModuleType("torch")
_torch.tensor = lambda x, **k: np.asarray(x, dtype=float)
_torch.norm = lambda x: float(np.linalg.norm(np.asarray(x)))
_torch.float32 = np.float32
sys.modules.setdefault("torch", _torch)

from core.cell import cell_config as C                      # REAL config
from core.cell.zones import ZoneMap                         # REAL rasters
from core.control.tasks import rule_based_allocate, Task     # REAL rule
from core.control import disruptions as dis                  # REAL engine
from core.decision import vlm_allocator as va                # REAL allocator

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


ZM = ZoneMap(os.path.join(os.path.dirname(__file__), "..", "fourarm",
                          "core", "cell", "reachability", "rasters"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm",
                                "ycb"))
from ycb_objects import register_specs                       # REAL registry
for n in ("gelatin_box", "mug", "banana"):
    register_specs(C.OBJECT_SPECS, f"ycb_{n}", n)

# ---------------------------------------------------------------------------
# H4 (a) the RULE's handover finisher must exclude disabled arms
# ---------------------------------------------------------------------------
# gelatin_box in the far east, destination the food basket in the west.
# ur_e can reach the object and the centre pad; ur_w and franka_n can
# finish from the pad. Kill both finishers and the handover must vanish.
t = Task(obj="ycb_gelatin_box", dest=(-0.70, 0.50))
OBJ = (0.82, 0.22)
arm, target, sub = rule_based_allocate(t, OBJ, ["ur_e"], ZM)
check("rule proposes a handover when a finisher is alive",
      sub is not None and arm == "ur_e", f"{arm} {target} {sub}")

arm2, target2, sub2 = rule_based_allocate(
    t, OBJ, ["ur_e"], ZM, disabled=frozenset({"ur_w", "franka_n", "franka_s"}))
check("rule refuses the handover when every finisher is disabled",
      sub2 is None and arm2 is None, f"{arm2} {target2} {sub2}")
check("the disabled argument defaults to empty (old callers unaffected)",
      rule_based_allocate(t, OBJ, ["ur_e"], ZM)[2] is not None)

# ---------------------------------------------------------------------------
# H4 (b) the VALIDATOR's finisher list must exclude disabled arms
# ---------------------------------------------------------------------------
def make_coord(disabled=()):
    agents, arms = {}, {}
    for name in C.ARMS:
        a = NS(disabled=name in disabled, _carried=None)
        arms[name] = a
        agents[name] = NS(arm=a, state="IDLE")
    task = Task(obj="ycb_gelatin_box", dest=(-0.70, 0.50))
    task.id = 0
    scene = {"ycb_gelatin_box": NS(data=NS(
        root_pos_w=np.array([[OBJ[0], OBJ[1], 0.9]])))}
    return NS(agents=agents, pool=[task], cell=NS(scene=scene, arms=arms))


# Since 2026-08-01 the model does not name a pad: it names an arm and the
# router builds the handover. The via_pad key is left in this decision on
# purpose, to pin that a volunteered pad is ignored rather than obeyed.
DEC = {"task_id": 0, "arm": "ur_e", "via_pad": "center"}
ok, tgt, sub, why = va.validate_decision(DEC, make_coord(), ZM)
check("validator accepts the handover with finishers alive", ok, why)
check("the route it built is the pad, carried by a subtask",
      sub is not None and va._pad_name(tgt) is not None,
      f"{tgt} {sub}")
ok2, _, _, why2 = va.validate_decision(
    DEC, make_coord(disabled={"ur_w", "franka_n", "franka_s"}), ZM)
check("validator refuses it when every finisher is disabled",
      not ok2 and "no handover route exists" in (why2 or ""), str(why2))

# ---------------------------------------------------------------------------
# M4 arm_idle must not fire for a disabled arm
# ---------------------------------------------------------------------------
import inspect
from core.control import tasks as tasks_mod
# The availability ledger moved out of tick() into _record_transitions()
# on 2026-08-02, so that a round held by the settle-wait policy still
# records the transitions its arms make. The guard moved with it. This
# check follows the code rather than pinning it to a method name: whichever
# method emits arm_idle must carry the disabled guard.
_emitters = [m for m in (tasks_mod.Coordinator.tick,
                         tasks_mod.Coordinator._record_transitions)
             if "arm_idle" in inspect.getsource(m)]
check("exactly one method emits arm_idle", len(_emitters) == 1,
      str([m.__name__ for m in _emitters]))
src = inspect.getsource(_emitters[0]) if _emitters else ""
check("arm_idle emission is guarded on disabled",
      'ag.state == "IDLE" and not ag.arm.disabled' in src,
      src[max(0, src.find("arm_idle") - 120):src.find("arm_idle") + 40])

# ---------------------------------------------------------------------------
# M3 permanence is re-tested on a clock, not once
# ---------------------------------------------------------------------------
asrc = inspect.getsource(tasks_mod.Coordinator._assign)
i_perm = asrc.find("_permanently_unallocatable")
i_warn = asrc.find("self._warned.add(task.id)")
check("the permanence test is NOT inside the once-only warning guard",
      0 <= i_perm < i_warn, f"perm at {i_perm}, warn at {i_warn}")
check("it is gated on a recheck period, not a set membership",
      "PERMANENCE_RECHECK" in asrc and isinstance(C.PERMANENCE_RECHECK, int),
      str(getattr(C, "PERMANENCE_RECHECK", None)))

# ---------------------------------------------------------------------------
# H3 a declined busy-pad handover invalidates the allocator's decision
# ---------------------------------------------------------------------------
check("the coordinator calls invalidate() on a pad decline",
      'getattr(self.allocate, "invalidate", None)' in asrc)

alloc = va.VLMAllocator(lambda: None, engine=None, condition="A",
                        model_fn=lambda m, timeout=30.0: "{}")
alloc._cached = (0, "ur_w", (0.1, 0.2), None)
alloc._sig = ("something",)
alloc.invalidate()
check("invalidate() clears the cached decision and the signature",
      alloc._cached is None and alloc._sig is None
      and alloc.stats["invalidated"] == 1, str(alloc.stats.get("invalidated")))

# ---------------------------------------------------------------------------
# H2 a standing noop cannot freeze the cell
# ---------------------------------------------------------------------------
va.build_state = lambda c, e, tick=None, baskets=None, zonemap=None, eligible=False: {
    "arms": [], "tasks": []}
va.build_prompt = lambda s, cond, image_b64=None: [
    {"role": "system", "content": "s"},
    {"role": "user", "content": [{"type": "text", "text": "t"}]}]
va.validate_decision = lambda d, c, z, b=None: (True, (0.1, 0.2), None, None)

class FrozenCell:
    """Every arm idle, one task ready, and a model that always waits.
    The signature never changes, so only the watchdog can break the loop."""
    def __init__(self):
        self.t = Task(obj="ycb_mug", dest=(0.7, 0.5)); self.t.id = 0
        self.agents = {n: NS(arm=NS(disabled=False), state="IDLE")
                       for n in C.ARMS}
        self.pool = [self.t]
        self.cell = NS(scene={}, arms={})
        self._assign_round = 0

calls = {"n": 0}
def always_wait(messages, timeout=30.0):
    calls["n"] += 1
    return '{"task_id": -1, "arm": null, "reason": "waiting"}'

cellf = FrozenCell()
alloc = va.VLMAllocator(lambda: cellf, engine=None, condition="A",
                        model_fn=always_wait)
alloc.noop_watchdog = 50
for tick in range(1, 301):
    cellf._assign_round = tick
    alloc(cellf.t, (0.3, 0.55), list(C.ARMS), ZM)
check("a standing noop does NOT stop the model being re-asked",
      calls["n"] > 1, f"{calls['n']} model calls over 300 ticks")
check("the watchdog fired and is counted",
      alloc.stats.get("noop_watchdog_fired", 0) >= 4,
      str(alloc.stats.get("noop_watchdog_fired")))
calls["n"] = 0
cellf2 = FrozenCell()
alloc2 = va.VLMAllocator(lambda: cellf2, engine=None, condition="A",
                         model_fn=always_wait)
alloc2.noop_watchdog = 0                     # watchdog off = old behaviour
for tick in range(1, 301):
    cellf2._assign_round = tick
    alloc2(cellf2.t, (0.3, 0.55), list(C.ARMS), ZM)
check("watchdog off reproduces the freeze exactly (1 call in 300 ticks)",
      calls["n"] == 1, f"{calls['n']} calls")

# ---------------------------------------------------------------------------
# disruption timing: every event must land inside the tick budget
# ---------------------------------------------------------------------------
SIM_HZ = 1.0 / C.SIM_DT
for horizon, budget in ((20.0, 2450), (30.0, 3600)):
    sch = dis.make_schedule(seed=0, profile="mixed", horizon_s=horizon)
    late = [(e.kind, e.t) for e in sch if e.t * SIM_HZ >= budget]
    check(f"every mixed event fires before tick {budget} (horizon {horizon}s)",
          not late, str(late))
check("D3 arm failure is scheduled at all",
      any(e.kind == "disable_arm"
          for e in dis.make_schedule(seed=0, profile="D3", horizon_s=20.0)))
check("the OLD absolute schedule would have missed it (regression record)",
      30.0 * SIM_HZ >= 2450, f"tick {30.0 * SIM_HZ:.0f} vs a ~2450-tick run")
check("D4 draws from the categories it is given",
      dis.make_schedule(seed=0, profile="D4", categories=["tools"]
                        )[0].params["command"].startswith("tools"))

# ---------------------------------------------------------------------------
# disruption bodies: victims and targets
# ---------------------------------------------------------------------------
esrc = inspect.getsource(dis.DisruptionEngine._apply)
check("displacement skips already-sorted objects",
      "self.is_sorted(o)" in esrc)
check("displacement targets a cell a CAPABLE arm can serve",
      "_reachable_clear_xy" in esrc)
check("spawn reports pool exhaustion instead of firing inertly",
      "object pool exhausted" in esrc)

eng = dis.DisruptionEngine.__new__(dis.DisruptionEngine)
eng.arms = {n: None for n in C.ARMS}
eng.zonemap = ZM
import random as _r
eng.rng = _r.Random(0)
check("_in_reach agrees with the rasters for a capable arm",
      eng._in_reach("ycb_mug", 0.68, 0.03)
      and not eng._in_reach("ycb_mug", -1.39, -0.79),
      "mug is UR-only; the far SW corner is outside ur_w's measured map")
xs = [eng._reachable_clear_xy("ycb_mug", []) for _ in range(25)]
check("every sampled displacement target is servable",
      all(eng._in_reach("ycb_mug", x, y) for x, y in xs),
      str([p for p in xs if not eng._in_reach("ycb_mug", *p)][:3]))

# ---------------------------------------------------------------------------
# RUNNER WIRING: the fixes above are inert unless the runner passes them
# ---------------------------------------------------------------------------
runner = os.path.join(os.path.dirname(__file__), "..", "fourarm", "ycb",
                      "run_ycb_sort.py")
rsrc = open(runner).read()
# The horizon must be an EXPECTED episode length, not the safety cap.
# Deriving it from --max-ticks (default 12000 = 100 s) put seven of eight
# mixed events after the episode had already ended: a b1 run fired one.
check("runner does NOT scale the horizon to the tick cap",
      "horizon_s=args_cli.max_ticks" not in rsrc)
check("runner uses the measured episode horizon, overridable",
      "C.EPISODE_HORIZON_S" in rsrc and "--disrupt-horizon" in rsrc)
SHORTEST = 2410            # shortest makespan measured across all columns
sched = dis.make_schedule(seed=0, profile="mixed",
                          horizon_s=C.EPISODE_HORIZON_S)
outside = [(e.kind, round(e.t / C.SIM_DT)) for e in sched
           if e.t / C.SIM_DT >= SHORTEST]
check("every mixed event lands inside the SHORTEST observed episode",
      not outside, str(outside))
check("the old wiring would have missed most of them (regression record)",
      sum(1 for e in dis.make_schedule(seed=0, profile="mixed",
                                       horizon_s=12000 * C.SIM_DT)
          if e.t / C.SIM_DT < 2710) == 1,
      "1 of 8 fired in the b1 run that caught this")

# the runner must not whitelist event params: "skipped" was being dropped,
# so a correctly-reported exhausted pool logged as a silent inert spawn
check("runner copies every disruption param, not a whitelist",
      'if k not in ("tick", "type", "kind")' in rsrc
      and 'if k in ("object", "arm", "x", "y", "command")' not in rsrc)
check("runner passes the scene's real categories to D4",
      "categories=sorted(CATEGORY_BASKET)" in rsrc)
check("runner gives the engine its own sorted test",
      "is_sorted=_already_sorted" in rsrc and "CATCH_RADIUS" in rsrc)
check("runner gives the engine the measured rasters",
      "zonemap=zonemap" in rsrc)
check("zonemap is built BEFORE the engine that receives it",
      rsrc.index("zonemap = ZoneMap()") < rsrc.index("DisruptionEngine("))

# the engine's own signature must accept them, with safe defaults
import inspect as _i
sig = _i.signature(dis.DisruptionEngine.__init__)
for arg in ("horizon_s", "categories", "is_sorted", "zonemap"):
    check(f"DisruptionEngine accepts {arg} with a default",
          arg in sig.parameters
          and sig.parameters[arg].default is not _i.Parameter.empty)

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
