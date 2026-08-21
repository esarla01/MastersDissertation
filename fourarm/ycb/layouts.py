"""Frozen, pre-validated object layouts for the four-arm cell.

These are hand-checked coordinate tables, deliberately NOT a runtime
sampler. The seeded sampler has an open hang and a route-existence bug, and
discovering a bad layout only after twenty minutes of simulation is too
expensive to risk per episode. So each layout is validated once, here, and
frozen: every one passes the real ycb_scene.validate_layout and
verify_basket_capacity, and every object is guaranteed completable -- a
capable arm reaches both it and its basket, or a valid two-arm relay exists
through a pad.

INVARIANT: who can finish a task.

Basket positions and the arm capability table decide WHO CAN FINISH each
object, and no arrangement of objects can change that -- an arm has to reach
the basket, not just the object:

    food        (-0.70, 0.50)  deliverable by ur_w, franka_n
    kitchenware ( 0.70, 0.50)  deliverable by ur_e, franka_n
    tools       (-0.70,-0.50)  deliverable by ur_w, franka_s

    ur_w      can complete 7 of 11 objects
    franka_n  can complete 5
    ur_e      can complete 2 (mug, mug2)
    franka_s  can complete 1 (power_drill)

So franka_s is near-idle in ANY layout: a layout can hand it relay legs but
never a new completion. Lifting that floor takes a fourth or repositioned
basket -- the sixth-box question, out of scope here.

WHAT LAYOUTS DO CONTROL: the difficulty knobs. Within that fixed capability
structure, placement still sets which arms can pick each object, how many
tasks force a handover, how many (object, arm) pairs are reachable but not
graspable (the capability trap), and how tightly the work concentrates by
zone and by pad. Each named layout below tunes one of these to isolate a
specific metric.
"""

# L1: the layout every episode so far has used. Kept for continuity.
L1_DESIGNED = {
    "soup_can":    (-0.82,  0.22),
    "banana":      ( 0.05,  0.30),
    "gelatin_box": ( 0.82,  0.22),
    "meat_can":    (-0.85, -0.25),
    "mustard":     ( 0.75, -0.25),
    "mug":         ( 0.30,  0.55),
    "mug2":        ( 0.65,  0.02),
    "bowl":        (-0.30,  0.55),
    "power_drill": (-0.65, -0.02),
    "large_clamp": ( 0.40, -0.05),
    "wood_block":  (-0.15, -0.25),
}

# L2: every arm can pick; franka_s goes from 0 eligible picks to 5, so the
# cell stops behaving as three arms and a spectator.
L2_BALANCED = {
    "soup_can":    (-0.15, -0.15),
    "banana":      ( 0.65, -0.65),
    "gelatin_box": (-0.30, -0.50),
    "meat_can":    ( 0.05,  0.35),
    "mustard":     ( 0.25,  0.45),
    "mug":         ( 1.05, -0.50),
    "mug2":        (-1.10,  0.55),
    "bowl":        (-0.40, -0.05),
    "power_drill": (-0.20,  0.05),
    "large_clamp": ( 0.25, -0.50),
    "wood_block":  (-0.25,  0.30),
}

# L3: 7 of 11 tasks need a handover (vs 3 in L1), so M6/M7 relay precision
# and recall rest on a real sample instead of n = 3.
L3_RELAY_HEAVY = {
    "soup_can":    ( 1.25, -0.60),
    "banana":      (-0.35, -0.60),
    "gelatin_box": ( 0.60,  0.10),
    "meat_can":    ( 0.05, -0.20),
    "mustard":     ( 0.60, -0.65),
    "mug":         ( 1.30,  0.65),
    "mug2":        (-1.00, -0.45),
    "bowl":        ( 0.00,  0.30),
    "power_drill": ( 0.35,  0.50),
    "large_clamp": ( 0.80, -0.10),
    "wood_block":  (-0.65,  0.10),
}

# L4: 11 (object, arm) reach-but-not-grasp pairs (vs 7 in L1). Capability
# errors become maximally tempting, making the capability metric
# non-degenerate.
L4_CAPABILITY_TRAP = {
    "soup_can":    ( 0.60, -0.20),
    "banana":      (-0.05, -0.20),
    "gelatin_box": ( 1.05,  0.55),
    "meat_can":    (-0.10,  0.15),
    "mustard":     ( 1.05, -0.50),
    "mug":         ( 0.75, -0.40),
    "mug2":        ( 0.20,  0.10),
    "bowl":        (-0.45,  0.70),
    "power_drill": ( 0.50,  0.00),
    "large_clamp": (-0.55,  0.10),
    "wood_block":  (-0.35,  0.00),
}

# L5: work concentrated into few zones and routed through few pads, so zone
# locks and pad occupancy bind. M9 pad_wait is 0 in every episode so far,
# making it unreportable.
L5_CONTENTION = {
    "soup_can":    (-0.25,  0.00),
    "banana":      ( 0.25,  0.55),
    "gelatin_box": (-0.30,  0.45),
    "meat_can":    ( 0.70, -0.30),
    "mustard":     ( 0.75, -0.10),
    "mug":         ( 0.65, -0.70),
    "mug2":        ( 0.40, -0.10),
    "bowl":        ( 0.05, -0.25),
    "power_drill": ( 1.10, -0.35),
    "large_clamp": ( 0.55, -0.50),
    "wood_block":  ( 0.80, -0.50),
}


