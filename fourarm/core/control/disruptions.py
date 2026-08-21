"""Seeded disruption engine (D1 to D4).

Generates a deterministic event schedule from a seed and applies it to the
running scene, so every allocation method later faces identical disruptions.

  D1 spawn        parked object teleported onto the table
  D2 displace     an active object teleported elsewhere
  D3 disable_arm  one arm freezes (optionally dropping its cargo)
  D4 priority     a natural-language operator command (consumed by Layer 4)

The engine knows nothing about tasks or allocation; it emits applied events.
"""

import math
import random
from dataclasses import dataclass, field

import torch

from core.cell import cell_config as C


@dataclass
class Event:
    t: float
    kind: str                    # spawn | displace | disable_arm | priority
    params: dict = field(default_factory=dict)
    applied: bool = False


def _table_xy(rng, margin=0.15):
    return (rng.uniform(-C.TABLE_HALF_X + margin, C.TABLE_HALF_X - margin),
            rng.uniform(-C.TABLE_HALF_Y + margin, C.TABLE_HALF_Y - margin))


def _clear_xy(rng, occupied, margin=0.15, tries=30):
    """A table position at least MIN_OBJ_SPACING from every occupied (x, y).
    Teleporting an object onto another interpenetrates, and PhysX resolves
    that by firing them apart, so spawn positions must be reject-sampled.
    Falls back to the last sample if the table is too crowded (logged)."""
    for _ in range(tries):
        x, y = _table_xy(rng, margin)
        if all((x - ox) ** 2 + (y - oy) ** 2 >= C.MIN_OBJ_SPACING ** 2
               for ox, oy in occupied):
            return x, y
    print("[disrupt] warning: no clear spawn cell found, placing anyway")
    return x, y


def make_schedule(seed, profile, horizon_s=20.0, categories=None):
    """profile in {none, D1, D2, D3, D4, mixed}. Deterministic per seed.

    Times are FRACTIONS of horizon_s, the expected episode length in
    seconds, not absolute constants. The old schedule hardcoded seconds
    against an assumed run length: disable_arm sat at t = 30.0 s, which is
    tick 3600 at 120 Hz, while measured episodes end near 2450 ticks
    (20.4 s). The arm-failure disruption therefore never fired in any
    episode ever recorded, and --disruptions D3 was silently inert.

    categories: the taxonomy of the RUNNING scene, for the D4 urgency
    command. Defaults to the legacy cube colours, which name nothing in a
    YCB scene, so the runner should pass ycb_scene.CATEGORIES.
    """
    rng = random.Random(seed)
    cats = list(categories or C.OBJECT_CATEGORIES)
    H = float(horizon_s)
    ev = []
    if profile in ("D1", "mixed"):
        for k in range(4):
            x, y = _table_xy(rng)
            ev.append(Event(H * (0.20 + 0.15 * k), "spawn", {"x": x, "y": y}))
    if profile in ("D2", "mixed"):
        for k in range(2):
            x, y = _table_xy(rng)
            ev.append(Event(H * (0.30 + 0.30 * k), "displace",
                            {"x": x, "y": y}))
    if profile in ("D3", "mixed"):
        arm = list(C.ARMS)[seed % len(C.ARMS)]      # victim rotates with seed
        ev.append(Event(H * 0.35, "disable_arm", {"arm": arm, "drop": True}))
    if profile in ("D4", "mixed"):
        ev.append(Event(H * 0.25, "priority",
                        {"command": f"{rng.choice(cats)} items are now urgent"}))
    ev.sort(key=lambda e: e.t)
    return ev


