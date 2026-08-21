"""YCB object registry (step 2 of the YCB migration).

The single source of truth for the experiment's object cast. Everything
here traces to a source: sizes and rest heights were MEASURED in Isaac by
run_ycb_probe (upright pose); masses are the real product weights from the
YCB dataset (Calli et al. 2015), because the sim's auto-computed masses
assume solid volume; grasp widths are the measured minimum horizontal
dimension, EXCEPT the two authored exceptions flagged grasp_authored
(bounding boxes are conservative for non-convex shapes: the drill is
grasped by its handle, the bowl by its rim). The delicate flag marks
objects requiring force-controlled grasping (Franka-only), an authored
modelling attribute pending supervisor sign-off (proposal Q3).

Consumers: the scene builder (usd/variant/rot/rest_z), cell_config's
can_grasp via register_specs (grasp_m/mass_kg/delicate), the state builder
and oracle (category).
"""

YCB_PHYS = "Props/YCB/Axis_Aligned_Physics"
YCB_VIS = "Props/YCB/Axis_Aligned"
_UP_X = (0.7071, 0.7071, 0.0, 0.0)      # 90 deg about X: stands the
                                        # sideways-authored assets upright

YCB = {
    # ---- food -------------------------------------------------------------
    "soup_can": {
        "usd": "005_tomato_soup_can.usd", "variant": "physics",
        "category": "food", "grasp_m": 0.068, "grasp_authored": False,
        "mass_kg": 0.349, "rest_z": 0.032, "height": 0.068, "footprint_m": 0.066,
        "rot": None, "delicate": False,
    },
    "banana": {
        "usd": "011_banana.usd", "variant": "visual",
        "category": "food", "grasp_m": 0.039, "grasp_authored": False,
        "mass_kg": 0.236, "rest_z": 0.015, "height": 0.074, "footprint_m": 0.197,
        "rot": None, "delicate": True,       # Franka-only (proposal Q3)
    },
    "gelatin_box": {
        "usd": "009_gelatin_box.usd", "variant": "visual",
        "category": "food", "grasp_m": 0.073, "grasp_authored": False,
        "mass_kg": 0.176, "rest_z": 0.015, "height": 0.030, "footprint_m": 0.089,
        "rot": None, "delicate": False,
    },
    "meat_can": {
        "usd": "010_potted_meat_can.usd", "variant": "visual",
        "category": "food", "grasp_m": 0.084, "grasp_authored": False,
        "mass_kg": 0.407, "rest_z": 0.027, "height": 0.058, "footprint_m": 0.102,
        "rot": None, "delicate": False,      # 4 mm over Franka (Q1)
    },
    "mustard": {
        # Lies as authored (rot None): spawned upright it was knocked over
        # almost every run. Lying min_grasp is 0.096 (0.191 x 0.058 across),
        # over the Franka's 0.080 limit, so UR-only.
        "usd": "006_mustard_bottle.usd", "variant": "physics",
        "category": "food", "grasp_m": 0.096, "grasp_authored": False,
        "mass_kg": 0.603, "rest_z": 0.028, "height": 0.058, "footprint_m": 0.191,
        "rot": None, "delicate": False,      # no _UP_X: rests as authored
    },
    # ---- kitchenware -------------------------------------------------------
    "mug": {
        "usd": "025_mug.usd", "variant": "visual",
        "category": "kitchenware", "grasp_m": 0.081, "grasp_authored": False,
        "mass_kg": 0.493, "rest_z": 0.036, "height": 0.093, "footprint_m": 0.117,
        "rot": None, "delicate": False,      # 1 mm over Franka (Q1)
    },
    "mug2": {
        # Second mug: same asset/facts as "mug", own name and a blue tint so
        # the two stay distinguishable in the overhead image (condition V).
        "usd": "025_mug.usd", "variant": "visual",
        "category": "kitchenware", "grasp_m": 0.081, "grasp_authored": False,
        "mass_kg": 0.493, "rest_z": 0.036, "height": 0.093,
        "footprint_m": 0.117,
        "rot": None, "delicate": False,
        "tint": (0.15, 0.35, 0.85),
    },
    "bowl": {
        "usd": "024_bowl.usd", "variant": "visual",
        "category": "kitchenware", "grasp_m": 0.030, "grasp_authored": True,
        "mass_kg": 0.670, "rest_z": 0.025, "height": 0.055, "footprint_m": 0.161,
        "rot": _UP_X, "delicate": True    # thin-walled: compliant force-
                                          # controlled grasp, Franka-only,
                                          # rim grasp (Q2)
    },
    # ---- tools --------------------------------------------------------------
    "power_drill": {
        "usd": "035_power_drill.usd", "variant": "visual",
        "category": "tools", "grasp_m": 0.050, "grasp_authored": True,
        "mass_kg": 1.216, "rest_z": 0.025, "height": 0.057, "footprint_m": 0.187,
        "rot": None, "delicate": False,      # handle grasp (Q2)
    },
    "large_clamp": {
        "usd": "051_large_clamp.usd", "variant": "visual",
        "category": "tools", "grasp_m": 0.122, "grasp_authored": False,
        "mass_kg": 0.358, "rest_z": 0.018, "height": 0.036, "footprint_m": 0.165,
        "rot": None, "delicate": False,
    },
    "wood_block": {
        "usd": "036_wood_block.usd", "variant": "visual",
        "category": "tools", "grasp_m": 0.090, "grasp_authored": False,
        "mass_kg": 1.580, "rest_z": 0.045, "height": 0.091, "footprint_m": 0.206,
        "rot": None, "delicate": False,
    },

    # ---- duplicates for the abundant-choice layout (2026-07-29) ------------
    # soup_can, gelatin_box and power_drill are the only objects two arms can
    # COMPLETE (capable AND able to reach a basket); every other object is
    # single-arm. Duplicating these three is the only way to raise the mean
    # feasible-arm count with the current assets. Same USD and facts as the
    # original, only the scene key differs (as mug2 reuses 025_mug.usd).
    # Appended at the END: the runner casts list(YCB)[:--objects], so new
    # entries here cannot change which objects an existing layout spawns.
    "soup_can2": {
        "usd": "005_tomato_soup_can.usd", "variant": "physics",
        "category": "food", "grasp_m": 0.068, "grasp_authored": False,
        "mass_kg": 0.349, "rest_z": 0.032, "height": 0.068, "footprint_m": 0.066,
        "rot": None, "delicate": False,
        "tint": (0.90, 0.55, 0.10),   # distinguishable in condition V
    },
    "gelatin_box2": {
        "usd": "009_gelatin_box.usd", "variant": "visual",
        "category": "food", "grasp_m": 0.073, "grasp_authored": False,
        "mass_kg": 0.176, "rest_z": 0.015, "height": 0.030, "footprint_m": 0.089,
        "rot": None, "delicate": False,
        "tint": (0.55, 0.15, 0.60),
    },
    "power_drill2": {
        "usd": "035_power_drill.usd", "variant": "visual",
        "category": "tools", "grasp_m": 0.050, "grasp_authored": True,
        "mass_kg": 1.216, "rest_z": 0.025, "height": 0.057, "footprint_m": 0.187,
        "rot": None, "delicate": False,      # handle grasp (Q2)
        "tint": (0.10, 0.60, 0.55),
    },
    "power_drill3": {
        "usd": "035_power_drill.usd", "variant": "visual",
        "category": "tools", "grasp_m": 0.050, "grasp_authored": True,
        "mass_kg": 1.216, "rest_z": 0.025, "height": 0.057, "footprint_m": 0.187,
        "rot": None, "delicate": False,      # handle grasp (Q2)
        "tint": (0.85, 0.75, 0.15),
    },
    # ---- EX2 pose pairs (2026-08-02) ---------------------------------------
    # One object, two authored poses differing only in capability class (what
    # EX2 measures). All values from run_ycb_probe.py, 2026-08-02:
    #   mustard_lying     0.096 m across  ->  URs only   (over the 0.080 limit)
    #   mustard_upright   0.058 m across  ->  all four arms
    #   meat_can_flat     0.084 m across  ->  URs only
    #   meat_can_onedge   0.058 m across  ->  all four arms
    # Each carries a tint so the two poses are distinguishable in a frame.
    # The mustard pair is the primary: physics variant, a 16 mm straddle of
    # the limit (vs 4 mm), and lying-vs-standing reads more clearly overhead.
    "mustard_lying": {
        "usd": "006_mustard_bottle.usd", "variant": "physics",
        "category": "food", "grasp_m": 0.096, "grasp_authored": False,
        "mass_kg": 0.603, "rest_z": 0.028, "height": 0.058, "footprint_m": 0.191,
        "rot": None, "delicate": False,
        "tint": (0.95, 0.62, 0.02),   # TUPLE, not list: USD wants a GfVec3f;
                                      # a list silently leaves it untinted
    },
    "mustard_upright": {
        "usd": "006_mustard_bottle.usd", "variant": "physics",
        "category": "food", "grasp_m": 0.058, "grasp_authored": False,
        "mass_kg": 0.603, "rest_z": 0.096, "height": 0.191, "footprint_m": 0.096,
        "rot": _UP_X, "delicate": False,
        "tint": (0.95, 0.62, 0.02),   # TUPLE, not list (see mustard_lying)
    },
    "meat_can_flat": {
        "usd": "010_potted_meat_can.usd", "variant": "visual",
        "category": "food", "grasp_m": 0.084, "grasp_authored": False,
        "mass_kg": 0.407, "rest_z": 0.027, "height": 0.058, "footprint_m": 0.102,
        "rot": None, "delicate": False,
        "tint": (0.85, 0.30, 0.15),
    },
    "meat_can_onedge": {
        "usd": "010_potted_meat_can.usd", "variant": "visual",
        "category": "food", "grasp_m": 0.058, "grasp_authored": False,
        "mass_kg": 0.407, "rest_z": 0.041, "height": 0.084, "footprint_m": 0.102,
        "rot": _UP_X, "delicate": False,
        "tint": (0.85, 0.30, 0.15),
    },

    # ---- SET B, 2026-08-18 -----------------------------------------------
    # Second cast for the generalisation check, disjoint from cast A. All
    # values measured by run_ycb_probe; grasp_m is its min_grasp.
    # Split: 3 franka-only (delicate), 4 ur-only, 3 either, as in cast A.
    # A delicate object must be under 0.080 or no arm can take it.
    # Rejected: bearing_pin (rest_z below ground), bracket_large (mass
    # 17361 kg/m3), bolts/nuts/gears (all under 0.080, grasp never binds),
    # cracker_box (over both apertures), angled_connector (scale error).

    # food
    "tuna_can": {
        "usd": "007_tuna_fish_can.usd", "variant": "visual",
        "category": "food", "grasp_m": 0.034, "grasp_authored": False,
        "mass_kg": 0.177, "rest_z": 0.041, "height": 0.086,
        "footprint_m": 0.086, "rot": None, "delicate": False,
    },
    "sugar_box": {
        "usd": "004_sugar_box.usd", "variant": "physics",
        "category": "food", "grasp_m": 0.093, "grasp_authored": False,
        "mass_kg": 0.514, "rest_z": 0.021, "height": 0.045,
        "footprint_m": 0.176, "rot": None, "delicate": False,
    },
    "mac_n_cheese": {
        "usd": "mac_n_cheese_centered.usd", "variant": "visual",
        "folder": "Props/Food",
        "category": "food", "grasp_m": 0.093, "grasp_authored": False,
        "mass_kg": 0.586, "rest_z": 0.016, "height": 0.042,
        "footprint_m": 0.185, "rot": None, "delicate": False,
    },

    # kitchenware
    "foam_brick": {          # crushable foam, hence delicate
        "usd": "061_foam_brick.usd", "variant": "visual",
        "category": "kitchenware", "grasp_m": 0.051, "grasp_authored": False,
        "mass_kg": 0.194, "rest_z": 0.026, "height": 0.053,
        "footprint_m": 0.078, "rot": None, "delicate": True,
    },
    "scissors": {            # 0.091 is across the blades, not the handles
        "usd": "037_scissors.usd", "variant": "visual",
        "category": "kitchenware", "grasp_m": 0.091, "grasp_authored": False,
        "mass_kg": 0.121, "rest_z": 0.007, "height": 0.017,
        "footprint_m": 0.197, "rot": None, "delicate": False,
    },
    "bleach": {
        "usd": "021_bleach_cleanser.usd", "variant": "visual",
        "category": "kitchenware", "grasp_m": 0.102, "grasp_authored": False,
        "mass_kg": 0.964, "rest_z": 0.028, "height": 0.068,
        "footprint_m": 0.251, "rot": None, "delicate": False,
    },

    # tools
    "bracket_small": {
        "usd": "small_corner_bracket_physics.usd", "variant": "physics",
        "folder": "Props/Flip_Stack",
        "category": "tools", "grasp_m": 0.018, "grasp_authored": False,
        "mass_kg": 0.004, "rest_z": 0.006, "height": 0.018,
        "footprint_m": 0.018, "rot": None, "delicate": False,
    },
    "screw_99": {
        "usd": "screw_99_physics.usd", "variant": "physics",
        "folder": "Props/Flip_Stack",
        "category": "tools", "grasp_m": 0.025, "grasp_authored": False,
        "mass_kg": 0.010, "rest_z": 0.007, "height": 0.023,
        "footprint_m": 0.033, "rot": None, "delicate": False,
    },
    "t_connector": {         # 346 kg/m3: hollow, hence delicate
        "usd": "t_connector_physics.usd", "variant": "physics",
        "folder": "Props/Flip_Stack",
        "category": "tools", "grasp_m": 0.038, "grasp_authored": False,
        "mass_kg": 0.060, "rest_z": 0.012, "height": 0.040,
        "footprint_m": 0.114, "rot": None, "delicate": True,
    },
    "caster": {              # bearing surface, hence delicate
        "usd": "caster.usd", "variant": "visual",
        "folder": "Props/Flip_Stack",
        "category": "tools", "grasp_m": 0.037, "grasp_authored": False,
        "mass_kg": 0.156, "rest_z": 0.019, "height": 0.077,
        "footprint_m": 0.087, "rot": None, "delicate": True,
    },
}

