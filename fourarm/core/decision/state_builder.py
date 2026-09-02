"""Layer 3: state builder and prompt construction.

Turns the live cell into the inputs the MLLM allocator will receive. Two
experiment conditions are supported:

  A (Text): a ground-truth JSON state of arms, objects, tasks, locks,
    and recent events. Tests reasoning with perfect structured perception.
  V (Text+Image): the SAME text, byte-identical, plus the overhead camera
    frame. Tests whether the image channel adds allocation value; the
    single difference between A and V is the image block (E6 fairness).

Condition B (image with object positions withheld) was retired 2026-07-25
as redundant; its shakeout episodes are characterisation material only.

No LLM calls happen here. Layer 4 consumes build_state / build_prompt and
adds the model behind the allocator interface.
"""

import base64
import io
import json
import math

import numpy as np

from core.cell import cell_config as C
from core.cell.locks import zone_of


# ---------------------------------------------------------------------------
# State assembly (ground truth, condition A).
# ---------------------------------------------------------------------------

def pad_at(x, y):
    """Name of the exchange pad at (x, y), or None. Stated explicitly in
    the object state because deriving it requires matching coordinates
    across the JSON, which the model demonstrably fails at (it repeatedly
    re-proposed handovers for objects already sitting on the pad)."""
    for pad, spec in C.EXCHANGE_PADS.items():
        px, py = spec["pos"]
        if math.hypot(x - px, y - py) < C.PAD_SKIP_RADIUS:
            return pad
    return None

def can_handle(spec, arm_name):
    """The three capability checks the validator applies, for one arm.

    Kept here rather than imported so the table cannot drift from what the
    model is shown; the harness asserts it against the validator's own
    numbers in cell_config.
    """
    t = C.ARM_TYPES[C.ARMS[arm_name]["type"]]
    if spec.get("delicate", False) and not t["delicate_ok"]:
        return False
    return (spec["grasp_m"] <= t["max_grasp_m"]
            and spec["mass_kg"] <= t["payload_kg"])


def compute_eligible_arms(task, obj_xy, spec, zonemap, dead=()):
    """Arms that can legally START this task: capable of the object, able to
    reach it, and able to deliver it either directly or through a handover
    the cell arranges under R5.

    Lifted out of build_state 2026-08-02, logic unchanged, so the offline
    probe replay can render a saved state at the L4 rung. A state harvested
    without the ablation has no eligible_arms field, and re-deriving it in
    the replay runner would be a second copy of this rule. One copy, two
    callers.

    Before 2026-08-01 the third clause was "reaches the destination", so a
    relay-requiring task produced an EMPTY list. R3 then forbade every arm
    while R5 demanded a pad leg, and no proposal could satisfy both: the L4
    rung was built on a prompt that could be impossible to obey. With pad
    routing owned by the router this is a true allowlist. Every arm in it
    yields a legal proposal, every arm outside it does not, and an empty
    list means nothing can start this task now, so wait.

    Disabled arms are excluded. A frozen arm cannot be used, and the field
    promises usable arms, not physically suitable ones.
    """
    # Local import on purpose. tasks.py is Isaac-free so this keeps the
    # offline property, but importing it at module scope would make every
    # caller of state_builder depend on the control layer, including the
    # probe harness that only wants a prompt rendered.
    from core.control.tasks import route_via_pad
    ox, oy = obj_xy
    out = []
    for a in C.ARMS:
        if a in dead or not can_handle(spec, a):
            continue
        if not zonemap.reachable(a, ox, oy):
            continue
        if task.dest is not None and not zonemap.reachable(a, *task.dest):
            # Not a direct deliverer. Legal only if the router can build a
            # handover with this arm carrying the first leg.
            if route_via_pad(task, (ox, oy), [a], zonemap, dead)[0] is None:
                continue
        out.append(a)
    return out