# L6: DECISION-RICH (2026-07-29). Designed against analysis/episode/episode_layout_audit.py,
# and hits the cell's structural ceiling: all four objects that CAN have two
# feasible arms do, median cost spread 213 ticks (above the ~160-tick
# makespan noise), 12 static traps.
#
# Only four objects have a choice because an arm must reach the BASKET too:
# food only by ur_w/franka_n, kitchenware only by ur_e/franka_n, tools only
# by ur_w/franka_s. Crossed with the grasp table, 7 of 11 objects are
# single-arm wherever placed. Raising that is a basket question.
#
# The traps follow from the timing model: a Franka's fixed per-leg cost
# (335.8 ticks) exceeds a UR's typical whole-task cost, so where both are
# feasible the UR is ALWAYS cheaper. A cost-minimising allocator thus always
# spends ur_w, the only arm that can finish meat_can, large_clamp and
# wood_block. Choosing the slower Franka to preserve ur_w is the scarcity
# judgement under study.
L6_DECISION_RICH = {
    "soup_can":    ( 0.10, -0.20),
    "banana":      ( 0.55,  0.10),
    "gelatin_box": (-0.40,  0.00),
    "meat_can":    (-0.65, -0.15),
    "mustard":     (-0.20,  0.25),
    "mug":         ( 0.85, -0.25),
    "mug2":        ( 0.30,  0.50),
    "bowl":        (-0.30,  0.45),
    "power_drill": ( 0.10,  0.20),
    "large_clamp": (-0.25, -0.45),
    "wood_block":  (-1.05, -0.35),
}


# L7: ABUNDANT-CHOICE (2026-07-29). Uses its own cast (see LAYOUT_CASTS),
# since the two-completing-arm objects had to be duplicated to build it.
#
# Mean feasible arms per object 1.80 against a structural ceiling of 2.00; 8
# of 10 tasks carry a genuine choice, vs 4 of 11 in L6 and 0 of 11 in
# designed. Median cost spread 324 ticks, twice the makespan noise floor.
#
# The 2.00 ceiling: each basket is reachable by exactly two arms, so no
# object can have more than two completing arms without moving a basket. The
# two mugs are ur_e-only and deliberately cast: ur_e delivers ONLY to
# kitchenware, and the registry has no small non-delicate kitchenware asset,
# so dropping them would silently reduce this to a three-arm cell.
#
# Purpose: the regime where choice is abundant and arms are busy. Tests
# whether availability, not capability, becomes the binding constraint once
# capability stops being one -- the question the buffer measurement could
# not answer on choice-poor layouts.
L7_ABUNDANT = {
    "soup_can":     (-0.35, -0.10),
    "soup_can2":    (-0.15, -0.20),
    "gelatin_box":  (-0.20,  0.05),
    "gelatin_box2": (-0.50,  0.05),
    "mustard":      (-0.70,  0.15),
    "power_drill":  (-0.35, -0.60),
    "power_drill2": (-0.70, -0.15),
    "power_drill3": (-0.25, -0.40),
    "mug":          ( 1.05,  0.55),
    "mug2":         ( 0.25, -0.55),
}

LAYOUTS = {
    "abundant":        L7_ABUNDANT,
    "decision_rich": L6_DECISION_RICH,
    "designed":        L1_DESIGNED,
    "balanced":        L2_BALANCED,
    "relay_heavy":     L3_RELAY_HEAVY,
    "capability_trap": L4_CAPABILITY_TRAP,
    "contention":      L5_CONTENTION,
}

# Measured profile, from analysis/layout_profile.py:
#
#   layout             relay  trap  legs  ur_w ur_e fr_s fr_n
#   designed               3     7    14     4    5    0    2
#   balanced               4     5    15     5    4    5    4
#   relay_heavy            7     5    18     2    7    2    3
#   capability_trap        4    11    15     3    6    3    2
#   contention             6     8    17     2    7    2    3
#
# relay = tasks with no single capable arm reaching object and basket
# trap  = (object, arm) pairs reachable but not graspable
# legs  = task records, 11 primaries plus one extra per relay
# per-arm columns = objects that arm may PICK (capable and in its annulus)

# ---------------------------------------------------------------------------
# Optional per-layout CASTS (2026-07-29).
#
# The runner normally casts list(YCB)[:--objects] (registry order). A layout
# listed here overrides that with its own object set -- which lets abundant
# use the duplicate registry entries. Layouts absent here are untouched.
# ---------------------------------------------------------------------------
LAYOUT_CASTS = {
    "abundant": [
        # 8 objects two arms can complete (choice), 2 to keep ur_e busy.
        # ur_e delivers only to kitchenware, so a cast without it would
        # silently turn this into a three-arm cell.
        "soup_can", "soup_can2", "gelatin_box", "gelatin_box2",   # food, 2 arms
        "mustard",                                                # food, 2 arms
        "power_drill", "power_drill2", "power_drill3",            # tools, 2 arms
        "mug", "mug2",                                            # kitchenware, ur_e
    ],

    # SET B (2026-08-18): second cast for the generalisation check, disjoint
    # from the default. bearing_pin and bracket_large were cut, see
    # ycb_objects. Absent from LAYOUTS on purpose, so positions come from
    # --seed; a designed layout would fix geometry as well as objects.
    "set_b": [
        "tuna_can", "sugar_box", "mac_n_cheese",          # food
        "foam_brick", "scissors", "bleach",               # kitchenware
        "bracket_small", "screw_99", "t_connector", "caster",   # tools
    ],
}


def cast_for(layout, default_cast):
    """Objects this layout spawns. Falls back to registry order."""
    return LAYOUT_CASTS.get(layout, default_cast)
