"""YCB sorting scene (step 3 of the YCB migration).

Three CATEGORY baskets (food / kitchenware / tools) replace the four
colour baskets, and the object pool is built from the ycb_objects
registry instead of coloured cubes.

Basket positions satisfy three constraints at once:
  1. each in its own corner lock zone (sorting streams never contend)
  2. each reachable by exactly one UR and one Franka (capability matters
     at delivery; verify against the measured rasters with
     zones.ZoneMap once on the server, like validate_pads)
  3. each MORE than CATCH_RADIUS from every exchange pad (the old colour
     layout had basket-pad separation of 0.158 m against a 0.16 m catch
     radius, a latent false-positive in scoring)
Deliberate asymmetry: with three baskets in four corners, franka_n serves
two baskets and franka_s one.

The delicate banana's basket (food, nw) is franka_n-reachable, and a
banana in franka_s territory has a legal all-Franka relay via the centre
pad, so delicate handovers exist in this scene.
"""

import math
import os
import sys

# This file lives in ycb/, one level below the core modules it imports.
# Put the parent folder on the import path so `import cell_config` works
# no matter who imports us (a run script here, or a test elsewhere).
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from core.cell import cell_config as C
from ycb_objects import YCB, CATEGORIES, usd_path, register_specs

# Safe pick annulus, learned the hard way: the flat raster blesses points
# the 3D IK cannot serve. Inner bound is PER ARM TYPE: the UR10 value is
# evidence (the pitcher at 0.24 m from ur_e's base entangled the arm with
# its own column); the Franka value is an assumption for a much smaller
# arm, to be revised if a Franka ever aborts close-in. Outer bound: margin
# against the reach edge, where the solver stalls past LOOSE_TOL.
PICK_INNER = {"ur10": 0.35, "franka": 0.25}
PICK_OUTER_FRAC = 0.92


def validate_layout(spawns, order):
    """Fail fast, BEFORE a 20-minute run: every object's pick point must
    lie in the safe annulus of at least one arm that can grasp it.
    NOTE: ARMS['pos'] is (x, y, z): index it, never 2-unpack it."""
    bad = []
    for (x, y), ycb_name in zip(spawns, order):
        ok = False
        for arm, spec in C.ARMS.items():
            d = math.hypot(x - spec["pos"][0], y - spec["pos"][1])
            inner = PICK_INNER[spec["type"]]
            outer = C.ARM_TYPES[spec["type"]]["reach"] * PICK_OUTER_FRAC
            if inner <= d <= outer and C.can_grasp(arm, f"ycb_{ycb_name}"):
                ok = True
                break
        if not ok:
            bad.append(f"{ycb_name} at ({x}, {y})")
        for arm, spec in C.ARMS.items():
            if math.hypot(x - spec["pos"][0],
                          y - spec["pos"][1]) < SPAWN_BASE_CLEAR:
                bad.append(f"{ycb_name} at ({x}, {y}) inside {arm}'s "
                           f"parked envelope (< {SPAWN_BASE_CLEAR} m "
                           f"from its base)")
    if bad:
        raise SystemExit(f"[ycb] LAYOUT INVALID: {bad}")
    print("[ycb] layout valid: every object in a capable arm's safe annulus")



BASKETS = {
    "basket_food":        {"pos": (-0.70, 0.50), "zone": "nw",
                           "rgb": (0.15, 0.65, 0.20),
                           "arms": ("ur_w", "franka_n")},
    "basket_kitchenware": {"pos": (0.70, 0.50), "zone": "ne",
                           "rgb": (0.15, 0.30, 0.80),
                           "arms": ("ur_e", "franka_n")},
    "basket_tools":       {"pos": (-0.70, -0.50), "zone": "sw",
                           "rgb": (0.45, 0.45, 0.50),
                           "arms": ("ur_w", "franka_s")},
}

CATEGORY_BASKET = {cat: f"basket_{cat}" for cat in CATEGORIES}
BASKET_SIZE = (2 * C.BASKET_WALL_HALF, 2 * C.BASKET_WALL_HALF, 0.008)
                                       # thin visual pad, no collision;
                                       # spans exactly to the wall centre
                                       # lines so tile and walls read as one
                                       # container (no bare-table ring)
CATCH_RADIUS = 0.16                    # scored as sorted if within this


def oracle_dest(category):
    """Ground-truth destination for a category (scoring truth, and the
    rule baseline's knowledge in oracle mode)."""
    return BASKETS[CATEGORY_BASKET[category]]["pos"]


def category_of(scene_name):
    """Category of a pooled object from its scene name (ycb_<registry>)."""
    return YCB[scene_name.removeprefix("ycb_")]["category"]


