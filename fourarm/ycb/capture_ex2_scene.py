"""EX2 scene capture: build a constructed scene, render it, save the state
and frame in the format the probe store already reads.

WHY THIS EXISTS. EX2 compares paired scenes that differ in exactly one
thing: an object's pose, which flips its capability class. Such a pair
cannot be harvested from an episode, because you cannot wait for a run to
happen to produce the matched member. The pairs are authored, and the
construction is disclosed rather than glossed.

WHAT IS AND IS NOT CONSTRUCTED. The frame is a REAL Isaac render of a REAL
spawned scene, so the pixels are not synthetic. The object positions and
the arm occupancy are chosen rather than emergent. Everything downstream
(prompt, validator, router) is the same code an episode uses, and every
captured state is validated exactly as a harvested one is.

THE PAIR DESIGN, and why the partner is fixed.

  member A   mustard_lying     0.096 m across  ->  URs only
  member B   mustard_upright   0.058 m across  ->  all four arms
  partner    large_clamp       0.122 m, tools  ->  URs only, both members

Idle arms are ur_w and franka_n. The mustard is food and the food basket is
reachable by exactly ur_w and franka_n; the clamp is tools and, with
franka_s busy, only ur_w can deliver it.

The DEFAULT POSITIONS are not guesses. They were selected by searching the
legal spawn grid for a point where the real validator gives the mustard
[ur_w] when lying and [ur_w, franka_n] when upright, and the clamp [ur_w]
in both, then taking the closest such pair separated by at least 0.45 m.
The first positions tried, inherited from the designed layout, put the
mustard where NEITHER presented arm could reach it, so the flip did not
exist at all. Verify any new position the same way before capturing.

  In A the mustard is legal for ur_w only, and so is the clamp: they
  compete.
  In B the mustard is also legal for franka_n, so the scarce arm can be
  spared.

A model that reads pose assigns differently in the two members. A model
that ignores pose and always answers franka_n proposes something ILLEGAL in
A, which the validator catches. Either way the measurement is unambiguous,
and it does not rest on cost reasoning, which matters because a Franka is
never cost-optimal in this cell and a purely cost-driven model would never
choose one.

NULL PAIRS. Both members identical except for position jitter. Whatever
flip rate they produce is the noise floor. Without it a measured 0.20
cannot be told from answer instability. Pass --jitter to produce one.

THE RENDER MUST BE RENDERED. The overhead camera only refreshes on a
rendered sim step; stepping with render=False leaves the frame frozen while
physics advances, which once produced an entire episode of identical
frames. cell.hold() renders, and the frame is grabbed after it.

Usage (one member per invocation, appending to one capture file):

    python3 ycb/capture_ex2_scene.py --headless \\
        --pair p01 --member A --flip-object mustard_lying
    python3 ycb/capture_ex2_scene.py --headless \\
        --pair p01 --member B --flip-object mustard_upright

Writes out/ex2_capture/consults.jsonl plus one PNG per capture, which
analysis/probe_store.py harvests with no changes.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--spec", required=True,
                    help="scene list, one per line: "
                         "'<kind> <id> <flip_x,flip_y> <partner_x,partner_y>' "
                         "where kind is pair or null. Every line produces "
                         "BOTH members. Blank lines and # comments ignored. "
                         "The whole file runs in ONE Isaac session: "
                         "launching per scene cost 20 seconds of startup "
                         "each and needed a manual exit each time.")
parser.add_argument("--lying", default="mustard_lying",
                    help="member A pose, and both members of a null")
parser.add_argument("--upright", default="mustard_upright",
                    help="member B pose")
parser.add_argument("--partner", default="large_clamp",
                    help="the fixed competing task. Held constant across "
                         "every pair on purpose: the two members must "
                         "differ in ONE thing")

parser.add_argument("--idle", default="ur_w,franka_n",
                    help="arms presented as IDLE; the rest are busy")
parser.add_argument("--jitter", type=float, default=0.02,
                    help="metres of position jitter applied to NULL scenes")
parser.add_argument("--camera", default="ex2_cam",
                    choices=["ex2_cam", "table_cam", "both"],
                    help="ex2_cam is the oblique view, in which an upright "
                         "bottle reads as upright. table_cam is the "
                         "overhead view every episode uses, in which the "
                         "same bottle is a small ellipse. 'both' saves each "
                         "and is worth it: if a reviewer asks whether the "
                         "oblique view did the work, the overhead condition "
                         "is the comparison")
parser.add_argument("--min-visible", type=float, default=0.45,
                    help="reject the capture if less than this fraction of "
                         "the object's expected top-down footprint is "
                         "visible. The overhead camera occludes objects "
                         "under arm links at their home poses, and an "
                         "invisible object makes the flip test "
                         "unanswerable rather than negative")
parser.add_argument("--allow-occluded", action="store_true",
                    help="capture anyway, recording the measured visibility")
parser.add_argument("--render-warmup", type=int, default=180,
                    help="rendered ticks immediately before the frames are "
                         "grabbed. Isaac's renderer accumulates across "
                         "frames, so after an object moves the old position "
                         "keeps contributing until enough frames have been "
                         "drawn. In batch mode that put a faded duplicate of "
                         "the previous scene's object in the image. The prim "
                         "had moved; the picture had not caught up. Raise "
                         "this if any ghost remains.")
parser.add_argument("--settle-ticks", type=int, default=30,
                    help="physics ticks after placement. Objects are "
                         "teleported at their rest height with zero "
                         "velocity, so they need only a few ticks to come "
                         "to rest. The previous 240 was two seconds, ample "
                         "time for an upright mustard bottle to fall over, "
                         "which is what the registry comment warned about.")
parser.add_argument("--out-dir", default="out/ex2_capture")
parser.add_argument("--note", default="", help="free text into provenance")

from isaaclab.app import AppLauncher                              # noqa: E402

# AppLauncher must register its OWN arguments, --headless among them, and
# then receive the parsed namespace. Declaring --headless by hand instead
# left the launcher unconfigured: the app came up but close() never ended
# the process, so every capture had to be interrupted by hand and a loop
# of them hung. Same call, same order, as run_ycb_sort.py.
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import isaaclab.sim as sim_utils                                  # noqa: E402
from isaaclab.scene import InteractiveScene                       # noqa: E402

from core.cell import cell_config as C                            # noqa: E402
from core.cell.arms import Arm, Cell                              # noqa: E402
# Import sites copied from run_ycb_sort.py rather than guessed:
# add_pad_markers lives in scene_cfg, not ycb_scene, and
# apply_physics_schemas lives in ycb_objects, not ycb_scene.
from core.cell.scene_cfg import (FourArmSceneCfg,                 # noqa: E402
                                 add_pad_markers)
from core.cell.zones import ZoneMap                               # noqa: E402
from core.control.tasks import Coordinator                        # noqa: E402
from core.decision.state_builder import (build_state,             # noqa: E402
                                         grab_frame_b64,
                                         prompt_version)
from ycb_scene import (add_ycb_pool, add_baskets, BASKETS,        # noqa: E402
                       CATEGORY_BASKET, spawn_specs)
from ycb_objects import YCB, apply_physics_schemas                # noqa: E402
from core.control.disruptions import DisruptionEngine             # noqa: E402


def xy(s):
    a, b = s.split(",")
    return (float(a), float(b))



def _rgb(scene, camera="table_cam"):
    """Raw camera pixels, in the same orientation grab_frame_b64 encodes."""
    import numpy as np
    a = scene[camera].data.output["rgb"][0].detach().cpu().numpy()[..., :3]
    a = np.ascontiguousarray(np.rot90(a, k=-1))
    if a.dtype != np.uint8:
        a = ((a * 255).clip(0, 255) if a.max() <= 1.0
             else a.clip(0, 255)).astype(np.uint8)
    return a.astype("int16")


def _px_per_m(scene, camera="table_cam"):
    """Image scale from the camera config, not from a hardcoded constant.

    Pinhole: the width seen at distance d is aperture / focal * d. The
    camera sits at z=5.0 looking straight down and the objects rest on the
    table top, so d is the drop from the camera to the table surface.
    """
    cfg = scene[camera].cfg
    d = cfg.offset.pos[2] - C.TABLE_H
    span_m = (cfg.spawn.horizontal_aperture / cfg.spawn.focal_length) * d
    return cfg.width / span_m


def visible_fraction(before, after, expected_px):
    """How much of an object the camera can actually see.

    Differences the frame before the object was placed against the frame
    after. Everything else in the scene is identical and static, so the
    changed pixels ARE the object, minus whatever an arm link hides. That
    is a measurement of the real render rather than a geometric guess, and
    it is why this is done here instead of with a rectangle filter.
    """
    import numpy as np
    changed = int((np.abs(after - before).max(axis=2) > 12).sum())
    return changed, (changed / expected_px if expected_px else 0.0)


def read_spec(path):
    """Scene list -> [(kind, id, flip_xy, partner_xy)]. Refuses a malformed
    line by number rather than skipping it: a silently dropped scene is a
    missing pair nobody notices until the analysis."""
    out = []
    for n, raw in enumerate(open(path), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 4 or parts[0] not in ("pair", "null"):
            raise SystemExit(f"{path} line {n}: expected "
                             f"'<pair|null> <id> <x,y> <x,y>', got {line!r}")
        out.append((parts[0], parts[1], xy(parts[2]), xy(parts[3])))
    if not out:
        raise SystemExit(f"{path} contains no scenes")
    return out


def activate_named(engine, name, x, y):
    """Place a SPECIFIC object. engine.activate_object takes whatever is at
    the head of the parked list, which is fine for an episode and useless
    here: member A needs mustard_lying and member B mustard_upright, and
    both are in the pool at once."""
    prim = "ycb_" + name
    if prim not in engine.parked:
        raise SystemExit(f"{prim} is not parked; active={engine.active}")
    engine.parked.remove(prim)
    engine.parked.insert(0, prim)
    return engine.activate_object(x, y)


def settle_until_still(cell, scene, camera, limit=8, tol=200):
    """Hold until two successive frames agree.

    A fixed hold was not evidence the cell had stopped: the arms were still
    micro-moving after settle(), and arms are large and pale, so the
    baseline frame differed from the next by ~15,500 px whatever the object.
    That made every visibility fraction meaningless.
    """
    import numpy as np
    moved, frame = None, None
    for _ in range(limit):
        cell.hold(60)
        a = _rgb(scene, camera)
        cell.hold(60)
        frame = _rgb(scene, camera)
        moved = int((np.abs(frame - a).max(axis=2) > 12).sum())
        if moved < tol:
            break
    return frame, moved


def park_everything(scene, engine, pool, cell=None):
    """Put every pool prim at PARK_POS and VERIFY it got there.

    engine.retire_all only moves objects it has marked ACTIVE, and at
    startup none are, so a prim never activated stays where the scene config
    first placed it. With both mustard poses in the cast that left a second
    bottle in frame, pale but plainly visible.

    Writing a root pose is not enough on its own: the write has to be
    flushed and a step taken before the renderer sees it. The first version
    wrote and moved on, and the ghost survived. This one writes, steps, and
    reads the positions back, repeating until every prim is actually below
    the table. It raises rather than continuing if that never happens,
    because a silent ghost contaminates the image with a second object the
    model can read.
    """
    import torch
    pose = torch.tensor([[C.PARK_POS[0], C.PARK_POS[1], C.PARK_POS[2],
                          1.0, 0.0, 0.0, 0.0]],
                        device=engine.device, dtype=torch.float32)
    zero = torch.zeros((1, 6), device=engine.device)
    for attempt in range(5):
        for name in pool:
            scene[name].write_root_pose_to_sim(pose)
            scene[name].write_root_velocity_to_sim(zero)
        scene.write_data_to_sim()
        if cell is not None:
            cell.hold(4)
        stray = [n for n in pool
                 if float(scene[n].data.root_pos_w[0, 2]) > C.TABLE_H - 0.2]
        if not stray:
            engine.active = []
            engine.parked = list(pool)
            return
    raise SystemExit(
        f"could not park {stray}: they are still at table height after "
        f"{attempt + 1} attempts, so they would appear in the frame as "
        f"extra objects.")


def capture_one(cell, scene, coord, engine, zonemap, kind, pid, member,
                fxy, pxy, cameras, trail, out_dir, pool):
    """One scene, start to finish, inside the shared Isaac session."""
    import base64
    flip = args_cli.lying if (member == "A" or kind == "null") \
        else args_cli.upright
    stem = f"{pid}_{member}"

    if kind == "null":
        # Deterministic per scene and member, so a null pair is
        # reproducible and its jitter is recorded rather than random.
        import random
        rng = random.Random(f"{pid}{member}")
        j = args_cli.jitter
        fxy = (fxy[0] + rng.uniform(-j, j), fxy[1] + rng.uniform(-j, j))
        pxy = (pxy[0] + rng.uniform(-j, j), pxy[1] + rng.uniform(-j, j))

    park_everything(scene, engine, pool, cell)
    for t in list(coord.pool):
        coord.pool.remove(t)

    primary = cameras[0]
    frame_empty, moved = settle_until_still(cell, scene, primary)

    names = [activate_named(engine, flip, *fxy)]
    cell.hold(args_cli.settle_ticks)
    frame_flip = _rgb(scene, primary)
    names.append(activate_named(engine, args_cli.partner, *pxy))
    cell.hold(args_cli.settle_ticks)
    frame_both = _rgb(scene, primary)

    for name in names:
        coord.submit(name, None)          # the model chooses the basket (R7)

    idle = [a.strip() for a in args_cli.idle.split(",") if a.strip()]
    for n, ag in coord.agents.items():
        ag.state = "IDLE" if n in idle else "TO_PICK"

    scale = _px_per_m(scene, primary)
    vis = {}
    for name, before, after in ((names[0], frame_empty, frame_flip),
                                (names[1], frame_flip, frame_both)):
        spec = C.OBJECT_SPECS[name]
        expected = (spec["grasp_m"] * spec.get("footprint_m", spec["grasp_m"])
                    * scale * scale)
        px, frac = visible_fraction(before, after, expected)
        vis[name] = {"visible_px": px, "expected_px": round(expected, 1),
                     "visible_fraction": round(frac, 3)}
        if frac > 1.5:
            vis[name]["suspect"] = "difference caught motion, not the object"

    worst = min(v["visible_fraction"] for v in vis.values())
    bad = [n for n, v in vis.items() if "suspect" in v]
    if (bad or worst < args_cli.min_visible) and not args_cli.allow_occluded:
        print(f"  SKIP {stem}: visibility {worst:.2f}"
              + (f", suspect {bad}" if bad else ""))
        return None

    state = build_state(coord, engine, tick=0, baskets=BASKETS,
                        zonemap=zonemap)

    # Let the renderer converge on the CURRENT scene before grabbing. hold()
    # renders on every other tick, so this is about 90 drawn frames.
    cell.hold(args_cli.render_warmup)

    on_table = [n for n in pool
                if float(scene[n].data.root_pos_w[0, 2]) > C.TABLE_H - 0.2]
    if sorted(on_table) != sorted(names):
        raise SystemExit(
            f"{stem}: the table holds {sorted(on_table)} but the scene is "
            f"meant to hold {sorted(names)}. An extra object in the frame "
            f"is a second thing the model can read, so the pair is no "
            f"longer minimal.")

    images = {}
    for cam in cameras:
        # ex2_cam is not the overhead camera, so the north-up correction
        # that table_cam needs would be wrong for it.
        b64 = grab_frame_b64(scene, cam, rot_k=(-1 if cam == "table_cam" else 0))
        fn = f"{stem}.png" if cam == cameras[0] else f"{stem}_{cam}.png"
        with open(os.path.join(out_dir, fn), "wb") as f:
            f.write(base64.b64decode(b64))
        images[cam] = fn

    positions_exact = {}
    settled = {}
    for name in names:
        p = scene[name].data.root_pos_w[0]
        positions_exact[name] = [float(p[0]), float(p[1])]
        # THE pose test, and the only reliable one. An upright mustard
        # bottle's origin sits 0.096 m above the table; fallen, 0.028 m.
        # The visible-area ratio does NOT distinguish them: p01_B scored
        # 1.12 while lying on its side. Height does.
        spec = C.OBJECT_SPECS[name]
        z = float(p[2]) - C.TABLE_H
        want = spec.get("rest_z")
        settled[name] = {"z_above_table": round(z, 4),
                         "expected_rest_z": want,
                         "pose_ok": want is not None and abs(z - want) < 0.010}

    rec = {"seq": stem, "round": 0, "condition": "V",
           "prompt_version": prompt_version(state),
           "enriched": True, "eligible": False, "model": None,
           "state": state, "positions_exact": positions_exact,
           "image_file": images[cameras[0]], "messages": [],
           "ex2": {"pair": pid, "member": member, "kind": kind,
                   "flip_object": flip, "partner": args_cli.partner,
                   "flip_xy": list(fxy), "partner_xy": list(pxy),
                   "idle": idle, "jitter": (args_cli.jitter
                                            if kind == "null" else 0.0),
                   "constructed": True, "camera": cameras[0],
                   "images": images, "settled": settled, "visibility": vis,
                   "px_per_m": round(scale, 2), "settle_residual_px": moved,
                   "note": args_cli.note}}
    with open(trail, "a") as f:
        f.write(json.dumps(rec) + "\n")

    print(f"  {stem}: " + ", ".join(
        f"{n.replace('ycb_','')} z {settled[n]['z_above_table']:.3f}"
        f"/{settled[n]['expected_rest_z']:.3f}"
        f"{'' if settled[n]['pose_ok'] else '  <-- POSE WRONG'}"
        for n in names))

    return rec


def main():
    scenes = read_spec(args_cli.spec)
    cameras = (["ex2_cam", "table_cam"] if args_cli.camera == "both"
               else [args_cli.camera])

    cast = sorted({args_cli.lying, args_cli.upright, args_cli.partner})
    for n in cast:
        if n not in YCB:
            raise SystemExit(f"{n!r} is not in the YCB registry")

    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    cfg = FourArmSceneCfg(num_envs=1, env_spacing=8.0)
    pool, needs_schema = add_ycb_pool(cfg, cast=cast)
    add_baskets(cfg)
    add_pad_markers(cfg)
    scene = InteractiveScene(cfg)
    for name in needs_schema:
        apply_physics_schemas(f"/World/envs/env_0/{name}")
    sim.reset()

    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    zonemap = ZoneMap()
    coord = Coordinator(cell, zonemap)
    engine = DisruptionEngine(scene, arms, pool, seed=0, profile="none",
                              device=sim.device, spawn_specs=spawn_specs(),
                              categories=sorted(CATEGORY_BASKET),
                              zonemap=zonemap)
    cell.settle()
    park_everything(scene, engine, pool, cell)

    os.makedirs(args_cli.out_dir, exist_ok=True)
    trail = os.path.join(args_cli.out_dir, "consults.jsonl")
    print(f"[ex2] {len(scenes)} scenes x 2 members, camera(s) {cameras}, "
          f"one Isaac session")

    done = skipped = 0
    for kind, pid, fxy, pxy in scenes:
        for member in ("A", "B"):
            rec = capture_one(cell, scene, coord, engine, zonemap,
                              kind, pid, member, fxy, pxy, cameras,
                              trail, args_cli.out_dir, pool)
            done += rec is not None
            skipped += rec is None

    print(f"\n[ex2] captured {done}, skipped {skipped} -> {trail}")
    print("  CHECK THE IMAGES: if the pose is not legible, a zero flip rate "
          "measures the camera, not the model.")
    simulation_app.close()
    # Isaac leaves non-daemon threads behind, so a clean close is not a
    # clean exit: without this the process hangs and has to be killed by
    # hand, which is exactly what made a 36-scene run unusable.
    os._exit(0)


if __name__ == "__main__":
    main()
