# runs/ — Experiment 2 run files, plus one Experiment 1 file

Named historically, like `out/`, and for the same reason: these names appear
in the write-up and in the analysis scripts. Not renamed.

See `docs/EX2_GUIDE.md` for the pipeline that produces them.

## The one Experiment 1 file that lives here

`ex1_L1-nowidth_V_gpt.jsonl` — 486 rows, GPT, No Width + Anonymous, **image
on** (`_V_` means the overhead frame was supplied). It is the image ablation,
and it belongs to Experiment 1 rather than Experiment 2. It sits here for
historical reasons and is not moved, because `docs/TABLE_PROVENANCE.md` and
`analysis/ex1/ex1_verify_tables.py` both reference this path.

The result is a clean null: 75.4% against 76.7% text-only, a difference of
-1.3 points [-8.3, 5.7].

## Main Experiment 2 datasets

| File | Rows | Role |
|---|---|---|
| `All_conflict.jsonl` | 2,827 | The main conflict dataset. Three models, seven rungs, 22 scenes, three repeats. About 55 rows are filtered in hygiene |
| `piece_dims_P2.jsonl` | 1,759 | The dimension-only condition |
| `piece_dims_P2_ur.jsonl` | 396 | The same under UR preference |

Some earlier notes name a `piece_dims_P2-2.jsonl`. No such file exists in this
tree.

## Instrument validation

| File | Checks |
|---|---|
| `ex2_cue.jsonl` | Cue validation |
| `ex2_mancheck.jsonl`, `ex2_mancheck_gpt.jsonl` | Can the model read pose when asked about nothing else |
| `ex2_seecheck.jsonl` | What the model says it sees, against the pose it names |
| `ex2_floor*.jsonl` | Perception floor |

## Superseded

`A_conflict_gemini.jsonl`, `A_conflict_noimage_P4.jsonl`, `A0_textonly.jsonl`,
`B_baseline*.jsonl` and `C_all_r2.jsonl` use an earlier condition-A/B/C naming
and are superseded by `All_conflict.jsonl`.

The nine `ex2_solo*.jsonl` files are development and pilot runs of the solo
design.

## Ambiguous names, decoded

These predate the naming convention and are kept for provenance only. None is
cited by any reported result.

| File | What it is |
|---|---|
| `pose.jsonl` | Early pose-reading probe |
| `probe.jsonl` | Early single-scene probe |
| `smoke_check.jsonl`, `smoke_gemini.jsonl`, `ex2_smoke.jsonl` | Smoke tests |
| `_check_A.jsonl`, `_check_V.jsonl` | Text-only and image-on spot checks |
| `ex2_quota_probe.jsonl` | Tier-1 rate-limit probe |
| `ex2_reps.jsonl`, `ex2_formats.jsonl` | Repeat-count and output-format pilots |
