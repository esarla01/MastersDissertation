"""Layer 2: tasks, per-arm state machines, allocation, coordination.

A Task is "move object O to destination (x, y)". The pick position is never
stored; it is read live from the simulator when an arm claims the task, so
displaced or dropped objects are handled for free.

Handovers are not a special mechanism. If no single arm reaches both the
object and the destination, the allocator creates a subtask that moves the
object to an exchange pad reachable from both sides, and parks the original
task until the subtask completes. Once the object sits on the pad, the
original task becomes ordinarily feasible for the second arm.

ArmAgent is a small state machine over the Layer 1 Arm:
  IDLE -> (claim) -> TO_PICK -> DESCEND -> ATTACH -> LIFT
       -> TO_PLACE -> LOWER -> RELEASE -> RETREAT -> IDLE
with BLOCKED (waiting on a zone lock, metered) reachable before any motion
into a zone, and D3-disabled arms drained by the coordinator.

The Coordinator owns the task pool, the allocator, the locks, and the
metrics. The allocator here is the RULE-BASED BASELINE; Layer 4 swaps in the
MLLM behind the same allocate() signature.
"""

from dataclasses import dataclass, field
import itertools
import math

from core.cell import cell_config as C
from core.cell.locks import ZoneLocks, zone_of

_ids = itertools.count()


@dataclass
class Task:
    obj: str                            # scene object name
    dest: tuple | None                  # (x, y), or None: allocator chooses the basket
    id: int = field(default_factory=lambda: next(_ids))
    waiting_on: int | None = None       # parked until this task id completes
    arm: str | None = None              # executor identity, set at claim
    claimed: bool = False               # currently executed by some arm
    done: bool = False
    attempts: int = 0                   # aborts so far
    failed: bool = False                # gave up after MAX_TASK_ATTEMPTS
    # provenance and lifecycle (episode logger / results tables)
    dest_by: str | None = None          # 'given' | 'model' | 'oracle'
    submit_tick: int | None = None
    claim_tick: int | None = None       # first claim only
    done_tick: int | None = None
    # PER-TASK EXECUTION WINDOW (2026-07-29). The timing model was fitted
    # against per-EPISODE travel while its target, productive ticks, spans
    # only claim..done. Measurement and predictor therefore described
    # different spans, the regression buried the difference in its
    # constants, and the fitted UR coefficient implied 6.3 m/s. These three
    # fields close that: exec_start_tick..done_tick is a window, and
    # travel_leg_m is exactly the distance this arm covered inside it.
    #
    # Recorded on EVERY claim, not just the first, so an aborted-and-
    # requeued task measures the arm that actually finished it rather than
    # a delta straddling two arms. claim_tick keeps its first-claim-only
    # meaning for wait-time accounting; exec_start_tick is the execution
    # window and is the one the calibration must use.
    exec_start_tick: int | None = None   # tick of the LAST claim
    travel_leg_m: float | None = None    # metres travelled claim..done
    _travel_at_claim: float | None = None   # internal cursor
    # Ticks this task spent waiting for a zone lock, cumulative over its
    # execution window. NOT the agent's _blocked counter, which resets on
    # every successful acquire because it exists to time out a stuck arm.
    # The calibration must SUBTRACT this: an arm waiting for a zone is not
    # moving slowly, it is standing still, and a fit that cannot tell the
    # difference learns whatever congestion happened on the training day.
    # Measured only, never predicted; the cost model prices motion, and
    # contention enters separately as an optional surcharge.
    blocked_ticks: int = 0
    # SERIALISED CELL (EX1 v2). A held task is in the pool, has an id, and
    # is INVISIBLE: build_state does not render it, the allocator is never
    # offered it, and the validator rejects it if a reply names one anyway.
    # It is how "one task at a time" reaches the MODEL and not only the
    # coordinator. Serialising the offer alone would leave every queued
    # task in the rendered state, so the model would still be choosing
    # which task to serve, and removing task selection from the decision is
    # half of what the redesign is for. Always False in the contended cell,
    # so nothing already recorded moves.
    held: bool = False
    kind: str = "primary"               # 'primary' | 'handover_leg' (set by
                                        # the coordinator when it authors a
                                        # pad leg); makes the tasks table
                                        # self-explanatory in the JSON
    required_zones: list = field(default_factory=list)
                                        # spatial footprint declared at claim
                                        # time (pick zone + target zone):
                                        # every decision's zone needs are
                                        # stated when made and auditable
                                        # against the lock ledger after


# ---------------------------------------------------------------------------
# Rule-based allocator (the baseline; the MLLM replaces exactly this).
# ---------------------------------------------------------------------------

def _base_dist(arm, xy):
    """Planar distance from an arm's BASE to a point. Tie-break only."""
    b = C.ARMS[arm]["pos"]
    return math.hypot(xy[0] - b[0], xy[1] - b[1])


def route_via_pad(task, obj_xy, candidates, zonemap, disabled=()):
    """Best progressing exchange pad for a first leg by one of `candidates`.

    Returns (arm_name, (px, py), subtask) or (None, None, None), the same
    shape rule_based_allocate returns.

    `candidates` are the arms allowed to carry the FIRST leg. For b1 that is
    every idle capable arm. For the VLM head it is the single arm the model
    named, so the model chooses the arm and the router chooses the pad,
    which is exactly what the classical heads do.

    Lifted out of rule_based_allocate 2026-08-01, logic unchanged, so the
    VLM head can delegate pad routing instead of naming a pad in its answer.
    h_pad_router.py pins b1 output over 1980 scenarios against values
    recorded before the extraction.
    """
    # Handover: pad must be reachable by a feasible first arm AND by some arm
    # (idle or not) that also reaches the destination. Two rules learned from
    # the first YCB runs: a leg must make STRICT PROGRESS toward the
    # destination (dict-order pad choice ping-ponged the gelatin box
    # center<->pad_ne four times, ~1.6 m of pointless carrying), and among
    # progressing pads the one nearest the destination wins. Monotone
    # progress makes relay cycles structurally impossible: each hop shrinks
    # the object's distance to its destination, so no pad repeats.
    d_dest = math.hypot(obj_xy[0] - task.dest[0], obj_xy[1] - task.dest[1])
    best = None
    for pad, spec in C.EXCHANGE_PADS.items():
        px, py = spec["pos"]
        if math.hypot(obj_xy[0] - px, obj_xy[1] - py) < C.PAD_SKIP_RADIUS:
            continue                   # object is already on this pad
        pad_to_dest = math.hypot(px - task.dest[0], py - task.dest[1])
        if pad_to_dest >= d_dest - 0.05:
            continue                   # would not (meaningfully) progress
        first = [a for a in candidates
                 if zonemap.reachable(a, *obj_xy) and zonemap.reachable(a, px, py)]
        second = [a for a in C.ARMS
                  if a not in disabled and C.can_grasp(a, task.obj)
                  and zonemap.reachable(a, px, py) and zonemap.reachable(a, *task.dest)]
        second = [a for a in second if a not in first or len(first) > 1]
        if first and second and (best is None or pad_to_dest < best[0]):
            best = (pad_to_dest, px, py, first)
    if best is not None:
        _, px, py, first = best
        sub = Task(obj=task.obj, dest=(px, py))
        return min(first, key=lambda a: _base_dist(a, obj_xy)), (px, py), sub
    return None, None, None


