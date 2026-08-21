"""Pose probe: MEASURE which hover and lower poses each arm can actually
reach, instead of trusting the 2D annulus or the raster.

Motivation (2026-07-18): the reachability data said franka_n could deliver
to the ne basket; physics said no (stall at err 0.800). The same class of
surprise caused the gelatin stall at the centre pad and cost the pitcher
as collateral. This probe replaces those anecdotes with a table.

Protocol, per arm, one arm at a time (the others hold their tuck pose):
  for each of 8 destinations (5 exchange pads + 3 baskets):
    1. from the arm's tucked home posture, command HOVER over the
       destination at the arm type's hover height;
    2. drive until arrival (err < ARRIVE_EPS) or a windowed stall
       (production semantics: 1 cm best-error improvement per 600 ticks);
    3. if hover arrived, command the LOWER pose (representative set-down
       approach height) under the same rule;
    4. record both residuals; re-tuck; next destination.
Every trial starts from the same posture, so rows are comparable.

Output: per-arm table on stdout + out/pose_probe.json.

Run:  python3 ycb/run_ycb_probe_poses.py --headless
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse                                        # noqa: E402

from isaaclab.app import AppLauncher                   # noqa: E402

parser = argparse.ArgumentParser()
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import json                                            # noqa: E402
import isaaclab.sim as sim_utils                       # noqa: E402
from isaaclab.scene import InteractiveScene            # noqa: E402

from core.cell import cell_config as C                 # noqa: E402
from core.cell.scene_cfg import FourArmSceneCfg        # noqa: E402
from core.cell.arms import Arm, Cell                   # noqa: E402

ARRIVE_EPS = 0.02          # arrived when the EE is within 2 cm of the goal
STALL_TICKS = 600          # production stall window
STALL_MIN_IMPROVE = 0.01   # production improvement threshold
LOWER_ABOVE_TABLE = 0.15   # representative set-down approach height
MAX_TICKS = 1900           # hard cap per pose (3 stall windows + slack)

DESTINATIONS = {}
for _pn, _p in C.EXCHANGE_PADS.items():
    DESTINATIONS[_pn] = _p["pos"]
DESTINATIONS["basket_food"] = (-0.70, 0.50)
DESTINATIONS["basket_kitchenware"] = (0.70, 0.50)
DESTINATIONS["basket_tools"] = (-0.70, -0.50)


def hover_z_for(name):
    return C.ARM_TYPES[C.ARMS[name]["type"]]["hover_z"]


def drive_one(cell, name, goal):
    """Drive ONE arm to one goal with production stall semantics; the other
    arms have no goals (they hold their joint targets). Returns
    (final_err, ticks, arrived)."""
    arm = cell.arms[name]
    arm.set_goal(*goal)
    best = None
    window_ref = None
    window_start = 0
    for t in range(MAX_TICKS):
        errs = cell.tick(render=(t % 4 == 0))
        err = errs[name]
        if err is None:
            arm.clear_goal()
            return 0.0, t + 1, True
        if err < ARRIVE_EPS:
            arm.clear_goal()
            return err, t + 1, True
        if best is None or err < best:
            best = err
        if window_ref is None or best <= window_ref - STALL_MIN_IMPROVE:
            window_ref, window_start = best, t
        elif t - window_start >= STALL_TICKS:
            arm.clear_goal()
            return err, t + 1, False
    err = arm.error() or 0.0
    arm.clear_goal()
    return err, MAX_TICKS, False


def retuck(cell, name, max_ticks=900):
    """Return the arm to its tuck posture VERIFIABLY: hold the tuck joint
    targets until every joint is within tolerance (or the budget runs
    out), then settle briefly. The first version held tuck() for a fixed
    150 ticks, and tuck() was then a silent no-op for Frankas, so every
    Franka trial after the first started from the previous trial's final
    posture. That contamination manufactured the false franka_s
    tools-basket FAIL (probe err 0.392 == diagnostic T2 err 0.392,
    while T1 from a real tuck arrives in 106 ticks)."""
    import torch
    arm = cell.arms[name]
    arm.clear_goal()
    arm.tuck()
    q = arm.robot.data.default_joint_pos.clone()
    stance = C.TUCK_JOINT_POS.get(C.ARMS[name]["type"], {})
    for jname, val in stance.items():
        ids, _ = arm.robot.find_joints(jname)
        q[:, ids[0]] = val
    target = q[0, arm.joint_ids]
    for _t in range(max_ticks):
        cell.tick(render=False)
        qn = arm.robot.data.joint_pos[0, arm.joint_ids]
        if float(torch.max(torch.abs(qn - target))) < 0.05:
            break
    cell.hold(60, render=False)


def main():
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    cfg = FourArmSceneCfg(num_envs=1, env_spacing=8.0)   # empty table:
    scene = InteractiveScene(cfg)                        # pure kinematics
    sim.reset()
    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    cell.settle()

    results = {}
    for arm_name in C.ARMS:
        print(f"\n[probe] ===== {arm_name} =====", flush=True)
        results[arm_name] = {}
        hz = hover_z_for(arm_name)
        retuck(cell, arm_name)
        for dest_name, (x, y) in DESTINATIONS.items():
            entry = {}
            err, ticks, ok = drive_one(cell, arm_name, (x, y, hz))
            entry["hover_err"], entry["hover_ticks"], entry["hover_ok"] = \
                round(err, 4), ticks, ok
            if ok:
                lz = C.TABLE_H + LOWER_ABOVE_TABLE
                err2, ticks2, ok2 = drive_one(cell, arm_name, (x, y, lz))
                entry["lower_err"], entry["lower_ticks"], entry["lower_ok"] = \
                    round(err2, 4), ticks2, ok2
            else:
                entry["lower_err"], entry["lower_ticks"], entry["lower_ok"] = \
                    None, 0, False
            results[arm_name][dest_name] = entry
            lower_txt = ("--" if entry["lower_err"] is None
                         else f"{entry['lower_err']:.3f}")
            print(f"[probe] {arm_name:9} -> {dest_name:19} "
                  f"hover {'OK ' if entry['hover_ok'] else 'FAIL'} "
                  f"err {entry['hover_err']:.3f}  "
                  f"lower {'OK ' if entry['lower_ok'] else 'FAIL'} "
                  f"err {lower_txt}", flush=True)
            retuck(cell, arm_name)

    print("\n[probe] ===== SUMMARY (hover/lower) =====")
    print(f"{'destination':20}" + "".join(f"{a:>12}" for a in C.ARMS))
    for dest_name in DESTINATIONS:
        row = f"{dest_name:20}"
        for a in C.ARMS:
            e = results[a][dest_name]
            mark = ("OK" if e["hover_ok"] else "H!") + "/" + \
                   ("OK" if e["lower_ok"] else "L!")
            row += f"{mark:>12}"
        print(row)
    print("\n  H! = hover unreachable, L! = lower unreachable from the home")
    print("  posture. Any cell not OK/OK that the raster claims reachable")
    print("  is a feasibility correction the allocator needs.")

    os.makedirs("out", exist_ok=True)
    path = os.path.join("out", "pose_probe.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=1)
    print(f"\n[probe] written to {path}", flush=True)
    simulation_app.close()


if __name__ == "__main__":
    main()
