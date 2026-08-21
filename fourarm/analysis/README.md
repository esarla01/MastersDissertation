# analysis/

Flat by design. The path bootstrap in each script computes the package root
as one directory up, so nesting these into subfolders would break every one
of them. The prefix does the grouping instead.

| Prefix | Meaning |
|---|---|
| *(none)* | Shared infrastructure, imported by the rest |
| `ex1_` | Experiment 1 only, run directly, imported by nothing |
| `ex2_` | Experiment 2 only, run directly, imported by nothing |
| `episode_` | Pre-reframe episode-level analysis, not used by any reported result |
| `cell_` | Cell geometry, independent of any experiment |
| `retired_` | Dead, kept only because something still imports it |

## Shared infrastructure

These are the only modules in this directory that anything imports. Change
them with care.

| Module | Does | Imported by |
|---|---|---|
| `probe_store.py` | Harvest audit trails into frozen, content-hashed probe sets. Also `legal_options()` and `capability_cause()` | 10 modules |
| `frozen_coord.py` | Rebuild a validator-compatible coordinator from a saved state, with no simulator | 11 modules, including `experiments/ex2/run.py` |
| `probe_replay.py` | Re-render a frozen state at a chosen condition and judge the answer | 3 modules |
| `build_master_set.py` | Merge harvested trails into one master set | run directly |
| `refreeze_probe_set.py` | Refreeze a set with sources excluded. Produced `ex1_v2` from `ex1_v1` | run directly |

`probe_store` and `frozen_coord` are shared between Experiment 1 and
Experiment 2, which is why neither carries an experiment prefix.

## Experiment 1

Run in roughly this order. All read from `out/` and `probes/`.

| Module | Does |
|---|---|
| `ex1_chance_floor.py` | Computes the chance floor and width-blind reference lines. Writes `out/ex1_chance_floor.json` |
| `ex1_report.py` | The main tables, one pass over every run file |
| `ex1_verify_tables.py` | Regenerates every published table from raw data and diffs it against the thesis. **Start here.** See `docs/TABLE_PROVENANCE.md` |
| `ex1_audit_states.py` | Checks the probe set and pipeline before spending on a run |
| `ex1_audit_rows.py` | Independently re-scores a finished run |
| `ex1_explain_route.py` | Why a handover was or was not available, pad by pad. The R5 sensitivity check |
| `ex1_repair_failures.py` | Feedback on rejections in a finished run |
| `ex1_find_missing_rows.py` | Finds states a run did not cover |

`ex1_report.py` hardcodes the cast A reference lines, so its cast B output
prints the wrong header. Use `out/ex1_setb_floors.json` for cast B.

## Experiment 2

| Module | Does |
|---|---|
| `ex2_analyse_dims.py` | The dimension-only condition, from `runs/piece_dims_P2.jsonl` |
| `ex2_pose_probe.py` | Can the model tell a lying bottle from an upright one |
| `ex2_perception_floor.py` | Can the model read the frame at all |

The rest of the Experiment 2 pipeline lives in `experiments/ex2/`. See
`docs/EX2_GUIDE.md`.

## Episode-level, pre-reframe

These compute episode metrics from the era when the thesis benchmarked the
*system*. Since the reframe of 2 August the thesis evaluates a *model* at the
decision level, and **no reported result uses any of these**. They are kept
because the engineering-contribution appendix may still want them.

`episode_metrics.py`, `episode_trace.py`, `episode_input_audit.py`,
`episode_layout_audit.py`, `episode_verify_contention.py`,
`episode_verify_disruptions.py`, `episode_buffer_density.py`,
`episode_buffer_value.py`, `episode_calibrate_timing.py`.

## Retired

`retired_trap_check.py` is the trap detector for the abandoned Experiment 3
design. It stays here only because `episode_buffer_density.py` imports
`classify_decision` from it. Resolving that pair would let both move to
`attic/`.
