# Experiment 2, Question 1: status

**Date:** 2026-08-28. **Rung:** `N0` only. **Prompt version:** `2026-08-27b`.

Q1 asks: *when the text omits the capability-relevant quantity, can the model
obtain it from the scene?*

This document describes the state of the working tree, not a plan. Every
number in it was read off the files or recomputed from them, and where a
number disagrees with a note already written in the code that is said so
rather than smoothed over. Sections 7 and 8 are the parts that need action.

---

## 1. Where the work stands

The instrument is built and has been run end to end. `notebooks/ex2_q1_derivation.ipynb`
is a 31-cell notebook that derives the design from the authored object
dimensions, checks the captures, validates the cue, spends money in three
gated cells, and writes every table and the figure. Three models were run
rather than two. The gate that decides whether Q1 is measurable at all
passes: all three models separate the two resting faces well above the 50%
floor.

The headline result is on disk. In the **congruent** condition, where the
face and the opening are both stated, every model separates the two faces
perfectly, so the rule-application half of the task is not in doubt. In the
**dims** condition, where both are withheld, only Gemini separates them, at
46.9 points, which is about half its congruent contrast. GPT at high
reasoning effort collapses onto the Franka on both faces, and Claude at
medium effort sits at chance on both. Two of the three models therefore
apply the rule when handed the opening and cannot obtain the opening from
the picture.

The tables in `fourarm/tables/ex2_q1/` and the figure in
`fourarm/figures/ex2_q1/` are current, written at 11:51 on 2026-08-28. The
notebook's own saved outputs are older than that and show an earlier,
partial state. They must not be quoted, and the notebook needs re-running
and saving before it is cited. See item 3 in section 7.

---

## 2. The design as it now stands

| Element | Value |
|---|---|
| Object | Procedural cuboid, 0.130 x 0.100 x 0.050 m, no recognisable identity |
| Resting faces | `small_face` (stands, opening 0.050) and `large_face` (lies, opening 0.100) |
| Apertures | Franka 0.080 m, UR 0.140 m, so only `large_face` crosses the Franka |
| Conditions | `congruent` (face and opening stated and true) and `dims` (both withheld) |
| Rung | `N0`, the base prompt, with no attention, derivation or elicitation cue |
| Preference | `franka`, supplied by prompt guidance G1 |
| Positions | 34 captured, 32 usable |
| Models | `gpt_hi`, `gemini`, `claude_md` |
| Repeats | 3 |
| Paid trials | 612 congruent, 612 dims, 180 cue validation |

The contrast is the whole design. A model that obtains the opening from the
scene picks the Franka on `small_face` and the UR on `large_face`. A model
that cannot picks the same arm on both.

**Two positions are excluded, for two independent reasons.** `e02` fails on
legality, because `franka_n` cannot reach it at all and there is therefore no
arm choice to measure. `e10` fails on visibility, because the block presents
3% of the median block area for its bank against a next-worst 60%, the Franka
standing in front of it. Visibility is measured from pixels alone by
`experiments/ex2/visibility.py` and is blind to any model reply, so a
position is never excluded for having scored badly.

---

## 3. What changed since the last commit (`fd25cfd`)

### 3.1 Three resting faces became two

The middle face, `edge` (0.130 x 0.050 down), was withdrawn on 2026-08-27
because no model could read it. GPT separated `edge` from `large_face` on 58%
of 81 answered trials, Fisher p = 0.76, while answering a plain
standing-or-flat question about the same pictures 18 times out of 18.

This is the most consequential design change and it has a cost that must be
carried into Limitations. `edge` and `large_face` are both flat and differ
only in geometry, so that pair was the only contrast that separated
*deriving the opening from geometry* from *reading posture and applying a
rule*. With two faces, `small_face` stands and `large_face` lies, so posture
alone scores the entire design. Cell 10 prints this under every verdict and
cell 14 lists it as design fact 4.

