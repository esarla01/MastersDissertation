"""YCB sorting demo (step 3b): kitchen objects into CATEGORY baskets.

The YCB sibling of run_sorting_demo.py, same proven loop, three changes:
the pool comes from the ycb_objects registry (with physics schemas applied
to visual-only assets between scene build and sim.reset), spawning goes
through the pose-aware engine (upright rotations, true rest heights), and
semantics are categories (food / kitchenware / tools) instead of colours.

Spawn layout is deliberate: 8 objects are direct-deliverable by some arm,
3 (gelatin_box, mustard, large_clamp) require a handover, and the delicate
banana starts in franka_n's reach with a Franka-reachable basket.

Run:  python3 run_ycb_sort.py --headless --record                  (b1 rule)
      python3 run_ycb_sort.py --headless --record --allocator b2   (Hungarian)
      python3 run_ycb_sort.py --headless --record --allocator vlm1 (VLM Text)
      python3 run_ycb_sort.py --headless --record --allocator vlm2 (VLM Text+Image)
Outputs auto-name themselves <alloc>_<date>_<time>.{json,mp4}; --out-name
overrides (the matrix runner uses that for resumability).
"""

import os
import sys

# This script lives in ycb/, one level below the core modules. Put the
# parent folder on the import path so core imports resolve when launched
# as `python3 ycb/run_ycb_*.py` from the project root (or from anywhere).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import argparse
import math

from cli_names import CLI_CHOICES, normalize_allocator, unique_out_name
from layouts import LAYOUTS, LAYOUT_CASTS, cast_for  # tables + casts

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--record", action="store_true")
parser.add_argument("--max-ticks", type=int, default=12000,
                    help="hard episode cap; the run finalises (RESULT, "
                         "episode JSON, video) when it fires. The old "
                         "implicit cap was 60000, ~40 min of watching a "
                         "wedged cell before outputs appeared")
parser.add_argument("--objects", type=int, default=11,
                    help="number of objects to spawn (1-11, registry order); "
                         "small counts make cheap live-model runs")
parser.add_argument("--layout", default="designed",
                    choices=sorted(set(LAYOUTS) | set(LAYOUT_CASTS))
                            + ["seeded"],
                    help="a frozen validated layout from ycb/layouts.py "
                         "(the sampler auto-places any cast object a table "
                         "does not name), or 'seeded' to generate fully "
                         "from --seed. A layout that defines only a cast "
                         "(LAYOUT_CASTS, no frozen table) is selectable too "
                         "and gets sampled positions.")
parser.add_argument("--disruptions", default="none",
                    help="disruption profile passed to the engine "
                         "(e.g. none, mixed)")
parser.add_argument("--disrupt-horizon", type=float, default=None,
                    help="expected episode length in SECONDS, used to place "
                         "disruption events. Defaults to "
                         "cell_config.EPISODE_HORIZON_S. NOT --max-ticks, "
                         "which is a safety cap several times a real run")
parser.add_argument("--out-name", default=None,
                    help="episode JSON filename (for the matrix runner's "
                         "resumability); default keeps the timestamp name")
parser.add_argument("--seed", type=int, default=0,
                    help="layout seed (also recorded in the episode JSON)")
parser.add_argument("--timing", default="distance",
                    choices=("distance", "estimate"),
                    help="b2 cost currency. distance: metres (historical, "
                         "default, byte-identical to prior episodes). "
                         "estimate: ticks via the calibrated TIMING table, "
                         "so a franka metre costs 3.67x a ur10 metre.")
parser.add_argument("--b2-objective", default="minisum",
                    choices=("minisum", "minimax"),
                    help="b2 per-round objective. minisum: total cost "
                         "(Hungarian, default, historical). minimax: "
                         "bottleneck assignment, aligned with makespan.")
parser.add_argument("--b2-contention", type=float, default=0.0,
                    help="b2 contention surcharge on pairs whose zones are "
                         "held or reserved by another arm. 0.0 (default) is "
                         "the pre-registered contention-blind classical "
                         "baseline. Units follow --timing.")
parser.add_argument("--settle-wait", type=int, default=0,
                    help="hold an allocation round up to N ticks when fewer "
                         "than two arms are idle and one is finishing. 0 is "
                         "OFF and reproduces every pre-2026-08-02 episode. "
                         "Raises the share of decisions taken with a real "
                         "choice; expect a small makespan cost")
