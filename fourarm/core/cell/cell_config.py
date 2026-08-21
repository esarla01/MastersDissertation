"""Central configuration for the four-arm cell.

The two arm types are exactly the two robots supported by Isaac Lab's
official differential-IK tutorial (run_diff_ik.py --robot franka_panda|ur10),
so every controller detail can be checked against real documentation.

Quaternions are (w, x, y, z). World origin at the table centre, z up.
"""

import math                     # route_m (timing model) only

# ------------------------------------------------------------------ table --
TABLE_H = 0.75
TABLE_TOP = (2.8, 1.6, 0.05)          # x, y, thickness
TABLE_HALF_X = TABLE_TOP[0] / 2
TABLE_HALF_Y = TABLE_TOP[1] / 2

# ------------------------------------------------------------------- arms --
# URs (long reach) on the long x edges, Frankas on the short y edges, all
# facing inward, so every arm reaches the table centre.
_R2 = 0.70710678
ARMS = {
    "ur_w":     {"type": "ur10",   "pos": (-1.15, 0.0, TABLE_H), "rot": (1.0, 0.0, 0.0, 0.0)},
    "ur_e":     {"type": "ur10",   "pos": (1.15, 0.0, TABLE_H),  "rot": (0.0, 0.0, 0.0, 1.0)},
    "franka_s": {"type": "franka", "pos": (0.0, -0.60, TABLE_H), "rot": (_R2, 0.0, 0.0, _R2)},
    "franka_n": {"type": "franka", "pos": (0.0, 0.60, TABLE_H),  "rot": (_R2, 0.0, 0.0, -_R2)},
}

# Joint and end-effector names exactly as in the tutorial's two variants.
ARM_TYPES = {
    # max_grasp_m: largest graspable object dimension; payload_kg: max mass.
    # Modelled on real hardware (Franka hand ~8 cm opening, 3 kg payload;
    # UR10 with a large industrial gripper ~14 cm, 10 kg). Enforced in
    # attach(), the allocator filter, and the Layer 4 validator, exactly
    # like reachability.
    "franka": {"joint_names": ["panda_joint.*"], "ee_body": "panda_hand",
               "reach": 0.855, "max_grasp_m": 0.08, "payload_kg": 3.0,
               "delicate_ok": True, "hover_z": TABLE_H + 0.25},
    "ur10":   {"joint_names": [".*"],            "ee_body": "ee_link",
               "reach": 1.30,  "max_grasp_m": 0.14, "payload_kg": 10.0,
               "delicate_ok": False, "hover_z": TABLE_H + 0.30},
}


def can_grasp(arm_name, obj_name):
    """Capability check: object size and mass within the arm's limits, and
    delicate objects (force-controlled grasp required) only for arms with
    delicate_ok. Objects missing from OBJECT_SPECS use the default (small
    cube); missing 'delicate' defaults to False, so every existing object
    and every cube behaves exactly as before."""
    t = ARM_TYPES[ARMS[arm_name]["type"]]
    spec = OBJECT_SPECS.get(obj_name, OBJECT_SPECS["_default"])
    if spec.get("delicate", False) and not t["delicate_ok"]:
        return False
    return spec["grasp_m"] <= t["max_grasp_m"] and spec["mass_kg"] <= t["payload_kg"]

# Compact elbow-up rest stance for the URs (set as their default joint state
# in the scene config; low gravity torque, tool above the base).
UR_READY_JOINT_POS = {
    "shoulder_pan_joint": 0.0, "shoulder_lift_joint": -1.57, "elbow_joint": 1.57,
    "wrist_1_joint": -1.57, "wrist_2_joint": -1.57, "wrist_3_joint": 0.0,
}

