"""Layer 2 acceptance test.

  A. CONTENTION  two arms are given tasks whose place targets share the
     centre zone; they must sequence via the lock (blocked ticks > 0,
     never two holders of one zone, both tasks complete)
  B. HANDOVER    an object only ur_w reaches must end where only ur_e
     reaches; the allocator must route it through a pad in two legs
  C. D3 RECOVERY the carrying arm is disabled mid-transport; its task is
     requeued and finished by another arm

Run:  python3 run_layer2_test.py --headless [--record] [--scenario B]
Requires reachability rasters (reachability/rasters/*.npz).
A status line prints every 600 ticks; a healthy run shows states advancing
and errors shrinking. A stalled run shows the same state with a frozen or
plateaued error, which identifies the stuck stage directly.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # project root


import argparse
import os

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--record", action="store_true",
                    help="save the overhead camera to out/layer2.mp4")
parser.add_argument("--scenario", default="all", choices=["A", "B", "C", "all"],
                    help="run a single scenario for debugging")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import torch                                          # noqa: E402
import isaaclab.sim as sim_utils                      # noqa: E402
from isaaclab.scene import InteractiveScene           # noqa: E402

from core.cell import cell_config as C                               # noqa: E402
from core.cell.scene_cfg import FourArmSceneCfg, add_object_pool  # noqa: E402
from core.cell.arms import Arm, Cell                            # noqa: E402
from core.control.disruptions import DisruptionEngine              # noqa: E402
from core.cell.zones import ZoneMap                             # noqa: E402
from core.control.tasks import Coordinator                         # noqa: E402

MAX_TICKS = 20000


def run_scenario(cell, coord, until=None, max_ticks=MAX_TICKS, watch=None):
    """Tick coordinator + cell until done (or `until` returns True).
    Prints a status line every 600 ticks so a stalled run is visible."""
    render_every = 8 if cell.recorder is not None else 20
    for t in range(max_ticks):
        coord.tick()
        cell.tick(render=(t % render_every == 0))
        if watch:
            watch(t)
        if t % 600 == 0:
            ag = "  ".join(
                f"{n}:{a.state}"
                + (f"({a.arm.error():.3f})" if a.arm.error() is not None else "")
                for n, a in coord.agents.items())
            todo = sum(1 for x in coord.pool if not x.done and not x.failed)
            print(f"    [L2 tick {t:5d}] {ag}  locks={coord.locks.holder}  "
                  f"pool_todo={todo}  requeued={coord.m.requeued}", flush=True)
        if until is not None and until():
            return True
        if until is None and not coord.pending():
            return True
    return False


def reset_cell(cell, arms, engine=None):
    """Restore every arm to its default stance AND clear the table, so one
    scenario's outcome (a wreck, or leftover placed objects) cannot
    contaminate the next. Retiring objects is what stops a finished block
    from a previous scenario being re-grabbed."""
    for a in arms.values():
        a.enable()
        a.clear_goal()
        a.detach()
        q = a.robot.data.default_joint_pos.clone()
        a.robot.write_joint_state_to_sim(q, torch.zeros_like(q))
        a.robot.set_joint_position_target(q)
    if engine is not None:
        engine.retire_all()
    cell.hold(60)


def exclusive_cell(zm, arm, prefer):
    """Raster cell reachable by EXACTLY this arm, nearest to `prefer`.
    Scenario coordinates come from the measured rasters instead of being
    hardcoded, so the test survives raster regeneration and layout changes.
    (The two URs are 180-degree rotations of each other, not mirrors, so a
    hardcoded 'mirrored' point can be honestly unreachable.)"""
    best, best_d = None, 1e9
    for iy, y in enumerate(zm.ys):
        for ix, x in enumerate(zm.xs):
            owners = [a for a in zm.masks if zm.masks[a][iy, ix]]
            if owners == [arm]:
                d = (x - prefer[0]) ** 2 + (y - prefer[1]) ** 2
                if d < best_d:
                    best_d, best = d, (float(x), float(y))
    return best


def obj_at(scene, obj, xy, tol=0.15):
    p = scene[obj].data.root_pos_w[0]
    return abs(float(p[0]) - xy[0]) < tol and abs(float(p[1]) - xy[1]) < tol


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
    zonemap = ZoneMap()
    if args_cli.record:
        from instrumentation.recorder import Recorder
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
        cell.recorder = Recorder(os.path.join(out_dir, "layer2.mp4"))
    cell.settle()
    results = {}
    want = args_cli.scenario

    # ---- A. contention on the centre zone -----------------------------------
    if want in ("A", "all"):
        print("\n[L2] scenario A: two arms contest the centre zone")
        coord = Coordinator(cell, zonemap, engine=engine)
        a1 = engine.activate_object(-0.85, 0.15)     # ur_w side
        a2 = engine.activate_object(0.85, -0.15)     # ur_e side
        cell.hold(60)
        coord.submit(a1, (0.10, 0.05))               # both destinations in center
        coord.submit(a2, (-0.10, -0.05))
        overlap_violation = []

        def watch(_):
            holders = list(coord.locks.holder.values())
            if len(holders) != len(set(holders)):
                overlap_violation.append(True)

        done = run_scenario(cell, coord, watch=watch)
        blocked = sum(coord.m.blocked.values())
        results["A_completed"] = done and obj_at(scene, a1, (0.10, 0.05)) \
            and obj_at(scene, a2, (-0.10, -0.05))
        results["A_sequenced"] = blocked > 0 and not overlap_violation
        print(f"[L2] A done={done} blocked_ticks={blocked} "
              f"requeued={coord.m.requeued}")

    # ---- B. handover through a pad -------------------------------------------
    if want in ("B", "all"):
        reset_cell(cell, arms, engine)
        print("\n[L2] scenario B: handover (ur_w object, ur_e destination)")
        coord = Coordinator(cell, zonemap, engine=engine)
        obj_xy = exclusive_cell(zonemap, "ur_w", (-1.30, 0.35))
        dest_xy = exclusive_cell(zonemap, "ur_e", (1.30, 0.35))
        print(f"[L2] B: obj {obj_xy} (ur_w only) -> dest {dest_xy} (ur_e only)")
        b = engine.activate_object(*obj_xy)
        cell.hold(60)
        coord.submit(b, dest_xy)
        done = run_scenario(cell, coord)
        legs = sum(coord.m.completed.values())
        results["B_handover"] = done and legs >= 2 and obj_at(scene, b, dest_xy)
        print(f"[L2] B done={done} legs={legs} per-arm={coord.m.completed}")

    # ---- C. D3 mid-transport, task recovered ---------------------------------
    if want in ("C", "all"):
        print("\n[L2] scenario C: disable the carrier mid-task")
        coord = Coordinator(cell, zonemap, engine=engine)
        c = engine.activate_object(-0.55, 0.30)      # in the ur_w / franka_n overlap
        cell.hold(60)
        coord.submit(c, (0.0, 0.0))                  # centre: several arms reach it
        carrier = {}

        def kill_when_carrying(t):
            if not carrier:
                for n, ag in coord.agents.items():
                    # TO_PLACE only: a LIFT kill drops the cargo onto the
                    # frozen arm's own corner, where the rescue pick is
                    # physically blocked by the dead robot.
                    if ag.task is not None and ag.state == "TO_PLACE":
                        carrier[n] = t
                        arms[n].disable(drop=True)
                        print(f"[L2] C: disabled {n} at tick {t} while carrying")

        done = run_scenario(cell, coord, watch=kill_when_carrying)
        finisher = [n for n, k in coord.m.completed.items() if k > 0]
        results["C_recovered"] = done and bool(carrier) \
            and obj_at(scene, c, (0.0, 0.0)) \
            and all(n not in carrier for n in finisher)
        print(f"[L2] C done={done} disabled={list(carrier)} "
              f"finished_by={finisher} requeued={coord.m.requeued}")

    print("\n[L2] SUMMARY")
    for k, v in results.items():
        print(f"  {k:>12}: {'PASS' if v else 'FAIL'}")
    if cell.recorder is not None:
        cell.recorder.close()
    simulation_app.close()


if __name__ == "__main__":
    main()
