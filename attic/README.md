# Attic

Code that is no longer on any live path. Retained so the lineage of the work
stays legible. Nothing here is imported by the package, and nothing here
should be read as describing the current design.

| File | Why it is here |
|---|---|
| `h_trap_check.py` | The regression gate for the above. Orphaned with it. |
| `ex1_mechanism.py` | Supported an explanation built on a mass hypothesis and the width-ordering of errors. The second object cast contradicted the width ordering, so the material does not hold across casts and was cut from the chapter. Should not be reintroduced. |
| `run_smoke_test.py` | L1 milestone test. Superseded. |
| `run_layer2_test.py` | L2 acceptance test. Superseded. |
| `run_layer3_test.py` | L3 acceptance test. Broken since condition B was retired: it calls `build_prompt(state, "B")`, which now raises. |
| `PLAYBOOK.md` | Describes the pre-August E1 to E6 scope against RQ1 to RQ6. It predates the reframe from benchmarking a system to evaluating a model at the decision level, and will mislead anyone who reads it as current. |

## Not moved, and why

`fourarm/analysis/ ex1/retired_trap_check.py` belongs here on merit. It is the trap
detector for the original Experiment 3 design, "judgement under scarcity",
which was retired on 18 August: the harvested states held too few genuine
traps to carry the claim, and an artificial trap setup was not endorsed.
Experiment 3 is now capability variation against task difficulty.

It stays in `analysis/` because `analysis/episode/episode_buffer_density.py` imports
`classify_decision` from it. `episode_buffer_density.py` is itself pre-reframe
episode analysis and is probably also dead, but that has not been confirmed,
so nothing has been moved. Resolving the pair is a small job and worth doing
before publication.

## Known breakage, not moved

`fourarm/core/decision/batch_vlm_allocator.py` imports `build_batch_prompt`
from `core/decision/state_builder.py`, and that function does not exist. The
module therefore cannot be imported. This predates the reorganisation and is
not caused by it. It is on no path used by any reported result, so it has been
left in place rather than moved or patched, but it should be fixed or retired
before publication.
