# Experiment 1: table and figure provenance

Every number in the Experiment 1 chapter, where it comes from, and how to
regenerate it.

Run `make verify` from the repository root rather than trusting a count written
here: three different totals were quoted in this file and the README at various
points, and all three were stale. The gate reports the current number.

> **The table list below uses the labels the chapter carried in August.** Six of
> them have since been renamed or dropped: `spine`, `gaps`, `offspine`,
> `consistency`, `objects` and `optionspace` are no longer in the thesis, and
> the results tables it does carry are `design`, `baseline`, `composition`,
> `signatures`, `castb` and `swap`. For the current set, and for a table-by-table
> rebuild from the raw data, run
> `notebooks/ex1/ex1_reproduce_tables.ipynb`. It regenerates all thirteen
> published tables and checks each against the thesis; its section 20 is the
> up-to-date provenance list.

Run the whole check from the `fourarm/` directory:

```bash
python3 analysis/ex1/ex1_verify_tables.py
```

One table at a time:

```bash
python3 analysis/ex1/ex1_verify_tables.py --table spine --table gaps
python3 analysis/ex1/ex1_verify_tables.py --quiet          # failures only
```

Exit status is 0 when everything passes and 1 otherwise, so it works as a
pre-submission gate. The script uses only the standard library and reads the
frozen data directly, so it is an independent check on
`ex1_reproduce_tables.ipynb` rather than a re-run of it. If the two ever disagree, one of them has a bug and the
disagreement is the finding.

---

## Where the scripts live

`analysis/` is flat and prefixed rather than nested, because each script's
path bootstrap computes the package root as one directory up. `ex1_` marks
Experiment 1 tools, `ex2_` marks Experiment 2, `episode_` marks pre-reframe
episode analysis used by no reported result, and unprefixed modules are
shared infrastructure. See `fourarm/analysis/README.md`.

Directory-level manifests: `fourarm/out/README.md` decodes the Experiment 1
run filenames and lists the files that must never be passed to a report.
`fourarm/runs/README.md` does the same for Experiment 2.

---

## Source data

| File | Contents | Hash (first 16) |
|---|---|---|
| `probes/ex1_v2.json` | Cast A, 162 frozen states | `e23cd23479778f76` |
| `probes/ex1_setb_v1.json` | Cast B, 108 frozen states | `b8abfb3391dd6d52` |
| `out/ex1_chance_floor.json` | Cast A reference lines | derived from `ex1_v2` |
| `out/ex1_setb_floors.json` | Cast B reference lines | derived from `ex1_setb_v1` |
| `out/ex1_<model>_<cond>.jsonl` | Cast A runs, 18 files, 6804 rows | see below |
| `out/ex1_setb_gpt_<cond>_r3.jsonl` | Cast B runs, 3 files, 972 rows | |
| `out/ex1_casta_gpt_nowidth-anon_r3_image.jsonl` | Image-on cell, GPT, 486 rows. Backs no table | |

### The 18 cast A run files

Three models by six conditions. 486 rows is 162 states by 3 repeats, 162 rows
is a single repeat.

| Condition | Tag | Run-file code | Repeats | Rows |
|---|---|---|---|---|
| Full Information | `P-FULL` | `L3` | 3 | 486 |
| Anonymous | `P-ANON` | `L3anon` | 3 | 486 |
| No Width | `P-NOWIDTH` | `L3nw` | 3 | 486 |
| No Width + Anonymous | `P-NOWIDTH-ANON` | `L1nw` | 3 | 486 |
| No Rules | `P-NORULES` | `L2` | 1 | 162 |
| Legal-Arm Control | `P-GIVENSET` | `L4` | 1 | 162 |

GPT's No Width + Anonymous run is `ex1_gpt_L1nw_r3b.jsonl`, not `_r3`. The
original was destroyed on 16 August when a finished command was re-run and
`replay_set` opened `--out` in write mode. A `--force` guard now prevents a
repeat.

### Files that must never be passed to a report

