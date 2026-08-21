"""YCB probe (step 0 of the YCB migration).

Verifies which YCB assets exist on this machine's asset server, in which
variant, and MEASURES each loadable candidate: bounding box, footprint,
rest height, and mass. Prints a ready-to-paste OBJECT_SPECS block.

Asset resolution, per candidate:
  1. Axis_Aligned_Physics/<file>  (RigidBodyAPI pre-applied by NVIDIA)
  2. Axis_Aligned/<file>          (visual-only: we APPLY the physics
     schemas ourselves after the scene is built, before sim.reset())
  3. neither -> reported missing and skipped
The schema application in (2) is the same mechanism the real scene config
will use later, so this probe also rehearses step 3's machinery.

NOTE on mass: schema-applied objects get an auto-computed mass (volume x
default density), which is physically wrong for hollow things. Real
masses are authored in the object registry (step 2); the probe's mass
column just shows what is authored vs computed.

Run:  python3 run_ycb_probe.py --headless
Then inspect out/ycb_probe.png.
"""

import os
import sys

# This script lives in ycb/, one level below the core modules. Put the
# parent folder on the import path so core imports resolve when launched
# as `python3 ycb/run_ycb_*.py` from the project root (or from anywhere).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import os                                              # noqa: E402
import numpy as np                                     # noqa: E402
import isaaclab.sim as sim_utils                       # noqa: E402
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg  # noqa: E402
from isaaclab.scene import InteractiveScene, InteractiveSceneCfg  # noqa: E402
from isaaclab.sensors import TiledCameraCfg            # noqa: E402
from isaaclab.utils import configclass                 # noqa: E402
from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR, check_file_path  # noqa: E402

YCB_PHYS = f"{ISAAC_NUCLEUS_DIR}/Props/YCB/Axis_Aligned_Physics"
YCB_VIS = f"{ISAAC_NUCLEUS_DIR}/Props/YCB/Axis_Aligned"
# Everything under Props that is NOT the YCB grocery set. A candidate whose
# value contains a slash is resolved here instead of under the two YCB
# folders, so non-YCB props can be screened by the same machinery.
PROPS = f"{ISAAC_NUCLEUS_DIR}/Props"

# Props that ALREADY carry RigidBodyAPI on a nested prim, so the probe must
# NOT apply schemas on top. Measured the hard way on 2026-08-18: the first
# run applied schemas to everything not named *_physics.usd, which put a
# second rigid body on the PARENT of the asset's own one, and Isaac refused
# the scene with "Failed to find a single rigid body ... Found multiple
# [probe_21, probe_21/factory_bolt]".
#
# Filename is not a reliable signal here: Flip_Stack ships bearing_pin.usd
# and caster.usd as genuinely visual-only and they need the schemas, while
# every Factory asset and the beaker are pre-rigged. So the rule is by
# location, which is what actually varies.
ALREADY_RIGID = ("Factory/", "Beaker/")