def build_state(coord, engine, tick, baskets=None, zonemap=None,
                eligible=False):
    """Full ground-truth cell state as a JSON-ready dict.

    zonemap=None (default) reproduces the 2026-07-25d state EXACTLY, byte
    for byte. Existing vlm1/vlm2 episodes stay comparable and need no
    re-run.

    Passing a zonemap turns on the ENRICHED variant: every object, basket
    and exchange pad gains a "reach_ok_arms" list, taken from the SAME
    zonemap.reachable the validator uses, so the model can never be told
    something the guard will then refuse. b1 and b2 have always queried
    that map; this gives every allocator the same complete state.

    REACH ONLY, by design. Grasp size, payload and the delicate rule stay
    the model's own judgement: the numbers are all present in the state and
    comparing them IS the capability reasoning under study. The measured IK
    envelope is different in kind. It depends on our controller and our
    raster, appears in no datasheet, and could not be derived from anything
    the model is given.

    An earlier version named this field "reachable_by", which reads as a
    permission list. Five of the eleven designed objects name an arm that
    can reach them but cannot take them: large_clamp 0.122 m and
    wood_block 0.09 m against a 0.08 m Franka gripper, mug and mug2 at
    0.081 m, and banana and bowl are delicate so the URs are excluded.
    Capability rejections doubled from a stable 2 to 4 on the first run.
    Hence the explicit name and the explicit prompt sentence.

    arms[].reach_m is REMOVED when enriched. It is superseded by the list
    and disagrees with it at the boundary, so leaving both in tells the
    model to obey a rule while handing it the material to break it.
    base_xy stays: positions are still needed to compare travel.

    eligible=True is the ABLATION (2026-07-28, at Erin's direction). Each
    task gains "eligible_arms": the arms that can actually do that task,
    reach and capability resolved together, so the model is handed the
    answer to the question it has been getting wrong instead of the
    material to work it out. Default False, so every existing episode and
    every baseline stays valid without a re-run.

    The contrast is the measurement. With eligible=False the model must
    join three tables and compare numbers; with eligible=True it must only
    read a list. The difference in capability and reach rejections is how
    much of the failure was reasoning rather than perception.
    """
    scene = coord.cell.scene

    def reach_ok_arms(x, y):
        """Arms that can REACH (x, y), in cell_config order. Reach only:
        grasp size, payload and the delicate rule are deliberately NOT
        folded in, because judging those from the numbers already in the
        state is the capability reasoning under study. None unless the
        enriched variant is active."""
        if zonemap is None:
            return None
        return [a for a in C.ARMS if zonemap.reachable(a, x, y)]

    arms = []
    for name, agent in coord.agents.items():
        arm = agent.arm
        ee = arm.ee_pos_w()[0]
        arms.append({
            "name": name,
            "type": C.ARMS[name]["type"],
            "base_xy": [round(v, 2) for v in C.ARMS[name]["pos"][:2]],
            "reach_m": C.ARM_TYPES[C.ARMS[name]["type"]]["reach"],
            "max_grasp_m": C.ARM_TYPES[C.ARMS[name]["type"]]["max_grasp_m"],
            "payload_kg": C.ARM_TYPES[C.ARMS[name]["type"]]["payload_kg"],
            "delicate_ok": C.ARM_TYPES[C.ARMS[name]["type"]]["delicate_ok"],
            "state": agent.state,
            "disabled": arm.disabled,
            "holding": arm._carried[0] if arm._carried else None,
            "ee_xy": [round(float(ee[0]), 2), round(float(ee[1]), 2)],
        })
        if zonemap is not None:
            # reach_m is superseded by reach_ok_arms and contradicts it at
            # the boundary. Leaving both in asks the model to obey a rule
            # while handing it the material to break it. base_xy stays:
            # positions are still needed to compare travel.
            arms[-1].pop("reach_m")

    objects = []
    obj_info = {}                        # name -> (x, y, spec), for eligibility
    carried = {a._carried[0]: n for n, a in coord.cell.arms.items()
               if a._carried is not None}
    for obj_name in engine.active:
        p = scene[obj_name].data.root_pos_w[0]
        spec = C.OBJECT_SPECS.get(obj_name, C.OBJECT_SPECS["_default"])
        if "category" in spec:               # YCB: semantic category
            cat = spec["category"]
        else:                                # legacy cube pool: colour by
            idx = int(obj_name.split("_")[-1])   # creation index
            cat = C.OBJECT_CATEGORIES[idx % len(C.OBJECT_CATEGORIES)]
        entry = {
            "name": obj_name,
            "category": cat,
            "xy": [round(float(p[0]), 2), round(float(p[1]), 2)],
            "zone": zone_of(float(p[0]), float(p[1])),
            "at_pad": pad_at(float(p[0]), float(p[1])),
            "grasp_m": spec["grasp_m"],
            "mass_kg": spec["mass_kg"],
            "delicate": spec.get("delicate", False),
            "carried_by": carried.get(obj_name),
        }
        rb = reach_ok_arms(float(p[0]), float(p[1]))
        if rb is not None:
            entry["reach_ok_arms"] = rb
        obj_info[obj_name] = (float(p[0]), float(p[1]), spec)
        objects.append(entry)

    dead = {a["name"] for a in arms if a["disabled"]}

    def eligible_arms(t):
        """Arms that can legally START this task: capable of the object, able
        to reach it, and able to deliver it either directly or through a
        handover the cell arranges under R5.

        None unless the ablation is on.

        Before 2026-08-01 the third clause was "reaches the destination", so
        a relay-requiring task produced an EMPTY list. R3 then forbade every
        arm while R5 demanded a pad leg, and no proposal could satisfy both:
        the L4 rung was built on a prompt that could be impossible to obey.
        With pad routing owned by the router this is a true allowlist. Every
        arm in it yields a legal proposal, every arm outside it does not, and
        an empty list means nothing can start this task now, so wait.

        Disabled arms are excluded. A frozen arm cannot be used, and the
        field promises usable arms, not physically suitable ones.
        """
        if zonemap is None or not eligible:
            return None
        info = obj_info.get(t.obj)
        if info is None:                 # object gone (delivered, despawned)
            return []
        ox, oy, spec = info
        return compute_eligible_arms(t, (ox, oy), spec, zonemap, dead)

    def task_status(t):
        if t.failed:
            return "failed"
        if t.done:
            return "done"
        if t.claimed:
            return "in_progress"
        if t.waiting_on is not None:
            return "waiting_on_" + str(t.waiting_on)
        return "queued"

    # Only actionable tasks are shown to the allocator. Completed and failed
    # tasks are hidden (they invite reasoning about already-handled work);
    # their count is summarised instead. Handover parent/child both appear
    # only while still active.
    #
    # HELD tasks are hidden too. A held task belongs to a SERIALISED cell
    # (Coordinator(serialised=True), EX1 v2): it is in the pool and has an
    # id, and the cell has not released it yet. Rendering it would leave
    # every queued task visible in a cell whose whole point is that one
    # task is offered, and the model would still be choosing which task to
    # serve. getattr, not attribute access, so a coordinator rebuilt from a
    # frozen state by analysis/frozen_coord.py needs no new field.
    actionable = [t for t in coord.pool
                  if not t.done and not t.failed
                  and not getattr(t, "held", False)]
    tasks = []
    for t in actionable:
        entry = {
            "id": t.id, "object": t.obj,
            "dest_xy": ([round(v, 2) for v in t.dest]
                        if t.dest is not None else None),
            "dest_zone": (zone_of(*t.dest) if t.dest is not None
                          else "unassigned"),
            "status": task_status(t), "attempts": t.attempts,
        }
        ea = eligible_arms(t)
        if ea is not None:
            # A task with no destination yet (dest_xy null) is scored on the
            # object alone: the basket is the model's to choose under R7, and
            # naming one here would pre-empt the sorting decision we measure.
            entry["eligible_arms"] = ea
        tasks.append(entry)
    completed_count = sum(1 for t in coord.pool if t.done)
    failed_count = sum(1 for t in coord.pool if t.failed)

    events = [{"t": round(e.t, 1), "kind": e.kind,
               "params": {k: (round(v, 2) if isinstance(v, float) else v)
                          for k, v in e.params.items()}}
              for e in engine.applied_log[-6:]]

    def pad_entry(v):
        e = {"xy": list(v["pos"]), "arms": list(v["arms"])}
        rb = reach_ok_arms(v["pos"][0], v["pos"][1])
        if rb is not None:
            # zone stated, not derived: the prompt asks for "regions" and
            # making the model recompute a quadrant from coordinate signs
            # is geometry we already told it not to do.
            e["zone"] = zone_of(v["pos"][0], v["pos"][1])
            e["reach_ok_arms"] = rb
        return e

    def basket_entry(spec):
        e = {"xy": list(spec["pos"])}
        rb = reach_ok_arms(spec["pos"][0], spec["pos"][1])
        if rb is not None:
            e["zone"] = zone_of(spec["pos"][0], spec["pos"][1])
            e["reach_ok_arms"] = rb
        return e

    state = {
        "tick": tick,
        "table": {"size_xy": list(C.TABLE_TOP[:2]),
                  "zones": ["center"] + ["nw", "ne", "sw", "se"],
                  "center_radius": C.CENTER_RADIUS},
        "exchange_pads": {k: pad_entry(v)
                          for k, v in C.EXCHANGE_PADS.items()},
        "arms": arms,
        "objects": objects,
        "tasks": tasks,
        "baskets": ({name: basket_entry(spec)
                     for name, spec in baskets.items()} if baskets else None),
        "tasks_completed": completed_count,
        "tasks_failed": failed_count,
        "zone_locks": dict(coord.locks.holder),
        "zone_inbound": {z: list(q) for z, q in
                         getattr(coord.locks, "reservations", {}).items()
                         if q},
        "recent_events": events,
        "metrics": {"blocked_ticks": dict(coord.m.blocked),
                    "requeued": coord.m.requeued},
    }
    if zonemap is not None:
        # Single marker. build_prompt reads THIS rather than a second flag,
        # so the prompt wording can never disagree with the state contents.
        state["reachability"] = "listed+eligible" if eligible else "listed"
    return state


