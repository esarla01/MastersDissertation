"""Four-arm Layer 1 smoke test (concurrent, simplified stack).

  1. all four arms move CONCURRENTLY to inward waypoints
  2. ur_w picks a spawned cube (kinematic attach) and relays it to the centre
  3. a D3 disruption freezes franka_n
  4. one top-down frame is saved to out/

Run:  python3 run_smoke_test.py --headless
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # project root


import argparse
import os

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--record", action="store_true",
                    help="save the overhead camera to out/smoke.mp4")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import numpy as np                                    # noqa: E402
import torch                                          # noqa: E402
import isaaclab.sim as sim_utils                      # noqa: E402
from isaaclab.scene import InteractiveScene           # noqa: E402

from core.cell import cell_config as C                               # noqa: E402
from core.cell.scene_cfg import FourArmSceneCfg, add_object_pool  # noqa: E402
from core.cell.arms import Arm, Cell                            # noqa: E402
from core.control.disruptions import DisruptionEngine              # noqa: E402

WAYPOINTS = {
    "ur_w": (-0.65, 0.0), "ur_e": (0.65, 0.0),
    "franka_s": (0.0, -0.10), "franka_n": (0.0, 0.10),
}


def save_top_frame(scene, sim, out_dir):
    for _ in range(15):
        scene.write_data_to_sim()
        sim.step(render=True)
        scene.update(sim.get_physics_dt())
    rgb = scene["table_cam"].data.output["rgb"][0].detach().cpu().numpy()[..., :3]
    if rgb.dtype != np.uint8:
        rgb = ((rgb * 255).clip(0, 255) if rgb.max() <= 1.0 else rgb).astype(np.uint8)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "smoke_rgb.png")
    try:
        from PIL import Image
        Image.fromarray(rgb).save(path)
    except ImportError:
        path = path.replace(".png", ".npy")
        np.save(path, rgb)
    return path


def main():
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    scene_cfg = FourArmSceneCfg(num_envs=1, env_spacing=8.0)
    pool = add_object_pool(scene_cfg)
    scene = InteractiveScene(scene_cfg)
    sim.reset()

    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    engine = DisruptionEngine(scene, arms, pool, seed=0, profile="none",
                              device=sim.device)
    if args_cli.record:
        from instrumentation.recorder import Recorder
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
        cell.recorder = Recorder(os.path.join(out_dir, "smoke.mp4"))
    cell.settle()
    results = {}

    # ---- 1. concurrent reach -----------------------------------------------
    print("\n[smoke] stage 1: all four arms move together")
    for n, (x, y) in WAYPOINTS.items():
        arms[n].set_goal(x, y, C.HOVER_Z)
    ok, last = cell.run_until(max_ticks=1200)
    for n in arms:
        e = last.get(n)
        results[f"reach_{n}"] = bool(e is None or e < C.REACH_TOL)   # None = arrived, goal cleared
    print(f"[smoke] concurrent reach: {'all OK' if ok else 'some FAILED'}")

    # ---- 2. pick and relay to the centre pad --------------------------------
    print("\n[smoke] stage 2: ur_w picks a cube, others hold")
    obj = engine.activate_object(-0.95, -0.40)
    cell.hold(60)
    px, py, pz = (float(v) for v in scene[obj].data.root_pos_w[0])

    arms["ur_w"].set_goal(px, py, C.HOVER_Z)
    cell.run_until(max_ticks=900)
    arms["ur_w"].set_goal(px, py, pz + C.HANG)         # descend to hang height
    cell.run_until(max_ticks=900)
    results["grasp"] = arms["ur_w"].attach(obj)
    z0 = float(scene[obj].data.root_pos_w[0, 2])
    arms["ur_w"].set_goal(px, py, C.HOVER_Z)
    cell.run_until(max_ticks=900)
    results["lift"] = bool(float(scene[obj].data.root_pos_w[0, 2]) - z0 > 0.05)
    print(f"[smoke] grasp: {'OK' if results['grasp'] else 'FAIL'}  "
          f"lift: {'OK' if results['lift'] else 'FAIL'}")

    dx, dy = C.EXCHANGE_PADS["center"]["pos"]
    arms["ur_w"].set_goal(dx, dy, C.HOVER_Z)
    cell.run_until(max_ticks=900)
    arms["ur_w"].set_goal(dx, dy, C.OBJECT_SPAWN_Z + C.HANG)
    cell.run_until(max_ticks=900)
    arms["ur_w"].detach()
    cell.hold(90)
    arms["ur_w"].set_goal(dx, dy, C.HOVER_Z)
    cell.run_until(max_ticks=600)
    fx, fy = (float(v) for v in scene[obj].data.root_pos_w[0, 0:2])
    results["place_center"] = bool(abs(fx - dx) < 0.12 and abs(fy - dy) < 0.12)
    print(f"[smoke] place at centre: {'OK' if results['place_center'] else 'FAIL'} "
          f"(cube at [{fx:.2f}, {fy:.2f}])")

    # ---- 3. D3 disable --------------------------------------------------------
    print("\n[smoke] stage 3: disable franka_n")
    q0 = scene["franka_n"].data.joint_pos.clone()
    arms["franka_n"].disable()
    cell.hold(120)
    results["disable_arm"] = bool(
        torch.allclose(q0, scene["franka_n"].data.joint_pos, atol=0.05))
    print(f"[smoke] D3 freeze: {'OK' if results['disable_arm'] else 'FAIL'}")

    # ---- 4. camera --------------------------------------------------------------
    path = save_top_frame(scene, sim,
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    results["camera"] = os.path.exists(path)
    print(f"[smoke] top-down frame saved to {path}")

    print("\n[smoke] SUMMARY")
    for k, v in results.items():
        print(f"  {k:>14}: {'PASS' if v else 'FAIL'}")
    if cell.recorder is not None:
        cell.recorder.close()

    # When livestreaming, keep the app (and therefore the stream) alive so a
    # viewer can connect and look around. Ctrl+C to exit.
    if getattr(args_cli, "livestream", 0) and args_cli.livestream > 0:
        print("[smoke] holding for the stream viewer; press Ctrl+C to exit")
        try:
            while simulation_app.is_running():
                cell.tick(render=True)
        except KeyboardInterrupt:
            pass
    simulation_app.close()


if __name__ == "__main__":
    main()
