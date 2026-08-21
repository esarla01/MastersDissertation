"""YCB smoke test (step 1 of the YCB migration).

ONE soup can, ONE arm (ur_w), ONE full pick-and-place, driven by hand at
Layer 1, exactly like run_smoke_test stage 2. First contact between the
kinematic grasp machinery and a real non-cube shape. Tests the three
things the cube code silently assumed:

  1. attach tolerance against a taller object (the gap check measures
     from the object ROOT, which sits higher on a can than on a cube)
  2. set-down at the object's TRUE rest height (measured by the probe;
     Arm.detach gained a place_z parameter for this). A wrong height
     re-creates the PhysX ejection artifact, so the pass criteria
     include a post-release drift check.
  3. the carry pose on video (--record)

Deliberately NOT tested here: the Coordinator (tasks.py's LOWER state has
its own cube-height assumption, generalised in the registry step).

Run:  python3 run_ycb_smoke.py --headless [--record]
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
parser.add_argument("--record", action="store_true",
                    help="save the overhead camera to out/ycb_smoke.mp4")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import math                                            # noqa: E402
import isaaclab.sim as sim_utils                       # noqa: E402
from isaaclab.assets import RigidObjectCfg             # noqa: E402
from isaaclab.scene import InteractiveScene            # noqa: E402
from isaaclab.utils.assets import ISAAC_NUCLEUS_DIR    # noqa: E402

from core.cell import cell_config as C                                # noqa: E402
from core.cell.scene_cfg import FourArmSceneCfg                  # noqa: E402
from core.cell.arms import Arm, Cell                             # noqa: E402

# Soup can facts, measured by run_ycb_probe (upright, physics variant):
CAN_USD = f"{ISAAC_NUCLEUS_DIR}/Props/YCB/Axis_Aligned_Physics/005_tomato_soup_can.usd"
CAN_REST = 0.032                     # root height above the surface at rest
CAN_REST_Z = C.TABLE_H + CAN_REST    # absolute resting root height on table

PICK = (-0.85, 0.15)                 # ur_w territory (same as smoke test)
PLACE = (-0.45, -0.30)               # still ur_w territory, across the zone


def main():
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    cfg = FourArmSceneCfg(num_envs=1, env_spacing=8.0)
    # one YCB object instead of the cube pool; the _Physics variant carries
    # RigidBodyAPI, so the standard property-modify path just works
    cfg.ycb_can = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/ycb_can",
        spawn=sim_utils.UsdFileCfg(
            usd_path=CAN_USD,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(),
            mass_props=None,             # keep the authored 0.349 kg
            collision_props=sim_utils.CollisionPropertiesCfg(),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(
            pos=(PICK[0], PICK[1], CAN_REST_Z + 0.005)),
    )
    scene = InteractiveScene(cfg)
    sim.reset()

    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    if args_cli.record:
        from instrumentation.recorder import Recorder
        cell.recorder = Recorder("out/ycb_smoke.mp4", every=2, fps=30)
    cell.settle()
    ur = arms["ur_w"]
    can = scene["ycb_can"]
    results = {}

    def can_pos():
        p = can.data.root_pos_w[0]
        return float(p[0]), float(p[1]), float(p[2])

    # ---- 0. the can rests where the probe said it would ------------------
    x0, y0, z0 = can_pos()
    results["rest_height_as_measured"] = abs(z0 - CAN_REST_Z) < 0.01
    print(f"[ycb] can at rest: z={z0:.3f} (expected {CAN_REST_Z:.3f})")

    # ---- 1. hover, descend, attach ---------------------------------------
    print("[ycb] stage 1: pick")
    ur.set_goal(x0, y0, C.HOVER_Z)
    cell.run_until(max_ticks=900)
    ur.set_goal(x0, y0, z0 + C.HANG)
    cell.run_until(max_ticks=900)
    results["attach"] = ur.attach("ycb_can")
    print(f"[ycb] attach: {'OK' if results['attach'] else 'FAIL'}")

    # ---- 2. lift ----------------------------------------------------------
    ur.set_goal(x0, y0, C.HOVER_Z)
    cell.run_until(max_ticks=900)
    results["lift"] = can_pos()[2] - z0 > 0.05
    print(f"[ycb] lift: {'OK' if results['lift'] else 'FAIL'}")

    # ---- 3. carry and set down at the measured rest height ----------------
    print("[ycb] stage 2: place")
    ur.set_goal(PLACE[0], PLACE[1], C.HOVER_Z)
    cell.run_until(max_ticks=1200)
    ur.set_goal(PLACE[0], PLACE[1],
                CAN_REST_Z + C.HANG + C.PLACE_CLEARANCE)
    cell.run_until(max_ticks=900)
    ur.detach(place_xy=PLACE, place_z=CAN_REST_Z + 0.003)
    cell.hold(30)
    ur.set_goal(PLACE[0], PLACE[1], C.HOVER_Z)
    cell.run_until(max_ticks=600)

    # ---- 4. the ejection detector -----------------------------------------
    # a wrongly-buried set-down fires the object sideways within a few
    # ticks; a correct one drifts millimetres while settling
    px, py, pz = can_pos()
    cell.hold(120)
    qx, qy, qz = can_pos()
    drift = math.hypot(qx - px, qy - py)
    results["placed_on_target"] = (abs(qx - PLACE[0]) < 0.12
                                   and abs(qy - PLACE[1]) < 0.12)
    results["no_ejection_drift"] = drift < 0.02
    results["settled_at_rest_height"] = abs(qz - CAN_REST_Z) < 0.01
    print(f"[ycb] final: at ({qx:.2f}, {qy:.2f}, z={qz:.3f}), "
          f"post-release drift {drift * 100:.1f} cm")

    print("\n[ycb] SUMMARY")
    for k, v in results.items():
        print(f"  {k:>24}: {'PASS' if v else 'FAIL'}")
    if cell.recorder is not None:
        cell.recorder.close()
    simulation_app.close()


if __name__ == "__main__":
    main()