# Candidate objects, PROVISIONAL until the supervisor discussion. The cast
# spans both experiment axes: semantic category (food/kitchenware/tool) and
# capability (Franka-graspable vs expected UR-only). cracker_box is kept as
# an instructive flag: expected to settle with min_grasp > 0.14 (graspable
# by NOBODY).
CANDIDATES = {
    # food
    "soup_can":     "005_tomato_soup_can.usd",
    "banana":       "011_banana.usd",
    "gelatin_box":  "009_gelatin_box.usd",
    "meat_can":     "010_potted_meat_can.usd",
    # kitchenware
    "mug":          "025_mug.usd",
    "bowl":         "024_bowl.usd",
    "pitcher":      "019_pitcher_base.usd",
    # tools
    "power_drill":  "035_power_drill.usd",
    "large_clamp":  "051_large_clamp.usd",
    "wood_block":   "036_wood_block.usd",
    # substitutes / instructive flags
    "cracker_box":  "003_cracker_box.usd",
    # ---- pitcher-replacement candidates, added 2026-07-19 ----------------
    # The spoon proved MISSING from the Isaac-packaged YCB subset, so this
    # screens every plausible alternative in one run. Existence + measured
    # geometry decide the shortlist; the pick is wired in afterwards.
    "spoon":        "031_spoon.usd",       # known MISSING; kept to confirm
    "foam_brick":   "061_foam_brick.usd",  # 'kitchen sponge': small, soft,
                                           # the most natural delicate item
    "scissors":     "037_scissors.usd",    # kitchen scissors: thin, distinct
    "tuna_can":     "007_tuna_fish_can.usd",   # small flat can (food-side)
    "sugar_box":    "004_sugar_box.usd",       # slim box (food-side)
    "bleach":       "021_bleach_cleanser.usd", # tall bottle: screened for
                                           # completeness, advised against
                                           # (the pitcher problem reborn)
    "mustard":      "006_mustard_bottle.usd",
    # ---- shared-band kitchenware candidates, added 2026-08-02 ------------
    # The cell has no kitchenware object a Franka can grasp: mug and mug2
    # are 0.081 m against the Franka's 0.080 limit, and the bowl is
    # delicate. Measured consequence: of 15 registry objects only 4 can
    # ever have two feasible arms, and ur_w is the cheapest arm for all of
    # them at every legal position, because food and tools both route to
    # ur_w and only kitchenware routes to ur_e. So "pick the cheapest arm"
    # is a lookup rather than a decision, which is what made L7 abundant
    # run two to four times slower than L6.
    #
    # What is needed is ONE kitchenware object under 0.080 m and not
    # delicate. Then it gets replicated, as soup_can2 and power_drill2 were.
    # Screened on existence and measurement, not on assumption: 031_spoon
    # was already found missing from the Isaac-packaged subset, so
    # plausibility is not evidence of availability.
    # ---- EX2 pose pairs, added 2026-08-02 --------------------------------
    # EX2 needs one object whose CAPABILITY CLASS changes with pose: over
    # the Franka's 0.080 m limit in one orientation, under it in the other.
    # The same USD is probed twice under different rotations, and the two
    # measurements decide which object carries the experiment.
    #
    # mustard was the assumed candidate on the strength of a code comment
    # saying 8.6 cm standing against 5.8 cm lying. The comment refers to a
    # different axis: the probe already spawns it rotated and reports
    # min_grasp 0.058, the same as the lying registry row. So the flip may
    # not exist. Measured here rather than argued about.
    #
    # meat_can is the better candidate on its measured box, 0.102 x 0.084 x
    # 0.058. As authored the narrow horizontal axis is 0.084, four
    # millimetres OVER the Franka limit, which the registry already flags
    # (Q1). Rotated 90 degrees about X the narrow axis should become 0.058,
    # comfortably under. That inference is from the bounding box, NOT a
    # measurement, which is why it is probed before it becomes a registry
    # row.
    "mustard_lying":    "006_mustard_bottle.usd",   # as authored
    "mustard_upright":  "006_mustard_bottle.usd",   # rotated, see UPRIGHT
    "meat_can_flat":    "010_potted_meat_can.usd",  # as authored
    "meat_can_onedge":  "010_potted_meat_can.usd",  # rotated, see UPRIGHT
    "cup_small":    "065-b_cups.usd",      # nesting cups: the most natural
    "cup_medium":   "065-d_cups.usd",      # small kitchenware in the set

    # ---- NON-YCB props, added 2026-08-18 ---------------------------------
    # A second object set for the generalisation check EX1 needs. The point
    # is NOT visual difference: EX1 runs text-only, so the model never sees
    # a render and only the NAME and the width matter. The point is that
    # every object in the current set is a household grocery, a category
    # these models have very strong priors about. Industrial fasteners test
    # whether the width fallback measured at L3-nowidth depends on the
    # objects being familiar household items at all.
    #
    # The M-numbers also give a width ladder BY CONSTRUCTION rather than by
    # luck: an M20 head is wider than an M4. If the fallback is a general
    # size prior it should order these correctly; if it was grocery-specific
    # knowledge it should not.
    #
    # Paths are relative to Props. Folder layout confirmed as
    # Factory/<name>/<name>.usd; the gear paths are INFERRED from that
    # pattern and will simply report MISSING if wrong, which is what this
    # screen is for.
    "bolt_m4":      "Factory/factory_bolt_m4_tight/factory_bolt_m4_tight.usd",
    "bolt_m8":      "Factory/factory_bolt_m8_tight/factory_bolt_m8_tight.usd",
    "bolt_m12":     "Factory/factory_bolt_m12_tight/factory_bolt_m12_tight.usd",
    "bolt_m16":     "Factory/factory_bolt_m16_tight/factory_bolt_m16_tight.usd",
    "bolt_m20":     "Factory/factory_bolt_m20_tight/factory_bolt_m20_tight.usd",
    "nut_m4":       "Factory/factory_nut_m4_tight/factory_nut_m4_tight.usd",
    "nut_m8":       "Factory/factory_nut_m8_tight/factory_nut_m8_tight.usd",
    "nut_m12":      "Factory/factory_nut_m12_tight/factory_nut_m12_tight.usd",
    "nut_m16":      "Factory/factory_nut_m16_tight/factory_nut_m16_tight.usd",
    "nut_m20":      "Factory/factory_nut_m20_tight/factory_nut_m20_tight.usd",
    "gear_small":   "Factory/gear_assets/factory_gear_small/factory_gear_small.usd",
    "gear_medium":  "Factory/gear_assets/factory_gear_medium/factory_gear_medium.usd",
    "gear_large":   "Factory/gear_assets/factory_gear_large/factory_gear_large.usd",
    # Flip_Stack ships _physics variants for several parts, so those resolve
    # without schema application.
    "bracket_large": "Flip_Stack/large_corner_bracket_physics.usd",
    "bracket_small": "Flip_Stack/small_corner_bracket_physics.usd",
    "t_connector":  "Flip_Stack/t_connector_physics.usd",
    "screw_95":     "Flip_Stack/screw_95_physics.usd",
    "bearing_pin":  "Flip_Stack/bearing_pin.usd",
    "caster":       "Flip_Stack/caster.usd",
    "angled_connector": "Flip_Stack/angled_connector.usd",
    # Single props worth one measurement each.
    "rubiks_cube":  "Rubiks_Cube/rubiks_cube.usd",
    "beaker":       "Beaker/beaker_500ml.usd",
    "nvidia_cube":  "Blocks/nvidia_cube.usd",
    "mac_n_cheese": "Food/mac_n_cheese_centered.usd",
    "klt_bin":      "KLT_Bin/small_KLT.usd",

    # ---- EX2 pose pairs in the industrial set -----------------------------
    # EX2 needs ONE object whose CAPABILITY CLASS changes with pose: over
    # the Franka's 0.080 m limit in one orientation and under it in the
    # other. In the grocery set that object is the mustard bottle, and the
    # supervisor has asked for EX2 to be repeated on something else.
    #
    # A gear is the natural candidate: lying flat it is grasped across its
    # diameter, on edge across its thickness, and those two numbers are far
    # apart. Brackets and the T-connector have the same property for the
    # same reason. Whether either pair actually straddles 0.080 is a
    # measurement, not an assumption, which is what these rows are for.
    # Only the *_onedge member is rotated; its partner is probed as
    # authored, so one pair of rows gives both poses of one asset.
    "gear_large_flat":   "Factory/gear_assets/factory_gear_large/factory_gear_large.usd",
    "gear_large_onedge": "Factory/gear_assets/factory_gear_large/factory_gear_large.usd",
    "gear_medium_flat":   "Factory/gear_assets/factory_gear_medium/factory_gear_medium.usd",
    "gear_medium_onedge": "Factory/gear_assets/factory_gear_medium/factory_gear_medium.usd",
    "bracket_large_flat":   "Flip_Stack/large_corner_bracket_physics.usd",
    "bracket_large_onedge": "Flip_Stack/large_corner_bracket_physics.usd",
    "t_connector_flat":   "Flip_Stack/t_connector_physics.usd",
    "t_connector_onedge": "Flip_Stack/t_connector_physics.usd",

    # ---- EX3 headroom: the loose fastener variants ------------------------
    # EX3 now varies task DIFFICULTY, and its first axis is object count:
    # 30, 40, 50, 60 objects against the current 11. That needs distinct
    # spawnable assets, and it needs them SMALL: eleven groceries already
    # fill a 2.8 x 1.6 m table once basket capacity and placement clearance
    # are respected, and verify_basket_capacity refuses a cast that cannot
    # physically fit. Fasteners are one to two centimetres across, so sixty
    # of them is a crowded table rather than an impossible one, and clutter
    # becomes a variable that can actually be turned up.
    #
    # The loose variants double the fastener pool at no modelling cost.
    "bolt_m4_loose":  "Factory/factory_bolt_m4_loose/factory_bolt_m4_loose.usd",
    "bolt_m8_loose":  "Factory/factory_bolt_m8_loose/factory_bolt_m8_loose.usd",
    "bolt_m12_loose": "Factory/factory_bolt_m12_loose/factory_bolt_m12_loose.usd",
    "bolt_m16_loose": "Factory/factory_bolt_m16_loose/factory_bolt_m16_loose.usd",
    "bolt_m20_loose": "Factory/factory_bolt_m20_loose/factory_bolt_m20_loose.usd",
    "nut_m4_loose":   "Factory/factory_nut_m4_loose/factory_nut_m4_loose.usd",
    "nut_m8_loose":   "Factory/factory_nut_m8_loose/factory_nut_m8_loose.usd",
    "nut_m12_loose":  "Factory/factory_nut_m12_loose/factory_nut_m12_loose.usd",
    "nut_m16_loose":  "Factory/factory_nut_m16_loose/factory_nut_m16_loose.usd",
    "nut_m20_loose":  "Factory/factory_nut_m20_loose/factory_nut_m20_loose.usd",
    "gear_base":      "Factory/gear_assets/factory_gear_base/factory_gear_base.usd",
    "screw_99":       "Flip_Stack/screw_99_physics.usd",
    "caster_bearing": "Flip_Stack/caster_bearing.usd",
    "cup_large":    "065-f_cups.usd",
    "sponge":       "026_sponge.usd",      # soft, thin, clearly kitchenware
    "plate":        "029_plate.usd",       # flat: likely ungraspable
                                           # top-down, screened to confirm
    "fork":         "030_fork.usd",        # utensils: thin. If they load,
    "knife":        "032_knife.usd",       # the grasp width will be tiny
    "spatula":      "033_spatula.usd",     # and the concern is whether the
                                           # kinematic grasp holds them
    "windex":       "022_windex_bottle.usd",   # tall bottle: advised
                                           # against (the pitcher problem)
                                           # but cheap to measure
}
PER_ROW = 6
SPACING = 0.35
ROW_GAP = 0.60
DROP_Z = 0.15   # low enough not to tumble, high enough that rotated
                # objects (whose extent below the root changes with the
                # rotation) cannot start inside the ground