def is_enriched(state):
    """True when this state carries reach_ok_arms lists."""
    return str(state.get("reachability", "")).startswith("listed")


def has_eligible(state):
    """True when each task carries a resolved eligible_arms list."""
    return state.get("reachability") == "listed+eligible"


# ---------------------------------------------------------------------------
# Camera frame (condition V).
# ---------------------------------------------------------------------------

def grab_frame_b64(scene, camera="table_cam", rot_k=-1):
    """Current overhead RGB frame as base64 PNG (for the vision model).

    The raw camera renders east-up (see scene_cfg table_cam). The model
    should never have to mentally rotate the scene, so the frame is
    rotated 90 degrees clockwise here: the encoded image is NORTH-UP,
    EAST-RIGHT, matching the map convention of the text state."""
    rgb = scene[camera].data.output["rgb"][0].detach().cpu().numpy()[..., :3]
    # rot_k=-1 is the overhead camera's correction: it renders east-up and
    # the model should never have to mentally rotate the scene. A camera
    # mounted at another angle needs a different value, so it is a
    # parameter rather than a constant. ex2_cam passes 0.
    rgb = (np.ascontiguousarray(np.rot90(rgb, k=rot_k)) if rot_k else rgb)
    if rgb.dtype != np.uint8:
        rgb = ((rgb * 255).clip(0, 255) if rgb.max() <= 1.0
               else rgb.clip(0, 255)).astype(np.uint8)
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------------------
# Prompt construction.
# ---------------------------------------------------------------------------

