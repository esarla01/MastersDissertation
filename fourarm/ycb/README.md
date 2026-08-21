# ycb/ - the YCB "clear the table" experiment

Everything that knows these eleven specific objects exist lives here.
The core (parent folder) knows about *objects in general*: it reads
per-object facts from `cell_config.OBJECT_SPECS`, which this folder
fills in at scene-build time. If a future experiment uses different
objects, it gets its own folder like this one and touches core not at all.

## The pipeline, in the order it was built (and should be understood)

**Step 0 - `run_ycb_probe.py`: do the assets exist, and what are they?**
Standalone (no arms, no coordinator). Resolves each candidate asset
(physics variant, visual-only, or missing), applies physics schemas to
visual-only ones, drops everything on a ground plane, and MEASURES:
bounding box, minimum grasp span, resting height, mass. Prints a
paste-ready specs block and saves an overhead frame. Every number in the
registry traces back to this script's output, not to datasheets.
Run: `python3 ycb/run_ycb_probe.py --headless`

**`ycb_objects.py` - the registry (single source of truth).**
Pure data plus three helpers. Per object: USD file + variant, category,
grasp span (measured, or authored for the non-convex drill/bowl), real
product mass, resting height, upright rotation (some assets are authored
lying down), delicate flag (banana: force-controlled grasp, Franka-only).
`register_specs` publishes an object's facts into core's OBJECT_SPECS;
`apply_physics_schemas` adds rigid-body physics to visual-only assets
(must run after scene build, before sim.reset).
After the supervisor meeting, cast changes are EDITS TO THIS FILE ONLY.

**Step 1 - `run_ycb_smoke.py`: can the executive move one real object?**
One soup can, one arm, one pick-and-place, driven by hand at Layer 1.
Tests the three things cube code silently assumed: attach tolerance on a
taller root, set-down at the measured rest height (wrong height =
PhysX ejection), and the carry on video. Includes a post-release drift
check as the ejection detector.
Run: `python3 ycb/run_ycb_smoke.py --headless [--record]`

**`ycb_scene.py` - the world of the experiment.**
Three category baskets (food nw, kitchenware ne, tools sw), each in its
own lock zone, each served by one UR + one Franka, each >catch-radius
from every exchange pad. `add_ycb_pool` builds the object pool from the
registry (parked off-table, correct variant/rotation) and registers
specs. `spawn_specs` gives the disruption engine per-object spawn poses.
`validate_layout` is the fail-fast guard: every object must sit in the
safe pick annulus of at least one capable arm (inner bound per arm type:
UR 0.35 m - learned when the pitcher entangled ur_e's column - Franka
0.25 m assumed; outer bound 0.92 x reach).

**Step 3 - `run_ycb_sort.py`: the full experiment episode.**
Assembles everything: scene + pool + baskets, schemas, pose-aware
spawning, one task per object, coordinator loop, scoring against the
catch radius, episode JSON. Oracle mode = destinations from the category
table (rule baseline); vlm mode = the model chooses each basket.
Run: `python3 ycb/run_ycb_sort.py --headless [--record] [--allocator vlm]`

## What deliberately does NOT live here
Core files changed during the YCB work, but only into *generalisations
with cube-safe defaults*: per-object rest heights in the executive's
set-down (tasks.py, arms.py), pose-aware teleport (disruptions.py),
category/delicate fields in the state (state_builder.py), the delicate
capability clause (cell_config.py). None of them names a YCB object.
The cube demos still run byte-for-byte identically.

## Import rule
Files here start by adding the parent folder to the import path, so they
can be launched from the project root (`python3 ycb/run_ycb_sort.py`)
and imported by tests from anywhere. The project stays otherwise flat.
