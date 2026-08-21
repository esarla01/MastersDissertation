"""Rebuild a validator-compatible coordinator from a saved state dict.

This is the shim every offline experiment stands on. If it misrepresents
the cell, every replayed number is wrong in the same direction and nothing
looks broken, which is why h_frozen_coord.py exists alongside it and why
the acceptance test compares against a real episode rather than against
expectations written here.

WHAT THE VALIDATOR ACTUALLY TOUCHES. Read line by line from
vlm_allocator.validate_decision and core.control.tasks.route_via_pad, this
is the entire surface:

    coord.pool                 tasks with .id .obj .dest .done .failed
                               .claimed .waiting_on .dest_by .attempts
    coord.agents[name].state   the arm state string, "IDLE" or otherwise
    coord.agents[name].arm.disabled
    coord.cell.scene[obj].data.root_pos_w[0]     object position

Everything else the two functions use is cell_config, the zonemap loaded
from the rasters, and the baskets dict, none of which depend on a live sim.
That is why EX1, EX2 and EX3 can run with no simulator at all.

POSITIONS ARE EXACT, NOT ROUNDED. The state's "xy" is rounded to 2 dp for
the prompt, but the live validator reads full precision out of the scene.
Rebuilding from the rounded value would feed it a position up to 5 mm away,
and this cell places objects at up to 97% of an arm's reach, so a boundary
verdict could flip. Audit records written from 2026-08-01 carry
"positions_exact"; this module REQUIRES it and refuses to guess. Replaying
an older record raises rather than silently degrading, because a silent
degradation here is exactly the failure mode nobody would notice.

MUTATION. validate_decision writes task.dest and task.dest_by on success,
by design: the decision is only allowed to persist once it is known valid.
A rebuilt coordinator is therefore single-use. from_record() returns a
fresh one each call, and replaying the same record twice must build it
twice.

Usage:

    from analysis.frozen_coord import from_record
    coord = from_record(record)                 # one consults.jsonl line
    ok, target, sub, why = validate_decision(decision, coord, zm, baskets)
"""

import types

from core.cell import cell_config as C


class _Data:
    __slots__ = ("root_pos_w",)

    def __init__(self, xy):
        # A list of one row, indexed [0] then [0]/[1], matching the Isaac
        # tensor access pattern the validator uses. Not numpy: nothing here
        # needs it, and float() is applied on the live path anyway.
        self.root_pos_w = [[float(xy[0]), float(xy[1]), 0.9]]


class _SceneItem:
    __slots__ = ("data",)

    def __init__(self, xy):
        self.data = _Data(xy)


class FrozenScene:
    """Mapping name -> object with .data.root_pos_w, and nothing else.

    A missing name raises KeyError exactly as the live scene would. Silently
    returning a default would let a decision about a despawned object look
    valid offline and be rejected live.
    """

    def __init__(self, positions):
        self._items = {k: _SceneItem(v) for k, v in positions.items()}

    def __getitem__(self, name):
        return self._items[name]

    def __contains__(self, name):
        return name in self._items

    def __iter__(self):
        return iter(self._items)

    def keys(self):
        return self._items.keys()


class FrozenTask:
    """The task fields the validator and the router read.

    Deliberately NOT core.control.tasks.Task: that class carries execution
    bookkeeping (exec_start_tick, travel_leg_m, blocked_ticks) which has no
    meaning on a frozen state, and populating it with zeros would invite
    someone to compute a timing number from a state that never ran.
    route_via_pad only reads .obj and .dest, and constructs its own real
    Task for the subtask it returns.
    """

    def __init__(self, id, obj, dest=None, claimed=False, waiting_on=None,
                 attempts=0, dest_by=None):
        self.id = id
        self.obj = obj
        self.dest = dest
        self.done = False           # done/failed tasks are absent from the
        self.failed = False         # state by construction: build_state
        self.claimed = claimed      # filters to actionable tasks only
        self.waiting_on = waiting_on
        self.attempts = attempts
        self.dest_by = dest_by

    def __repr__(self):
        return (f"FrozenTask(id={self.id}, obj={self.obj!r}, "
                f"dest={self.dest}, claimed={self.claimed}, "
                f"waiting_on={self.waiting_on})")


def _decode_status(status):
    """state_builder.task_status inverted: (claimed, waiting_on).

    "done" and "failed" cannot appear, because build_state only emits
    actionable tasks. If one turns up, the state did not come from
    build_state and the caller should know rather than get a plausible
    object back.
    """
    if status == "queued":
        return False, None
    if status == "in_progress":
        return True, None
    if status.startswith("waiting_on_"):
        return False, int(status[len("waiting_on_"):])
    raise ValueError(
        f"unexpected task status {status!r}. build_state emits only "
        f"'queued', 'in_progress' and 'waiting_on_<id>'; 'done' and "
        f"'failed' tasks are filtered out before the state is built.")