def rule_based_allocate(task, obj_xy, idle_arms, zonemap, disabled=()):
    if task.dest is None:
        return None, None, None         # cannot place without a destination
    """Return (arm_name, target_xy, subtask_or_None).

    Direct if some idle arm reaches both object and destination (nearest
    base wins). Otherwise route via the best exchange pad an idle arm can
    reach from the object side, emitting a subtask to that pad.
    """
    capable = [a for a in idle_arms if C.can_grasp(a, task.obj)]
    direct = [a for a in capable
              if zonemap.reachable(a, *obj_xy) and zonemap.reachable(a, *task.dest)]
    if direct:
        return min(direct, key=lambda a: _base_dist(a, obj_xy)), task.dest, None

    return route_via_pad(task, obj_xy, capable, zonemap, disabled)


# make_contention_aware_allocate (the retired B2-contention design) was
# removed here 2026-07-25 and archived VERBATIM in
# archive/retired_b2_contention.py. The thesis's B2 is the Hungarian
# matcher in core/decision/optimal_allocator.py (CLI name "opt").


# ---------------------------------------------------------------------------
# Per-arm state machine.
# ---------------------------------------------------------------------------

def find_place_spot(halfw, occupied, wall_half=None, gap=None):
    """Pure placement search in target-local coordinates.

    halfw: placing object's half footprint (m).
    occupied: [(dx, dy, other_halfw)] of objects already near the target.
    Returns (dx, dy, ok). Deterministic.

    Strategy: CORNER-FIRST. Candidates are tried in DESCENDING distance
    from the basket centre, the centre itself last. Centre-first filling
    let the first bulky arrival park in the middle and poison the basket
    for every later long object (the wood block at centre makes the drill
    unplaceable, arithmetic, not code). Corners are square-bounded (walls
    are square; the diagonal reach is what fits three long objects) and
    radially capped at PLACE_MAX_R so every set-down still scores as
    sorted.
    """
    wall_half = C.BASKET_WALL_HALF if wall_half is None else wall_half
    gap = C.PLACE_GAP if gap is None else gap
    u = wall_half - halfw - gap            # max |dx|, |dy| inside the walls
    if u < 0:                              # object wider than the basket
        return 0.0, 0.0, False
    cands = []
    for frac in (1.0, 0.75, 0.5):
        d = u * frac
        for cx, cy in ((d, d), (-d, -d), (d, -d), (-d, d),
                       (d, 0.0), (-d, 0.0), (0.0, d), (0.0, -d)):
            r = math.hypot(cx, cy)
            if r > C.PLACE_MAX_R:          # radial cap: stay scoreable
                s = C.PLACE_MAX_R / r
                cx, cy = cx * s, cy * s
            cands.append((round(cx, 4), round(cy, 4)))
    cands.append((0.0, 0.0))
    seen, ordered = set(), []
    for c in cands:                        # dedup, keep first occurrence
        if c not in seen:
            seen.add(c); ordered.append(c)
    ordered.sort(key=lambda c: (-math.hypot(*c), c))
    best, best_margin = (0.0, 0.0), -1e9
    for cx, cy in ordered:
        margin = min((math.hypot(cx - ox, cy - oy) - (halfw + oh + gap)
                      for ox, oy, oh in occupied), default=1e9)
        if margin >= 0.0:
            return cx, cy, True
        if margin > best_margin:
            best, best_margin = (cx, cy), margin
    return best[0], best[1], False