# Idle tuck stances, commanded in joint space once an arm has parked. URs
# fold into their proven ready pose. Frankas rely on the sideways home
# instead (see HOME_XY); the tuck below is the FALLBACK if the sideways
# park is still too bulky: wire it by adding "franka": FRANKA_TUCK_JOINT_POS
# to TUCK_JOINT_POS. Sign note: the default stance pitches the shoulder
# toward the table with panda_joint2 = -0.569, so POSITIVE joint2 leans
# away; flip its sign if the video shows the fold going inward.
FRANKA_TUCK_JOINT_POS = {
    # The canonical Panda READY pose, replacing the deep authored fold
    # (j2 0.9, j4 -2.7) on 2026-07-19. That fold had NEVER run before the
    # tuck map was wired (tuck() was a Franka no-op), and once live it
    # curled bizarrely and struck the table: a joint-space command's
    # transit is uncontrolled, and the deep wrap swept links low. The
    # ready pose is the universally validated Franka home: elbow up, hand
    # high, nothing near the table at start, end, or plausibly between.
    # What the tuck fix actually bought us is preserved: a CONSISTENT
    # posture that resets the IK basin between tasks (the gelatin fix),
    # which needs consistency, not compactness.
    "panda_joint1": 0.0, "panda_joint2": -0.785, "panda_joint3": 0.0,
    "panda_joint4": -2.356, "panda_joint5": 0.0, "panda_joint6": 1.571,
    "panda_joint7": 0.785,
}
TUCK_JOINT_POS = {"ur10": UR_READY_JOINT_POS,
                  "franka": FRANKA_TUCK_JOINT_POS}
# The franka entry was missing until 2026-07-19: Arm.tuck() was a
# silent NO-OP for Frankas, so their posture drifted across whole
# episodes (the common root of the gelatin stalls and the false
# franka_s tools-basket reading). Diagnostic: out/probe_diag.json,
# T1 vs T2: same target arrives in 106 ticks from a real tuck and
# stalls at err 0.392 from a drifted posture.

# ---------------------------------------------------------- exchange pads --
# "center" is reachable by all four arms; corner pads each sit in one
# UR/Franka overlap. Validate with zones.validate_pads once rasters exist.
EXCHANGE_PADS = {
    # Corner pads moved inward from (+-0.50, +-0.35) when the baskets gained
    # real walls: a wall large enough to contain a placement (half >= 0.17 m)
    # would have overhung a pad only 0.25 m away, and an object set down on
    # that pad would touch the wall. The pads have slack toward the centre;
    # the baskets do not (they are pinned by Franka reach). Zones, routes,
    # and reachability are unaffected: each pad stays in its own quadrant and
    # well inside both its arms' workspaces.
    "center": {"pos": (0.0, 0.0),     "arms": tuple(ARMS)},
    "pad_nw": {"pos": (-0.42, 0.28),  "arms": ("ur_w", "franka_n")},
    "pad_ne": {"pos": (0.42, 0.28),   "arms": ("ur_e", "franka_n")},
    "pad_se": {"pos": (0.42, -0.28),  "arms": ("ur_e", "franka_s")},
    "pad_sw": {"pos": (-0.42, -0.28), "arms": ("ur_w", "franka_s")},
}

# ---------------------------------------------------------------- objects --
OBJECT_SIZE = 0.05
OBJECT_SPAWN_Z = TABLE_H + OBJECT_SIZE / 2
MIN_OBJ_SPACING = 0.18                # teleported spawns keep this far from
                                      # active objects (overlap would eject)
NUM_POOL_OBJECTS = 16
PARK_POS = (4.0, 4.0, -1.0)
# LEGACY: the cube pool's colours. The YCB scene's categories are
# food/kitchenware/tools and live in ycb_scene.CATEGORIES. Anything that
# needs the categories of the RUNNING scene must be told them; drawing
# from this list gave the D4 urgency disruption colours no object has.
OBJECT_CATEGORIES = ["red", "green", "blue", "yellow"]

# Expected episode length in SECONDS, used to place disruption events.
# NOT the tick limit: --max-ticks defaults to 12000 (100 s) and is a safety
# cap roughly four times a real run. Scaling the schedule to it put every
# event after the episode had already finished; a b1 mixed run fired one
# event of eight. Measured makespans are 2410 to 3353 ticks, so 20 s is
# the shortest observed run and the schedule's 0.20-0.75 fractions land
# between ticks 480 and 1800, inside even that.
EPISODE_HORIZON_S = 20.0