parser.add_argument("--settle-phases", default="tight",
                    choices=["tight", "broad"],
                    help="which arm phases count as finishing. tight is "
                         "SETTLING and PRE_TUCK (no travel); broad adds "
                         "GO_HOME and RETREAT (real return legs)")
parser.add_argument("--serialised", action="store_true",
                    help="EX1 v2: run the cell ONE TASK AT A TIME. A round "
                         "is offered only when every arm is idle, and only "
                         "the first assignable task in pool order is "
                         "offered. Every arm is therefore available at "
                         "every decision, and the allocator never chooses "
                         "which task. Costs makespan and makes every "
                         "contention measure vacuous, so it is for EX1 "
                         "state harvesting and never for EX3")
parser.add_argument("--eligible-arms", action="store_true",
                    help="ABLATION (vlm only): give the model a resolved "
                         "eligible_arms list per task, reach and capability "
                         "together, instead of the numbers to work it out "
                         "from. Stamped as prompt_version ...+eligible so it "
                         "can never be pooled with the default column.")
parser.add_argument("--record-states", action="store_true",
                    help="write a harvestable consults.jsonl for a NON-VLM "
                         "column by wrapping its allocator in "
                         "RecordingAllocator. Decisions are unchanged: the "
                         "wrapper records the state and returns the "
                         "delegate's result untouched. A probe set stores "
                         "states, not decisions, so harvesting this way "
                         "costs no model calls and lets a set draw from "
                         "several allocators instead of inheriting one "
                         "model's arm preference as its coverage.")
parser.add_argument("--audit-cameras", default="table_cam",
                    help="comma list of camera prims whose view is SAVED "
                         "per consult in the audit trail (vlm only). Does "
                         "not change what the model is sent: condition V "
                         "still sends the table_cam frame and condition A "
                         "still sends none. EX2 showed a viewpoint has to "
                         "be validated against an experiment's visual "
                         "requirement (table_cam cannot resolve upright "
                         "from lying; ex2_cam occludes the region between "
                         "the Frankas), and re-running Isaac to revisit "
                         "that choice is expensive, so a harvest should "
                         "pass 'table_cam,ex2_cam' and let replay decide. "
                         "Any camera already sent as the primary frame is "
                         "skipped rather than written twice.")
parser.add_argument("--allocator", default="b1", choices=CLI_CHOICES,
                    help="b1: rule baseline. b2: Hungarian matcher. "
                         "vlm1: VLM Text. vlm2: VLM Text+Image. "
                         "bvlm1/bvlm2: BATCH VLM (whole round decided "
                         "jointly), Text / Text+Image. "
                         "(oracle/opt accepted as legacy aliases)")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
ALLOC_SHORT, ALLOC_KIND, ALLOC_CONDITION = \
    normalize_allocator(args_cli.allocator)
if args_cli.out_name:                   # matrix runner's explicit name
    OUT_STEM = (args_cli.out_name[:-5]
                if args_cli.out_name.endswith(".json")
                else args_cli.out_name)
else:                                   # auto: <alloc>_<date>_<time>
    OUT_STEM = unique_out_name(ALLOC_SHORT)
print(f"[ycb] column {ALLOC_SHORT} (kind={ALLOC_KIND}"
      + (f", condition={ALLOC_CONDITION}" if ALLOC_CONDITION else "")
      + f"), outputs out/{OUT_STEM}.json"
      + (f" + out/{OUT_STEM}.mp4" if args_cli.record else ""))
args_cli.enable_cameras = True
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import isaaclab.sim as sim_utils                       # noqa: E402
from isaaclab.scene import InteractiveScene            # noqa: E402

from core.cell import cell_config as C                                # noqa: E402
from core.cell.scene_cfg import FourArmSceneCfg, add_pad_markers  # noqa: E402
from ycb_scene import (add_baskets, add_ycb_pool, spawn_specs, verify_basket_capacity,
                       validate_layout,     # noqa: E402
                       oracle_dest, category_of, BASKETS,
                       CATEGORY_BASKET, CATCH_RADIUS)