class DisruptionEngine:
    def __init__(self, scene, arms, pool_names, seed, profile, device,
                 spawn_specs=None, horizon_s=20.0, categories=None,
                 is_sorted=None, zonemap=None):
        self.scene = scene
        self.arms = arms
        self.device = device
        self.rng = random.Random(seed)
        # horizon_s: the episode's own length, so events land INSIDE the
        # run. categories: the running scene's taxonomy, so the urgency
        # command names something that exists.
        self.schedule = make_schedule(seed, profile, horizon_s=horizon_s,
                                      categories=categories)
        self.applied_log = []
        self.parked = list(pool_names)
        self.active = []
        # Optional per-object spawn pose: name -> {"z": ..., "rot": (w,x,y,z)}.
        # Without it, the cube defaults apply. YCB objects NEED it: the old
        # hardcoded identity rotation would flatten the upright-corrected
        # assets (mustard, bowl, pitcher) back onto their sides, and the
        # cube spawn height would bury tall objects' roots in the table.
        self.spawn_specs = spawn_specs or {}
        # Optional callbacks the runner supplies. Defaults keep the engine
        # free of any scene-specific import.
        # Supplied by the runner. Defaults keep the engine free of any
        # scene-specific import: nothing sorted, circle-test reach.
        self.is_sorted = is_sorted or (lambda name: False)
        self.zonemap = zonemap

    def _capable(self, obj_name):
        return [a for a in self.arms if C.can_grasp(a, obj_name)]

    def _in_reach(self, obj_name, x, y):
        """Could SOME arm that can grasp this object also reach (x, y)?"""
        for a in self._capable(obj_name):
            if self.zonemap is not None:
                if self.zonemap.reachable(a, x, y):
                    return True
                continue
            bx, by = C.ARMS[a]["pos"][0], C.ARMS[a]["pos"][1]
            d = math.hypot(x - bx, y - by)
            if 0.25 <= d <= C.ARM_TYPES[C.ARMS[a]["type"]]["reach"] * 0.92:
                return True
        return False

    def _reachable_clear_xy(self, obj_name, occupied, tries=400):
        """A clear cell that a CAPABLE arm can still serve.

        Without this, displacement could throw an object outside every
        capable arm's envelope: mug2 once landed 1.83 m from the nearest
        capable base against a 1.30 m reach, which makes the task
        impossible rather than harder and turns a recovery test into a
        scoring test."""
        for _ in range(tries):
            x, y = _table_xy(self.rng)
            if not self._in_reach(obj_name, x, y):
                continue
            if all((x - ox) ** 2 + (y - oy) ** 2 >= C.MIN_OBJ_SPACING ** 2
                   for ox, oy in occupied):
                return x, y
        print("[disrupt] warning: no reachable clear cell; falling back")
        return _clear_xy(self.rng, occupied)

    def _teleport(self, obj_name, x, y):
        obj = self.scene[obj_name]
        s = self.spawn_specs.get(obj_name)
        z = (s["z"] if s else C.OBJECT_SPAWN_Z + 0.02)
        q = (s.get("rot") if s else None) or (1.0, 0.0, 0.0, 0.0)
        pose = torch.tensor(
            [[x, y, z, q[0], q[1], q[2], q[3]]],
            device=self.device, dtype=torch.float32,
        )
        obj.write_root_pose_to_sim(pose)
        obj.write_root_velocity_to_sim(torch.zeros((1, 6), device=self.device))

    def _occupied(self):
        return [(float(self.scene[o].data.root_pos_w[0, 0]),
                 float(self.scene[o].data.root_pos_w[0, 1]))
                for o in self.active]

    def retire_object(self, name):
        """Park an object back off the table and drop it from the active set,
        so a completed object is never reconsidered for a task."""
        if name in self.active:
            self.active.remove(name)
            pose = torch.tensor([[C.PARK_POS[0], C.PARK_POS[1], C.PARK_POS[2],
                                  1.0, 0.0, 0.0, 0.0]],
                                device=self.device, dtype=torch.float32)
            self.scene[name].write_root_pose_to_sim(pose)
            self.scene[name].write_root_velocity_to_sim(
                torch.zeros((1, 6), device=self.device))
            self.parked.append(name)

    def retire_all(self):
        """Retire every active object. Used to clear the table between test
        scenarios so leftovers cannot be re-grabbed."""
        for name in list(self.active):
            self.retire_object(name)

    def activate_object(self, x=None, y=None):
        """Teleport the next parked object onto the table. With no position
        given, a clear spot away from active objects is sampled."""
        if not self.parked:
            return None
        if x is None:
            x, y = _clear_xy(self.rng, self._occupied())
        name = self.parked.pop(0)
        self._teleport(name, x, y)
        self.active.append(name)
        return name

    def populate_initial(self, n):
        return [self.activate_object() for _ in range(n)]

    def step(self, t):
        """Apply all events due at episode time t. Returns applied events."""
        fired = []
        for e in self.schedule:
            if not e.applied and e.t <= t:
                self._apply(e)
                e.applied = True
                fired.append(e)
                self.applied_log.append(e)
        return fired

    def _apply(self, e):
        if e.kind == "spawn":
            # With a full cast there is nothing parked to activate, so the
            # event fired and did nothing while still being logged as a
            # disruption. Say so instead: M10 and M12 must not average over
            # events that never happened.
            if not self.parked:
                e.params["object"] = None
                e.params["skipped"] = "object pool exhausted"
                return
            x, y = _clear_xy(self.rng, self._occupied())   # scheduled xy may
            e.params["x"], e.params["y"] = x, y            # now be occupied
            e.params["object"] = self.activate_object(x, y)
        elif e.kind == "displace":
            # A displacement that picks an ALREADY SORTED object un-sorts
            # it, so the episode records 10/11 for a disruption meant to
            # test recovery rather than scoring.
            carried = {a._carried[0] for a in self.arms.values()
                       if a._carried is not None}
            free = [o for o in self.active
                    if o not in carried and not self.is_sorted(o)]
            if free:
                name = self.rng.choice(free)
                others = [(ox, oy) for o in self.active if o != name
                          for ox, oy in [(
                              float(self.scene[o].data.root_pos_w[0, 0]),
                              float(self.scene[o].data.root_pos_w[0, 1]))]]
                x, y = self._reachable_clear_xy(name, others)
                self._teleport(name, x, y)
                e.params["x"], e.params["y"] = x, y
                e.params["object"] = name
            else:
                e.params["object"] = None
                e.params["skipped"] = "no unsorted, uncarried object"
        elif e.kind == "disable_arm":
            self.arms[e.params["arm"]].disable(drop=e.params.get("drop", True))
        elif e.kind == "priority":
            pass                              # Layer 4 consumes the string