class ArmAgent:
    def __init__(self, arm, scene, locks, metrics, coord=None):
        self.arm = arm
        self.scene = scene
        self.locks = locks
        self.m = metrics
        self.coord = coord          # backref, for object retirement on completion
        self.state = "IDLE"
        self.task = None
        self.target = None                # this leg's place target (x, y)
        self._timer = 0
        self._blocked = 0
        self._place_at = None      # chosen set-down spot, held during descent
        self._home_fails = 0       # consecutive failed attempts to reach home
        self._recover_used = False # the one in-place recovery tuck per life

    # ------------------------------------------------------------- claims --
    def claim(self, task, target):
        task.claimed = True
        self._place_at = None
        # Declare the task's spatial footprint as inbound reservations:
        # advisory visibility for contention-aware allocation (B2, VLM
        # state), audited via the lock ledger. The physical acquire layer
        # is untouched.
        zones_needed = []
        p = self.scene[task.obj].data.root_pos_w[0]   # same access as obj_xy
        zones_needed.append(zone_of(float(p[0]), float(p[1])))
        if target is not None:
            zones_needed.append(zone_of(target[0], target[1]))
        task.required_zones = sorted(set(zones_needed))
        if any(self.locks.is_contended(z, self.arm.name)
               for z in task.required_zones):
            self.m.contended_claims += 1
        for z in task.required_zones:
            self.locks.reserve(z, self.arm.name)
        task.arm = self.arm.name       # executor identity: without it, the
                                       # episode JSON cannot answer 'which
                                       # arm ran this task, and was it free
                                       # earlier' (a reviewer question that
                                       # exposed the gap)
        if task.claim_tick is None:
            task.claim_tick = self.m.makespan_ticks
        # Execution window opens (or re-opens after an abort): stamp the
        # tick and the arm's travel odometer so the pair can be differenced
        # at done. getattr-guarded because Arm.travel_m is itself optional
        # instrumentation (episode_logger treats it the same way).
        task.exec_start_tick = self.m.makespan_ticks
        task._travel_at_claim = getattr(self.arm, "travel_m", None)
        task.blocked_ticks = 0           # window reopens: waiting from an
                                         # earlier, aborted attempt belongs
                                         # to that attempt, not this one
        self.task = task
        self._blocked = 0              # fresh task, fresh patience: a stale
                                       # counter burned 4 attempts in 4 ticks
        self.target = target
        self.state = "TO_PICK"
        self._timer = 0

    def obj_xy(self):
        p = self.scene[self.task.obj].data.root_pos_w[0]
        return float(p[0]), float(p[1]), float(p[2])

    # --------------------------------------------------------------- tick --
    def tick(self):
        if self.state == "IDLE" or self.arm.disabled:
            return
        self._timer += 1
        if self._timer == 1:               # fresh state: reset the detector
            self._best_err = None
            self._window_ref = None
            self._no_progress = 0
        err = self.arm.error()
        if err is not None:                # active goal: watch for progress
            if self._best_err is None:
                self._best_err = err
                self._window_ref = err     # window baseline = first sample
            elif err < self._best_err:
                self._best_err = err
            self._no_progress += 1
            if self._no_progress > C.STALL_ABORT_TICKS:
                # end of a window: the BEST error must have improved by the
                # threshold since the window baseline, else this is a stall.
                # (v1 reset the counter on ANY 1 cm twitch, so an
                # oscillating IK stall that occasionally scraped 1 cm
                # stretched its abort from ~600 to 2338 ticks and kept its
                # zone locked the whole time.)
                if self._window_ref - self._best_err >= C.STALL_MIN_IMPROVE:
                    self._window_ref = self._best_err
                    self._no_progress = 0
                else:
                    self.abort()
                    return
        else:
            self._no_progress = 0          # blocked/no goal: lock timeout rules
        handler = getattr(self, "_" + self.state.lower())
        handler()
        if self._timer > C.STEP_TIMEOUT_TICKS + C.LOCK_TIMEOUT_TICKS:
            self.abort()                   # safety net: never hang forever

    def _need(self, zone):
        """Acquire the zone or count a blocked tick. True when held."""
        if self.locks.acquire(zone, self.arm.name):
            self._blocked = 0
            return True
        self.m.blocked[self.arm.name] += 1
        if self.task is not None:        # per-task share of the same tick
            self.task.blocked_ticks += 1
        self._blocked += 1
        if self._blocked > C.LOCK_TIMEOUT_TICKS:
            self.abort()
        return False

    def _arrived(self):
        """Strict arrival, or stall acceptance: the position-only solver
        leaves a small residual at some poses (about 0.07 m was measured at
        the table centre), so after STALL_ACCEPT_TICKS in one state a goal
        within LOOSE_TOL counts as reached. A cube released 8 cm off target
        still satisfies every downstream tolerance."""
        e = self.arm.error()
        if e is None:
            return False
        if e < C.REACH_TOL:
            return True
        return self._timer > C.STALL_ACCEPT_TICKS and e < C.LOOSE_TOL

    # states ------------------------------------------------------------
    def _to_pick(self):
        ox, oy, _ = self.obj_xy()
        if not self._need(zone_of(ox, oy)):
            return
        self.arm.set_goal(ox, oy, self._hover_z())
        if self._arrived():
            self.arm.clear_goal()
            self.state, self._timer = "DESCEND", 0

    def _descend(self):
        ox, oy, oz = self.obj_xy()
        self.arm.set_goal(ox, oy, oz + C.HANG)
        if self._arrived():
            self.arm.clear_goal()
            self.state, self._timer = "ATTACH", 0

    def _attach(self):
        if self.arm.attach(self.task.obj):
            self.state, self._timer = "LIFT", 0
        else:
            self.abort()                   # e.g. object displaced mid-descend

    def _lift(self):
        x, y, _ = self.obj_xy()
        self.arm.set_goal(x, y, self._hover_z())
        if self._arrived():
            self.arm.clear_goal()
            pick_zone = zone_of(x, y)
            dest_zone = zone_of(*self.target)
            if pick_zone != dest_zone:
                self.locks.release(pick_zone, self.arm.name)
            # else KEEP the lock: when pick and destination share a zone,
            # releasing here opened a one-tick window another arm sniped
            # (ledger evidence: franka_n released ne at tick 199, ur_e
            # took it at 200, and the now-lockless franka_n loitered
            # INSIDE ne holding its object until the two collided at
            # 0.143 m). Never release a zone the next target still needs.
            self.state, self._timer = "TO_PLACE", 0

    def _to_place(self):
        tx, ty = self.target
        if not self._need(zone_of(tx, ty)):
            return
        self.arm.set_goal(tx, ty, self._hover_z())
        if self._arrived():
            self.arm.clear_goal()
            self.state, self._timer = "LOWER", 0

    def _hover_z(self):
        """Per-arm-type hover/transit height. A Franka hovering at the UR
        height over a far point runs out of arm (measured at the centre
        pad); URs keep the original value, so cube behaviour is
        unchanged for them."""
        return C.ARM_TYPES[C.ARMS[self.arm.name]["type"]]["hover_z"]

    def _rest_z(self):
        """The carried object's true resting ROOT height on the table,
        from OBJECT_SPECS (measured for YCB objects; the default equals
        the cube's half-height, so cube behaviour is unchanged)."""
        spec = C.OBJECT_SPECS.get(self.task.obj, C.OBJECT_SPECS["_default"])
        return C.TABLE_H + spec.get("rest_z",
                                    C.OBJECT_SPAWN_Z - C.TABLE_H)

    def _approach_clearance(self, px, py):
        """Release height above the object's rest height.

        A flat constant is wrong near tall objects: the wrist descends to
        about 0.18 m above the table while a standing pitcher is 0.242 m,
        so the hardware sits BELOW the rim of anything tall nearby. This
        returns the larger of the constant and (tallest neighbour within
        reach of the wrist + margin), so the wrist always passes above
        what is already in the basket.
        """
        gh = C.WRIST_HALF_SPAN + C.OBJECT_SPECS.get(
            self.task.obj if self.task else "", C.OBJECT_SPECS["_default"]
        ).get("footprint_m", C.OBJECT_SIZE) / 2
        tallest = 0.0
        names = ({t.obj for t in self.coord.pool} if self.coord is not None
                 else set())
        for name in names:
            if name == (self.task.obj if self.task else None):
                continue
            try:
                p = self.scene[name].data.root_pos_w[0]
            except KeyError:
                continue
            if math.hypot(float(p[0]) - px, float(p[1]) - py) < gh:
                spec = C.OBJECT_SPECS.get(name, C.OBJECT_SPECS["_default"])
                # height MUST be published by the registry; a silent default
                # once treated a 0.24 m pitcher as 0.05 m and the wrist came
                # down below its rim.
                tallest = max(tallest, spec.get("height", C.OBJECT_SIZE))
        # Work in TABLE-RELATIVE metres throughout. _rest_z() returns a WORLD
        # z (table height + rest offset), and subtracting it here once made
        # `need` hugely negative, silently disabling this whole guard while
        # the harness still reported a pass.
        rest_above_table = self._rest_z() - C.TABLE_H
        # The goal is EE z = rest_z + HANG + clearance, so the carried
        # object's underside sits `clearance` above its own rest height,
        # i.e. (rest_above_table + clearance) above the table. To pass over
        # a neighbour of height h we need that to exceed h + margin.
        need = tallest + C.WRIST_MARGIN - rest_above_table
        return max(C.PLACE_CLEARANCE, need)

    def _tallest_near(self, x, y, radius):
        """Tallest object (registry height) within radius of (x, y)."""
        tallest = 0.0
        names = ({t.obj for t in self.coord.pool} if self.coord is not None
                 else set())
        for name in names:
            if name == (self.task.obj if self.task else None):
                continue
            try:
                p = self.scene[name].data.root_pos_w[0]
            except KeyError:
                continue
            if math.hypot(float(p[0]) - x, float(p[1]) - y) < radius:
                spec = C.OBJECT_SPECS.get(name, C.OBJECT_SPECS["_default"])
                tallest = max(tallest, spec.get("height", C.OBJECT_SIZE))
        return tallest

    def _place_spot(self, tx, ty):
        """Footprint-aware set-down point near (tx, ty): first spot where
        this object's footprint clears every object already present, inside
        the basket walls. Falls back to the least-crowded candidate (with a
        warning) if the basket is genuinely full, which the startup
        capacity check should have prevented."""
        for pad in C.EXCHANGE_PADS.values():
            if math.hypot(tx - pad["pos"][0], ty - pad["pos"][1]) < 0.02:
                # PADS ARE EXACT. Corner-first placement at a pad set the
                # object up to 15 cm off-centre, which defeated the
                # PAD_SKIP occupancy test and the rule shuttled the
                # mustard to the same pad SEVEN times (4000 ticks). A pad
                # is a waypoint: exclusivity guarantees it is empty, and
                # the next leg picks up from its centre.
                return tx, ty
        spec = C.OBJECT_SPECS.get(self.task.obj if self.task else "",
                                  C.OBJECT_SPECS["_default"])
        halfw = spec.get("footprint_m", C.OBJECT_SIZE) / 2
        occupied = []
        names = ({t.obj for t in self.coord.pool} if self.coord is not None
                 else set())
        for name in names:
            if name == (self.task.obj if self.task else None):
                continue
            try:
                p = self.scene[name].data.root_pos_w[0]
            except KeyError:
                continue
            px, py = float(p[0]), float(p[1])
            if math.hypot(px - tx, py - ty) < 0.35:
                ospec = C.OBJECT_SPECS.get(name, C.OBJECT_SPECS["_default"])
                occupied.append((px - tx, py - ty,
                                 ospec.get("footprint_m", C.OBJECT_SIZE) / 2))
        dx, dy, ok = find_place_spot(halfw, occupied)
        if not ok:
            line = (f"[place] WARNING: no clear spot for "
                    f"{self.task.obj if self.task else '?'} near "
                    f"({tx:.2f},{ty:.2f}); using least-crowded fallback")
            if self.coord is not None:
                self.coord.event("place_fallback", text=line,
                                 object=self.task.obj if self.task else None,
                                 near=[round(tx, 2), round(ty, 2)])
            else:
                print(line, flush=True)
        return tx + dx, ty + dy

    def _lower(self):
        if self._place_at is None:         # decide ONCE per placement, then
            self._place_at = self._place_spot(*self.target)   # hold it: the
        px, py = self._place_at            # search reads live positions and
                                           # must not drift mid-descent
        rz = self._rest_z()
        self.arm.set_goal(px, py, rz + C.HANG + self._approach_clearance(px, py))
        if self._arrived():
            self.arm.clear_goal()
            self.arm.detach(place_xy=(px, py),        # kinematic set-down
                            place_z=rz + 0.003)       # at the TRUE height
            self.state, self._timer = "RELEASE", 0

    def _release(self):
        if self._timer >= C.DWELL_TICKS:   # let the object settle
            self.state, self._timer = "RETREAT", 0
            # Retreat VERTICALLY from where the object was actually placed.
            # Retreating to self.target (the basket CENTRE) dragged the wrist
            # diagonally across the basket interior at ~0.18 m, below the top
            # of a standing pitcher (0.242 m), which knocked objects over.
            px, py = self._place_at if self._place_at else self.target
            self.arm.set_goal(px, py, self._hover_z())
            self._place_at = None

    def _retreat(self):
        if self._arrived():
            self.arm.clear_goal()
            hx, hy = C.HOME_XY[self.arm.name]
            self.arm.set_goal(hx, hy, self._hover_z())
            self.state, self._timer = "GO_HOME", 0

    def _go_home(self):
        """Locks are held until the body is physically clear of the shared
        space; releasing on task completion caused arms parked over the
        centre to be hit by the next lock holder."""
        if self._arrived():
            self.arm.clear_goal()
            self.locks.release_all(self.arm.name)
            if self.task is not None:
                self.task.done = True
                self.task.done_tick = self.m.makespan_ticks
                # Close the execution window. done_tick is stamped HERE, on
                # arrival home, not at placement, so this distance spans
                # approach + carry + retreat + the trip home: exactly the
                # span the cost model must learn to price. The fold
                # (PRE_TUCK + SETTLING) happens after this and is derivable
                # offline from the next arm_idle event.
                now = getattr(self.arm, "travel_m", None)
                if now is not None and self.task._travel_at_claim is not None:
                    self.task.travel_leg_m = round(
                        now - self.task._travel_at_claim, 4)
                self.m.completed[self.arm.name] += 1
                self.task = None
            # Do NOT fold yet. tuck() is a joint-space command whose
            # transit arc is uncontrolled and dips low; folding at hover
            # height swept the wood block out of ur_w's reach (observed
            # on video, 2026-07-19: the wood ended 76 cm from its basket
            # in a spot no arm could serve). Rise first, fold up there.
            hx, hy = C.HOME_XY[self.arm.name]
            self.arm.set_goal(hx, hy, self._hover_z() + C.TUCK_RAISE)
            self.state, self._timer = "PRE_TUCK", 0

    def _recover(self):
        """In-place verified reset after repeated home failures: hold the
        tuck targets until the joints verifiably arrive (or the budget
        runs out), then attempt home once more. If home fails repeatedly
        AGAIN, the give-up branch fires for real (recover is once per
        life; _recover_used gates it)."""
        settled = getattr(self.arm, "tuck_settled", lambda: True)()
        if settled or self._timer >= C.RECOVER_MAX_TICKS:
            hx, hy = C.HOME_XY[self.arm.name]
            self.arm.set_goal(hx, hy, self._hover_z())
            self.state, self._timer = "GO_HOME", 0

    def _pre_tuck(self):
        """Fold-high: the arm is at home, off the books (task complete,
        locks released), and rises before folding so the fold's low arc
        happens far above every object. If the raise ever stalls, abort
        returns it to GO_HOME and the give-up guard bounds the loop."""
        if self._arrived():
            self.arm.clear_goal()
            self.arm.tuck()
            self.state, self._timer = "SETTLING", 0

    def _settling(self):
        """The arm is NOT offered new work until its fold has verifiably
        finished. Three episodes were lost to the same failure: a task
        claimed 50-60 ticks into the fold launched the carry from a
        half-reset posture and stalled at err ~0.79 (the bowl, twice
        under VLM and once under opt). Gate IDLE on tuck_settled(); the
        cost is a fraction of a second per task, uniformly for every
        allocator column."""
        settled = getattr(self.arm, "tuck_settled", lambda: True)()
        if settled or self._timer >= C.RECOVER_MAX_TICKS:
            self.state = "IDLE"

    # ------------------------------------------------------------- aborts --
    def abort(self):
        """Return the task to the pool (clear its claimed flag) and retreat
        home. Held locks travel home with the arm and are released there, so
        an aborting arm never becomes a surprise obstacle inside a zone it
        nominally freed. A disabled arm cannot move, so it releases
        immediately; being an obstacle is exactly what D3 is meant to test."""
        err = self.arm.error()
        line = (f"[coord] abort: arm={self.arm.name} "
                f"task={self.task.id if self.task else None} "
                f"obj={self.task.obj if self.task else None} "
                f"state={self.state} timer={self._timer} "
                f"err={f'{err:.3f}' if err is not None else 'n/a'}")
        if self.coord is not None:
            self.coord.event("abort", text=line, arm=self.arm.name,
                             task=self.task.id if self.task else None,
                             object=self.task.obj if self.task else None,
                             state=self.state, timer=self._timer,
                             err=round(err, 3) if err is not None else None)
        else:
            print(line, flush=True)
        self.arm.detach()
        self.arm.clear_goal()
        self._blocked = 0              # see claim(): never carry wait-debt
                                       # from one attempt into the next
        if self.task is not None:
            # The task's intent dies with the abort: drop its inbound
            # reservations now. Physical HOLDS still travel home with the
            # arm (the rule above); only the advisory layer clears here.
            for z in self.task.required_zones:
                self.locks.unreserve(z, self.arm.name)
            self.task.claimed = False
            self.task.attempts += 1
            if self.task.attempts >= C.MAX_TASK_ATTEMPTS:
                self.task.failed = True
                line = (f"[coord] task {self.task.id} FAILED after "
                        f"{self.task.attempts} attempts")
                if self.coord is not None:
                    self.coord.event("task_failed", text=line,
                                     task=self.task.id, object=self.task.obj,
                                     attempts=self.task.attempts,
                                     cause="attempts_exhausted")
                else:
                    print(line, flush=True)
            self.m.requeued += 1
            self.task = None
        if self.state in ("GO_HOME", "PRE_TUCK") and self.task is None:
            self._home_fails += 1
            if (self._home_fails >= C.MAX_HOME_FAILS
                    and not self._recover_used):
                # Before declaring the arm dead, try the PROVEN cure once:
                # a verified joint-space reset IN PLACE (no travel needed).
                # Diagnostic T3 (out/probe_diag.json): a Franka stalled at
                # err 0.39 toward this very target arrives in 103 ticks
                # after such a reset. Zones stay held: the body is still
                # physically there, and the attempt is bounded.
                self._recover_used = True
                line = (f"[coord] {self.arm.name} cannot reach home after "
                        f"{self._home_fails} attempts: trying an in-place "
                        f"recovery tuck before giving up")
                if self.coord is not None:
                    self.coord.event("recover_tuck", text=line,
                                     arm=self.arm.name,
                                     home_fails=self._home_fails)
                else:
                    print(line, flush=True)
                self._home_fails = 0
                self.arm.clear_goal()
                self.arm.tuck()
                self.state, self._timer = "RECOVER", 0
                return
            if self._home_fails >= C.MAX_HOME_FAILS:
                # The arm cannot physically return home (bad IK posture,
                # wedged against geometry). Retrying forever while HOLDING
                # its zones starved the whole cell once: franka_n looped
                # GO_HOME aborts at err 0.432 for 7000+ ticks, its zone
                # never freed, the pitcher timed out to FAILURE and the
                # episode never terminated. Give up: free every zone and
                # park disabled where it stands. The cell degrades to
                # three arms instead of zero.
                line = (f"[coord] {self.arm.name} cannot reach home after "
                        f"{self._home_fails} attempts: releasing zones and "
                        f"parking DISABLED in place")
                if self.coord is not None:
                    self.coord.event("give_up", text=line,
                                     arm=self.arm.name,
                                     home_fails=self._home_fails)
                else:
                    print(line, flush=True)
                self.arm.disabled = True
        else:
            self._home_fails = 0
        if self.arm.disabled:
            self.locks.release_all(self.arm.name)
            self.state = "IDLE"
        else:
            hx, hy = C.HOME_XY[self.arm.name]
            self.arm.set_goal(hx, hy, self._hover_z())
            self.state, self._timer = "GO_HOME", 0