from ycb_objects import apply_physics_schemas          # noqa: E402
from core.cell.arms import Arm, Cell                             # noqa: E402
from core.control.disruptions import DisruptionEngine               # noqa: E402
from core.cell.zones import ZoneMap                              # noqa: E402
from core.control.tasks import Coordinator                          # noqa: E402
from instrumentation.recorder import Recorder                          # noqa: E402
from core.decision.vlm_allocator import VLMAllocator                 # noqa: E402

# The hand-placed demo layout, keyed BY NAME so registry growth can never
# silently shift pairings. Any cast object missing from this dict is
# auto-placed by the seeded sampler, so adding an object to the experiment
# is a registry edit ONLY. ~8 direct tasks, 3 handovers by design; the
# delicate banana starts in franka_n's reach.
# NOTE (2026-07-29): this table is now a DOCUMENTED DUPLICATE of
# layouts.LAYOUTS["designed"]. Selection reads the frozen registry, not
# this dict, so the two cannot silently diverge into different runs; the
# assertion below fails loudly if anyone edits one and not the other. The
# per-object commentary is kept here because it explains WHY each spawn
# sits where it does, which layouts.py does not record.
DESIGNED = {
    "soup_can":     (-0.82, 0.22),   # food nw: ur_w direct (off the wall face)
    "banana":       (0.05, 0.30),    # food nw: franka_n direct (delicate)
    "gelatin_box":  (0.82, 0.22),    # food nw: HANDOVER (ur_e side, off the wall)
    "meat_can":     (-0.85, -0.25),  # food nw: ur_w direct (UR-only)
                                     #   (moved off the grown tools wall:
                                     #    old spot left 3.5 cm to the wall
                                     #    face vs a 5 cm half-width)
    "mustard":      (0.75, -0.25),   # food nw: HANDOVER (ur_e side)
    "mug":          (0.30, 0.55),    # kitchenware ne: ur_e direct (UR-only)
    "bowl":         (-0.30, 0.55),   # kitchenware ne: franka_n direct
    "mug2":         (0.65, 0.02),    # kitchenware ne: ur_e direct (UR-only;
                                     #   the pitcher's old solved spot, same
                                     #   delivery pattern)
    "power_drill":  (-0.65, -0.02),  # tools sw: ur_w direct
    "large_clamp":  (0.40, -0.05),   # tools sw: HANDOVER (UR-only, east)
                                     #   (moved when the pads moved inward
                                     #    for the basket walls: the old spot
                                     #    sat 13 cm from pad_se, close enough
                                     #    that an object placed on that pad
                                     #    would touch it)
    "wood_block":   (-0.15, -0.25),  # moved 2026-07-19: the old spot
                                     #   (-0.15,-0.45) was 0.21 m from
                                     #   franka_s's base, inside its parked
                                     #   fold, which nudged the wood into
                                     #   the dead zone and FAILED the task  # tools sw: ur_w direct (UR-only)
}
assert DESIGNED == LAYOUTS["designed"], (
    "run_ycb_sort.DESIGNED has drifted from layouts.LAYOUTS['designed']; "
    "edit layouts.py, which is what actually runs")


def cast_names():
    """The objects this run spawns. Computed BEFORE the scene is built,
    because add_ycb_pool fills the pool and defaults to registry order: a
    layout cast applied only later would set the positions and the basket
    checks while the wrong objects spawned (found on set_b, 2026-08-18)."""
    from ycb_objects import YCB
    return cast_for(args_cli.layout,
                    list(YCB))[:max(1, min(args_cli.objects, len(YCB)))]


