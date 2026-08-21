"""Offline reachability raster generation.

For each arm and each xy grid cell over the table: reset the arm to its
default stance, set a top-down hover goal at RASTER_TEST_Z, and tick the
cell until the arm converges or the step budget runs out. One .npz per arm.

Run:
  python3 reachability/gen_reachability.py --headless --resolution 0.1  # quick
  python3 reachability/gen_reachability.py --headless                    # full
"""

import argparse
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # project root (3 levels up)

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--resolution", type=float, default=None)
parser.add_argument("--max_ticks", type=int, default=240)
parser.add_argument("--arms", nargs="*", default=None)
AppLauncher.add_app_launcher_args(parser)
args = parser.parse_args()
args.enable_cameras = True      # scene includes the top-down camera
app_launcher = AppLauncher(args)
simulation_app = app_launcher.app

import torch                                          # noqa: E402
import isaaclab.sim as sim_utils                      # noqa: E402
from isaaclab.scene import InteractiveScene           # noqa: E402

from core.cell import cell_config as C                               # noqa: E402
from core.cell.scene_cfg import FourArmSceneCfg                 # noqa: E402
from core.cell.arms import Arm, Cell                            # noqa: E402


def main():
    res = args.resolution or C.RASTER_RESOLUTION
    arm_names = args.arms or list(C.ARMS)

    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    scene = InteractiveScene(FourArmSceneCfg(num_envs=1, env_spacing=8.0))
    sim.reset()
    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    cell.settle()

    xs = np.arange(-C.TABLE_HALF_X, C.TABLE_HALF_X + 1e-9, res)
    ys = np.arange(-C.TABLE_HALF_Y, C.TABLE_HALF_Y + 1e-9, res)
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rasters")
    os.makedirs(out_dir, exist_ok=True)

    for name in arm_names:
        arm = arms[name]
        # Park every OTHER arm at its rest stance before this sweep. Without
        # this, arms tested earlier are left stretched over the table where
        # their last cell put them, and physically block later arms' targets
        # (observed as franka_n scoring far below its mirror twin franka_s).
        for other_name, other in arms.items():
            if other_name != name:
                q = other.robot.data.default_joint_pos.clone()
                other.robot.write_joint_state_to_sim(q, torch.zeros_like(q))
                other.robot.set_joint_position_target(q)
        for _ in range(30):                       # brief settle
            cell.tick(render=False)

        bx, by, _ = C.ARMS[name]["pos"]
        reach = C.ARM_TYPES[C.ARMS[name]["type"]]["reach"]
        mask = np.zeros((len(ys), len(xs)), dtype=bool)
        tested = 0

        for iy, y in enumerate(ys):
            for ix, x in enumerate(xs):
                if not (0.15 < math.hypot(x - bx, y - by) < reach * 0.98):
                    continue
                tested += 1
                # Reset to the default stance, then try to converge.
                q = arm.robot.data.default_joint_pos.clone()
                arm.robot.write_joint_state_to_sim(q, torch.zeros_like(q))
                arm.set_goal(x, y, C.RASTER_TEST_Z)
                err = 99.0
                for _ in range(args.max_ticks):
                    err = cell.tick(render=False)[name]
                    if err is not None and err < C.REACH_TOL:
                        break
                mask[iy, ix] = err is not None and err < C.REACH_TOL
                arm.clear_goal()
            print(f"[{name}] row {iy + 1}/{len(ys)}", flush=True)

        path = os.path.join(out_dir, f"{name}.npz")
        np.savez_compressed(path, mask=mask, xs=xs, ys=ys, resolution=res)
        print(f"[{name}] {int(mask.sum())}/{tested} tested cells reachable -> {path}")

    simulation_app.close()


if __name__ == "__main__":
    main()
