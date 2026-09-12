# core/ — the cell, and the decision it asks for

The simulated four-arm cell and everything that runs inside it. **Nothing here
imports Isaac Lab**: the geometry, the validator and the allocators are plain
Python, which is what lets a frozen state be re-judged offline. Only the
`ycb/run_*` and `ycb/capture_*` entry points need a simulator.

Layered, and each layer's `__init__.py` says which it is.

## Layer 1 — `cell/`, the physical facts

| Module | Holds |
|---|---|
| `cell_config.py` | **The authority for every physical number.** `ARM_TYPES` carries reach, aperture, payload and the delicate flag; `ARMS` places the four arms. Nothing else restates them |
| `zones.py` | Zone queries over the per-arm reachability rasters. Pure numpy, no Isaac |
| `locks.py` | Zone locks. An arm may hold one zone at a time, which is what keeps two arms out of the same space |
| `arms.py` | Arm control, kept close to the Isaac Lab controller it drives |
| `scene_cfg.py` | Table, arms, object pool, camera |
| `reachability/` | The precomputed rasters, and `gen_reachability.py` which makes them |

Reachability is **looked up, not calculated**. The validator reads the raster,
the prompt prints it as `reach_ok_arms`, and the prompt tells the model to use
that list rather than derive reach from coordinates. One source, three readers.

## Layer 2 — `control/`

`tasks.py` holds the task queue, the per-arm state machines and the
coordinator. `disruptions.py` is the seeded disruption engine.

The division that matters: **the allocator names an arm and a task, and nothing
else.** Zone reservation, handovers and the second leg of a handover are the
coordinator's. That is what makes a decision small enough to freeze, replay and
compare across models.

## Layer 3 — `decision/`

| Module | Does |
|---|---|
| `state_builder.py` | Turns the cell into the state dict and the prompt. One template, one code path, so a condition cannot differ in wording as well as content |
| `random_allocator.py` | Uniform over pairs the validator accepts. The zero-knowledge floor, and what harvested most probe sets |
| `optimal_allocator.py` | Hungarian matching. The solver upper bound |
| `recording_allocator.py` | Wraps any allocator and records the decision state. This is what produces the audit trail probe sets are built from |
| `vlm_allocator.py` | Layer 4: renders, calls a model, parses the reply |
| `batch_vlm_allocator.py` | The whole-round joint variant |
| `model_registry.py` | An alias resolves to endpoint, model id, key variable and parameters, from `env/models.env`. **No key value lives in that file** — the harness checks, because it ships inside every zip |

`random_allocator` seeds its RNG on `(episode seed, sorted idle arms, ready
set)` rather than a call counter, so replaying a state reproduces the choice.
That is what makes harvesting deterministic.

**No probe set in this repository was harvested under a VLM.** A set shaped by
a model's behaviour would undercut the design, and `harvest/probe_audit.py`
asserts it.

## The validator

Not a module of its own — it is the coordinator's feasibility check, reached
through `harvest.probe_store.legal_options`. Five constraints: reach, grasp,
delicacy, payload, route. A rejected pair carries exactly one **binding cause**,
and `h_violations.py` holds that every rejection it can produce classifies to
one.

Capability is decomposed into grasp, payload and delicacy before the reason
string is read, because the cell reports all three under a single code and
Experiment 1 needs to know which bound.

## Changing something here

Physical numbers move the published tables. `cell_config.py` backs Table 3.1,
and the object registry backs A.1, so `make appendix` fails if either drifts
from what the thesis prints. That is the intended behaviour: decide whether the
thesis or the code is wrong, then fix one of them.

`docs/WALKTHROUGH.md` §1 and §2 put this in context. `make harness` covers it.