# Bumped on ANY wording change to the prompts below or the feedback
# re-prompt in vlm_allocator. Recorded in every episode JSON so runs are
# attributable to an exact prompt. Freeze this before experiments.
# CURRENT. Every object, basket and pad carries a reachable_by list and the
# model is told to use it instead of computing reach from coordinates. This
# is the default: the radius rule described a workspace the cell does not
# actually enforce, and b1/b2 have always queried the true envelope, so
# giving the model the same removes an asymmetry rather than adding a
# crutch.
PROMPT_VERSION = "2026-08-01a"   # pad routing delegated to the router: R5 rewritten, via_pad removed from the answer, R4 no longer requires destination reach

# The previous lineage, kept so the 2026-07-25d episodes stay reproducible.
# Selected with enriched=False; not used by default.
PROMPT_VERSION_BASELINE = "2026-07-25d"   # strategic noop granted neutrally; reason required for noops (RQ4 licensing)

# The single sentence that differs between the two variants.
REACH_RULE_BASELINE = (
    "An arm can only do a task if BOTH the object\n"
    "and the destination are within its reach, AND the object fits within its\n"
    "grasp size and payload limits; large or heavy objects are UR-only.")

REACH_RULE_ENRICHED = (
    "The arm must appear in the \"reach_ok_arms\" list of the OBJECT. Every\n"
    "    object, basket and pad carries one, and it is authoritative for\n"
    "    reach: use it, do not work reach out from coordinates.\n"
    "    It says nothing about R3: an arm can often reach an object it\n"
    "    cannot pick up. Reaching the destination is not required of you;\n"
    "    see R5.")

