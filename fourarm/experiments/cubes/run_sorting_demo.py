"""Sorting demo, stage 1: coloured blocks into corner baskets, rule baseline.

Eight blocks (two per colour) are scattered mid-table. Each block's task
destination comes from the colour oracle (ground truth mapping). The rule
allocator assigns arms; everything below (locks, pick and place, set-down)
is the tested system, untouched. At the end, the demo scores itself: every
block must rest within the catch radius of its own colour's basket.

Stage 2 will replace the oracle with the VLM choosing baskets.

Run:  python3 run_sorting_demo.py --headless --record
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # project root (2 levels up)


import argparse
import math

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--record", action="store_true")
parser.add_argument("--blocks", type=int, default=8,
                    help="number of blocks to spawn and sort (1-8); small "
                         "counts make cheap live-model runs")
parser.add_argument("--allocator", default="oracle", choices=["oracle", "vlm"],
                    help="oracle: destinations from the colour table (rule "
                         "baseline). vlm: the model chooses each basket")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import isaaclab.sim as sim_utils                       # noqa: E402
from isaaclab.scene import InteractiveScene            # noqa: E402

from core.cell import cell_config as C                                # noqa: E402
from core.cell.scene_cfg import FourArmSceneCfg, add_object_pool  # noqa: E402
from experiments.cubes.sorting_scene import add_baskets, oracle_dest, BASKETS, CATEGORY_BASKET  # noqa: E402
from core.cell.arms import Arm, Cell                             # noqa: E402
from core.control.disruptions import DisruptionEngine               # noqa: E402
from core.cell.zones import ZoneMap                              # noqa: E402
from core.control.tasks import Coordinator                          # noqa: E402
from instrumentation.recorder import Recorder                          # noqa: E402
from core.decision.vlm_allocator import VLMAllocator                 # noqa: E402

# eight spawn spots: spread over the middle, clear of baskets and each other
SPAWNS = [(-0.70, 0.20), (0.70, -0.20), (-0.30, 0.15), (0.30, -0.15),
          (-0.70, -0.20), (0.70, 0.20), (-0.30, -0.15), (0.30, 0.15)]
CATCH_RADIUS = 0.16                     # scored as sorted if within this


def color_of(index):
    """Pool objects cycle through categories in creation order, the same
    convention state_builder uses."""
    return C.OBJECT_CATEGORIES[index % len(C.OBJECT_CATEGORIES)]


def main():
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    cfg = FourArmSceneCfg(num_envs=1, env_spacing=8.0)
    pool = add_object_pool(cfg)
    add_baskets(cfg)
    scene = InteractiveScene(cfg)
    sim.reset()
    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    if args_cli.record:
        cell.recorder = Recorder("out/sorting_demo.mp4", every=2, fps=30)
    engine = DisruptionEngine(scene, arms, pool, seed=0, profile="none",
                              device=sim.device)
    zonemap = ZoneMap()
    cell.settle()

    if args_cli.allocator == "vlm":
        holder = {}
        alloc = VLMAllocator(lambda: holder["c"], engine, condition="A",
                             baskets=BASKETS, timeout=60.0,
                             fallback_resolver=lambda t: oracle_dest(
                                 color_of(int(t.obj.split("_")[-1]))))
        coord = Coordinator(cell, zonemap, allocate=alloc, engine=engine)
        holder["c"] = coord
    else:
        alloc = None
        coord = Coordinator(cell, zonemap, engine=engine)

    # place the blocks and submit one sorting task per block. In vlm mode the
    # task has NO destination: choosing the basket IS the allocator's job.
    names = []
    n_blocks = max(1, min(args_cli.blocks, len(SPAWNS)))
    for i, (x, y) in enumerate(SPAWNS[:n_blocks]):
        name = engine.activate_object(x, y)
        names.append(name)
    cell.hold(60)
    for i, name in enumerate(names):
        col = color_of(i)
        if args_cli.allocator == "vlm":
            coord.submit(name, None)
            print(f"[sort] {name} is {col:>6} -> model must choose")
        else:
            coord.submit(name, oracle_dest(col))
            print(f"[sort] {name} is {col:>6} -> {CATEGORY_BASKET[col]}")

    # run until the pool is finished or the cap is hit
    for t in range(60000):
        coord.tick()
        cell.tick(render=args_cli.record or (t % 4 == 0))
        if t % 1200 == 0:
            todo = sum(1 for k in coord.pool if not k.done and not k.failed)
            print(f"[sort] tick {t:>6}  tasks left {todo}")
        if not coord.pending():
            break

    # score: each block within catch radius of its own colour's basket
    print("\n[sort] RESULT")
    correct = 0
    for i, name in enumerate(names):
        col = color_of(i)
        bx, by = oracle_dest(col)
        p = scene[name].data.root_pos_w[0]
        d = math.hypot(float(p[0]) - bx, float(p[1]) - by)
        ok = d < CATCH_RADIUS
        correct += ok
        print(f"  {name} ({col:>6}): {d*100:5.1f} cm from its basket  "
              f"{'SORTED' if ok else 'MISPLACED'}")
    print(f"\n[sort] {correct}/{len(names)} blocks in the right basket, "
          f"requeues={coord.m.requeued}, "
          f"blocked_ticks={sum(coord.m.blocked.values())}")
    print(f"[sort] VERDICT: {'PASS' if correct == len(names) else 'CHECK'}")
    from instrumentation.episode_logger import EpisodeLogger
    from core.decision.state_builder import PROMPT_VERSION
    EpisodeLogger(seed=0, allocator=args_cli.allocator,
                  condition=(alloc.condition if alloc is not None else None),
                  prompt_version=PROMPT_VERSION,
                  blocks=len(names)).finish(
        coord, alloc=alloc,
        extra_metrics={"sorted_correct": int(correct),
                       "sorted_total": len(names)})
    if alloc is not None:
        print(f"[sort] model stats: {alloc.stats}")
        for entry in alloc.log:
            print("  " + str(entry))
    if cell.recorder is not None:
        cell.recorder.close()
    simulation_app.close()


if __name__ == "__main__":
    main()