# How often an unassignable task is re-tested for permanent impossibility.
# Ticks, not once: an object displaced out of reach after the first test
# would otherwise never fail and the episode would run to the tick limit.
PERMANENCE_RECHECK = 120
CATEGORY_RGB = {
    "red": (0.85, 0.10, 0.10), "green": (0.10, 0.70, 0.15),
    "blue": (0.10, 0.25, 0.85), "yellow": (0.90, 0.80, 0.10),
}

# ----------------------------------------------------------------- motion --
SIM_DT = 1.0 / 120.0
HOVER_Z = TABLE_H + 0.30              # legacy global (equals the UR value);
                                      # agent states use the PER-TYPE
                                      # ARM_TYPES['hover_z']: a Franka
                                      # hovering at UR height over a point
                                      # 0.6 m out runs out of arm (measured:
                                      # franka_n stalled over the centre pad
                                      # with residuals 0.125-0.18, four
                                      # aborts, task failed)
SETTLE_STEPS = 90
REACH_TOL = 0.02                      # arrival tolerance (m)
HANG = 0.10                           # carried object hangs this far below the EE
WRIST_HALF_SPAN = 0.10                # horizontal half-extent of the gripper
                                      # body: what the wrist can strike while
                                      # descending or lifting near a neighbour
TUCK_RAISE = 0.18                     # rise this far above hover BEFORE
                                      # folding: tuck() is a joint-space
                                      # command whose transit arc dips low
                                      # and once swept the wood block away;
                                      # at hover+0.18 the arc clears the
                                      # tallest cast object (~0.20 m) with
                                      # more than 20 cm to spare
RECOVER_MAX_TICKS = 900               # budget for the in-place recovery
                                      # tuck (the verified reset takes
                                      # ~900 ticks worst case in the
                                      # diagnostic)
MAX_HOME_FAILS = 3                    # consecutive GO_HOME aborts before an
                                      # arm gives up, frees its zones, and
                                      # parks disabled (liveness: a trapped
                                      # arm must not starve the cell)
WRIST_MARGIN = 0.04                   # air the wrist keeps above the tallest
                                      # object it passes over (a standing
                                      # pitcher is 0.242 m; a flat clearance
                                      # put the wrist BELOW its rim)
PLACE_CLEARANCE = 0.06                # extra release height so the wrist never
                                      # touches the set-down object (position-only
                                      # IK leaves wrist orientation free, and stall
                                      # acceptance can arrive up to LOOSE_TOL low)
ATTACH_TOL = 0.10                     # extra slack allowed when attaching

# ------------------------------------------------------------ reachability --
RASTER_RESOLUTION = 0.05              # m per cell (0.02 for the final run)
RASTER_DIR = "reachability/rasters"
RASTER_TEST_Z = TABLE_H + 0.15

# ---------------------------------------------------------------- layer 2 --
CENTER_RADIUS = 0.35                  # radius of the "center" lock zone (m)
LOCK_TIMEOUT_TICKS = 1800             # blocked this long -> requeue the task.
                                      # Recalibrated for the YCB scene: legs
                                      # take 600-1300 ticks (longer carries,
                                      # taller lifts) and five food items
                                      # funnel into one corner, so waits of
                                      # ~700 ticks are NORMAL queueing; the
                                      # old cube-era 720 read them as failure
DWELL_TICKS = 30                      # pause after attach/detach
STEP_TIMEOUT_TICKS = 900              # one motion step may take at most this

STALL_ACCEPT_TICKS = 120              # accept arrival after this long if close
LOOSE_TOL = 0.08                      # 'close' bound for stall acceptance (m)

