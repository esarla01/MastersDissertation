# The cell, and how a probe set is made

Everything upstream of the experiments: what the simulated cell is, how an
episode runs, and how a run becomes the frozen probe set both experiments
replay.

The experiments themselves do not need any of this. They read frozen probe
sets and frozen run files, and `make verify` never starts a simulator. This
document is for changing the cell or harvesting new states.

---

## Where the code is

| Directory | Holds | Needs Isaac Lab |
|---|---|---|
| `fourarm/core/cell/` | Geometry, arms, zones, zone locks, reachability rasters | no |
| `fourarm/core/control/` | The task queue and the coordinator | no |
| `fourarm/core/decision/` | The allocators: random-valid, rule, optimal, VLM, recording | no |
| `fourarm/ycb/` | Object registry, scene assembly, layouts, and the episode and capture entry points | **yes**, for the `run_*` and `capture_*` scripts |
| `fourarm/instrumentation/` | Episode logging and the audit trail | no |
| `fourarm/harvest/` | Turning a trail into a frozen probe set, and replaying one offline | no |

The split that matters is the last column. Only the `ycb/run_*` and
`ycb/capture_*` scripts import Isaac. Everything else is plain Python, which is
what lets a saved decision state be re-rendered and re-judged without a
simulator.

---

## The cell

A 2.8 x 1.6 m table with four arms mounted around it: two UR10 on the long
sides, two Franka on the short edges. The two types differ in ways the
experiments turn on:

| | Reach (m) | Aperture (m) | Payload (kg) | Delicate |
|---|---|---|---|---|
| UR10 | 1.300 | 0.140 | 10 | no |
| Franka | 0.855 | 0.080 | 3 | yes |

Authoritative in `core/cell/cell_config.py` as `ARM_TYPES`; nothing restates
these numbers.

The aperture difference is nearly a factor of two, which is why grasp is the
constraint both experiments manipulate: a large part of the object set is
graspable by a UR10 and not by a Franka, so the constraint binds often enough
to measure.

Zones are a centre disc of radius 0.35 m plus four quadrants, one holder at a
time. Reachability is a precomputed raster per arm under
`core/cell/reachability/rasters/`, and it is authoritative — the validator uses
it rather than deriving reach from coordinates.

---

## How an episode runs

```
objects placed  ->  a decision round per idle arm  ->  allocator names (arm, task)
                ->  coordinator reserves zones     ->  arm executes
                ->  zones released                 ->  next round
```

The allocator only names an arm and a task. Zone locks, handovers and the
second leg of a handover are the coordinator's, not the allocator's. An
illegal assignment is recorded as made and judged afterwards by the validator,
so the trail is faithful to what was actually decided.

Four allocators, in `core/decision/`:

| Allocator | Picks | Used for |
|---|---|---|
| `random_allocator` | Uniformly among pairs the validator accepts | Harvesting states without involving a model |
| Rule | A legal pair in queue order | The rule-based baseline |
| `optimal_allocator` | Hungarian matching | Comparison |
| `vlm_allocator` | Renders the state, asks a model, parses the reply | The experiments |

`random_allocator` seeds its RNG on `(episode seed, sorted idle arms, ready
set)` rather than on a call counter, so replaying a state reproduces the
choice. That is what makes harvesting deterministic.

**Every probe set in this repository was harvested with the random-valid or
rule allocator. None was harvested under a VLM**, so the states are not shaped
by any model's behaviour.

---

## Running one (needs Isaac Lab)

```bash
cd fourarm
python3 ycb/run_ycb_sort.py --allocator b1 --layout capability_trap
```

`b1` is the rule allocator, `b2` the Hungarian matcher, `random` the
random-valid one. `ycb/cli_names.py` is authoritative for the names.

Scene capture for Experiment 2 is separate:

```bash
python3 ycb/capture_ex2_scene.py --spec ycb/ex2_block.txt
```

`ex2_block.txt` is the live spec: 34 positions, 17 per bank. Its header claims
every position was pre-screened against the rasters the validator uses, and
`ycb/screen_ex2_block.py` checks that claim — the harness runs it and requires
that exactly one position fail, `e10`, which is the position Chapter 5 excludes
as occluded.

`ycb/ex2_scenes.txt`, `ex2_east.txt` and `ex2_west.txt` are the retired
mustard pilots and are read by nothing.

---

## From a run to a probe set

An episode writes an audit trail. A probe set lifts each decision point out of
it and freezes everything needed to re-render the prompt and re-run the real
validator offline: the state dict, object positions, the camera frame, and
where the state came from.

```
episode trail  ->  harvest_trail()      probe_store.py
               ->  merge + dedup        build_master_set.py
               ->  refreeze             refreeze_probe_set.py
               ->  probes/<name>.json
```

**Probe sets are content-addressed.** The hash covers the identity fields of
every probe, in order. Editing one state moves the hash and invalidates every
run made against that set — which is the point: a run file is only meaningful
paired with the states it was answered on.

`harvest/frozen_coord.py` is the shim the whole offline path stands on. It
rebuilds a validator-compatible coordinator from a saved state dict. If it
misrepresented the cell, every replayed number would be wrong in the same
direction and nothing would look broken, which is why `h_frozen_coord.py`
tests it against a real episode rather than against expectations.

### The cast A chain, as Appendix D describes it

| Step | States | |
|---|---|---|
| Harvested from six runs | 278 | `master_v1.json` |
| Deduplicated to one state per distinct option set | 185 | `ex1_v1.json`, a loss of 93 |
| Refrozen without `seed_v3` | **162** | `ex1_v2.json`, the reported set |

`seed_v3` was dropped because it predates a correction to the mustard bottle's
declared grasp width, 0.058 to 0.096 m. Twenty-three of its 29 states had
survived deduplication into `ex1_v1`; none reaches `ex1_v2`. Since grasp is the
constraint both experiments manipulate, a state carrying the wrong width would
corrupt the measurement rather than merely add noise.

---

## Verifying it without a simulator

```bash
cd fourarm && python3 harvest/probe_audit.py
```

Checks all nine probe sets' content hashes, recomputes the 278 → 185 → 162
chain against Appendix D, confirms no `seed_v3` state reaches the reported
set, and checks the six per-source counts in Table D.1. `make verify` runs it,
and `harness/h_probe_sets.py` additionally tampers with a state to confirm the
hash actually moves.

What this cannot check is the harvest itself, which needs Isaac Lab. The
guarantee is that the frozen sets still hold what they held when they were
frozen, not that re-harvesting would reproduce them — different episodes visit
different states, which is the induced-state-distribution problem freezing
exists to remove.

---

## Two probe sets that exist and are not used

`ex3_v1.json` (135 states) and `ex3_setb_v1.json` (72) were harvested for a
third experiment that was not run. They are checked by the audit so that
"unused" stays a recorded decision rather than an oversight.