def verify_basket_capacity(scene_names):
    """Startup guarantee: every basket can physically hold its assigned
    objects with safe clearances, using the SAME search the executor uses
    at set-down. Discovering a full basket at runtime means a violent
    PhysX ejection; discovering it here costs one second and a clear
    error naming the object that does not fit."""
    from core.control.tasks import find_place_spot
    by_basket = {}
    for name in scene_names:
        spec = C.OBJECT_SPECS[name]
        by_basket.setdefault(spec["category"], []).append(
            (name, spec.get("footprint_m", 0.10) / 2))
    for cat, items in by_basket.items():
        placed = []
        # worst case first: placing the widest late is the hard order
        for name, halfw in sorted(items, key=lambda t: -t[1]):
            dx, dy, ok = find_place_spot(halfw, placed)
            if not ok:
                raise ValueError(
                    f"[ycb] basket capacity: {name} (footprint "
                    f"{halfw*2:.3f} m) cannot fit in the {cat} basket with "
                    f"{[n for n, _ in items if n != name]}; grow "
                    f"BASKET_WALL_HALF or reassign objects")
            placed.append((dx, dy, halfw))
        print(f"[ycb] basket capacity OK: {cat} holds "
              f"{len(items)} objects with clearance", flush=True)


def add_baskets(scene_cfg):
    """Attach the three basket pads. Visual only: no collision, so the
    kinematic set-down physics is unchanged."""
    import isaaclab.sim as sim_utils
    from isaaclab.assets import AssetBaseCfg
    from core.cell.scene_cfg import add_basket_walls
    for name, spec in BASKETS.items():
        x, y = spec["pos"]
        add_basket_walls(scene_cfg, name, x, y,   # real containment; walls
                         rgb=spec["rgb"])         # in the category colour so
                                                  # the basket reads as one
                                                  # coloured container
        setattr(scene_cfg, name, AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/" + name,
            init_state=AssetBaseCfg.InitialStateCfg(
                pos=(x, y, C.TABLE_H + BASKET_SIZE[2] / 2)),
            spawn=sim_utils.CuboidCfg(
                size=BASKET_SIZE,
                visual_material=sim_utils.PreviewSurfaceCfg(
                    diffuse_color=spec["rgb"]),
            ),
        ))
    return list(BASKETS)


def add_ycb_pool(scene_cfg, cast=None):
    """Attach the YCB object pool (parked off-table) from the registry.
    Returns (scene_names, needs_schema): apply_physics_schemas must be
    called for every name in needs_schema after the scene is built and
    BEFORE sim.reset(). Also registers every object's capability and
    geometry facts into cell_config.OBJECT_SPECS."""
    import isaaclab.sim as sim_utils
    from isaaclab.assets import RigidObjectCfg
    from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR
    names, needs_schema = [], []
    for i, ycb_name in enumerate(cast or list(YCB)):
        spec = YCB[ycb_name]
        scene_name = f"ycb_{ycb_name}"
        park = (C.PARK_POS[0] + 0.35 * i, C.PARK_POS[1], C.PARK_POS[2])
        setattr(scene_cfg, scene_name, RigidObjectCfg(
            prim_path="{ENV_REGEX_NS}/" + scene_name,
            spawn=sim_utils.UsdFileCfg(
                usd_path=usd_path(ycb_name, ISAAC_NUCLEUS_DIR),
                rigid_props=(sim_utils.RigidBodyPropertiesCfg()
                             if spec["variant"] == "physics" else None),
                collision_props=(sim_utils.CollisionPropertiesCfg()
                                 if spec["variant"] == "physics" else None),
                mass_props=None,        # masses authored in the registry
                # optional per-object colour override ("tint" in the
                # registry): keeps duplicated assets distinguishable in
                # the overhead image (condition V)
                visual_material=(sim_utils.PreviewSurfaceCfg(
                    diffuse_color=spec["tint"])
                    if spec.get("tint") else None),
                visual_material_path=("material_override"
                                      if spec.get("tint") else "material"),
            ),
            init_state=RigidObjectCfg.InitialStateCfg(
                pos=park,
                rot=spec["rot"] or (1.0, 0.0, 0.0, 0.0)),
        ))
        register_specs(C.OBJECT_SPECS, scene_name, ycb_name)
        names.append(scene_name)
        if spec["variant"] != "physics":
            needs_schema.append(scene_name)
    return names, needs_schema


def spawn_specs():
    """Per-object spawn poses for the DisruptionEngine: true rest height
    (slightly above, to settle) and the upright rotation."""
    out = {}
    for ycb_name, spec in YCB.items():
        out[f"ycb_{ycb_name}"] = {
            "z": C.TABLE_H + spec["rest_z"] + 0.005,
            "rot": spec["rot"],
        }
    return out