# Idle/park positions: near each arm's own base, clear of the shared middle.
# Idle park positions. URs retreat well behind the shared space. Frankas
# park almost directly above their own bases: at (0, +-0.40) an idle Franka
# leaned forward with its forearm slanting over the table and a UR working a
# centre pick collided with it (position-only IK leaves the wrist free to
# stick out, and stall acceptance adds up to LOOSE_TOL of arrival error, so
# nominal gaps need real margin). At +-0.55 the parked arm stands as a
# compact near-vertical column at the table edge.
HOME_XY = {
    "ur_w": (-0.85, 0.0), "ur_e": (0.85, 0.0),
    # Franka homes are SIDEWAYS along each arm's own table edge. This
    # rotates the whole arm plane at the base joint, so the upper arm,
    # elbow, and forearm lie along the edge strip nothing else uses,
    # instead of leaning toward the centre. Opposite lateral sides so the
    # two parked arms occupy different quadrant corners.
    "franka_s": (-0.30, -0.68), "franka_n": (0.30, 0.68),
}

MAX_TASK_ATTEMPTS = 4                 # aborts before a task is marked failed
PAD_SKIP_RADIUS = 0.12                # handover planning ignores pads the
                                      # object already sits on (prevents a
                                      # degenerate pick-up-and-put-down leg)

# Per-object grasp specs: grasp_m is the smallest horizontal dimension the
# gripper must span; mass_kg the object mass. The YCB import fills this
# table; unknown objects fall back to _default (the small cube).
OBJECT_SPECS = {
    "_default": {"grasp_m": 0.05, "mass_kg": 0.05,
                 "rest_z": OBJECT_SPAWN_Z - TABLE_H,    # cube half-height
                 "footprint_m": OBJECT_SIZE,            # cube width
                 "height": OBJECT_SIZE},                # cube height
}
# --- arm-arm proximity watch (instrumentation, no control effect) ---------
PROX_CHECK_EVERY = 5        # ticks between pairwise EE distance checks
PROX_NEAR_MISS_M = 0.25     # closer than this -> one near_miss event
PROX_REARM_M = 0.30         # must separate past this before the pair can
                            # trigger again (hysteresis: one event per pass)

# --- no-progress stall abort -----------------------------------------------
STALL_ABORT_TICKS = 600     # with an ACTIVE goal, if the position error has
                            # not improved for this many consecutive ticks,
                            # the arm aborts and releases its zones. Bounds
                            # the damage of any IK stall: before this, a
                            # stalled franka_n camped on the CENTER lock for
                            # 2700 ticks x 4 attempts and starved four tasks.
                            # Lock waiting (no goal) is untouched: that is
                            # LOCK_TIMEOUT_TICKS territory.
STALL_MIN_IMPROVE = 0.01    # error must drop by this (m) to count as progress

# --- footprint-aware placement -----------------------------------------------
# Objects are set down where they actually FIT. The previous fixed scatter
# ring spaced arrivals 7.5 cm apart, but the bulky objects are far wider
# (bowl 15.9 cm, wood block lying 20.6 cm): a kinematic set-down into an
# overlap makes PhysX eject the neighbours violently (a mug flew 2.4 m out
# of a walled basket). Placement now searches for a spot whose distance to
# every object already present is at least the sum of the two half
# footprints plus PLACE_GAP, staying PLACE_GAP inside the basket walls.
PLACE_GAP = 0.015           # air between placed objects, and to the walls (m)
PLACE_MAX_R = 0.15          # max set-down distance from the basket centre:
                            # scoring counts an object sorted within 0.16 m,
                            # so every legal spot must stay inside that.
                            # Corner-first filling needs the corners, hence
                            # close to the limit; set-down is kinematic
                            # (exact), so the 1 cm margin is safe.
BASKET_WALL_HALF = 0.22     # basket wall half-extent. Sized so the three
                            # LYING tools (drill 0.184, clamp 0.165, wood
                            # 0.206 m long) provably fit with clearances;
                            # at 0.19 they could not (arithmetic, not code).
                            # Pad and table clearance re-verified for 0.22.