# The ABLATION. Eligibility is resolved for the model instead of by it, so
# R3 stops being an arithmetic instruction and R4 shrinks to the one place
# the table cannot cover: a basket the model picks itself.
REACH_RULE_ELIGIBLE = (
    "\"eligible_arms\" already settles reach. For a basket you choose under\n"
    "    R7, use the \"reach_ok_arms\" list on that basket.")

CAPABILITY_RULE = (
    "The arm must be able to handle the object, on every leg:\n"
    "      \"grasp_m\" at most the arm's \"max_grasp_m\"\n"
    "      \"mass_kg\" at most the arm's \"payload_kg\"\n"
    "      a \"delicate\" object needs an arm whose \"delicate_ok\" is true")

CAPABILITY_RULE_ELIGIBLE = (
    "The arm must appear in the task's \"eligible_arms\" list. That list is\n"
    "    authoritative and final: it already applies grasp size, payload, the\n"
    "    delicate rule, reach to the object, and the existence of a delivery\n"
    "    route. Do not re-derive it from the numbers. An EMPTY list means no\n"
    "    arm can start this task now, so wait.")

# Ablation lineage. The suffix exists so episode_metrics.py can never pool an
# ablation episode with the default column by accident.
PROMPT_VERSION_ELIGIBLE = PROMPT_VERSION + "+eligible"


def prompt_version(state_or_enriched=True, eligible=False):
    """Version string to record in meta, for a state dict or a bool."""
    if isinstance(state_or_enriched, dict):
        enriched = is_enriched(state_or_enriched)
        eligible = has_eligible(state_or_enriched)
    else:
        enriched = bool(state_or_enriched)
    if not enriched:
        return PROMPT_VERSION_BASELINE
    return PROMPT_VERSION_ELIGIBLE if eligible else PROMPT_VERSION

SYSTEM_PROMPT = """You are the task allocator for a four-arm robotic cell.

The cell: a {tx} x {ty} m table, world origin at its centre, x east, y north.
Two UR10 arms (grasp up to 0.14 m and 10 kg) sit mid-table on the west and
east edges. Two Franka arms (grasp up to 0.08 m and 3 kg) sit on the south
and north edges. All face inward. If an overhead
image is provided, its top edge is north (+y) and its right edge is east
(+x). Objects must be
transported to destinations. {reach_rule} If no single
arm can, route via an exchange pad reachable from both sides and answer with
the pad leg. Use a pad ONLY when no single arm can reach both the object and
the destination; never propose a pad for an arm that can deliver directly.
An object whose "at_pad" field names a pad has ALREADY completed
its handover leg and is waiting on that pad: never route it via any pad
again; assign an arm that can deliver it directly to the destination, or
wait (task_id -1) until one is idle. Objects marked "delicate" require a
force-controlled grasp: only arms with "delicate_ok" true may handle them,
including every leg of a handover. Zones (center disc r={cr} m plus quadrants nw/ne/sw/se) are
mutually exclusive workspaces; prefer allocations that avoid making arms
queue for the same zone. The state shows each zone's occupancy:
"zone_locks" lists current holders and "zone_inbound" lists arms already
assigned work heading into a zone. In every assignment answer, ALSO
declare the zones your chosen assignment will occupy as "regions": the
zone containing the object and the zone containing its target (the pad if
you answer via_pad, otherwise the destination). Do not compute these:
every object, basket and pad states its own "zone", so copy those two. Disabled arms cannot move and their bodies block
the space where they froze. Tasks marked in_progress or waiting are already
being handled: never reassign them. Choose only among queued tasks for an
idle arm. If no queued task can be assigned to any idle arm right now,
answer with task_id -1 and arm null. A noop can also be STRATEGIC: if
every idle arm is a poor match for a remaining task (long travel, or a
relay it could avoid) and a better-suited arm will become free soon,
waiting is legitimate and sometimes better. Always include a reason,
for a noop too: say what you are waiting for.

SORTING TASKS: a task whose dest_xy is null has no destination yet. YOU
choose it: pick the basket where this object belongs so that objects of the
same kind end up together (the state lists "baskets" with their positions;
match the object's "category" to the basket named for it). For such a task,
include "basket": "<basket name>" in your reply. The chosen arm must be able
to reach both the object and that basket.

Answer ONLY with JSON, no prose:
{{"task_id": <int>, "arm": "<arm name>", "via_pad": "<pad name or null>",
  "basket": "<basket name, or null if the task already has a destination>",
  "regions": ["<zone>", "<zone>"],
  "reason": "<one short sentence>"}}
For a noop (task_id -1) omit "regions" or use []."""