`ex1_smoke_gpt_L3.jsonl` and every `*_repair*.jsonl` land in the same
`(model, condition)` bucket as a real run and overwrite it, because files are
read in alphabetical order. This produced a wrong figure that stood for two
days. **Pass run files by name, never by glob.** The verification script
hardcodes the 18 good files for this reason.

---

## Tables

| Table | Reports | Source | Check |
|---|---|---|---|
| `tab:ex1:rungs` | The six prompt conditions | `experiments/ex1/prompts.py` | Not data. `SPINE` and `FACTORIAL` in that module are the authority for the tag-to-code mapping. |
| `tab:ex1:binding` | Binding constraints, states and pairs | `probes/ex1_v2.json` | `--table binding` |
| `tab:ex1:optionspace` | Option space per state | `probes/ex1_v2.json` | `--table optionspace` |
| `tab:ex1:worked` | One state in full | `probes/ex1_v2.json` | `--table worked` |
| `tab:ex1:terms` | State counts inside definitions | `probes/ex1_v2.json` | `--table terms` |
| `tab:ex1:floors` | Cast A reference lines | `out/ex1_chance_floor.json` | `--table floors` |
| `tab:ex1:offspine` | The two controls | 6 run files | `--table offspine` |
| `tab:ex1:spine` | Legality, trial and scene level | 12 run files | `--table spine` |
| `tab:ex1:gaps` | The four design contrasts | 12 run files | `--table gaps` |
| `tab:ex1:consistency` | Per-scene agreement over repeats | 9 run files | `--table consistency` |
| `tab:ex1:objects` | Grasp errors per opportunity | 3 run files + probes | `--table objects` |
| `tab:ex1:setb:floors` | Cast B reference lines | `out/ex1_setb_floors.json` | `--table setb_floors` |

## Non-table checks

| Check | Verifies | Command |
|---|---|---|
| `in-text` | Figures quoted in prose: grasp violations, run-file counts, cast B at three repeats, the image-on cell | `--table in-text` |
| `route` | How much of the R5 limitation is real. Rebuilds the deployed router with each unstated rule disabled and re-runs all 52 route rejections | `--table route` |
| `effects` | Contrasts the Results section quotes with intervals: the interaction, correct-refusal falls, Franka-share rises, the bound on reasons admitting the gap, and the width-ordering violation | `--table effects` |

`ex1_effects.py` used to compute the same quantities for reporting. It is now
in `attic/analysis_ex1_pipeline/`: the `effects` block here and section 18 of
`ex1_reproduce_tables.ipynb` both cover what it did, from two independent
implementations.

The `route` check runs a control first: with the threshold left at 0.05 m the
rebuilt router must reproduce the deployed verdict on all 52 rejections. If
that control fails, the rest of the block means nothing. It then finds that
removing the 0.05 m progress threshold unblocks 1 rejection and removing the
same-arm rule unblocks none, so 51 of 52 route rejections are decided by
reachability the printed `reach_ok_arms` lists make determinable.

---

## Definitions that are easy to get wrong

Each of these was got wrong at least once during verification. They are
recorded because a reader recomputing a number will hit the same forks.

**Legality** is proposals accepted over proposals made, on picking states.
Declines are **not** in the denominator, on either side. Including them changes
every headline figure. This is why the trial denominators differ between cells:
a model that declines on a picking state removes that trial from the fraction.
It is also why a scene can leave the scene-level denominator entirely, when
every one of its three repeats was a decline.

**The grasp-binding subset is 122 states, but legality is measured on 96.**
The 122 split into 96 picking and 26 refusal. The 26 are scored by correct
refusal instead. Expecting 122 by 3 repeats gives 366 rows where the real
denominator is 288.

**Scene level uses grasp-binding picking scenes, not all picking scenes.**
Majority over the three repeats, then a Wilson interval on the scene count.
Using all 126 picking scenes instead of the 96 grasp-binding ones changes
Gemini No Width from 71.9 to 78.6. GPT's scene denominators are 95 rather
than 96 on three of four conditions, because one scene has no majority-eligible
repeat.