# ---------------------------------------------------------------------------
# Coordinator.
# ---------------------------------------------------------------------------

@dataclass
class Metrics:
    blocked: dict = field(default_factory=dict)     # arm -> blocked ticks
    completed: dict = field(default_factory=dict)   # arm -> legs completed
    requeued: int = 0
    makespan_ticks: int = 0
    contended_claims: int = 0   # claims whose required zones were held or
                                # reserved by another arm at claim time;
                                # measured, never vetoed (guard principle)
    pad_wait: dict = field(default_factory=dict)
                                # M9: pad name -> ticks a handover leg was
                                # held back because that pad was occupied
                                # or reserved. _assign() runs every tick,
                                # so one increment per blocked assignment
                                # attempt IS one tick of waiting. The
                                # handover_wait EVENT marks the onset once
                                # per task; this counter measures duration.


# ---------------------------------------------------------------------------
# Settle-wait: hold an allocation round briefly when an arm is finishing.
# ---------------------------------------------------------------------------
# Why. Measured over two episodes, 18 of 21 accepted decisions were taken
# with exactly ONE arm idle, so "which arm" had one answer and there was
# nothing to judge. That is a scheduling artefact: every task is submitted
# at the start, the round assigns one task and re-consults with one fewer
# arm free, draining to a single candidate. Meanwhile every idle-arm subset
# of size two or more on decision_rich already offers a scarcity trap, so
# the cell's decision content is there and the rounds simply do not visit
# it.
#
# Holding the round for a bounded number of ticks when an arm is finishing
# raises the share of decisions taken with a real choice. Measured
# counterfactually (analysis/episode/episode_buffer_density.py): tasks with a choice roughly
# double at a 200-tick window on both episodes.
#
# What this deliberately does NOT do: it gives the allocator no information.
# Only genuinely IDLE arms are ever offered. Nothing about remaining time
# enters the state or the prompt, so the methods stay ND [ST-SR-IA] under
# Gerkey and Mataric and the scope's taxonomy claim is unaffected. It also
# lives in the Coordinator, so every allocator column gets the identical
# substrate and differences between them remain attributable.
#
# Expect it to COST makespan. episode_buffer_value.py measured the value of waiting
# for a better arm at 2 opportunities across 148 tasks, so the honest
# expectation is a small loss, uniform across columns, to be reported.
#
# TIGHT is the final wind-down: no travel, the arm is genuinely seconds from
# IDLE. BROAD adds the return legs, which are real travel, so a wait on
# BROAD is a short bounded delay rather than a wait for imminent
# availability. They are separate presets because they need different
# sentences in the write-up, not just different numbers.
SETTLE_PHASES = {
    "tight": ("SETTLING", "PRE_TUCK"),
    "broad": ("SETTLING", "PRE_TUCK", "GO_HOME", "RETREAT"),
}


