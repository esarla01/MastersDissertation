"""Teaching tracer: watch ONE arm do ONE pick-and-place.

This adds nothing to the system. It runs the manager and the world you have
already studied, and simply PRINTS the arm's state each time it changes, plus
what happens to its zone keys. The goal is to see the state machine in
tasks.py move through the exact states you read, in real output.

Run:  python3 run_state_tracer.py --headless
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # project root


import argparse
from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--record", action="store_true",
                    help="also write an MP4 of the arm doing the task")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import isaaclab.sim as sim_utils                       # noqa: E402
from isaaclab.scene import InteractiveScene            # noqa: E402
from core.cell import cell_config as C                                # noqa: E402
from core.cell.scene_cfg import FourArmSceneCfg, add_object_pool  # noqa: E402
from core.cell.arms import Arm, Cell                             # noqa: E402
from core.control.disruptions import DisruptionEngine               # noqa: E402
from core.cell.zones import ZoneMap                              # noqa: E402
from core.control.tasks import Coordinator                          # noqa: E402
from instrumentation.recorder import Recorder                          # noqa: E402


def main():
    # --- build the world (Layer 1) ---
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    cfg = FourArmSceneCfg(num_envs=1, env_spacing=8.0)
    pool = add_object_pool(cfg)
    scene = InteractiveScene(cfg)
    sim.reset()
    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    if args_cli.record:
        # every=1 grabs a frame each tick (326 ticks -> 326 frames); fps=30
        # plays it back as smooth, visible motion rather than a few snapshots.
        cell.recorder = Recorder("out/state_tracer.mp4", every=1, fps=30)
    engine = DisruptionEngine(scene, arms, pool, seed=0, profile="none",
                              device=sim.device)
    zonemap = ZoneMap()
    cell.settle()

    # --- set up the manager (Layer 2) with ONE task for ONE arm ---
    coord = Coordinator(cell, zonemap, engine=engine)
    obj = engine.activate_object(-0.85, 0.45)     # far NW corner, ur_w territory
    cell.hold(60)
    coord.submit(obj, (-0.30, -0.45))             # cross to the SW side
    print(f"\nTASK: move {obj} from about (-0.85, 0.45) to (-0.30, -0.45)\n")
    print(f"{'tick':>5}  {'state change':<22}  keys held by ur_w")
    print("-" * 60)

    # --- run, printing ONLY when ur_w's state changes ---
    agent = coord.agents["ur_w"]
    last_state = None
    for t in range(6000):
        coord.tick()
        # The camera's image only refreshes on a rendered step. When recording
        # we must render, or every captured frame is the frozen first image
        # (the arm appears not to move even though the physics advances).
        cell.tick(render=args_cli.record or (t % 2 == 0))
        if agent.state != last_state:
            keys = coord.locks.held_by("ur_w")           # which zone keys it holds
            keys_str = ", ".join(keys) if keys else "(none)"
            print(f"{t:>5}  {last_state or 'START':>9} -> {agent.state:<9}  [{keys_str}]")
            last_state = agent.state
        if not coord.pending():
            print("-" * 60)
            print(f"done at tick {t}: task complete, arm back to IDLE\n")
            break

    if cell.recorder is not None:
        cell.recorder.close()
        print("video written to out/state_tracer.mp4")
    simulation_app.close()


if __name__ == "__main__":
    main()