# The CURRENT prompt. Split into HARD RULES and GUIDANCE rather than one
# paragraph, mirroring the architecture: the validator enforces R1-R7 and
# vetoes nothing in G1-G5, so the prompt now tells the model which of its
# instructions can get a proposal refused and which only make it better.
# The 25d wording
# stated every rule with equal weight in a 45-line block, and the failures we
# measured were overwhelmingly ones where the relevant fact WAS present and
# under-attended (busy arms named two paragraphs above, capability numbers
# sitting beside the object). Headings give each rule a findable home.
#
# Changes of substance against 25d, each deliberate:
#   - capability stated ONCE, in its own section, as three named checks
#     against named state fields (it was split across two places before)
#   - "large or heavy objects are UR-only" removed: a category heuristic
#     that competed with the per-object numbers
#   - arm radii removed from the prose: superseded by reach_ok_arms
#   - "most urgent" removed: urgency was never defined, and the model ran
#     first-in-first-out on 24 of 25 first attempts under 25d
#   - scarce-resource sentence added in section 6. NOT a makespan
#     instruction: the model gets one assignment per call, no memory between
#     calls, and no duration information, so it cannot reason about a
#     schedule. That instruction becomes answerable once travel time is in
#     the state, and not before.
SYSTEM_PROMPT_SECTIONED = """You are the task allocator for a four-arm robotic cell. Each time you are asked, choose ONE queued task and ONE idle arm, or
choose to wait.

THE CELL
A {tx} x {ty} m table, origin at its centre, x east, y north. Two UR10 arms sit
mid-table on the west and east edges, two Franka arms on the south and north
edges, all facing inward. Zones are a centre disc of radius {cr} m plus the
quadrants nw, ne, sw, se, and one arm may hold a zone at a time. If an overhead
image is given, its top edge is north (+y) and its right edge is east (+x).

HARD RULES. A proposal that breaks any of these is rejected.
R1  Assign only a task whose status is "queued". A task marked "in_progress"
    or "waiting_on_..." is already being handled.
R2  Assign only to an arm named in the idle list. A disabled arm is never
    available, and its body still blocks the space where it froze.
R3  {capability_rule}
R4  {reach_rule}
R5  You do not choose exchange pads. If the arm you name cannot reach the
    destination, the cell arranges a handover itself, using your arm for the
    first leg and another arm to finish. Your proposal is legal only when
    such a route exists; if none does it is rejected, so name a different arm
    or wait. A handover costs two trips instead of one, so prefer an arm that
    can deliver directly when you have the choice.
R6  An object whose "at_pad" names a pad has already completed its handover
    and is waiting there. It goes straight to its destination now: name an
    arm that reaches both the pad and the destination, or wait for one.
R7  A task whose "dest_xy" is null has no destination yet. Name one in
    "basket". R3 still applies to it, and R5 governs how it is reached.

GUIDANCE. Not enforced, but this is what a good allocation does.
G1  Sort correctly: send each object to the basket named for its "category",
    so that objects of the same kind end up together.
G2  Avoid contention: prefer allocations that do not make arms queue for the
    same zone. "zone_locks" names current holders, "zone_inbound" names arms
    already heading into one.
G3  Ignore queue order: it carries no priority. Pick the task that best fits
    an arm that is free now, not the first one listed.
G4  Protect scarce arms: if the arm you are about to use is the only one that
    could serve another queued task, prefer an alternative for this one.
G5  Waiting can be a choice, not only a last resort. If every idle arm is a
    poor fit and a better-suited one will free up soon, wait.

YOUR ANSWER
Answer ONLY with JSON, no prose:
{{"task_id": <int>, "arm": "<arm name>",
  "basket": "<basket name, or null if the task already has a destination>",
  "regions": ["<zone>", "<zone>"],
  "reason": "<one short sentence>"}}
"regions" are the zones the assignment occupies: the object's zone, and its
destination's zone. Do not work these out; every object, basket and pad
states its own "zone", so copy those two values.
To wait, answer task_id -1 with arm null and omit "regions".
Always give a reason, for a wait too: say what you are waiting for."""


