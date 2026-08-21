# out/ — Experiment 1 run files

**Nothing in this directory is renamed, ever.** These filenames appear in
`docs/TABLE_PROVENANCE.md`, in `analysis/ex1/ex1_verify_tables.py`, and in the
thesis itself. They are the audit trail from a published number back to the
data that produced it. Renaming them would break exactly the traceability the
provenance record exists to give.

The names are historical rather than descriptive. This file is the
translation.

## Condition codes

The thesis uses prose names. The run files use the codes the experiment was
built under. They are frozen, so the mapping lives here instead.

| Thesis name | Display tag | Run-file code |
|---|---|---|
| Full Information | `P-FULL` | `L3` |
| Anonymous | `P-ANON` | `L3anon` |
| No Width | `P-NOWIDTH` | `L3nw` |
| No Width + Anonymous | `P-NOWIDTH-ANON` | `L1nw` |
| No Rules | `P-NORULES` | `L2` |
| Legal-Arm Control | `P-GIVENSET` | `L4` |

## Filename grammar

`ex1_[setb_]<model>_<code>[_r3|_r3b|_repair].jsonl`

- no suffix: one repeat (162 rows for cast A, 108 for cast B)
- `_r3`: three repeats (486 rows for cast A, 324 for cast B)
- `_r3b`: a re-run of a three-repeat cell, see below
- `_repair`: **not a run.** See "Do not use" below
- `setb_`: the second object cast, `probes/ex1_setb_v1.json`

## The 18 files that produce every published cast A number

Three models by six conditions. 6,804 rows total.

```
ex1_gemini_L3_r3      ex1_gpt_L3_r3       ex1_qwen_L3_r3
ex1_gemini_L3anon_r3  ex1_gpt_L3anon_r3   ex1_qwen_L3anon_r3
ex1_gemini_L3nw_r3    ex1_gpt_L3nw_r3     ex1_qwen_L3nw_r3
ex1_gemini_L1nw_r3    ex1_gpt_L1nw_r3b    ex1_qwen_L1nw_r3
ex1_gemini_L2         ex1_gpt_L2          ex1_qwen_L2
ex1_gemini_L4         ex1_gpt_L4          ex1_qwen_L4
```

**GPT's No Width + Anonymous is `_r3b`, not `_r3`.** The original was
destroyed on 16 August when a finished command was re-run and `replay_set`
opened `--out` in write mode, truncating 486 rows to 2. A `--force` guard now
prevents a repeat. `_r3b` is the honest re-run and is the correct file.

## Cast B, GPT only

`ex1_setb_gpt_{L3,L3nw,L1nw}_r3.jsonl`, 324 rows each. The single-repeat
versions without `_r3` are superseded and should not be used: the three-repeat
run moved the width gap from 9.6 points [-0.6, 21.2], which spanned zero, to
8.7 [3.9, 14.3], which does not.

## Do not use

These land in the same `(model, condition)` bucket as a real run and
**overwrite it**, because report scripts read files in alphabetical order.
This produced a wrong published figure that stood for two days.

| File | Why it is dangerous |
|---|---|
| `ex1_smoke_gpt_L3.jsonl` | 10 rows. Sorts after `ex1_gpt_L3_r3` and wins |
| `ex1_gpt_L3nw_repair2.jsonl` | Errored rows only. Sorts after the real run and wins |
| `ex1_gemini_L3nw_repair2.jsonl` | Same |
| `ex1_qwen_L3nw_repair.jsonl` | Same |
| `ex1_gpt_L3.jsonl` | Single repeat, collides with `ex1_gpt_L3_r3` |

**Pass run files by name, never by glob.** `ex1_verify_tables.py` hardcodes
the 18 good files for this reason.

## Reference lines

| File | Contents |
|---|---|
| `ex1_chance_floor.json` | Cast A chance floor and width-blind lines, per binding subset. Values are fractions of 1 |
| `ex1_setb_floors.json` | The same for cast B |

## Everything else here

| File | What it is |
|---|---|
| `harvest_01.json`, `harvest_smoke.json` | Raw harvest trails, superseded by the frozen sets in `probes/` |
| `random_2026*.json` | Random-valid allocator harvest runs, 18 and 19 August. Source material for the probe sets |
| `setb_s10*_frames/` | Rendered frames from cast B states. Not used by any analysis |
| `ex2_capture/` | 49 MB of frozen Experiment 2 scene captures. Ignored by git |
| `floor_illegal.txt`, `floor_wrong.txt`, `solo_prompt.txt`, `gemini_ladder.log` | Scratch output kept for provenance |