Design fact 5 records a second posture route that retiring the third face did
not create. The `dims` state still names its extents `size_upright_m`, which
states the frame the three numbers were taken in, so a two-way posture
judgement fixes the opening without the model ever working out which two
extents are horizontal. This is deliberately not patched: the extents reach
the model as an unordered set whatever the field is called, so dropping the
frame would add an ambiguity rather than restore a step, and `min(0.100,
0.050) = 0.050` would then be the wrong opening on the correct condition.
Q1 measures posture-plus-lookup and cannot separate it from geometric
derivation.

### 3.2 A third model, spoken natively

Two models are one failure away from one model, and one model cannot show
that a result is a property of models rather than of that model. Claude was
added as the third. It could not simply be pointed at a gateway, because the
Anthropic API is not OpenAI-shaped, so the following was built:

- `vlm_allocator.to_anthropic`, a pure translation from OpenAI-shaped
  messages. It lifts the system prompt to the top level, converts the image
  from a data URI to `{"type": "image", "source": {...}}` with the media type
  read off the URI rather than assumed, and raises on a non-data-URI image
  rather than dropping it. A lost image is the dangerous failure here,
  because a text-only trial still returns a plausible answer and grades as a
  real trial.
- `vlm_allocator.anthropic_chat`, with the same signature and contract as
  `openai_chat`. It remaps `usage` onto the OpenAI field names, because every
  EX2 row ever written records `prompt_tokens` and `completion_tokens` and
  `cost_table` sums those. It raises on a policy refusal rather than
  returning an empty string, so a decline lands in the row's `error` field
  instead of grading as a model failure. It never raises `TypeError`, because
  `one_trial` probes for `return_usage` with a bare `except TypeError` and
  would otherwise make a second, duplicate, paid call.
- `vlm_allocator.chat`, a dispatcher that routes on a new registry field
  rather than on the model name. Every runner and probe now imports `chat`
  instead of `openai_chat`: `run`, `solo`, `cue`, `mancheck`, `seecheck`,
  `heightcheck`, `twoway`, `ex2_pose_probe`, `ex2_perception_floor`.
- `model_registry` gained `{PREFIX}_API`, defaulting to `openai`, so no alias
  written before 2026-08-27 needs a line adding. An unknown value raises. The
  protocol is config rather than a branch on the model name for the same
  reason the request parameters are, and because an Anthropic endpoint
  addressed as OpenAI fails with a `KeyError` on `choices` *after* the call
  has been paid for.

### 3.3 Two effort aliases, and why each exists

| Alias | Model | Effort | Reason it is a separate alias |
|---|---|---|---|
| `gpt_hi` | `gpt-5.6-terra` | `reasoning_effort: high` | Claude runs at the Anthropic default of high and Gemini Flash exposes no effort control, so `gpt` at low made the model with the least test-time compute the yardstick for the other two |
| `claude_md` | `claude-sonnet-5` | `output_config.effort: medium` | At the default effort Claude read the two-way face probe at 65%, and the failure was a bias rather than blindness: `large_face` on 75% of trials, 90% right when the block lies and 40% when it stands |

The Claude case is the interesting one. A prior of the form "blocks lie flat"
gains weight with deliberation rather than losing it, so lowering the effort
is the move that fits the shape of the failure. The cue probe is what tests
it, and the answer, in section 5, is that medium moved Claude from 65% to
75% but did not remove the bias.

A separate alias rather than an edit to the existing `*_PARAMS` is what keeps
the earlier rows readable. The alias is stamped into every row and into
`check_id`, so editing parameters in place would leave two efforts writing
rows labelled the same, indistinguishable afterwards and resumable onto each
other.

Effort is still not matched across providers and cannot be. That belongs in
Limitations rather than being papered over with a nominally equal setting.

### 3.4 The registry re-reads a file that has changed

Before 2026-08-27 every value was written with `setdefault` and the file was
read once per process, so editing `env/models.env` in a live kernel did
nothing, and did nothing *selectively*: a newly added variable arrived because
nothing held that name yet, while an edited one kept the first read's value.
The registry that resulted was half old and half new, and it cost sixty paid
calls failing on a `max_tokens` that the file plainly set.