# Upright corrections: these assets are AUTHORED lying on their side (the
# identical measurements at 0.30 and 0.02 drop heights prove the poses come
# from the files, not from falling). A 90-degree rotation about X converts
# each measured lying box into its upright box. Quaternions are (w,x,y,z).
UPRIGHT = {
    # EX2 pose pairs: only the *_upright / *_onedge members are rotated,
    # their partners are probed exactly as authored, so one pair of rows
    # gives both poses of the same asset.
    "mustard_upright": (0.7071, 0.7071, 0.0, 0.0),
    "meat_can_onedge": (0.7071, 0.7071, 0.0, 0.0),
    # Industrial pose pairs, screened for an EX2 replacement object.
    "gear_large_onedge":    (0.7071, 0.7071, 0.0, 0.0),
    "gear_medium_onedge":   (0.7071, 0.7071, 0.0, 0.0),
    "bracket_large_onedge": (0.7071, 0.7071, 0.0, 0.0),
    "t_connector_onedge":   (0.7071, 0.7071, 0.0, 0.0),
    "mustard": (0.7071, 0.7071, 0.0, 0.0),
    "bowl":    (0.7071, 0.7071, 0.0, 0.0),
    "pitcher": (0.7071, 0.7071, 0.0, 0.0),
}


def resolve_assets():
    """(resolved name->path, names needing manual schemas, missing names)."""
    resolved, needs_schema, missing = {}, [], []
    for name, fn in CANDIDATES.items():
        if "/" in fn:
            # Non-YCB prop, given as a path relative to Props. These ship a
            # single USD with no physics/visual split, so the schema question
            # is decided by whether the file carries RigidBodyAPI already.
            # The probe applies schemas to anything not named *_physics,
            # which is the same conservative rule the YCB visual path uses:
            # applying twice is an error, applying to an already-rigid prim
            # is not, so the cost of guessing wrong here is a loud failure
            # rather than a silent bad measurement.
            p = f"{PROPS}/{fn}"
            if check_file_path(p):
                resolved[name] = p
                pre_rigged = (fn.endswith("_physics.usd")
                              or fn.startswith(ALREADY_RIGID))
                if not pre_rigged:
                    needs_schema.append(name)
            else:
                missing.append(name)
            continue
        p_phys, p_vis = f"{YCB_PHYS}/{fn}", f"{YCB_VIS}/{fn}"
        if check_file_path(p_phys):
            resolved[name] = p_phys
        elif check_file_path(p_vis):
            resolved[name] = p_vis
            needs_schema.append(name)
        else:
            missing.append(name)
    print("\n[probe] asset resolution:")
    for name in CANDIDATES:
        if name in missing:
            status = "MISSING in both variants"
        elif name in needs_schema:
            status = "visual-only (schemas applied by probe)"
        elif "/" in CANDIDATES[name] and not CANDIDATES[name].endswith(
                "_physics.usd"):
            status = "pre-rigged prop (schemas NOT applied)"
        else:
            status = "physics variant"
        print(f"  {name:>12}: {status}")
    return resolved, needs_schema, missing