def system_prompt(enriched=True, eligible=False):
    """Default renders the CURRENT sectioned prompt. enriched=False renders
    the frozen 2026-07-25d wording, byte for byte, so the earlier lineage
    stays reproducible. eligible=True renders the ablation: R3 and R4 point
    at the resolved list instead of asking for the arithmetic.

    Only R3 and R4 move. Every other line of the sectioned prompt is
    byte-identical across the default and the ablation, which is what makes
    the pair a clean comparison."""
    if not enriched:
        return SYSTEM_PROMPT.format(
            tx=C.TABLE_TOP[0], ty=C.TABLE_TOP[1], cr=C.CENTER_RADIUS,
            reach_rule=REACH_RULE_BASELINE)
    return SYSTEM_PROMPT_SECTIONED.format(
        tx=C.TABLE_TOP[0], ty=C.TABLE_TOP[1], cr=C.CENTER_RADIUS,
        capability_rule=(CAPABILITY_RULE_ELIGIBLE if eligible
                         else CAPABILITY_RULE),
        reach_rule=(REACH_RULE_ELIGIBLE if eligible else REACH_RULE_ENRICHED))


def build_prompt(state, condition, image_b64=None):
    """Messages list (OpenAI chat format) for condition 'A' or 'V'.

    A: full structured state as text. V: the SAME text (built once,
    shared, byte-identical by construction) plus the overhead frame;
    the image block is the single added variable, the E6 fairness
    requirement. The orientation convention lives in the shared system
    prompt, identical across conditions. Condition B (image with object
    positions withheld) was retired 2026-07-25 as redundant with the
    A-vs-V pair; its shakeout data is characterisation material only.
    """
    if condition not in ("A", "V"):
        raise ValueError(f"unknown VLM condition: {condition!r}")
    # The arm states are already in the JSON, but restating the idle set in
    # the instruction line makes it salient: observed first-attempt errors
    # were overwhelmingly picks of busy arms whose busy status was present
    # in the state yet under-attended (same rationale as EMOS's resumes).
    idle = [a["name"] for a in state["arms"]
            if a["state"] == "IDLE" and not a["disabled"]]
    if is_enriched(state):
        ask = ("\nIdle arms right now: " + (", ".join(idle) or "none") +
               ".\nAssign ONE queued task to ONE of these idle arms, or "
               "answer task_id -1 if none can be assigned now.")
    else:                                  # frozen 2026-07-25d wording
        ask = ("\nIdle arms right now: " + (", ".join(idle) or "none") +
               ".\nAllocate the most urgent QUEUED task to ONE of these idle "
               "arms, or answer task_id -1 if none can be assigned now.")
    user_text = "Cell state:\n" + json.dumps(state, indent=1) + ask
    content = [{"type": "text", "text": user_text}]
    if condition == "V":
        content = [{"type": "image_url",
                    "image_url":
                        {"url": f"data:image/png;base64,{image_b64}"}},
                   ] + content
    return [{"role": "system",
             "content": system_prompt(is_enriched(state), has_eligible(state))},
            {"role": "user", "content": content}]


def parse_decision(text):
    """Extract the decision JSON from a model reply. Returns dict or None."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        d = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if "task_id" in d and "arm" in d:
        d.setdefault("via_pad", None)
        d.setdefault("regions", None)
        return d
    return None


def is_noop(decision):
    """True if the model declined to allocate (nothing assignable now)."""
    return decision is not None and decision.get("task_id") == -1