# --- timing model ------------------------------------------------------------
# Refitted 2026-07-29 from 145 PER-TASK execution windows across 10 episodes
# and 3 layouts (analysis/episode/episode_calibrate_timing.py):
#
#     moving_ticks = ticks_per_m * travel_leg_m + fixed_ticks
#     moving_ticks = (done_tick - exec_start_tick) - blocked_ticks
#
#   ur10    70.4 ticks/m (1.70 m/s) + 82.9 per task   R2 0.49, n=90
#   franka  97.2 ticks/m (1.23 m/s) + 314.2 per task  R2 0.36, n=55
#
# The FIRST fit (19.0 / 209.1 for ur10) was wrong and is kept here as a
# warning: it regressed per-EPISODE productive ticks on per-EPISODE travel,
# two different spans, so it implied a UR end-effector speed of 6.3 m/s
# while scoring R2 0.99. A high R2 on aggregated, collinear predictors is
# not evidence. The guards in episode_calibrate_timing.py now refuse any fit whose
# implied speed leaves [0.15, 4.0] m/s.
#
# WHAT THE NUMBERS SAY. The Franka is only 1.38x slower per metre; its real
# penalty is the per-task overhead, 314 vs 83 ticks, roughly 3.8x. It is
# slow at picking things up, not at carrying them. Anyone trying to close
# that gap should look at descend/attach/lift/lower/release/settle, not at
# travel gains.
#
# SPAN. done_tick is stamped on arrival HOME, so these coefficients cover
# approach + carry + retreat + travel home. leg_cost() must therefore be
# given the full round trip INCLUDING the return; pricing only
# base->object->destination applies the coefficients to a shorter journey
# than they were fitted on and systematically under-costs far-homing tasks.
# The fold that follows (PRE_TUCK + SETTLING, about 75 ticks for a UR and
# 180 for a Franka) is NOT included: it lies after done_tick, so these
# coefficients answer "when is the task done", not "when is the arm free".
#
# R2 is modest because each row is now one task rather than an arm-episode
# average, so genuine task-to-task variation is visible. With n=90 and n=55
# the slopes are still determined to roughly 8% and 15%, and residual
# standard deviations of 40 and 85 ticks are 10-20% of a typical task,
# which is adequate for a RELATIVE cost matrix. Refit after any controller,
# gain, or hover-height change: these are properties of the controller.
TIMING = {
    "franka": {"ticks_per_m": 97.2, "fixed_ticks": 314.2},
    "ur10":   {"ticks_per_m": 70.4, "fixed_ticks": 82.9},
}


def leg_cost(arm_name, path_m, legs=1):
    """Estimated execution ticks for arm_name to cover path_m metres in
    `legs` pick-place cycles. The currency of the timing-aware cost matrix
    ("--timing estimate"); distance mode does not call this.

    path_m must be the FULL journey the calibration measured, which ends at
    the arm's home pose. Use route_m() to build it rather than summing
    approach and carry by hand."""
    t = TIMING[ARMS[arm_name]["type"]]
    return t["ticks_per_m"] * path_m + t["fixed_ticks"] * legs


def route_m(arm_name, obj_xy, dest_xy):
    """Metres for arm_name to fetch an object and return to its home pose:
    base -> object -> destination -> home.

    The return leg is not optional bookkeeping. done_tick is stamped when
    the arm ARRIVES HOME and the zone locks are released there, not at
    placement, so a task whose destination sits far from the arm's home
    occupies that arm, and holds its zone, for materially longer. Omitting
    the leg made every such task look as cheap as a nearby one.

    HOME_XY is not the base: each arm parks about 0.30 m inward, so the
    return leg is read from the table rather than assumed."""
    ax, ay = ARMS[arm_name]["pos"][0], ARMS[arm_name]["pos"][1]
    hx, hy = HOME_XY[arm_name]
    return (math.hypot(obj_xy[0] - ax, obj_xy[1] - ay)
            + math.hypot(dest_xy[0] - obj_xy[0], dest_xy[1] - obj_xy[1])
            + math.hypot(hx - dest_xy[0], hy - dest_xy[1]))