def _object_cfg(name, usd_path, i, with_props):
    x = (i % PER_ROW) * SPACING
    y = (i // PER_ROW) * ROW_GAP - ROW_GAP / 2
    # The Factory props are authored for ASSEMBLY tasks, so each one carries
    # an articulation root. RigidObject refuses those outright ("Found an
    # articulation root when resolving ..."), and Isaac's own error names
    # the remedy: disable the root at spawn. These are measured as single
    # rigid bodies here because that is what they are on a sorting table;
    # nothing in this project screws a bolt into anything.
    #
    # Applied to every NON-YCB prop rather than to a hand-kept list: it is
    # harmless on an asset that has no articulation root, and the Flip_Stack
    # _physics variants may carry one too. The YCB groceries are excluded
    # because they are known single bodies and because nothing about their
    # spawn should change from the run that produced the current registry.
    non_ycb = "/Props/YCB/" not in usd_path
    return RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/" + f"probe_{i:02d}",
        spawn=sim_utils.UsdFileCfg(
            usd_path=usd_path,
            # modify props only where the API already exists (physics
            # variant); visual-only assets get schemas applied manually.
            rigid_props=(sim_utils.RigidBodyPropertiesCfg()
                         if with_props else None),
            collision_props=(sim_utils.CollisionPropertiesCfg()
                             if with_props else None),
            articulation_props=(
                sim_utils.ArticulationRootPropertiesCfg(
                    articulation_enabled=False)
                if non_ycb else None),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(x, y, DROP_Z),
            rot=UPRIGHT.get(name, (1.0, 0.0, 0.0, 0.0))),
    )


