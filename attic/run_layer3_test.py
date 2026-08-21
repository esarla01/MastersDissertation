"""Layer 3 dry run: exercise the state builder against a live episode.

Runs the rule-based cell for a while, injects a D3 disruption, then builds
the ground-truth state and both conditions A and V, writing everything to
out/ for inspection:

  out/l3_state.json      the condition A state
  out/l3_prompt_A.txt    full condition A message text
  out/l3_prompt_V.txt    condition V text part (byte-identical to A)
  out/l3_frame.png       the exact frame condition V embeds

Checks that the state matches the simulator (spot checks) and that
parse_decision round-trips a well-formed reply.

Run:  python3 run_layer3_test.py --headless
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # project root


import argparse
import json
import os

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import base64                                          # noqa: E402
import isaaclab.sim as sim_utils                       # noqa: E402
from isaaclab.scene import InteractiveScene            # noqa: E402

from core.cell import cell_config as C                                # noqa: E402
from core.cell.scene_cfg import FourArmSceneCfg, add_object_pool  # noqa: E402
from core.cell.arms import Arm, Cell                             # noqa: E402
from core.control.disruptions import DisruptionEngine               # noqa: E402
from core.cell.zones import ZoneMap                              # noqa: E402
from core.control.tasks import Coordinator                          # noqa: E402
from core.decision.state_builder import (build_state, build_prompt, grab_frame_b64,
                           parse_decision)             # noqa: E402


def main():
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    scene_cfg = FourArmSceneCfg(num_envs=1, env_spacing=8.0)
    pool = add_object_pool(scene_cfg)
    scene = InteractiveScene(scene_cfg)
    sim.reset()

    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    engine = DisruptionEngine(scene, arms, pool, seed=3, profile="none",
                              device=sim.device)
    coord = Coordinator(cell, ZoneMap())
    cell.settle()

    # A representative mid-episode moment: objects on the table, one task in
    # flight, one queued, one arm freshly disabled.
    o1 = engine.activate_object(-0.85, 0.15)
    o2 = engine.activate_object(0.85, -0.20)
    o3 = engine.activate_object(-0.30, 0.45)
    cell.hold(60)
    coord.submit(o1, (0.10, 0.05))
    coord.submit(o2, (-0.60, 0.0))
    for t in range(700):
        coord.tick()
        cell.tick(render=(t % 8 == 0))
    arms["franka_n"].disable(drop=True)
    coord.submit(o3, (0.0, 0.0))
    for t in range(120):
        coord.tick()
        cell.tick(render=(t % 4 == 0))

    state = build_state(coord, engine, tick=820)
    img = grab_frame_b64(scene)
    msgs_a = build_prompt(state, "A")
    msgs_v = build_prompt(state, "V", image_b64=img)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "l3_state.json"), "w") as f:
        json.dump(state, f, indent=1)
    with open(os.path.join(out, "l3_prompt_A.txt"), "w") as f:
        f.write(msgs_a[0]["content"] + "\n\n" + msgs_a[1]["content"][0]["text"])
    with open(os.path.join(out, "l3_prompt_V.txt"), "w") as f:
        f.write(msgs_v[0]["content"] + "\n\n" + msgs_v[1]["content"][1]["text"])
    with open(os.path.join(out, "l3_frame.png"), "wb") as f:
        f.write(base64.b64decode(img))

    # ---- checks --------------------------------------------------------------
    results = {}
    results["arms_count"] = len(state["arms"]) == 4
    results["disabled_visible"] = any(
        a["name"] == "franka_n" and a["disabled"] for a in state["arms"])
    results["objects_tracked"] = {o["name"] for o in state["objects"]} == \
        {o1, o2, o3}
    sim_xy = scene[o3].data.root_pos_w[0]
    st_xy = next(o["xy"] for o in state["objects"] if o["name"] == o3)
    results["positions_match"] = (abs(float(sim_xy[0]) - st_xy[0]) < 0.02
                                  and abs(float(sim_xy[1]) - st_xy[1]) < 0.02)
    results["tasks_present"] = len(state["tasks"]) >= 3
    results["v_text_identical"] = (msgs_v[1]["content"][1]["text"]
                                   == msgs_a[1]["content"][0]["text"])
    reply = ('Sure! ```json\n{"task_id": 2, "arm": "ur_w", '
             '"via_pad": null, "reason": "nearest"}\n```')
    d = parse_decision(reply)
    results["parse_roundtrip"] = bool(d and d["arm"] == "ur_w"
                                      and d["task_id"] == 2)

    print("\n[L3] SUMMARY")
    for k, v in results.items():
        print(f"  {k:>18}: {'PASS' if v else 'FAIL'}")
    print(f"[L3] wrote state, both prompts, and frame to {out}")
    simulation_app.close()


if __name__ == "__main__":
    main()
