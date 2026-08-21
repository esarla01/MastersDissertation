"""Probe diagnostic: WHY did franka_s fail the tools basket?

Finding that motivated this (2026-07-19): in each arm's local frame,
franka_s -> basket_tools and franka_n -> basket_kitchenware are the SAME
target, (0.10, 0.70), with the same tuck joints. Identical kinematics,
different probe outcomes, so the failure cannot be geometry. Prime
suspect: trial-order contamination. In the main probe, franka_s entered
its tools trial straight after a deep kitchenware stall, with only a
fixed 150-tick retuck, possibly not enough to recover the posture.

Trials (franka_s -> basket_tools unless stated):
  T1 fresh:      first motion after settle. If this arrives, the arm can
                 do it and the probe's FAIL was contaminated.
  T2 reproduce:  deliberately stall toward the kitchenware basket first,
                 then the probe's exact 150-tick retuck, then tools.
                 Expected to reproduce the FAIL if the theory is right.
  T3 long tuck:  same poisoning, then retuck HELD until the joints are
                 verifiably back at tuck (up to 900 ticks). If this
                 arrives, the fix is a verified retuck in the probe.
  T4 waypoint:   same poisoning, 150-tick retuck, then via pad_sw. Tests
                 posture routing as a fallback fix.
  T5 control:    franka_n -> basket_kitchenware fresh (the twin task).

Run:  python3 ycb/run_probe_diag.py --headless
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

ARRIVE_EPS = 0.02
STALL_TICKS = 600
STALL_MIN_IMPROVE = 0.01
MAX_TICKS = 1900
TOOLS = (-0.70, -0.50)
KITCHEN = (0.70, 0.50)
PAD_SW = C.EXCHANGE_PADS["pad_sw"]["pos"]


def hover_z(name):
    return C.ARM_TYPES[C.ARMS[name]["type"]]["hover_z"]


def drive(cell, name, goal):
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


def retuck_fixed(cell, name, ticks=150):
    """EXACTLY what the main probe did between trials: call tuck() (a
    Franka no-op, see retuck_verified) and hold. Kept faithful so T2
    reproduces the probe's contamination rather than a cleaned-up
    version of it."""
    cell.arms[name].clear_goal()
    cell.arms[name].tuck()
    cell.hold(ticks, render=False)


def retuck_verified(cell, name, max_ticks=900):
    """Retuck held until the JOINTS verifiably reach the tuck pose.

    NOTE (the diagnostic's first finding, made while writing it): the
    production Arm.tuck() is a NO-OP for Frankas. TUCK_JOINT_POS wires
    only the UR entry; FRANKA_TUCK_JOINT_POS exists in cell_config but
    was never added to the map (its comment even says to wire it). So
    the main probe's between-trial retuck did nothing for the Frankas,
    and every Franka trial after the first started from the previous
    trial's final posture. This function does the reset properly, by
    hand, so the trials here are clean."""
    import torch
    arm = cell.arms[name]
    arm.clear_goal()
    q = arm.robot.data.default_joint_pos.clone()
    stance = (C.FRANKA_TUCK_JOINT_POS
              if C.ARMS[name]["type"] == "franka"
              else C.UR_READY_JOINT_POS)
    for jname, val in stance.items():
        ids, _ = arm.robot.find_joints(jname)
        q[:, ids[0]] = val
    arm.robot.set_joint_position_target(q)
    target = q[0, arm.joint_ids]
    for t in range(max_ticks):
        cell.tick(render=False)
        qn = arm.robot.data.joint_pos[0, arm.joint_ids]
        if float(torch.max(torch.abs(qn - target))) < 0.03:
            cell.hold(30, render=False)
            return t + 31
    return max_ticks


def poison(cell, name):
    """Reproduce the contamination: a full stall toward the kitchenware
    basket (unreachable for franka_s), exactly like the main probe's
    trial that preceded tools."""
    err, ticks, ok = drive(cell, name, (KITCHEN[0], KITCHEN[1], hover_z(name)))
    print(f"    (poison stall: err {err:.3f} after {ticks} ticks, "
          f"arrived={ok})", flush=True)


def main():
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    cfg = FourArmSceneCfg(num_envs=1, env_spacing=8.0)
    scene = InteractiveScene(cfg)
    sim.reset()
    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    cell.settle()

    out = {}
    fs, fn = "franka_s", "franka_n"
    hz = hover_z(fs)

    print("\n[diag] T1 fresh: franka_s -> tools from a VERIFIED tuck",
          flush=True)
    needed = retuck_verified(cell, fs)
    print(f"    (initial verified tuck took {needed} ticks)", flush=True)
    err, ticks, ok = drive(cell, fs, (TOOLS[0], TOOLS[1], hz))
    out["T1_fresh"] = {"err": round(err, 4), "ticks": ticks, "ok": ok}
    print(f"[diag] T1: {'ARRIVED' if ok else 'STALLED'} err {err:.3f} "
          f"in {ticks} ticks", flush=True)

    print("\n[diag] T2 reproduce: poison stall, fixed 150-tick retuck, tools",
          flush=True)
    retuck_fixed(cell, fs)
    poison(cell, fs)
    retuck_fixed(cell, fs, 150)
    err, ticks, ok = drive(cell, fs, (TOOLS[0], TOOLS[1], hz))
    out["T2_reproduce"] = {"err": round(err, 4), "ticks": ticks, "ok": ok}
    print(f"[diag] T2: {'ARRIVED' if ok else 'STALLED'} err {err:.3f} "
          f"in {ticks} ticks", flush=True)

    print("\n[diag] T3 verified retuck: poison, retuck until joints AT tuck, "
          "tools", flush=True)
    retuck_fixed(cell, fs)
    poison(cell, fs)
    needed = retuck_verified(cell, fs)
    print(f"    (verified retuck took {needed} ticks)", flush=True)
    err, ticks, ok = drive(cell, fs, (TOOLS[0], TOOLS[1], hz))
    out["T3_verified_retuck"] = {"err": round(err, 4), "ticks": ticks,
                                 "ok": ok, "retuck_ticks": needed}
    print(f"[diag] T3: {'ARRIVED' if ok else 'STALLED'} err {err:.3f} "
          f"in {ticks} ticks", flush=True)

    print("\n[diag] T4 waypoint: poison, 150-tick retuck, via pad_sw, tools",
          flush=True)
    retuck_fixed(cell, fs)
    poison(cell, fs)
    retuck_fixed(cell, fs, 150)
    err_w, ticks_w, ok_w = drive(cell, fs, (PAD_SW[0], PAD_SW[1], hz))
    err, ticks, ok = drive(cell, fs, (TOOLS[0], TOOLS[1], hz))
    out["T4_waypoint"] = {"waypoint_ok": ok_w, "err": round(err, 4),
                          "ticks": ticks, "ok": ok}
    print(f"[diag] T4: waypoint {'ok' if ok_w else 'STALLED'}; tools "
          f"{'ARRIVED' if ok else 'STALLED'} err {err:.3f}", flush=True)

    print("\n[diag] T5 control: franka_n -> kitchenware fresh", flush=True)
    retuck_verified(cell, fn)
    err, ticks, ok = drive(cell, fn, (KITCHEN[0], KITCHEN[1], hover_z(fn)))
    out["T5_control"] = {"err": round(err, 4), "ticks": ticks, "ok": ok}
    print(f"[diag] T5: {'ARRIVED' if ok else 'STALLED'} err {err:.3f} "
          f"in {ticks} ticks", flush=True)

    print("\n[diag] ===== VERDICT GUIDE =====")
    print("  T1 ARRIVED + T2 STALLED -> probe contamination confirmed:")
    print("    fix = verified retuck in the probe, re-run it, and REMOVE")
    print("    the franka_s tools deny entry.")
    print("  T1 STALLED -> genuine infeasibility from home posture after")
    print("    all; deny entry stays; T4 tells us if a waypoint helps.")
    print("  T3 ARRIVED -> recovery is possible and bounded; production")
    print("    aborts already pass through home, so no motion change needed.")

    os.makedirs("out", exist_ok=True)
    with open(os.path.join("out", "probe_diag.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("\n[diag] written to out/probe_diag.json", flush=True)
    simulation_app.close()


if __name__ == "__main__":
    main()