`load()` now fingerprints the file and re-reads when it changes, but only
refreshes keys it wrote itself. A real shell export still always wins.

### 3.5 The notebook

Thirty-one cells. Cells 1 to 4 and 8 to 14 are free, and cells 5, 6 and 7
spend. Each spending cell prints its exact call count and refuses to run
until `CONFIRM_SPEND` is set to that number, and the runners resume, so
re-running a cell costs nothing and destroys nothing.

Changes made to it in this block of work:

- Cell 0 accepts `ANTHROPIC_API_KEY`, and the presence report loops over
  `KEYS`, so a key that loads from `env/keys.local.env` without being
  reported cannot look the same as one that did not load.
- Cell 1 names its three models explicitly rather than taking whatever the
  registry carries, and warns if the registry cannot supply one, because a
  run's model set is a decision to be recorded rather than a side effect of
  `FOURARM_MODELS`.
- Cell 8 filters to `MODELS` and **prints what it skipped**. A run file
  accumulates, which is right for a record and wrong for a denominator: the
  low-effort `gpt` rows were being counted in the diagnostics while cells 9
  to 13 never saw them, so the diagnostics described a model the chapter does
  not report.
- Cell 13 requires a colour per model and raises if two share one. With the
  old `.get(..., "q1blue")` default, adding a third model would have drawn a
  legend naming three models over bars showing two colours, which reads as a
  duplicated series rather than a missing definition.
- **Cell 7b and cell 15 were added on 2026-08-28 and have not been run.**
  Cell 7b repeats the dims condition at `N0` over the same 68 scenes, three
  models and three repeats with the image withheld, which is `solo.run`'s
  modality `A`. Cell 15 reads it against cell 10. Written and gated, 612 calls
  waiting on a `CONFIRM_SPEND`. See section 5.5 for what it is expected to
  show and why it is worth paying for.

### 3.6 Parallel sweeps

`experiments/ex2/launch.py` runs several sweeps at once, one OS process each,
and pools them at read time. A notebook kernel runs one cell at a time, so
three model cells queue rather than overlap while looking as though they ran
together. Nothing inside `solo.py` changed: the run loop, the trial id, the
resume set and the crash-safe write are as they were, so the code that
produced the results already on disk is the code that produces the rest.
Each process writes its own file, because three processes appending to one
JSONL interleave partial lines and corrupt it.

### 3.7 Harness

`harness/h_anthropic_client.py` is new and pins the translation and the
client against the exact message shape EX2 builds, with the transport
stubbed, so it is free to run. It currently passes in full.
`harness/h_model_registry.py` was updated for the new field, and currently
fails one check. See section 7.

---

## 4. Data on disk

| File | Rows | Contents |
|---|---|---|
| `runs/ex2_q1_congruent_N0.jsonl` | 748 unique | `gpt_hi` 204, `gemini` 204, `claude_md` 204, plus `gpt` 136 at low effort, retained and filtered out at cell 8 |
| `runs/ex2_q1_dims_N0.jsonl` | 612 unique | `gpt_hi` 204, `gemini` 204, `claude_md` 204, no errors |
| `runs/ex2_q1_cue2way_{gpt_hi,gemini,claude_md}_r{1,2,3}.jsonl` | 20 each | The two-way face probe, one file per repeat because `mancheck.check_id` has no repeat field |
| `runs/_archive/ex2_q1_cue_*.jsonl` | 4 files | Part of the three-way probe that withdrew the middle face |
| `runs/ex2_q1_dims_N-D_*.jsonl` | 4 files | Side probes of elicitation, extents framing and face order, not part of the reported design |

204 rows per model per condition is 68 scenes (34 positions x 2 faces) by 3
repeats. The analysis then restricts to the 32 usable positions, giving 96
trials per model, face and condition, and 1,152 in total. The excluded
positions were asked deliberately, so that the exclusion is visible in the
data rather than only in a filter.