def apply_physics_schemas(prim_path):
    """Apply RigidBodyAPI to the root and convex-hull collision to every
    mesh, i.e. exactly what the _Physics variant ships pre-applied."""
    from pxr import Usd, UsdGeom, UsdPhysics
    import omni.usd
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    UsdPhysics.RigidBodyAPI.Apply(prim)
    UsdPhysics.MassAPI.Apply(prim)         # mass auto-computed from volume
    for p in Usd.PrimRange(prim):
        if p.IsA(UsdGeom.Mesh):
            UsdPhysics.CollisionAPI.Apply(p)
            mesh_api = UsdPhysics.MeshCollisionAPI.Apply(p)
            mesh_api.CreateApproximationAttr("convexHull")


@configclass
class ProbeSceneCfg(InteractiveSceneCfg):
    ground = AssetBaseCfg(prim_path="/World/ground",
                          spawn=sim_utils.GroundPlaneCfg())
    light = AssetBaseCfg(
        prim_path="/World/Light",
        spawn=sim_utils.DomeLightCfg(intensity=3000.0, color=(0.9, 0.9, 0.9)),
    )
    probe_cam = TiledCameraCfg(
        prim_path="{ENV_REGEX_NS}/probe_cam",
        offset=TiledCameraCfg.OffsetCfg(
            pos=((PER_ROW - 1) * SPACING / 2, 0.0, 4.0),
            rot=(0.7071, 0.0, 0.7071, 0.0), convention="world"),
        data_types=["rgb"],
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=24.0, focus_distance=400.0,
            horizontal_aperture=20.955, clipping_range=(0.1, 20.0)),
        width=1280, height=720,
    )