# ---------------------------------------------------------------------------
# Layout generation. A spawn position is a fact about an EPISODE, not about
# an object, so it never lives in the registry: adding an object to the cast
# is a registry edit only, and every layout accommodates it automatically.
# The seeded sampler is also the seeded-worlds generator the experiment
# matrix needs (N seeds = N layouts of the same cast).
# ---------------------------------------------------------------------------

SPAWN_X = (-0.92, 0.92)                # sampling bounds on the table
SPAWN_Y = (-0.58, 0.58)
SPAWN_SPACING = 0.25                   # min distance between objects
SPAWN_PAD_CLEAR = C.PAD_SKIP_RADIUS + 0.05
SPAWN_BASE_CLEAR = 0.25                # min distance from every ARM BASE,
                                       # calibrated to the Franka pick
                                       # annulus inner bound (0.25): any
                                       # object a Franka may legitimately
                                       # pick is outside its parked fold
                                       # by construction. Evidence: the
                                       # wood at 0.21 m was swept into the
                                       # dead zone; spawns at 0.30 have
                                       # survived every run.
                                       # a parked, folded robot occupies a
                                       # volume around its own base, and an
                                       # object inside it gets nudged into
                                       # the dead zone no arm can serve
                                       # (the wood block spawned 0.21 m
                                       # from franka_s, was swept under it,
                                       # and FAILED, 2026-07-19 run)
# Basket clearance is per-object and wall-aware: the walls extend
# C.BASKET_WALL_HALF from the basket centre, and the OBJECT extends its
# half footprint from its spawn point, so the spawn point must clear
# wall_half + footprint/2 (+ 2 cm air). The old constant (CATCH + 0.05 =
# 0.21) predated the walls and could seed the wood block overlapping a
# wall by 11 cm, a guaranteed ejection at tick zero.
_SAMPLE_TRIES = 800                    # per object, before declaring the
                                       # seed infeasible for this cast


def check_cast_baskets(names):
    """A cast whose category has no basket must die loudly at startup:
    a NEW category is the one case that legitimately needs a scene edit
    (someone must decide where its basket goes)."""
    missing = sorted({YCB[n]["category"] for n in names}
                     - set(CATEGORY_BASKET))
    if missing:
        raise SystemExit(f"[ycb] no basket exists for categories {missing}; "
                         f"add them to BASKETS in ycb_scene.py")


def _spot_ok(x, y, ycb_name, placed):
    if any(math.hypot(x - px, y - py) < SPAWN_SPACING for px, py in placed):
        return False
    if any(math.hypot(x - p["pos"][0], y - p["pos"][1]) <= SPAWN_PAD_CLEAR
           for p in C.EXCHANGE_PADS.values()):
        return False
    if any(math.hypot(x - a["pos"][0], y - a["pos"][1]) < SPAWN_BASE_CLEAR
           for a in C.ARMS.values()):
        return False
    basket_clear = (C.BASKET_WALL_HALF + YCB[ycb_name]["footprint_m"] / 2
                    + 0.02)
    if any(math.hypot(x - b["pos"][0], y - b["pos"][1]) <= basket_clear
           for b in BASKETS.values()):
        return False
    for arm, spec in C.ARMS.items():       # safe annulus of a CAPABLE arm;
        d = math.hypot(x - spec["pos"][0], y - spec["pos"][1])
        inner = PICK_INNER[spec["type"]]   # can_grasp handles size, mass,
        outer = C.ARM_TYPES[spec["type"]]["reach"] * PICK_OUTER_FRAC
        if inner <= d <= outer and C.can_grasp(arm, f"ycb_{ycb_name}"):
            return True                    # and the delicate flag
    return False


def sample_layout(names, seed, designed=None):
    """Positions for the cast, in the given order. Objects named in
    `designed` keep their hand-placed spot (validated); the rest are
    rejection-sampled deterministically from the seed under every layout
    constraint. Registers specs first, since capability drives placement."""
    import random
    for n in names:
        register_specs(C.OBJECT_SPECS, f"ycb_{n}", n)
    check_cast_baskets(names)
    rng = random.Random(seed)
    designed = designed or {}
    placed, out = [], []
    for n in names:                        # fixed spots first, then sampled
        if n in designed:
            x, y = designed[n]
            placed.append((x, y))
    for n in names:
        if n in designed:
            out.append(designed[n])
            continue
        for _ in range(_SAMPLE_TRIES):
            x = round(rng.uniform(*SPAWN_X), 2)
            y = round(rng.uniform(*SPAWN_Y), 2)
            if _spot_ok(x, y, n, placed):
                placed.append((x, y))
                out.append((x, y))
                break
        else:
            raise SystemExit(f"[ycb] seed {seed}: no feasible spot for "
                             f"{n} after {_SAMPLE_TRIES} tries")
    return out