**Transport errors.** The congruent file lost 9 of Gemini's 192 usable trials
and 3 of GPT's. The dims file lost none. Re-running cells 6 and 7 tops these
up for about twelve calls, since `solo.run` resumes only over trials answered
*without* an error.

---

## 5. Results as they stand

### 5.1 Cue validation, the gate

Two-way forced choice on 10 positions by 2 faces by 3 repeats. Chance is 50%.

| Model | `small_face` | `large_face` | Overall |
|---|---|---|---|
| `gpt_hi` | 96.7% [83.3, 99.4] | 93.3% [78.7, 98.2] | 57/60 = 95.0% |
| `gemini` | 100.0% [88.6, 100.0] | 100.0% [88.6, 100.0] | 60/60 = 100.0% |
| `claude_md` | 60.0% [42.3, 75.4] | 90.0% [74.4, 96.5] | 45/60 = 75.0% |

Verdict: separable above chance for all three, so Q1's contrast is
measurable and the paid cells were justified. Claude's bias survives the
effort change, though: it still answers `large_face` too often, 12 of its 30
`small_face` trials. Medium effort moved it from 65% to 75% and did not fix
the shape of the error, which is evidence against the hypothesis in section
3.3 rather than for it.

Raising GPT's effort bought nothing here either. Recomputed from the archived
low-effort files, `gpt` scored 56/60 = 93.3% against `gpt_hi`'s 57/60 = 95.0%.

### 5.2 Franka share by resting face

The endpoint. Declines are excluded from numerator and denominator and
reported separately.

| Condition | Model | `small_face` | `large_face` |
|---|---|---|---|
| congruent | `gpt_hi` | 100.0% (94/94) | 0.0% (0/95) |
| congruent | `gemini` | 100.0% (91/91) | 0.0% (0/92) |
| congruent | `claude_md` | 100.0% (96/96) | 0.0% (0/96) |
| dims | `gpt_hi` | 94.8% (91/96) | 92.7% (89/96) |
| dims | `gemini` | 97.9% (94/96) | 51.0% (49/96) |
| dims | `claude_md` | 46.9% (45/96) | 57.3% (55/96) |

### 5.3 Paired contrasts, `small_minus_large`

Computed within position and averaged over the 32 positions, so the unit is
the position and the interval to quote is the paired t interval. Newcombe is
emitted alongside as the conservative unpaired comparison.

| Condition | Model | Mean, points | Paired 95% | Spans zero | Ratio to congruent |
|---|---|---|---|---|---|
| congruent | `gpt_hi` | 100.0 | [100.0, 100.0] | No | - |
| congruent | `gemini` | 100.0 | [100.0, 100.0] | No | - |
| congruent | `claude_md` | 100.0 | [100.0, 100.0] | No | - |
| dims | `gpt_hi` | 2.1 | [-6.2, 10.3] | Yes | 0.02 |
| dims | `gemini` | 46.9 | [34.5, 59.3] | No | 0.47 |
| dims | `claude_md` | -10.4 | [-24.3, 3.5] | Yes | -0.10 |

### 5.4 The no-image floor, collected 2026-08-28

Cell 7b asks the dims condition with no picture attached. Under dims the
prompt withholds the resting face and the opening, and `size_upright_m` is
quoted in the standing frame whichever way the block rests, so at one position
the small-face prompt and the large-face prompt differ **only in the queued
task's id**. That was checked by rendering both and diffing them, not assumed.

Two things follow. The contrast this cell measures is zero by construction, so
what it records is how far a model's answer moves when nothing it can see has
moved, and that is the number Gemini's 46.9 points has to be larger than.
A floor that does not come out at zero would be an instrument fault rather
than a finding, and cell 15 says so in those words rather than reporting it as
a result.

It is also the one condition in the design where **declining is the right
answer**. R3 cannot be satisfied for either arm with no opening stated and no
picture to obtain one from, so a model that waits here is not failing.

**The result, over all 576 trials.** The floor is zero for every model, which
is what a sound instrument had to show:

| Model | Contrast with no image | With the image |
|---|---|---|
| `gpt_hi` | -2.1 [-7.1, 2.9] | 2.1 |
| `gemini` | **-6.2 [-14.3, 1.8]** | **46.9** |
| `claude_md` | -3.1 [-15.7, 9.4] | -10.4 |

All three span zero, so nothing in the text alone produces the contrast, and
**Gemini's 46.9 points require the picture**. That is the ablation a reader
will ask for and it lands cleanly.

**Two further findings.** Without the image the models do not fall to chance,
they fall to the *preference*: `gpt_hi` names a Franka on 95.8% and 97.9% of
trials by face, `gemini` on 87.5% and 93.8%, with `claude_md` nearer a coin
flip at 55.2% and 58.3%. Asked a question they cannot answer, two of the three
default to the arm the prompt prefers.

And **not one of the 576 trials declined**. Waiting was the defensible answer
here, and no model took it. Q1 recorded zero declines in 1,152 trials where
the information was available; this adds 576 where it provably was not. The
calibration finding is now much stronger than a null: these models do not
signal missing information, they guess.

### 5.5 Declines and self-consistency

Declines were zero in every cell, so Franka share reads at face value and the
wait table can be replaced by one sentence. In the congruent condition every
model stated the opening on every trial, got it right on every trial, and
named an arm consistent with its own report on every trial. Reasoning and
action do not come apart anywhere in the data. Where a model fails, it fails
at obtaining the opening, not at using it.

---

## 6. How to read this

The congruent row is the control and it is perfect for all three models, so
nothing here is a failure to understand the task, the schema or the
preference rule. The whole of the Q1 effect sits in the dims condition.

**GPT at high effort does not obtain the opening.** Its contrast is 2.1
points with an interval through zero, and the shape of the failure is
informative: it picks the Franka on 92.7% of `large_face` trials, which is
the arm that physically cannot span the object. It defaults to the preferred
arm rather than declining or guessing.

**Claude at medium effort does not obtain it either**, and is at chance on
both faces, which is consistent with its 75% on the cue probe. It is the
weakest of the three at reading the picture and the weakest at the task.

**Gemini separates the faces**, at 46.9 points, about half the contrast it
shows when handed the answer. That is the one positive result, and it must be
reported with the confound stated: `small_face` stands and `large_face` lies,
so posture alone produces this pattern, and `size_upright_m` gives posture a
second route to the same number. The reading is posture-plus-lookup, which
geometric derivation would also produce and which this design cannot separate
from it.

---

## 6a. Phase 0 of the Q2/Q3 build, done 2026-08-28

The shared-code work the Q2/Q3 instruction asked for landed first, and it
resolves or changes several items below. `analysis/ex2/ex2_q_common.py` now
holds the loaders, the exclusion rule, the share definition, the paired
contrast, the provenance row and the spend gate, with 41 pins in
`harness/h_ex2_q_common.py`. Q1's cells import it.

The refactor was verified by re-deriving every Q1 artefact from the run files
already on disk and diffing byte for byte against a snapshot taken first:
**11 of 11 identical**, CRLF included, with no run file touched. Two cells
changed behaviour deliberately and neither writes a byte, so the diff stayed
empty through both.

**The corrected coupling statistic already found something.** Reported over
both directions rather than one, `claude_md` in dims has **16 of 192 replies
that name a UR after reporting an opening a Franka fits**. The old statistic
scored every one of them as agreement, because it only asked whether the arm
could span the opening and a UR spans everything. Every other cell is at 100%,
and nothing anywhere over-reaches.

---

## 7. Open items

Ranked by how much damage each does if it is missed.

1. **`harness/h_model_registry.py` fails one check.** The assertion "every
   OpenAI-shaped alias still says so" excludes only `claude` from the sweep,
   and `claude_md` is also Anthropic, so it fails. The check is stale rather
   than the code being wrong, and it is a one-line fix, but the harness is
   currently red and should not be left that way.