**Flickering is defined on the raw outcome, not on correctness.** A state
flickers when its three repeats did not return the same result. A state
answered wrongly three times in two different ways, say `rejected, rejected,
noop`, is flickering, not stable wrong. Scoring on correctness instead moves
two GPT No Width states across, giving 78/12/36 where the table says 78/10/38.

**A decline is recorded as `noop`, not `declined`.** On a picking state it is
a wrong answer, but it is **not scored as an illegal proposal**: it is dropped
from the legality fraction, because legality is over proposals made and a
decline is not a proposal. It is instead measured directly by correct refusal,
which is the mirror measure on the 36 refusal states. An earlier version of this
document said a decline is "scored rather than dropped", which is the opposite
of what the pipeline does and of what the thesis glossary states. The
consequence of dropping it is that the denominator varies between cells for any
model that declines, which is exactly what the published `n` columns show.

**Reference lines are stored as fractions of 1, not percentages.** Keys are
`uniform/mean` and `width_blind/mean` for all picking states, and
`by_cause/<cause>/{uniform,width_blind}/mean` per subset.

**Binding cause and violation type are different things.** Binding cause is a
property of the frozen state, computed before any model is called. Violation
type is a property of the model's reply. Collapsing them destroys the
attribution. In a run row the fields are `violation_cause` and `violation`.

**The pairs column of the binding table partitions, the states column does
not.** Pairs sum to 1196, which is exactly the rejected pairs (1732 candidate
minus 536 legal), because each rejected pair carries one cause. States sum to
392 against 162 states, because a state can have several binding constraints.

**Cast A and cast B have different reference lines.** Cast A is chance 30.5,
width-blind 74.9; cast B is 34.6 and 69.2. The retired `ex1_report.py`
hardcoded cast A's and printed them over cast B output. Take them from
`out/ex1_setb_floors.json`, which the notebook re-derives and asserts against.

---

## Interval conventions

Wilson 95% for a proportion. Newcombe 95% for a difference of two proportions.
An interval that spans zero is flagged in the text.

The trial-level intervals treat 288 rows as independent when they are 96 scenes
by 3 repeats, so they are optimistic. The scene-level column is the conservative
version and is reported alongside for exactly that reason.

---

## Figures

**Chapter 4 carries no figures.** The four listed below were planned, their data
was generated, and they were cut before submission. Their CSVs are kept under
`fourarm/figures/` and plot verified numbers, but nothing in the thesis prints
them. They are recorded so the CSVs are not mistaken for the source of a
published figure.

| Cut figure | Would have plotted | Data |
|---|---|---|
| `ex1_legality` | Legality across the four main conditions | `figures/ex1_design_data.csv` |
| `ex1_interaction` | The two removals crossed, with the width-blind line at 74.9% | `figures/ex1_convergence_data.csv` |
| `ex1_objects` | Grasp errors per opportunity by object | `figures/ex1_gaps_trial.csv` |
| `ex1_setb` | The width effect on both object casts | `figures/ex1_gaps_scene.csv` |

The two figures the thesis does print are simulator captures, not plots:

| Figure | What it shows | Generator |
|---|---|---|
| 3.1 | The four-arm cell, arms at rest, baskets and exchange pads | **No generator.** Captured by hand from Isaac Sim. The image is committed at `fourarm/figures/thesis/workspace.png`; see the README there |
| 5.1 | One position on each of the block's three resting faces | `ycb/capture_ex2_scene.py --spec ycb/ex2_block.txt`. Its three panels are byte-identical to `out/ex2_capture_block/e00_{U,L,S}.png` |

---

## In-text figures the harness also checks

| Claim | Value |
|---|---|
| Grasp violations, both width-absent conditions, three models | 578 |
| Cast A run files and rows | 18 files, 6804 rows |
| Cast B Full Information, three repeats | 98.8% |
| Cast B No Width, three repeats | 90.1% |
| Cast B width gap | 8.7 points [3.9, 14.3] |
| Image-on legality | 75.4% |
| Image minus text | −1.3 points [−8.3, 5.7] |

The cast B width gap excludes zero at three repeats. At a single repeat it was
9.6 [−0.6, 21.2] and spanned zero. Any prose describing the interval as
touching zero is describing the superseded single-repeat run.