def register_specs_from_state(state):
    """Teach cell_config the physics of the objects in this state.

    THIS IS NOT OPTIONAL. cell_config.can_grasp falls back to
    OBJECT_SPECS["_default"], a small cube, for any object it does not
    know, and the live run populates OBJECT_SPECS when the SCENE is built.
    An offline process builds no scene, so without this every YCB object
    would be treated as a small graspable cube and the validator would be
    silently more permissive than it was live. Caught by the acceptance
    test on 2026-08-02: a 0.122 m large clamp came back valid for a Franka
    whose limit is 0.080.

    The state is the right source rather than the YCB registry, because it
    records the properties as they were AT THAT TICK. A conflict with an
    already-registered spec raises: between probes of one set the values
    must agree, so a disagreement means either cross-contamination from
    another episode or a registry that has changed under a frozen set.
    """
    for o in state.get("objects", []):
        name = o.get("name")
        missing = [k for k in ("grasp_m", "mass_kg") if o.get(k) is None]
        if missing:
            raise ValueError(
                f"object {name!r} in the saved state is missing {missing}, so "
                f"its capability cannot be reconstructed. Without it can_grasp "
                f"would silently fall back to the default cube and accept "
                f"decisions the live cell rejected.")
        spec = {"grasp_m": float(o["grasp_m"]),
                "mass_kg": float(o["mass_kg"]),
                "delicate": bool(o.get("delicate", False))}
        if o.get("category"):
            spec["category"] = o["category"]
        prev = C.OBJECT_SPECS.get(name)
        if prev is not None:
            for k in ("grasp_m", "mass_kg", "delicate"):
                old = prev.get(k, False if k == "delicate" else None)
                if old is not None and old != spec[k]:
                    raise ValueError(
                        f"object {name!r} is already registered with {k}="
                        f"{old!r} but this state says {spec[k]!r}. Refusing to "
                        f"overwrite: either two episodes with different object "
                        f"physics are being mixed, or the registry changed "
                        f"under a frozen probe set.")
            spec = {**prev, **spec}
        C.OBJECT_SPECS[name] = spec


def from_state(state, positions_exact):
    """Build the shim from a state dict plus exact object positions.

    positions_exact must cover every object named by a task, otherwise the
    validator would read a position that is merely close. Missing entries
    raise here rather than being filled from the rounded state.
    """
    register_specs_from_state(state)

    if not isinstance(positions_exact, dict) or not positions_exact:
        raise ValueError(
            "positions_exact is required and must be non-empty. The state's "
            "'xy' is rounded to 2 dp for the prompt; the validator reads "
            "full precision. Audit records from 2026-08-01 carry this field.")

    pool = []
    for t in state.get("tasks", []):
        claimed, waiting_on = _decode_status(t["status"])
        dest = tuple(t["dest_xy"]) if t.get("dest_xy") is not None else None
        pool.append(FrozenTask(id=t["id"], obj=t["object"], dest=dest,
                               claimed=claimed, waiting_on=waiting_on,
                               attempts=t.get("attempts", 0)))

    missing = sorted({t.obj for t in pool} - set(positions_exact))
    if missing:
        raise ValueError(
            f"positions_exact is missing objects named by tasks: {missing}. "
            f"Refusing to substitute the rounded state position.")

    agents = {}
    for a in state.get("arms", []):
        agents[a["name"]] = types.SimpleNamespace(
            state=a["state"],
            arm=types.SimpleNamespace(disabled=bool(a["disabled"]),
                                      _carried=((a["holding"],)
                                                if a.get("holding") else None)))

    scene = FrozenScene({k: tuple(v) for k, v in positions_exact.items()})
    return types.SimpleNamespace(
        pool=pool,
        agents=agents,
        cell=types.SimpleNamespace(
            scene=scene,
            arms={n: ag.arm for n, ag in agents.items()}))


def from_record(record):
    """Build the shim from one consults.jsonl line."""
    if "state" not in record:
        raise ValueError(
            "audit record has no 'state'. Records written before "
            "2026-08-01 saved only the rendered prompt, which cannot be "
            "re-rendered at another rung. Re-run the episode.")
    return from_state(record["state"], record.get("positions_exact"))


def idle_arms(coord):
    """Arms that are IDLE and not disabled, in state order.

    The same predicate the Coordinator uses when it assembles the idle list
    for an allocation round, so a replayed reference allocator is offered
    exactly what the live one was.
    """
    return [n for n, ag in coord.agents.items()
            if ag.state == "IDLE" and not ag.arm.disabled]