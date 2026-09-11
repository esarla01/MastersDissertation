# harvest/ — from an episode to a frozen probe set

These five modules turn a simulation run into the frozen decision states both
experiments replay, and let a saved state be re-judged without a simulator.
None of them imports Isaac.

They lived in `analysis/` until 2026-09-11, which put the thing that *makes*
the data beside the things that *read* it.

| Module | Does |
|---|---|
| `probe_store.py` | Lifts decision points out of an episode trail, freezes them, content-hashes the set. Also `legal_options`, which runs the deployed validator — the experiments import this rather than reimplementing the rules |
| `build_master_set.py` | Merges harvested trails into one master set and records the per-experiment selections over it |
| `refreeze_probe_set.py` | Rebuilds a set with one or more harvest sources excluded. This is what produced `ex1_v2` from `ex1_v1` |
| `frozen_coord.py` | Rebuilds a validator-compatible coordinator from a saved state dict. The shim the whole offline path stands on |
| `probe_replay.py` | Renders a saved state at a chosen rung, asks a model, runs the real validator, emits one row per decision |
| `probe_audit.py` | Checks every set against its hash and against Appendix D |

`docs/SIMULATION.md` has the pipeline end to end. `make probes` runs the audit.

Nothing here reimplements a rule. The prompt comes from `build_prompt`, the
verdict from the deployed validator. That is deliberate: a second copy of the
rules would test the copy, not the experiment.