CATEGORIES = ("food", "kitchenware", "tools")


def usd_path(name, nucleus_dir):
    """Resolved USD. An optional "folder" key overrides the YCB variant
    folders, so set_b can reach props outside Props/YCB."""
    spec = YCB[name]
    folder = spec.get("folder") or (
        YCB_PHYS if spec["variant"] == "physics" else YCB_VIS)
    return f"{nucleus_dir}/{folder}/{spec['usd']}"


def register_specs(object_specs, scene_name, ycb_name):
    """Write this object's capability and geometry facts into
    cell_config.OBJECT_SPECS under its scene name, so can_grasp, the state
    builder, and the executive's set-down see them."""
    s = YCB[ycb_name]
    object_specs[scene_name] = {"grasp_m": s["grasp_m"],
                                "mass_kg": s["mass_kg"],
                                "delicate": s["delicate"],
                                "rest_z": s["rest_z"],
                                "footprint_m": s["footprint_m"],
                                "height": s["height"],
                                "category": s["category"]}


def apply_physics_schemas(prim_path):
    """Apply RigidBodyAPI + convex-hull collision to a visual-only asset,
    i.e. what the _Physics variant ships pre-applied. Call after the scene
    is built and BEFORE sim.reset(). (Proven by run_ycb_probe.)"""
    from pxr import Usd, UsdGeom, UsdPhysics
    import omni.usd
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    UsdPhysics.RigidBodyAPI.Apply(prim)
    UsdPhysics.MassAPI.Apply(prim)
    for p in Usd.PrimRange(prim):
        if p.IsA(UsdGeom.Mesh):
            UsdPhysics.CollisionAPI.Apply(p)
            mesh_api = UsdPhysics.MeshCollisionAPI.Apply(p)
            mesh_api.CreateApproximationAttr("convexHull")