def measure(scene, key, prim_path):
    """Measured facts about a settled object: AABB size, rest z, mass."""
    from pxr import Usd, UsdGeom
    import omni.usd
    stage = omni.usd.get_context().get_stage()
    prim = stage.GetPrimAtPath(prim_path)
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                              ["default", "render"], useExtentsHint=False)
    box = cache.ComputeWorldBound(prim).ComputeAlignedRange()
    size = box.GetSize()
    obj = scene[key]
    pos = obj.data.root_pos_w[0]
    mass = float(obj.root_physx_view.get_masses()[0].sum())
    return {
        "size": (float(size[0]), float(size[1]), float(size[2])),
        "rest_z": float(pos[2]),
        "top_z": float(box.GetMax()[2]),
        "mass_kg": mass,
    }


def main():
    resolved, needs_schema, missing = resolve_assets()
    if not resolved:
        print("[probe] nothing loadable; check network access to the "
              "asset server and the paths above")
        simulation_app.close()
        return

    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=1.0 / 120.0))
    cfg = ProbeSceneCfg(num_envs=1, env_spacing=20.0)
    order = list(resolved)                  # index -> candidate name
    for i, name in enumerate(order):
        setattr(cfg, f"probe_{i:02d}",
                _object_cfg(name, resolved[name], i, name not in needs_schema))
    scene = InteractiveScene(cfg)

    # visual-only assets: apply the physics schemas BEFORE sim.reset(),
    # which is when Isaac Lab checks for the RigidBodyAPI
    for i, name in enumerate(order):
        if name in needs_schema:
            apply_physics_schemas(f"/World/envs/env_0/probe_{i:02d}")
    sim.reset()

    for _ in range(360):                    # fall and settle
        scene.write_data_to_sim()
        sim.step(render=False)
        scene.update(sim.get_physics_dt())

    print("\n[probe] measured object facts (settled on the ground plane):")
    print(f"{'name':>12}  {'size x*y*z (m)':>22}  {'min_grasp':>9}  "
          f"{'rest_z':>7}  {'top_z':>6}  {'mass':>7}  mass source")
    specs = {}
    for i, name in enumerate(order):
        m = measure(scene, f"probe_{i:02d}", f"/World/envs/env_0/probe_{i:02d}")
        sx, sy, sz = m["size"]
        min_grasp = min(sx, sy)
        src = "computed" if name in needs_schema else "authored"
        specs[name] = {"grasp_m": round(min_grasp, 3),
                       "mass_kg": round(m["mass_kg"], 3),
                       "rest_z": round(m["rest_z"], 3),
                       "height": round(sz, 3)}
        print(f"{name:>12}  {sx:6.3f}*{sy:6.3f}*{sz:6.3f}   {min_grasp:9.3f}"
              f"  {m['rest_z']:7.3f}  {m['top_z']:6.3f}  {m['mass_kg']:7.3f}"
              f"  {src}")
    if missing:
        print(f"\n[probe] missing entirely: {missing}")

    print("\n[probe] paste-ready OBJECT_SPECS entries "
          "(rest_z is on the GROUND; add TABLE_H on the table):")
    for name, s in specs.items():
        print(f'    "{name}": {{"grasp_m": {s["grasp_m"]}, '
              f'"mass_kg": {s["mass_kg"]}, "rest_z": {s["rest_z"]}, '
              f'"height": {s["height"]}}},')

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out, exist_ok=True)
    for _ in range(15):
        scene.write_data_to_sim()
        sim.step(render=True)
        scene.update(sim.get_physics_dt())
    rgb = scene["probe_cam"].data.output["rgb"][0].detach().cpu().numpy()[..., :3]
    if rgb.dtype != np.uint8:
        rgb = ((rgb * 255).clip(0, 255) if rgb.max() <= 1.0
               else rgb.clip(0, 255)).astype(np.uint8)
    from PIL import Image
    Image.fromarray(rgb).save(os.path.join(out, "ycb_probe.png"))
    print(f"\n[probe] frame saved to {out}/ycb_probe.png")
    simulation_app.close()


if __name__ == "__main__":
    main()