2. **RESOLVED, and it was never in the source.** The `REPEATS = 1` rebinding
   lived only in the built `.ipynb`, as a hand-edit, and the rebuild removed
   it. `nb_cells_a.py` has always set `REPEATS = 3` once. The hazard is real
   even so, since a hand-edit to the notebook is invisible to the source and
   lost on the next rebuild, so the spend gate now refuses when the factors
   stop multiplying to the confirmed total.
3. **The notebook has no saved outputs.** It was rebuilt from
   `nb_cells_a.py` and `nb_cells_b.py` on 2026-08-28 to add cells 7b and 15,
   and `build_q1_nb.py` emits every cell with `outputs: []`. Nothing was lost
   that was worth keeping: the outputs it held predated the completed dims run
   and showed `NA` for GPT and Claude. The CSVs in `tables/ex2_q1/` are the
   current numbers. Re-run the notebook and save it.
4. **Evidence paths in the documentation have moved.** `docs/EX2_GUIDE.md`,
   `notebooks/NOTEBOOK_DOCUMENTATION.md` and cell 14's own disclosure text
   all cite `runs/ex2_q1_cue_*.jsonl` as the retained evidence for
   withdrawing the middle face. Those files are now in `runs/_archive/`, and
   two of the six (Gemini repeats 2 and 3) are not in the working tree at
   all, only in git history.
5. **The dims file lost its low-effort record.** At the last commit it held
   136 `gpt` rows. The working-tree file does not. The congruent file kept
   its equivalent, and cell 8's filter was written on the premise that the
   record stays in the file and is excluded at read time. Either restore the
   rows from git or state plainly that the low-effort record lives in
   history.
6. **A quoted number does not reproduce.** The comment in `nb_cells_a.py`
   says `gpt` scored 95% at low effort on the cue probe. Recomputed from the
   archived files with the same last-write-wins rule the notebook uses, it is
   56/60 = 93.3%. 95.0% is `gpt_hi`'s figure. Reconcile before either number
   reaches the chapter.
7. **FIXED IN CODE, PENDING 180 CALLS.** `CUE_POSITIONS` is now ten east and
   ten west. The east ten are already collected, so cell 5 resumes and adds
   only the west: it prints `already answered: 180 across 9 files, so this
   run adds about 180 calls`. Until that run happens, `tab_ex2_q1_cue.csv`
   still describes the east half only.
8. **`fourarm/env/models.env` is not in `.gitignore`.** It holds no secrets
   today and is untracked, so nothing is exposed, but it sits where a key
   would be committed if someone put one there.
9. **Twelve congruent trials are missing** to transport errors, 9 Gemini and
   3 GPT. Cheap to top up and it makes the denominators equal.
10. **Only `ex2_cam` was captured**, so Q1 has no viewpoint control. A
    `table_cam` comparison would need a new capture run.
11. **DONE.** Cell 7b completed on 2026-08-28: 612 of 612, three models at
    204 each, no errors and no declines. See section 5.4 for the result.

---

## 8. Suggested next steps

In order, and the first three are cheap.

1. Fix the harness check, restore `REPEATS`, and re-run the notebook top to
   bottom with the two spending cells resuming, which tops up the twelve
   missing trials in the same pass. Save it with its outputs.
2. Reconcile the six documentation and provenance drifts in items 4 to 6, so
   that every path and number a reader can follow actually leads somewhere.
3. Run cell 7b and then cell 15. It is 612 calls with no images attached,
   and it converts "Gemini separates the faces" into "Gemini separates the
   faces and cannot do it without the picture", which is the claim the chapter
   actually needs. If the floor comes out anywhere but zero, that finding
   outranks everything else in this document.
4. Decide whether to re-run the cue probe over both banks (item 7). It costs
   180 calls and it removes a sampling objection from the gate that licenses
   the whole of Q1.
5. Write the Q1 section. The result is stable, the control is clean, and the
   confound is already documented in three places (cell 10's verdict, cell
   14's design facts 4 and 5, and section 3.1 above). What the chapter must
   say is that Q1 measures posture-plus-lookup, that one model of three
   clears it and at half strength, and that the two that fail do so by
   defaulting to the preferred arm rather than by declining.