class Coordinator:
    """Owns the pool, allocator, locks, and metrics. Call tick() every
    cell.tick(); pending() tells you when everything is done."""

    def __init__(self, cell, zonemap, allocate=rule_based_allocate, engine=None,
                 settle_wait=0, settle_phases="tight", serialised=False):
        self.cell = cell
        self.zonemap = zonemap
        self.allocate = allocate
        # SERIALISED CELL (EX1 v2, 2026-09-02). False reproduces every
        # episode recorded before this date tick for tick, so nothing
        # already on disk moves; the harness pins that.
        #
        # True makes the cell run ONE task at a time: a round is offered
        # only when every non-disabled arm is idle, and only the first
        # assignable task in pool order is offered. Two properties follow,
        # and EX1 v2 exists for both.
        #
        # EVERY ARM IS IDLE AT EVERY DECISION. Under the contended cell an
        # arm busy on another task is simply unavailable, so a state can
        # only discriminate on the arms that happen to be free. On the
        # frozen v1 set that left grasp binding a pair on 96 of 162
        # states. With all four arms offered at every decision, both arm
        # types are available almost everywhere and the gripper opening
        # can bind far more often.
        #
        # THE ALLOCATOR NO LONGER CHOOSES WHICH TASK. Pool order fixes
        # that, so the decision is one arm for one named task. Task
        # selection stops being a source of variance and of error, and a
        # rejection can only be about the arm.
        #
        # WHAT IT COSTS. Makespan, and every contention measure: zone
        # queueing, scarce-arm protection and relay avoidance all become
        # vacuous, because no second arm is ever working. That is why this
        # is an EX1 switch and not a new default. EX3 is the experiment
        # about contention and must never run serialised.
        self.serialised = bool(serialised)
        # settle_wait 0 is OFF and reproduces every episode recorded before
        # 2026-08-02 tick for tick. The harness pins that.
        self.settle_wait = int(settle_wait or 0)
        if settle_phases not in SETTLE_PHASES:
            raise ValueError(
                f"unknown settle_phases {settle_phases!r}; expected one of "
                f"{sorted(SETTLE_PHASES)}. Never defaulted: a run labelled "
                f"tight that actually waited on broad would be invisible in "
                f"the output.")
        self.settle_phases = settle_phases
        self._settle_set = frozenset(SETTLE_PHASES[settle_phases])
        self._settle_waited = 0       # ticks held in the CURRENT wait
        # The finishing-arm set a wait already expired on. Without this the
        # policy re-arms the tick after every expiry, so an arm sitting in a
        # settle phase would throttle allocation to once every cap+1 ticks
        # instead of holding once and moving on.
        self._settle_spent = frozenset()
        self.m_settle = {"waits": 0, "ticks_held": 0, "expired": 0,
                         "paid_off": 0}
        self.engine = engine        # optional: retire completed objects
        self.locks = ZoneLocks()
        self.m = Metrics(blocked={n: 0 for n in cell.arms},
                         completed={n: 0 for n in cell.arms})
        self.agents = {n: ArmAgent(a, cell.scene, self.locks, self.m, coord=self)
                       for n, a in cell.arms.items()}
        self.pool: list[Task] = []
        self._assign_round = 0        # bumped each tick; VLM allocator keys on it
        self._warned: set[int] = set()
        # Arm AVAILABILITY ledger (schema v3, 2026-07-26). A task being
        # done is NOT the same as its arm being assignable: after the
        # done stamp the arm still rises (PRE_TUCK) and folds (SETTLING),
        # and only then becomes IDLE. Offline readers cannot infer that
        # window from task records, so every transition INTO IDLE is
        # emitted as an "arm_idle" event. One event per completion or
        # abort, so the timeline stays small.
        self._last_state = {n: "IDLE" for n in cell.arms}
        # Tick at which each arm ENTERED each phase since it was last idle,
        # emptied on arrival. Feeds phase_dwell, which answers "how long
        # after entering GO_HOME does an arm actually become assignable" on
        # evidence instead of by assumption.
        self._phase_entered = {n: {} for n in cell.arms}
        self.phase_dwell = []
        # Arm-arm proximity watch: locks serialise DESTINATIONS, not swept
        # transit volumes, so arms can legally pass close to (or touch)
        # each other in flight. Every near miss is recorded with full
        # context (states, held locks) so collisions can be diagnosed from
        # the episode JSON instead of by squinting at video.
        self.prox_events = []
        # Typed simulation-event timeline (schema v2): every noteworthy
        # runtime occurrence is emitted ONCE through event(), which both
        # prints the human line and appends the machine record. Closed
        # vocabulary: abort, task_failed, give_up, near_miss,
        # place_fallback, handover_wait, disruption, tick_limit.
        self.sim_events = []
        self._prox_below: set = set()          # pairs currently under threshold
        self.min_pair_dist = {}                # pair -> closest ever (m)

    def submit(self, obj, dest):
        t = Task(obj=obj, dest=dest)
        t.submit_tick = self.m.makespan_ticks
        if dest is not None:
            t.dest_by = "given"
        # SERIALISED: every task but the first arrives HELD, and _release
        # lets the next one through when the live one finishes. Submission
        # order is pool order, which is what makes "handled in pool order"
        # a property of the cell rather than of the allocator.
        if self.serialised and any(not x.done and not x.failed and not x.held
                                   for x in self.pool):
            t.held = True
        self.pool.append(t)
        return t

    def _release(self):
        """Let the next held task through when nothing live is outstanding.

        Outstanding means any unheld task that is neither done nor failed,
        which includes a parent parked behind its own handover leg. Parent
        and leg are one unit of work and are released together, so a relay
        is never split across two decisions that see different pools.
        """
        if not self.serialised:
            return
        if any(not t.done and not t.failed and not t.held for t in self.pool):
            return
        for t in self.pool:
            if t.held:
                t.held = False
                t.submit_tick = self.m.makespan_ticks
                return

    def event(self, etype, text=None, **fields):
        """Emit once: append the typed record and (optionally) print the
        human-readable line, so prints are a view of the log, never a
        second source of truth."""
        self.sim_events.append({"tick": self.m.makespan_ticks,
                                "type": etype, **fields})
        if text:
            print(text, flush=True)

    def _permanently_unallocatable(self, task):
        """True only if NO non-disabled arm could serve the task's object
        from its CURRENT position by any route: no direct-capable arm and
        no progressing pad relay with a capable first and second arm.
        Deliberately conservative: busy arms count as available (they
        will free up), so temporary blockage never triggers this; only
        geometry does (e.g. an object dropped inside the dead ring)."""
        if task.dest is None or task.waiting_on is not None:
            return False
        p = self.cell.scene[task.obj].data.root_pos_w[0]
        ox, oy = float(p[0]), float(p[1])
        arms = [a for a in C.ARMS
                if not (a in self.agents and self.agents[a].arm.disabled)]
        capable = [a for a in arms if C.can_grasp(a, task.obj)]
        if any(self.zonemap.reachable(a, ox, oy)
               and self.zonemap.reachable(a, *task.dest) for a in capable):
            return False
        d_dest = math.hypot(ox - task.dest[0], oy - task.dest[1])
        for pad, spec in C.EXCHANGE_PADS.items():
            px, py = spec["pos"]
            if math.hypot(ox - px, oy - py) < C.PAD_SKIP_RADIUS:
                continue
            if math.hypot(px - task.dest[0], py - task.dest[1]) >= d_dest - 0.05:
                continue
            first = any(self.zonemap.reachable(a, ox, oy)
                        and self.zonemap.reachable(a, px, py)
                        for a in capable)
            second = any(self.zonemap.reachable(a, px, py)
                         and self.zonemap.reachable(a, *task.dest)
                         for a in capable)
            if first and second:
                return False
        return True

    def _drain_disabled(self):
        for name, agent in self.agents.items():
            if agent.arm.disabled and agent.task is not None:
                agent.abort()              # unclaims; the pool still has it

    def _assign(self):
        idle = [n for n, ag in self.agents.items()
                if ag.state == "IDLE" and not ag.arm.disabled]
        # A disabled arm is permanent. Counting it as a possible handover
        # FINISHER approves legs whose second arm will never arrive, and
        # counting it as a possible DIRECT deliverer suppresses handovers
        # that are genuinely needed. Both were live before this set existed.
        dead = frozenset(n for n, ag in self.agents.items()
                         if ag.arm.disabled)
        if not idle:
            return
        # THE SERIALISED GATE. Two halves, and they are not the same check.
        #
        # The first holds the round until every non-disabled arm is idle,
        # which is what makes "every arm is available at every decision"
        # true rather than merely usual. Without it a round could fire
        # while one arm was still folding, and the state harvested from
        # that round would carry a busy arm under a serialised label.
        #
        # The second is in the loop below: only the first assignable task
        # in pool order is offered, and the round ends whether or not it
        # was taken. Offering the rest would hand task selection back to
        # the allocator, which is the other half of what serialising buys.
        if self.serialised and len(idle) < len(
                [n for n, ag in self.agents.items() if not ag.arm.disabled]):
            return
        done_ids = {t.id for t in self.pool if t.done}
        failed_ids = {t.id for t in self.pool if t.failed}
        for task in list(self.pool):
            if task.done or task.claimed or task.failed or task.held:
                continue
            if task.waiting_on is not None:
                if task.waiting_on in failed_ids:
                    # The handover leg this task was waiting for has FAILED.
                    # Without this, the parent waits forever on a task that
                    # can never complete and the episode never terminates
                    # (observed: clamp parent hung 20000+ ticks after its
                    # pad leg failed). Propagate the failure loudly.
                    task.failed = True
                    task.waiting_on = None
                    self.event("task_failed", task=task.id,
                               object=task.obj, cause="leg_failed")
                    print(f"[coord] task {task.id} FAILED: its handover leg "
                          f"failed", flush=True)
                    continue
                if task.waiting_on not in done_ids:
                    continue
                # Predecessor finished: clear the dependency so this is an
                # ordinary queued task again. Leaving it set made the state
                # builder label it 'waiting' (so the model correctly refused
                # to assign it) and made the Layer 4 validator reject it as
                # 'already being handled', so a post-handover parent could
                # never be assigned in vlm mode and the run stalled forever.
                task.waiting_on = None
            ox, oy, _ = (lambda p: (float(p[0]), float(p[1]), float(p[2])))(
                self.cell.scene[task.obj].data.root_pos_w[0])
            try:
                arm, target, sub = self.allocate(task, (ox, oy), idle,
                                                 self.zonemap, disabled=dead)
            except TypeError:            # allocator predates the argument
                arm, target, sub = self.allocate(task, (ox, oy), idle,
                                                 self.zonemap)
            if arm is None:
                # The permanence test used to sit INSIDE the once-only
                # warning guard, so a task that was merely blocked the
                # first time was never re-examined. A displacement that
                # later strands an object out of reach then never failed
                # the task, and the episode ran to the tick limit.
                if (self._permanently_unallocatable(task)
                        and self.m.makespan_ticks % C.PERMANENCE_RECHECK == 0):
                    task.failed = True
                    self.event("task_failed", task=task.id, object=task.obj,
                               cause="unreachable",
                               text=(f"[coord] task {task.id} ({task.obj}) "
                                     f"FAILED: no arm can reach it by any "
                                     f"route from its current position"))
                    continue
                if task.id not in self._warned:
                    self._warned.add(task.id)
                    can_obj = [a for a in C.ARMS
                               if self.zonemap.reachable(a, ox, oy)]
                    can_dst = ([a for a in C.ARMS
                                if self.zonemap.reachable(a, *task.dest)]
                               if task.dest is not None else "unassigned")
                    if self._permanently_unallocatable(task):
                        task.failed = True
                        self.event("task_failed", task=task.id,
                                   object=task.obj, cause="unreachable",
                                   text=(f"[coord] task {task.id} "
                                         f"({task.obj}) FAILED: no arm can "
                                         f"reach it by any route from its "
                                         f"current position"))
                        continue
                    print(f"[coord] task {task.id} not allocatable now: "
                          f"obj({ox:.2f},{oy:.2f}) reachable by {can_obj}, "
                          f"dest{task.dest} reachable by {can_dst}, "
                          f"idle={idle}", flush=True)
                if self.serialised:
                    # The task was OFFERED and refused. Moving on to the
                    # next one would offer a choice of tasks, which is the
                    # thing serialising removes; the round simply ends and
                    # the same task is offered again next tick.
                    return
                continue
            if sub is not None:            # handover: run the pad leg first
                if not self._pad_available(sub.dest, task.obj):
                    pad_name = next(
                        (p for p, s in C.EXCHANGE_PADS.items()
                         if math.isclose(s["pos"][0], sub.dest[0], abs_tol=1e-6)
                         and math.isclose(s["pos"][1], sub.dest[1],
                                          abs_tol=1e-6)),
                        f"({sub.dest[0]:.2f},{sub.dest[1]:.2f})")
                    self.m.pad_wait[pad_name] = \
                        self.m.pad_wait.get(pad_name, 0) + 1
                    # PAD EXCLUSIVITY (validator-level MUST): setting a
                    # second object down on an occupied pad interpenetrates
                    # the first and PhysX scatters both (observed: mustard
                    # placed onto the centre pad at tick 682 while the
                    # gelatin sat there). The leg simply waits, exactly
                    # like a zone denial; the pad frees, the task retries.
                    # The allocator has already CONSUMED its cached
                    # decision for this round. Declining here without
                    # telling it leaves that decision spent and the
                    # re-consult signature unchanged, so the leg is not
                    # re-offered even after the pad clears.
                    inv = getattr(self.allocate, "invalidate", None)
                    if callable(inv):
                        inv()
                    if (task.id, "pad") not in self._warned:
                        self._warned.add((task.id, "pad"))
                        self.event("handover_wait",
                               text=(f"[coord] task {task.id}: pad "
                                     f"{sub.dest} occupied/reserved, "
                                     f"handover waits"),
                               task=task.id, pad=list(sub.dest))
                    if self.serialised:
                        return          # offered and held; see the gate above
                    continue
                task.waiting_on = sub.id
                sub.submit_tick = self.m.makespan_ticks
                if sub.dest_by is None:
                    sub.dest_by = "rule"   # pad picked by the rule's search
                sub.kind = "handover_leg"
                self.pool.append(sub)
                self.agents[arm].claim(sub, sub.dest)
            else:
                self.agents[arm].claim(task, target)   # stays in pool, claimed
            idle.remove(arm)
            if self.serialised or not idle:
                return

    def _pad_available(self, pad_xy, for_obj):
        """A pad is free when no OTHER object sits on it and no active task
        is already heading there. Both halves matter: occupancy covers the
        parked object, reservation covers one that is inbound but not yet
        set down."""
        px, py = pad_xy
        for t in self.pool:                          # reservation
            if (t.dest == tuple(pad_xy) and t.claimed and not t.done
                    and not t.failed and t.obj != for_obj):
                return False
        for name in {t.obj for t in self.pool}:      # occupancy
            if name == for_obj:
                continue
            try:
                p = self.cell.scene[name].data.root_pos_w[0]
            except KeyError:
                continue
            if math.hypot(float(p[0]) - px, float(p[1]) - py) < C.PAD_SKIP_RADIUS:
                return False
        return True

    def _hold_round(self):
        """True when this tick's allocation round should be skipped.

        Three conditions, in order, and every one of them matters:

        - Two or more arms already idle: never hold. A round that already
          offers a choice has nothing to gain and waiting would only cost
          makespan.
        - Some arm in a settle phase AND the current wait is under the cap:
          hold. A DISABLED arm never counts, because it will never reach
          IDLE and waiting on it would hold the round until the cap every
          single tick.
        - Otherwise: assign now.

        The cap makes deadlock structurally impossible: at worst the round
        is delayed settle_wait ticks and then proceeds exactly as it would
        have.
        """
        if self.settle_wait <= 0:
            return False
        idle = sum(1 for ag in self.agents.values()
                   if ag.state == "IDLE" and not ag.arm.disabled)
        if idle >= 2:
            if self._settle_waited:
                # A wait that ended because a second arm actually became
                # idle: the outcome the policy exists to produce. Counted
                # here because every exit path below clears the counter, so
                # the caller could never see it. It read 0 in every run
                # until 2026-08-02 and was dead code.
                self.m_settle["paid_off"] += 1
            self._settle_waited = 0
            self._settle_spent = frozenset()
            return False
        finishing = frozenset(
            n for n, ag in self.agents.items()
            if ag.state in self._settle_set and not ag.arm.disabled)
        if not finishing:
            self._settle_waited = 0
            self._settle_spent = frozenset()
            return False
        if finishing == self._settle_spent:
            return False          # already waited out this configuration
        if self._settle_waited >= self.settle_wait:
            self.m_settle["expired"] += 1
            self._settle_waited = 0
            self._settle_spent = finishing
            return False
        if self._settle_waited == 0:
            self.m_settle["waits"] += 1
        self._settle_waited += 1
        self.m_settle["ticks_held"] += 1
        return True

    def tick(self):
        self._assign_round += 1
        self.locks.tick = self.m.makespan_ticks
        self._drain_disabled()
        # Before the round, not inside _assign: a held round still has to
        # release, or a cell whose live task finished during a settle wait
        # would sit with nothing visible until the wait expired.
        self._release()
        held = self._hold_round()
        if held:
            # A held tick does EVERYTHING a normal tick does except assign.
            # The first version returned early, before the clock advanced,
            # so makespan was under-counted by exactly ticks_held: a run
            # with settle_wait=200 reported 1626 ticks against a true 3158,
            # and every tick-denominated metric, phase dwell included, was
            # wrong in the same direction. Time passes whether or not an
            # allocation happens.
            for agent in self.agents.values():
                agent.tick()
            self._record_transitions()
            if self.m.makespan_ticks % C.PROX_CHECK_EVERY == 0:
                self._watch_proximity()
            self.m.makespan_ticks += 1
            return
        self._assign()
        for agent in self.agents.values():
            agent.tick()
        self._record_transitions()
        if self.m.makespan_ticks % C.PROX_CHECK_EVERY == 0:
            self._watch_proximity()
        self.m.makespan_ticks += 1

    def _record_transitions(self):
        """Availability ledger, plus per-phase dwell times.

        Extracted from tick() 2026-08-02 so a held round records the same
        transitions an assigned one does: the arms still move while the
        round is held, and losing their transitions would corrupt the
        ledger exactly on the ticks the settle policy is active.

        The dwell record is new. Nothing measured how long an arm actually
        spends between entering a phase and reaching IDLE, so the choice of
        which phases count as "finishing" was a judgement call. One episode
        with this in place turns it into a distribution.
        """
        for name, ag in self.agents.items():
            if ag.state == self._last_state.get(name):
                continue
            # abort() parks a disabled arm in IDLE, so without this guard
            # the ledger claimed a frozen arm had just become available,
            # and then never fired if it truly did.
            if ag.state == "IDLE" and not ag.arm.disabled:
                self.event("arm_idle", arm=name)      # assignable from here
                start = self._phase_entered.get(name)
                if start is not None:
                    for phase, t0 in start.items():
                        self.phase_dwell.append(
                            {"arm": name, "type": C.ARMS[name]["type"],
                             "phase": phase,
                             "ticks_to_idle": self.m.makespan_ticks - t0})
                self._phase_entered[name] = {}
            else:
                self._phase_entered.setdefault(name, {}).setdefault(
                    ag.state, self.m.makespan_ticks)
            self._last_state[name] = ag.state

    def _watch_proximity(self):
        """Pairwise end-effector distances. One event per threshold
        crossing (with hysteresis, so a lingering close pass is one event,
        not hundreds), carrying each arm's state and held locks at that
        moment: enough to tell 'transit paths crossed' from 'lock released
        while the arm was still inside the zone'."""
        arms = [(n, a) for n, a in self.cell.arms.items() if not a.disabled]
        pos = {}
        for n, a in arms:
            p = a.ee_pos_w()[0]
            pos[n] = (float(p[0]), float(p[1]), float(p[2]))
        for i in range(len(arms)):
            for j in range(i + 1, len(arms)):
                a, b = arms[i][0], arms[j][0]
                pa, pb = pos[a], pos[b]
                d = math.sqrt((pa[0]-pb[0])**2 + (pa[1]-pb[1])**2
                              + (pa[2]-pb[2])**2)
                pair = f"{a}|{b}"
                if d < self.min_pair_dist.get(pair, 99.0):
                    self.min_pair_dist[pair] = round(d, 3)
                if d < C.PROX_NEAR_MISS_M and pair not in self._prox_below:
                    self._prox_below.add(pair)
                    self.prox_events.append({
                        "tick": self.m.makespan_ticks, "type": "near_miss",
                        "arms": [a, b], "ee_dist_m": round(d, 3),
                        "ee_pos": {a: [round(v, 2) for v in pa],
                                   b: [round(v, 2) for v in pb]},
                        "states": {a: self.agents[a].state,
                                   b: self.agents[b].state},
                        "locks": {a: self.locks.held_by(a),
                                  b: self.locks.held_by(b)},
                    })
                    print(f"[prox] tick {self.m.makespan_ticks}: {a} and "
                          f"{b} within {d:.2f} m "
                          f"({self.agents[a].state}/{self.agents[b].state})",
                          flush=True)
                elif d > C.PROX_REARM_M and pair in self._prox_below:
                    self._prox_below.discard(pair)

    def pending(self):
        busy = any(ag.task is not None for ag in self.agents.values())
        queued = any(not t.done and not t.failed for t in self.pool)
        return busy or queued