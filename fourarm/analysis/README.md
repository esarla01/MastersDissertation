# analysis/

Grouped by scope. Shared infrastructure sits at the top level, and everything
that belongs to exactly one experiment sits in that experiment's directory.

```
analysis/
├── probe_store.py          shared infrastructure, imported by the rest
├── frozen_coord.py
├── probe_replay.py
├── build_master_set.py
├── refreeze_probe_set.py
├── ex1/                    Experiment 1 only, run directly, imported by nothing
├── ex2/                    Experiment 2 only, run directly, imported by nothing
├── episode/                pre-reframe episode analysis, no reported result
├── cell/                   cell geometry, independent of any experiment
└── retired/                dead, kept only because something still imports it
```

Every script is run from `fourarm/`, not from its own directory:

```bash
cd fourarm
python3 analysis/ex1/ex1_verify_tables.py
```

Each script adds the package root to `sys.path` by walking three directories
up from its own file. A script moved between these directories needs that
depth adjusted to match, and the shared modules at the top level use a
different depth again.

## Shared infrastructure

These are the only modules in this directory that anything imports, and they
stay at the top level because `harness/` and `experiments/ex2/run.py` import
them as `analysis.<name>`. Change them with care.

| Module | Does | Imported by |
|---|---|---|
| `probe_store.py` | Harvest audit trails into frozen, content-hashed probe sets. Also `legal_options()` and `capability_cause()` | 10 modules |
| `frozen_coord.py` | Rebuild a validator-compatible coordinator from a saved state, with no simulator | 11 modules, including `experiments/ex2/run.py` |
| `probe_replay.py` | Re-render a frozen state at a chosen condition and judge the answer | 3 modules |
| `build_master_set.py` | Merge harvested trails into one master set | run directly |
| `refreeze_probe_set.py` | Refreeze a set with sources excluded. Produced `ex1_v2` from `ex1_v1` | run directly |

`probe_store` and `frozen_coord` are shared between Experiment 1 and
Experiment 2, which is why neither sits in an experiment directory.

`probe_store.py` and `frozen_coord.py` are import-only modules. Running either
directly fails on `No module named 'core'`, which is expected.

## ex1/

Three files. Everything else that was here is in `attic/analysis_ex1_pipeline/`
or deleted; `git log -- fourarm/analysis/ex1/` has the reasons.

| Module | Does |
|---|---|
| `ex1_reproduce_tables.ipynb` | **Start here.** Rebuilds all thirteen published Experiment 1 tables from the frozen probe sets and the run files, explains each population and statistic, and asserts every generated table against the numbers printed in the thesis. Imports nothing from the analysis scripts except the deployed validator and the condition roster, so it is not checking its own arithmetic |
| `ex1_verify_tables.py` | The second opinion. Recomputes the same quantities with the standard library only. It and the notebook share `run_files.py` and nothing else, so a disagreement between them is a real finding |
| `ex1_chance_floor.py` | Computes the chance floor and width-blind reference lines into `out/ex1_chance_floor.json`. The notebook re-derives both and asserts they agree with the cached file |

Run both with `make verify-ex1` from the repository root.

Which run files each reads is not decided here. `fourarm/run_files.py` is the
single manifest, and its audit fails if a listed file is missing or if a
`.jsonl` appears under `out/` that no list accounts for.

## ex2/

| Module | Does |
|---|---|
| `ex2_analyse_dims.py` | The dimension-only condition, from `runs/piece_dims_P2.jsonl` |
| `ex2_pose_probe.py` | Can the model tell a lying bottle from an upright one |
| `ex2_perception_floor.py` | Can the model read the frame at all |
| `dims_analysis.txt` | Saved output of `ex2_analyse_dims.py` |

The rest of the Experiment 2 pipeline lives in `experiments/ex2/`. See
`docs/EX2_GUIDE.md`.

## episode/

These compute episode metrics from the era when the thesis benchmarked the
*system*. Since the reframe of 2 August the thesis evaluates a *model* at the
decision level, and **no reported result uses any of these**. They are kept
because the engineering-contribution appendix may still want them.

`episode_metrics.py`, `episode_trace.py`, `episode_input_audit.py`,
`episode_layout_audit.py`, `episode_verify_contention.py`,
`episode_verify_disruptions.py`, `episode_buffer_density.py`,
`episode_buffer_value.py`, `episode_calibrate_timing.py`.

## cell/

`cell_reach_envelope.py` computes the reach envelope from the real cell
config. It depends on no experiment.

## retired/

`retired_trap_check.py` is the trap detector for the abandoned Experiment 3
design. It stays here only because `episode/episode_buffer_density.py` imports
`classify_decision` from it. Resolving that pair would let both move to
`attic/`.