def main():
    sim = sim_utils.SimulationContext(sim_utils.SimulationCfg(dt=C.SIM_DT))
    cfg = FourArmSceneCfg(num_envs=1, env_spacing=8.0)
    cast = cast_names()
    pool, needs_schema = add_ycb_pool(cfg, cast=cast)
    add_baskets(cfg)
    add_pad_markers(cfg)               # white visual tiles, no collision
    scene = InteractiveScene(cfg)
    # visual-only YCB assets: apply RigidBodyAPI + collision BEFORE reset,
    # the window where Isaac Lab checks for them (proven by run_ycb_probe)
    for name in needs_schema:
        apply_physics_schemas(f"/World/envs/env_0/{name}")
    sim.reset()
    arms = {n: Arm(n, scene, sim.device) for n in C.ARMS}
    cell = Cell(sim, scene, arms)
    if args_cli.record:
        cell.recorder = Recorder(f"out/{OUT_STEM}.mp4", every=2, fps=30)
    zonemap = ZoneMap()

    def _already_sorted(name):
        """The runner's own scoring test, reused by the disruption engine
        so a displacement cannot un-sort an object that is already home
        and turn a recovery test into a scoring test."""
        bx, by = oracle_dest(category_of(name))
        p = scene[name].data.root_pos_w[0]
        return math.hypot(float(p[0]) - bx, float(p[1]) - by) < CATCH_RADIUS

    engine = DisruptionEngine(scene, arms, pool, seed=args_cli.seed,
                              profile=args_cli.disruptions,
                              device=sim.device, spawn_specs=spawn_specs(),
                              # events must fire INSIDE this run, the
                              # urgency command must name a real category,
                              # and a displaced object must land somewhere
                              # a capable arm can still serve
                              horizon_s=(args_cli.disrupt_horizon
                                         or C.EPISODE_HORIZON_S),
                              categories=sorted(CATEGORY_BASKET),
                              is_sorted=_already_sorted,
                              zonemap=zonemap)
    cell.settle()

    if ALLOC_KIND == "vlm":
        holder = {}
        # Cameras SAVED per consult. Condition V already sends the
        # table_cam frame, and grab_frame_b64 writes it as the primary, so
        # naming it again here would write the same PNG twice per consult.
        _audit_cams = tuple(c.strip() for c in
                            args_cli.audit_cameras.split(",") if c.strip())
        if ALLOC_CONDITION == "V":
            _audit_cams = tuple(c for c in _audit_cams if c != "table_cam")
        alloc = VLMAllocator(lambda: holder["c"], engine,
                             condition=ALLOC_CONDITION,
                             baskets=BASKETS, timeout=60.0,
                             eligible=args_cli.eligible_arms,
                             fallback_resolver=lambda t: oracle_dest(
                                 category_of(t.obj)),
                             audit_dir=f"out/{OUT_STEM}_frames",
                             audit_cameras=_audit_cams)
        coord = Coordinator(cell, zonemap, allocate=alloc, engine=engine,
                            settle_wait=args_cli.settle_wait,
                            settle_phases=args_cli.settle_phases,
                            serialised=args_cli.serialised)
        holder["c"] = coord
    elif ALLOC_KIND == "bvlm":
        # BATCH VLM: one model call decides the whole round jointly (every
        # idle arm at once), the joint-decision counterpart of vlm1/vlm2.
        # Same conditions and validator; the Coordinator applies the cached
        # plan across the round without re-calling the model per claim.
        from core.decision.batch_vlm_allocator import BatchVLMAllocator
        holder = {}
        alloc = BatchVLMAllocator(lambda: holder["c"], engine,
                                  condition=ALLOC_CONDITION,
                                  baskets=BASKETS, timeout=60.0,
                                  eligible=args_cli.eligible_arms,
                                  fallback_resolver=lambda t: oracle_dest(
                                      category_of(t.obj)),
                                  audit_dir=f"out/{OUT_STEM}_frames")
        coord = Coordinator(cell, zonemap, allocate=alloc, engine=engine,
                            settle_wait=args_cli.settle_wait,
                            settle_phases=args_cli.settle_phases,
                            serialised=args_cli.serialised)
        holder["c"] = coord
    elif ALLOC_KIND == "opt":
        from core.decision.optimal_allocator import OptimalAllocator
        holder = {}
        opt = OptimalAllocator(lambda: holder["c"],
                               dest_resolver=lambda t: oracle_dest(
                                   category_of(t.obj)),
                               objective=args_cli.b2_objective,
                               timing=args_cli.timing,
                               lambda_contention=args_cli.b2_contention)
        coord = Coordinator(cell, zonemap, allocate=opt, engine=engine,
                            settle_wait=args_cli.settle_wait,
                            settle_phases=args_cli.settle_phases,
                            serialised=args_cli.serialised)
        holder["c"] = coord
        alloc = opt                    # logger records stats + matrix log
    elif ALLOC_KIND == "random":
        from core.decision.random_allocator import RandomValidAllocator
        holder = {}
        rnd = RandomValidAllocator(lambda: holder["c"], seed=args_cli.seed)
        # random tasks are submitted WITH oracle destinations, exactly like
        # b1 and b2 (the non-vlm branch below), so the column measures
        # allocation randomness among legal moves, not destination guessing
        allocate_fn = rnd
        if args_cli.record_states:
            # RandomValidAllocator IS an object, unlike b1, so the recorder
            # wraps it as the delegate rather than standing in for a
            # default function. Its decisions are returned untouched.
            #
            # Harvesting from random as well as b1 is a coverage measure,
            # not a redundancy: rule_based_allocate takes the nearest
            # capable base, so a pure-b1 set only ever contains the states
            # nearest-base greedy walks into. Random has no systematic arm
            # preference, so it reaches states neither greedy nor a model
            # would produce. provenance.source records which allocator
            # produced each state, so the mix is reportable and legality
            # rates can be compared across sources.
            from core.decision.recording_allocator import RecordingAllocator
            allocate_fn = RecordingAllocator(
                lambda: holder["c"], engine, zonemap=zonemap,
                baskets=BASKETS, audit_dir=f"out/{OUT_STEM}_frames",
                cameras=tuple(c.strip() for c in
                              args_cli.audit_cameras.split(",") if c.strip()),
                delegate=rnd,
                source_note=f"random:{args_cli.layout}")
        coord = Coordinator(cell, zonemap, allocate=allocate_fn,
                            engine=engine,
                            settle_wait=args_cli.settle_wait,
                            settle_phases=args_cli.settle_phases,
                            serialised=args_cli.serialised)
        holder["c"] = coord
        alloc = rnd                    # logger records stats + plan log
    else:
        alloc = None
        # b1 is not an allocator OBJECT: Coordinator's default allocate is
        # rule_based_allocate, so there is nothing to hang a trail on
        # unless one is supplied. RecordingAllocator delegates to that same
        # function, so the column's decisions are bit-identical.
        if args_cli.record_states:
            from core.decision.recording_allocator import RecordingAllocator
            holder = {}
            rec = RecordingAllocator(lambda: holder["c"], engine,
                                     zonemap=zonemap, baskets=BASKETS,
                                     audit_dir=f"out/{OUT_STEM}_frames",
                                     cameras=tuple(
                                         c.strip() for c in
                                         args_cli.audit_cameras.split(",")
                                         if c.strip()),
                                     source_note=f"{ALLOC_KIND}:"
                                                 f"{args_cli.layout}")
            coord = Coordinator(cell, zonemap, allocate=rec, engine=engine,
                                settle_wait=args_cli.settle_wait,
                                settle_phases=args_cli.settle_phases,
                                serialised=args_cli.serialised)
            holder["c"] = coord
        else:
            coord = Coordinator(cell, zonemap, engine=engine,
                                settle_wait=args_cli.settle_wait,
                                settle_phases=args_cli.settle_phases,
                                serialised=args_cli.serialised)

    # spawn the cast and submit one task per object. In vlm mode the task
    # has NO destination: choosing the basket IS the allocator's job.
    from ycb_scene import sample_layout
    # `cast` came from cast_names() above and was already used to build the
    # pool, so the objects spawned and the objects checked are the same set.
    spawns = sample_layout(
        cast, seed=args_cli.seed,
        designed=LAYOUTS.get(args_cli.layout))   # None for "seeded"
    validate_layout(spawns, cast)          # belt and braces
    verify_basket_capacity([f"ycb_{n}" for n in cast])
    names = []
    for x, y in spawns:
        names.append(engine.activate_object(x, y))
    spawn_by_name = dict(zip(names, spawns))   # for the episode JSON
                                               # (episode_metrics.py: reach truth)
    cell.hold(60)
    for name in names:
        cat = category_of(name)
        if ALLOC_KIND in ("vlm", "bvlm"):  # model chooses the basket
                                          # (bug fixed 2026-07-25: the old
                                          # == "vlm" test never matched
                                          # vlm1/vlm2 after the CLI rename;
                                          # batch heads choose baskets too)
            coord.submit(name, None)
            print(f"[ycb] {name:>16} is {cat:>11} -> model must choose")
        else:
            coord.submit(name, oracle_dest(cat))
            print(f"[ycb] {name:>16} is {cat:>11} -> {CATEGORY_BASKET[cat]}")

    for t in range(args_cli.max_ticks):
        # Disruption schedule (2026-07-26 FIX): engine.step was never
        # called from this runner, so --disruptions was inert and no
        # displacement or arm failure ever fired. Event times are in
        # SECONDS, so the tick counter is converted with the physics dt.
        # profile "none" builds an empty schedule, so every validated
        # baseline is bit-identical to before.
        for ev in engine.step(t * cell.dt):
            # Copy EVERY param except the keys coord.event owns. The old
            # whitelist silently dropped "skipped", so a spawn that
            # correctly reported an exhausted object pool was logged as an
            # inert spawn with object=null and no reason, which is exactly
            # the failure mode the reason was added to remove.
            coord.event("disruption", kind=ev.kind,
                        text=f"[disrupt] t={t} {ev.kind} {ev.params}",
                        **{k: v for k, v in ev.params.items()
                           if k not in ("tick", "type", "kind")})
        coord.tick()
        cell.tick(render=args_cli.record or (t % 4 == 0))
        if t % 1200 == 0:
            todo = sum(1 for k in coord.pool if not k.done and not k.failed)
            print(f"[ycb] tick {t:>6}  tasks left {todo}")
        if not coord.pending():
            break
    else:
        left = [k for k in coord.pool if not k.done and not k.failed]
        coord.event("tick_limit",
                    text=(f"\n[ycb] TICK LIMIT ({args_cli.max_ticks}) "
                          f"reached with {len(left)} task(s) unfinished: "
                          f"{[(k.id, k.obj) for k in left]}"),
                    limit=args_cli.max_ticks,
                    unfinished=[[k.id, k.obj] for k in left])

    print("\n[ycb] RESULT")
    correct = 0
    objects_report = []
    for name in names:
        cat = category_of(name)
        bx, by = oracle_dest(cat)
        p = scene[name].data.root_pos_w[0]
        d = math.hypot(float(p[0]) - bx, float(p[1]) - by)
        ok = d < CATCH_RADIUS
        correct += ok
        objects_report.append({"name": name, "category": cat,
                               "dist_cm": round(d * 100, 1),
                               "sorted": bool(ok),
                               "spawn_xy": [round(float(c), 4) for c in
                                            spawn_by_name[name]]})
        print(f"  {name:>16} ({cat:>11}): {d*100:5.1f} cm from its basket  "
              f"{'SORTED' if ok else 'MISPLACED'}")
    verdict = "PASS" if correct == len(names) else "CHECK"
    print(f"\n[ycb] {correct}/{len(names)} objects in the right basket, "
          f"requeues={coord.m.requeued}, "
          f"blocked_ticks={sum(coord.m.blocked.values())}")
    print(f"[ycb] VERDICT: {verdict}")
    from instrumentation.episode_logger import EpisodeLogger
    from core.decision.state_builder import PROMPT_VERSION
    EpisodeLogger(seed=args_cli.seed, layout=args_cli.layout,
                  allocator=ALLOC_SHORT,
                  condition=(alloc.condition if alloc is not None else None),
                  disruptions=args_cli.disruptions,
                  # The version the model was ACTUALLY shown, not the module
                  # constant. With the ablation live the two differ by design,
                  # so reading the constant here would stamp every ablation
                  # episode as if it were a default one.
                  prompt_version=getattr(alloc, "prompt_version",
                                         PROMPT_VERSION),
                  eligible_arms=bool(args_cli.eligible_arms),
                  timing=args_cli.timing,
                  b2_objective=(args_cli.b2_objective
                                if ALLOC_KIND == "opt" else None),
                  b2_contention=(args_cli.b2_contention
                                 if ALLOC_KIND == "opt" else None),
                  scene="ycb",
                  objects=len(names)).finish(
        coord, alloc=alloc, objects=objects_report, verdict=verdict,
        filename=f"{OUT_STEM}.json",
        extra_metrics={"sorted_correct": int(correct),
                       "sorted_total": len(names)})
    if alloc is not None:
        print(f"[ycb] model stats: {alloc.stats}")
        for entry in alloc.log:
            print("  " + str(entry))
    if cell.recorder is not None:
        cell.recorder.close()
    simulation_app.close()


if __name__ == "__main__":
    main()