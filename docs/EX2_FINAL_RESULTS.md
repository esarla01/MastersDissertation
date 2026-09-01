# Experiment 2: the final runs, and what they show

The single reference for writing the Experiment 2 chapter and its conclusion.
It states what was run, exactly what the models were asked, what was measured,
what came out, and what each figure shows. Where an older document or an older
number disagrees with the data, section 12 says so and says which to use.

**Status.** Final as of commit `4a551f1` ("all results in", 2026-08-29), with
`congruent_face` completed to 612 of 612 that day and every derived table and
figure regenerated from the run files afterwards. **All five N0 conditions now
stand at three repeats for all three models, with no cell short.**
Prompt version `2026-08-27b` throughout. Experiment 1 is not covered here; see
`docs/TABLE_PROVENANCE.md`.

**The rule for telling a current number from a superseded one.** A current
number is one that appears in a CSV under `fourarm/tables/ex2_q{1,2,3}/` or
`fourarm/figures/ex2_q{1,2}/`. Those files were rewritten on 2026-08-29 from
the complete run set. Numbers quoted in `docs/EX2_GUIDE.md`, in
`docs/EX2_Q1_STATUS.md`, or in prose written before that date may predate the
last data to land, and several do.

---

## 1. What Experiment 2 asks

The cell supplies frozen decision states. The model is asked to allocate one
queued task to one idle arm. What varies is where the capability-relevant
quantity comes from: stated in the text, visible only in the scene, or stated
falsely in the text while the scene shows otherwise.

| Question | Asks | Conditions | Rung |
|---|---|---|---|
| Q1 derivation | When the text omits the quantity, can the model get it from the scene? | `congruent`, `congruent_face`, `dims` | `N0` |
| Q2 precedence | When the text contradicts the scene, which source governs? | + `conflict`, `conflict_face` | `N0` |
| Q3 remediation | Which kind of instruction moves a model from the text to the scene? | `dims`, `conflict_face` | all six |

---

## 2. The design

**The object.** A procedural cuboid, 0.130 x 0.100 x 0.050 m, with no
recognisable identity, so nothing can be recalled about it. It has two resting
faces in use, and the face fixes the opening the object needs.

| Resting face | Face down | Vertical | Opening needed | Franka 0.080 | UR 0.140 |
|---|---|---|---|---|---|
| `small_face` (stands) | 0.100 x 0.050 | 0.130 | **0.050** | fits | fits |
| `large_face` (lies) | 0.130 x 0.100 | 0.050 | **0.100** | **does not fit** | fits |

Only `large_face` crosses the Franka aperture, so the face alone decides
whether the preferred arm is legal. That contrast is the whole design. A model
that obtains the opening from the scene names a Franka on `small_face` and a
UR on `large_face`. A model that cannot names the same arm on both.

The prim names cross the geometric ones: `ycb_block_upright` rests on the
genuinely smallest face and is recorded as `small_face`. This is the one
pairing in EX2 that is easy to get backwards, and `h_ex2_labels.py` and
`h_ex2_prompts.py` both pin it.

**The scenes.** 34 positions, each captured in both poses, so every contrast
is paired within a position: 68 captures, in
`fourarm/out/ex2_capture_block/consults.jsonl` (102 rows,
sha256 `b1579d5d8d1f...`). The 34 extra rows are the withdrawn third face,
kept on disk as evidence and skipped with a printed count at load time.

**32 of 34 positions are usable**, for two independent reasons decided before
any model reply:

- `e02` fails on **legality**. `franka_n` cannot reach it at all, so the Franka
  is never legal there and there is no arm choice to measure.
- `e10` fails on **visibility**. The block presents 3% of the median block area
  for its bank against a next-worst 60%, because the Franka stands in front of
  it. `experiments/ex2/visibility.py` measures this from pixels alone, blind to
  any model reply, so a position is never excluded for having scored badly. It
  runs per bank, because a west block renders about 10% larger than an east
  block in the same pose.

**One viewpoint.** Only `ex2_cam` was captured, so there is no viewpoint
control.

**The idle UR is chosen per position.** Every capture was written with the
default `--idle ur_w,franka_n`, which is right for the 15 west positions and
wrong for the 15 east ones. `run.present_reachable_ur` fixes this at load time
by presenting whichever UR is in the object's own reach list. It is legitimate
because the capture script sets arm state by attribute write after the frames
are rendered and never commands an arm to move, so the picture shows four
parked arms whichever labels the text carries.

---

## 3. The five conditions

The conditions are a 2x2 over what the text says about the face and whether it
supplies the opening, plus a corner where both are withheld.

| | Face stated TRUE | Face stated FALSE |
|---|---|---|
| **Opening supplied** | `congruent` | `conflict` |
| **Opening withheld** | `congruent_face` | `conflict_face` |
| **Both withheld** | `dims` | |

- `congruent` states the true face and the true opening. The control.
- `conflict` declares the other face, and swaps `pose`, `grasp_m`, `mass_kg`
  and `delicate` together so the text is internally consistent. The conflict
  map is a strict involution, so every conflict is a capability flip.
- `congruent_face` states the true face and withholds the opening. The matched
  ceiling for `conflict_face`.
- `conflict_face` declares the false face and withholds the opening.
- `dims` withholds both the face and the opening, leaving only the extents.

**Why `conflict_face` exists, and why `conflict` alone cannot carry the
precedence claim.** In `conflict` the state supplies `opening_needed_m` and R3
names that field verbatim, so a model that reads the number and applies the
rule has broken nothing. It is complying. No rule mentions `resting_face`, so
the false face there is inert. With the number withheld, R3 renders in the form
that names no field, there is nothing to comply with, and the only route to an
opening is a face: one asserted by the text, one visible in the image. That is
what makes the sign readable.

**`congruent` and `conflict` send byte-identical instructions**, because both
map to the full glossary and the full R3. The whole manipulation is in the
state, so no prompt difference can explain the contrast. `congruent_face` and
`conflict_face` are likewise byte-identical to each other. The notebooks assert
this rather than diffing it.

### The prompt text that distinguishes them

Two slots move. Everything else in the prompt is identical across conditions.

**The object field list.**

`congruent`, `conflict`:
```
Each object states the opening it needs from a gripper, "opening_needed_m",
which face it is resting on, "resting_face", its mass, "mass_kg", whether it
is "delicate", its height, width and depth measured standing on its smallest
face, "size_upright_m", and the arms that can reach it,
"arms_that_can_reach".
```

`congruent_face`, `conflict_face`:
```
Each object states which face it is resting on,
"resting_face", its mass, "mass_kg", whether it is "delicate", its height,
width and depth measured standing on its smallest face, "size_upright_m", and
the arms that can reach it, "arms_that_can_reach". No opening is given.
```

`dims`:
```
Each object states its mass, "mass_kg", whether it is "delicate", its height,
width and depth measured standing on its smallest face, "size_upright_m", and
the arms that can reach it, "arms_that_can_reach". No opening and no resting
face are given.
```

**Rule R3.**

`congruent`, `conflict`:
```
R3  Gripper opening
    The gripper must open wide enough for the object. The arm is capable
    only when its "opening_max_m" is at least the object's
    "opening_needed_m".
```

`congruent_face`, `conflict_face`, `dims`:
```
R3  Gripper opening
    The gripper must open wide enough for the object. The arm is capable
    only when its "opening_max_m" is at least the opening the object needs.
    That opening is not stated for this object.
```

R3 is **substituted, not deleted**: the capability check survives, the pointer
to a supplied number does not. Neither substitution states the relation between
face and opening, and neither calls the absence an error. This is asserted by
`prompts.assert_r3_matches_state` and
`prompts.assert_glossary_matches_state`.

---

## 4. The base prompt

Rendered here at `N0` / `congruent` / image attached / preference `franka`.
This is exactly what a model receives.

```
You are the task allocator for a four-arm robotic cell. Each time you are
asked, choose ONE queued task and ONE idle arm, or choose to wait.

THE CELL
A 2.8 x 1.6 m table, origin at its centre, x east, y north. Two UR10 arms sit
mid-table on the west and east edges, two Franka arms on the south and north
edges, all facing inward. Zones are a centre disc of radius 0.35 m plus the
quadrants nw, ne, sw, se. Three coloured boxes stand on the table for
sorting, and five exchange points are marked on it.

Every object is picked from directly above. The gripper turns to whichever
horizontal direction suits before it closes. The cell judges an object by the
box that encloses it, so a shape that tapers or curves counts as its full
extent.

WHAT THE STATE TELLS YOU
Each arm states the widest its gripper opens, "opening_max_m", the heaviest
object it can carry, "max_load_kg", and whether it is cleared for delicate
handling, "handles_delicate".

[the object field list for the condition goes here]

The image is taken from the south of the table, above it and
looking back at the centre, so north (+y) is away from the camera
and east (+x) is to the right.

The image shows the four arms at their rest positions, the coloured
boxes, and five white crosses which mark the exchange points and are
not objects to be sorted. Objects to be sorted lie loose on the table.
The image is a side view of this cell, taken now, and a written
description of the same scene follows below. Both describe the cell
you are allocating in.

HARD RULES. A proposal that breaks any of these is rejected.

R1  Task availability
    Assign only a task whose status is "queued". A task marked
    "in_progress" or "waiting_on_..." is already being handled.

R2  Arm availability
    Assign only an arm from the idle list. A disabled arm is never
    available.

[R3 for the condition goes here]

R4  Load
    The arm is capable only when its "max_load_kg" is at least the
    object's "mass_kg".

R5  Delicate handling
    An object marked "delicate" may go only to an arm whose
    "handles_delicate" is true.

R6  Reach
    The arm must appear in the object's "arms_that_can_reach" list. That
    list is authoritative, so use it rather than working reach out from
    coordinates. Reaching is not the same as handling: an arm can often
    reach an object it cannot pick up.

R7  Destination
    The task carries no destination, so name a box in "basket". Any box
    the arm you named can reach will do.

GUIDANCE. Not enforced, but this is what a good allocation does.

G1  Prefer a Franka arm for sorting tasks.

G2  Waiting can be a choice, not only a last resort. If no idle arm is a
    good fit and a better-suited one will free up soon, wait.

[the answer schema for the rung goes here]
```

The user message is the state as JSON, then:
```
Idle arms right now: <comma list or 'none'>.
Assign the queued task to ONE of these idle arms, or answer task_id -1 if none can take it now.
```

**No-image trials** drop the viewpoint paragraph and replace the image
paragraph with `A written description of the cell state follows below.`

**Field names shown to the model are aliases.** The validator, the probe sets
and the run files keep the deployed names. EX2 therefore prints different field
names from EX1, and the chapter must say so.

| Deployed | Shown to the model |
|---|---|
| `grasp_m` | `opening_needed_m` |
| `max_grasp_m` | `opening_max_m` |
| `payload_kg` | `max_load_kg` |
| `delicate_ok` | `handles_delicate` |
| `dims_m` | `size_upright_m` |
| `reach_ok_arms` | `arms_that_can_reach` |
| `pose` | `resting_face` |

Every float in the state is rendered to exactly three decimals, and the render
raises if a marker survives. Baskets are renamed `box_1..box_N` so no box is
named for a category. Exactly one task is queued; the partner object stays in
the scene and in the image but is not queued.

---

## 5. The six rungs

Three factors, each naming a different hypothesis about why a model follows a
supplied opening instead of the scene. The rungs come from `prompts.RUNGS` and
are never redefined in a notebook.

| Rung | Adds | Factor | Schema |
|---|---|---|---|
| `N0` | nothing | the base prompt, where Q1 and Q2 are read | `base` |
| `N-A` | look at the object in the image | attention | `base` |
| `N-C` | the opening is the smaller horizontal extent | derivation | `base` |
| `N-order` | no wording at all; the schema reorders | order (the control for D) | `report_first` |
| `N-D` | report the face and opening before the arm | elicitation | `face_first` |
| `N-CD` | C and D together | sufficiency against `N0` | `face_first` |

The added wording, verbatim, inserted immediately before `YOUR ANSWER`:

`N-A`:
```
The image shows the table as it is now. Look at the object in the image
before you choose.
```

`N-C`:
```
The opening an object needs is the smaller of its two horizontal extents,
so it depends on which face the object is resting on.
```

`N-D`:
```
Give "resting_face" and "opening_needed_m" BEFORE naming an arm, and choose
the arm to fit the opening you gave.
```

`N-CD` is `N-C` then `N-D`, in that order. `N-order` adds **no wording**: only
the field order in the schema changes.

**Why `N-order` exists.** `N-D` moves the report ahead of the arm and also asks
for the face, and a model generates left to right. Without the order control an
`N-D` effect could not be attributed to either. `N-CD` is a sufficiency cell
against `N0`, never an interaction test: the design is not powered for one.

The factor boundaries are checked mechanically by
`prompts.assert_rungs_isolated`, which forbids face or opening vocabulary in
`N-A`, look or report vocabulary in `N-C`, and derivation vocabulary in `N-D`.

### The three answer schemas

`base`, used by `N0`, `N-A`, `N-C`. The arm is committed before the opening:
```
Answer ONLY with JSON, no prose:
{"task_id": <int>,
  "arm": "<arm name>",
  "basket": "<any box the arm you named can reach>",
  "opening_needed_m": <number>
}
```

`report_first`, used by `N-order`. The opening moves ahead of the arm, with no
wording added:
```
Answer ONLY with JSON, no prose, with the fields in this order:
{"task_id": <int>,
  "opening_needed_m": <number>,
  "arm": "<arm name>",
  "basket": "<any box the arm you named can reach>"
}
```

`face_first`, used by `N-D` and `N-CD`:
```
Answer ONLY with JSON, no prose, with the fields in this order:
{"task_id": <int>,
  "resting_face": "<small_face | large_face>",
  "opening_needed_m": <number>,
  "arm": "<arm name>",
  "basket": "<any box the arm you named can reach>"
}
```

All three carry the same tail:
```
The boxes are interchangeable, so this never decides which arm to name.
"opening_needed_m" is the opening you judge the object needs, in metres, as a
number with three decimals.
To wait, answer task_id -1 with arm null. Give "opening_needed_m" if you can,
or null if you cannot.
```

`opening_needed_m` is required at every rung. `resting_face` is asked for
**only** at `N-D` and `N-CD`: naming the face as something to report would
otherwise tell the model that the face matters, which is the thing factor D
manipulates.

There is no prose `why` block and no extractor between the reply and the
measurement. `classify_reasoning` returns `none` for every current row because
there is no prose to keyword-match. That is not a zero result.

### Pre-registered predictions

From `prompts.PREDICTIONS`, fixed before the ladder was bought:

| Factor | Prediction |
|---|---|
| attention | inert |
| derivation | moves in conflict |
| elicitation | moves in both, more than derivation alone |
| order | inert |

---

## 6. Run configuration

| Setting | Value |
|---|---|
| Prompt version | `2026-08-27b` |
| Rung for Q1 and Q2 | `N0` |
| Preference | `franka`, supplied by guidance line G1 |
| View | `ex2_cam` only |
| Modality | `V` (image attached), with `A` (text only) used for the ablations |
| Face order in the schema | `small_first` |
| Dims frame | `named` (`size_upright_m`) |
| Positions | 34 captured, 32 usable |
| Timeout | 90 s, 2 attempts per call, 2 s apart |

### The three models

| Alias | Model | Effort setting | Why this alias exists |
|---|---|---|---|
| `gpt_hi` | `gpt-5.6-terra` | `reasoning_effort: high` | Claude runs at the Anthropic default of high and Gemini Flash exposes no effort control, so `gpt` at low made the model with the least test-time compute the yardstick for the other two |
| `gemini` | `gemini-3.6-flash` | none available | The provider exposes no effort or temperature control |
| `claude_md` | `claude-sonnet-5` | `output_config.effort: medium`, `max_tokens: 1024` | At the default effort Claude read the two-way face probe at 65%, and the failure was a bias rather than blindness: `large_face` on 75% of trials, 90% right when the block lies and 40% when it stands. A prior of the form "blocks lie flat" gains weight with deliberation, so lowering the effort fits the shape of the failure |

**Temperature is set only for `qwen` (0.0), which is not one of the three
reported models.** GPT reasoning tiers and Sonnet 5 reject a non-default
temperature, so it is deliberately absent. **Effort is not matched across
providers and cannot be**, and that belongs in Limitations rather than being
papered over with a nominally equal setting.

A separate alias rather than an edit to the existing parameters is what keeps
the earlier rows readable. The alias is stamped into every row, so editing
parameters in place would leave two efforts writing rows labelled the same,
indistinguishable afterwards and resumable onto each other.

### Reproducibility

**There are no RNG seeds anywhere in the pipeline.** Reproducibility rests on
the frozen captures and their content hash, not on seeding. Determinism is not
comparable across the three providers by construction, so self-consistency is
reported per model with its cause rather than compared across them.

Every row carries `model`, `ex2_prompt_version`, `rung`, `condition`,
`preference`, `modality`, `repeat` and a composite `trial_id`:

```
{seq}|{condition}|{model}|{preference}|{rung}|{modality}|r{repeat}
```

Resume works off that key, and a row carrying an `error` or an `unparseable`
outcome does not count as answered, so re-running a cell tops up failures
rather than skipping them. Each parallel sweep writes its own file, because
three processes appending to one JSONL interleave partial lines.

### The spend gate

Every paid cell prints its exact call count and refuses to run until
`CONFIRM_SPEND` is set to that integer. The gate also requires the declared
factors to multiply to the total, which catches a later cell rebinding
`REPEATS` and silently describing a smaller run than the design asks for. With
`CONFIRM_SPEND` unset the gate prints and returns, so a notebook can be
re-executed end to end without spending anything.

---

## 7. Measures and statistics

**Franka share.** The endpoint. The proportion of *proposals* that name a
Franka. The denominator is proposals, not trials: a decline is excluded from
both numerator and denominator and reported separately in the wait table. The
share is `None`, not zero, when nothing was proposed.

**The contrast, `small_minus_large`.** Franka share on the `small_face` scene
minus Franka share on the `large_face` scene, **computed within position and
then averaged over the 32 positions**. The unit of analysis is therefore the
position, not the trial. The contrast is **always anchored to the image**: the
face named is the one the capture shows, never the one the text declares. So a
positive contrast means the scene governed and a negative one means the text
did.

**Intervals.**

| Estimator | Used for |
|---|---|
| Wilson 95% | a single proportion. Not the normal approximation, which puts bounds outside 0 to 100, and several EX2 cells sit exactly at 0 or 100 |
| Paired-t 95% over positions | the contrasts. This is the interval to quote, because the differences are paired within position |
| Newcombe 95% | emitted alongside as the conservative unpaired comparison. Newcombe is an interval on a difference of *independent* proportions and throws the pairing away |

Both are in `tab_ex2_q*_contrasts.csv`. An interval that spans zero is flagged.

**The saturated-cell rule.** When every position gives the same difference the
t interval collapses to zero width, which reads as a precision no sample of 32
supports. Those cells are flagged and the count of full flips is reported with
a Wilson interval on it instead. In the final data the saturated cells are
`congruent` for all three models, `congruent_face` and `conflict_face` for
Gemini, and `conflict` for all three.

**Second-order contrasts (Q3).** A rung effect is `delta_vs_N0`, a difference
of paired differences, still paired at both levels. At 32 positions and one
repeat the interval on one of these is roughly 30 points wide whatever the
data. **An interval that spans zero there means the design cannot resolve it.
It is not evidence of no effect and must not be written as one.**

**Coupling.** Whether the arm named is consistent with the opening the model
itself reported, in both directions: `over_reach` (said wide, chose a Franka,
which is arithmetically self-contradictory) and `over_cautious` (said narrow,
chose a UR, which violates nothing but means the arm does not follow the
report). The earlier statistic only asked whether the named arm could span the
reported opening, so every UR passed automatically and it read 100% everywhere.

**Opening source.** For conflict trials, whether the reported opening matches
the image, the text, or neither. A model reporting neither has derived a third
number, which can only come from looking and misreading, not from never
looking. Tolerance 6 mm, against two candidates 38 mm apart.

**Physical infeasibility.** Whether the named arm is absent from the true legal
set. Preferred over outcome labels for conflict trials, because it is
unaffected by the grader's uninformative classification. `legal_true` and
`legal_declared` are computed by running the real validator over a frozen
coordinator twice, once per pose.

**Exclusions.** Exactly three: a transport error, an unparseable reply, and a
position outside the usable 32. A decline is **not** dropped, because a wait is
a real decision.

---

## 8. The run files

All at prompt `2026-08-27b`, preference `franka`, view `ex2_cam`, against
captures `out/ex2_capture_block/consults.jsonl`. 68 scenes is 34 positions by
2 faces. "Unique" counts distinct `trial_id`; rows can exceed it where a cell
was resumed.

### The N0 conditions, read by Q1 and Q2

| File | Rows | Unique per model | Repeats | Errors |
|---|---|---|---|---|
| `runs/ex2_q1_congruent_N0.jsonl` | 626 | 204 each | 3 | 11 Gemini, 3 GPT |
| `runs/ex2_q1_congruent_face_N0.jsonl` | 837 | 204 each | 3 | none outstanding |
| `runs/ex2_q1_dims_N0.jsonl` | 615 | 204 each | 3 | 3 Gemini |
| `runs/ex2_q2_conflict_N0.jsonl` | 612 | 204 each | 3 | none |
| `runs/ex2_q2_conflict_face_N0.jsonl` | 612 | 204 each | 3 | none |
| `runs/ex2_q1_dims_N0_noimage.jsonl` | 612 | 204 each | 3 | none |

**`congruent_face` was completed on 2026-08-29 and is now balanced.** It had
been sitting at 3 repeats for GPT, about 2.7 for Gemini and **one** for Claude,
because the spend gate miscounted the file as complete (see section 12). The
missing 157 trials were collected, and all three models now have three repeats.
One Claude trial, `e00_L` at repeat 3, first returned an empty reply at the
1024-token ceiling; the runner re-asked it and it answered, which is the
retry path that puts more than one row in the file for a single trial. Every
denominator is 96.

### The Q3 rung ladder

Every rung file is one repeat, 204 rows, 68 per model, no errors.

| Condition | Rungs on disk |
|---|---|
| `dims` | `N-A`, `N-C`, `N-order`, `N-D`, `N-CD` |
| `conflict_face` | `N-A`, `N-C`, `N-order`, `N-D`, `N-CD` |

`runs/ex2_q3_dims_N-D_noimage.jsonl` holds the no-image control, **Gemini
only**, 68 rows. The notebook is configured to run it for all three models
(204 calls); 136 are unbought.

The `conflict_face` ladder cell is configured for **two** repeats (2,040 calls)
and one repeat is on disk (1,020 answered). Every `conflict_face` rung number
below is therefore at one repeat.

### Cue validation

`runs/ex2_q1_cue2way_{gpt_hi,gemini,claude_md}_r{1,2,3}.jsonl`, 40 rows each,
9 files. One file per repeat because the check id has no repeat field. Covers
both banks: 20 positions by 2 faces by 3 repeats, 60 trials per model.

### Not part of any reported number

- `runs/ex2_q3_conflict_N-CD.jsonl`, 97 rows (gpt_hi 91, gemini 6, no Claude).
  An **aborted** run of the non-face conflict cell. Cited by no provenance
  table. It sits outside `_archive/` and could be mistaken for a result.
- Low-effort `gpt` rows retained inside `ex2_q1_congruent_N0.jsonl` and filtered
  out at read time. The record stays in the file deliberately; the loader
  filters to the three reported aliases and prints what it skipped.
- `runs/ex2_q1_dims_N-D_{quick,effort,extents,extents_gemini,order}.jsonl`,
  27 Aug pilots of what became the ladder.
- `runs/ex2_q1_2way_*` and `runs/_archive/20260827_cue_prerender/*`, earlier
  and smaller probes under the `gpt` and `claude` aliases.
- `tables/_archive/20260827_threeface/` and
  `figures/_archive/20260827_threeface/`, the three-face design. Its share
  table is all zero and its provenance records both run files as
  `rows,0 / sha256,MISSING`, so the archived figure was drawn from nothing.
- The whole 20 Aug legacy set: `All_conflict.jsonl` (2,827 rows),
  `piece_dims_P2.jsonl`, the A/B/C-named files, the `ex2_solo*` pilots and the
  instrument checks. Collected under prompt `2026-08-07e` and **not comparable**
  with anything reported here.

---

## 9. Results

Every number below is in a CSV under `fourarm/tables/ex2_q{1,2,3}/`, all
regenerated 2026-08-29.

### 9.1 The cue gate: can the models read the face at all?

Two-way forced choice, plain geometry, no design vocabulary. 20 positions by
2 faces by 3 repeats, chance 50%. `tab_ex2_q1_cue.csv`.

| Model | `small_face` | `large_face` | Overall |
|---|---|---|---|
| `gpt_hi` | 95.0 [86.3, 98.3] | 83.3 [72.0, 90.7] | 107/120 = 89.2% |
| `gemini` | 100.0 [94.0, 100.0] | 100.0 [94.0, 100.0] | 120/120 = 100.0% |
| `claude_md` | 63.3 [50.7, 74.4] | 95.0 [86.3, 98.3] | 95/120 = 79.2% |

All three separate the faces above chance, so Q1's contrast is measurable and
the paid cells were justified. **Claude's bias survives the effort change**: it
answers `large_face` too often, 22 of its 60 `small_face` trials wrong against
3 of 60 the other way. Medium effort did not fix the shape of the error, which
is evidence against the hypothesis that motivated the alias rather than for it.

### 9.2 Q1, derivation

Franka share by face, `tab_ex2_q1_share.csv`. Declines were zero everywhere.

| Condition | Model | `small_face` | `large_face` |
|---|---|---|---|
| congruent | `gpt_hi` | 100.0 (96/96) | 0.0 (0/96) |
| congruent | `gemini` | 100.0 (96/96) | 0.0 (0/96) |
| congruent | `claude_md` | 100.0 (96/96) | 0.0 (0/96) |
| congruent_face | `gpt_hi` | 90.6 (87/96) | 1.0 (1/96) |
| congruent_face | `gemini` | 100.0 (87/87) | 0.0 (0/86) |
| congruent_face | `claude_md` | 47.9 (46/96) | 53.1 (51/96) |
| dims | `gpt_hi` | 94.8 (91/96) | 92.7 (89/96) |
| dims | `gemini` | 97.9 (94/96) | 51.0 (49/96) |
| dims | `claude_md` | 46.9 (45/96) | 57.3 (55/96) |

Paired contrasts, `tab_ex2_q1_contrasts.csv`:

| Condition | Model | Mean, points | Paired 95% | Spans zero |
|---|---|---|---|---|
| congruent | all three | 100.0 | [100.0, 100.0] | No (saturated) |
| congruent_face | `gpt_hi` | **89.6** | [84.1, 95.0] | No |
| congruent_face | `gemini` | **100.0** | [100.0, 100.0] | No (saturated) |
| congruent_face | `claude_md` | -5.2 | [-21.6, 11.2] | Yes |
| dims | `gpt_hi` | 2.1 | [-6.2, 10.3] | Yes |
| dims | `gemini` | **46.9** | [34.5, 59.3] | No |
| dims | `claude_md` | -10.4 | [-24.3, 3.5] | Yes |

**The congruent row is a perfect control for all three models**, so nothing
here is a failure to understand the task, the schema or the preference rule.
The whole Q1 effect sits in the withheld conditions.

**`congruent_face` separates two failures that `dims` alone could not tell
apart.**

- **GPT can do the geometry and cannot read the orientation.** Handed a true
  face it derives the opening almost perfectly (+89.6); made to read the face
  off the picture it collapses to +2.1. That is a perception failure, not a
  derivation failure, and it retires the reading that its `dims` null might be
  R3 being treated as unevaluable. It evaluates R3 fine when it has a face.
- **Claude cannot do the geometry at all.** Even told the face truthfully it
  sits at chance, 47.9 against 53.1, a contrast of -5.2 [-21.6, 11.2]. Its
  `dims` null was never about the picture. At three repeats this is now the
  best-supported of the three readings rather than the weakest.
- **Gemini does both**, perfectly on a stated face and at 46.9 when it has to
  read one, about half its congruent contrast.

**The shape of the two failures is informative.** GPT picks the Franka on 92.7%
of `large_face` trials in `dims`, which is the arm that physically cannot span
the object. It defaults to the preferred arm rather than declining or guessing.
Claude sits near chance on both faces.

### 9.3 The no-image floor

`dims` with no picture attached, 576 trials, `tab_ex2_q1_noimage_contrast.csv`.
Under `dims` the prompt withholds the face and the opening, and
`size_upright_m` is quoted in the standing frame whichever way the block rests,
so at one position the two prompts differ only in the queued task's id. That
was checked by rendering both and diffing them. **The contrast this cell
measures is zero by construction**, so a floor that did not come out at zero
would be an instrument fault rather than a finding.

| Model | Contrast with no image | With the image |
|---|---|---|
| `gpt_hi` | -2.1 [-7.1, 2.9] | +2.1 |
| `gemini` | **-6.2 [-14.3, 1.8]** | **+46.9** |
| `claude_md` | -3.1 [-15.7, 9.4] | -10.4 |

All three span zero, so nothing in the text alone produces the contrast, and
**Gemini's 46.9 points require the picture**. That is the ablation a reader
will ask for and it lands cleanly.

**Two further findings from this cell.** Without the image the models do not
fall to chance, they fall to the **preference**: GPT names a Franka on 95.8%
and 97.9% of trials by face, Gemini on 87.5% and 93.8%, Claude nearer a coin
flip at 55.2% and 58.3%. And **not one of the 576 trials declined**, although
waiting was the defensible answer, since R3 cannot be satisfied for either arm
with no opening stated and no picture to obtain one from.

### 9.4 Q2, precedence

Franka share, `tab_ex2_q2_share.csv`, and contrasts.

| Condition | Model | `small_face` | `large_face` | Contrast | Paired 95% |
|---|---|---|---|---|---|
| conflict | `gpt_hi` | 0.0 (0/96) | 100.0 (96/96) | -100.0 | [-100.0, -100.0] |
| conflict | `gemini` | 0.0 (0/96) | 100.0 (96/96) | -100.0 | [-100.0, -100.0] |
| conflict | `claude_md` | 0.0 (0/96) | 100.0 (96/96) | -100.0 | [-100.0, -100.0] |
| conflict_face | `gpt_hi` | 0.0 | 89.6 | **-89.6** | [-95.0, -84.1] |
| conflict_face | `gemini` | 0.0 | 100.0 | **-100.0** | [-100.0, -100.0] |
| conflict_face | `claude_md` | 50.0 | 42.7 | +7.3 | [-6.7, 21.3] |

Read against their own matched ceilings on `congruent_face`, which renders a
byte-identical prompt and differs only in whether the stated face is true:
GPT +89.6, Gemini +100.0, Claude -5.2.

**The finding.** When a supplied face contradicts the scene, the two models
that can derive an opening follow the text, and they do so whether or not a
rule directs them to the stated field. `conflict` on its own could not support
that claim, because there R3 names `opening_needed_m` verbatim and the state
supplies it, so a model that reads the number and applies the rule is
complying. `conflict_face` removes that escape and the effect survives at full
strength.

**Claude dissociates and needs its own sentence.** Its -5.2 on
`congruent_face` and +7.3 on `conflict_face` are both nulls: it cannot derive
an opening from a face even when the face is true, so it has no source to
prefer. Its -100.0 in `conflict` was pure R3 compliance. Hand it a number and
it applies the rule, take the number away and it is at chance. Reporting the
three models as one unanimous block, which the `conflict`-only result invited,
would have been wrong about one of them.

**Where the reported opening came from**, `tab_ex2_q2_source.csv`. In
`conflict`, over all 576 analysed trials and in **both** directions:

| Source | Every model, every direction |
|---|---|
| matches the image | **0 / 96** (0.0%) in all six cells |
| matches the text | **96 / 96** (100.0%) in all six cells |
| matches neither | 0 / 96 in all six cells |

Not one trial in 576 reported an opening matching the image.

**Both directions are required, and the `text_forbids_franka` direction is what
makes this more than caution.** A model that simply avoids the Franka scores
correctly where the text permits it, without consulting the image. In the other
direction the model passes over a Franka that would fit. Note that
`transforms.py` stores these as `permissive` and `restrictive` in the opposite
sense to the one a reader expects, so the tables name what the text does and
the chapter should use `text_permits_franka` and `text_forbids_franka` too.

**Declines.** Zero in every cell of Q1 and Q2, 0.0% throughout. Franka share
therefore reads at face value. A model that never declines never signals the
conflict, which is the calibration finding: these models do not signal missing
or contradictory information, they guess.

**Coupling.** Every cell is at 100% except Claude: 95.3% on `congruent_face`
(183/192), 95.3% on `conflict_face` (183/192) and 91.7% on `dims` (176/192).
Almost all of the shortfall is over-caution, naming a UR after reporting an
opening a Franka fits: **16 of 192 in `dims`**, 9 of 192 in `congruent_face`,
8 of 192 in `conflict_face`. There is exactly **one over-reach in the whole
dataset**, a Claude `conflict_face` reply naming an arm that cannot span the
opening it had just stated. In `conflict` a model that follows the text reports the declared opening and
names the arm that fits it, so it stays internally coupled while being wrong
about the world. Coupling is a measure of self-consistency, never of
correctness.

### 9.5 Q3, remediation

**Rewritten 2026-09-01 from the three-repeat run set at commit `dd5fa96`.** The
previous text on this section described the one-repeat pilot and every number
in it was superseded when repeat 3 landed (`dd34691`, "running repeat 3 for
rungs"). Ladder cells are now 96 trials each, 32 positions x 3 repeats, read
against `N0` baselines also at three. Every trial in every ladder cell produced
a proposal, so no cell contains a wait. Source: `tab_ex2_q3_contrasts.csv`.

Second-order intervals are still wide by construction. At 32 positions an
interval of roughly 30 points is expected whatever the data, so a movement
whose interval spans zero is unresolved rather than null.

**In `dims`**, where the configuration has to supply a missing fact:

| Model | N0 | N-A | N-C | N-order | N-D | N-CD |
|---|---|---|---|---|---|---|
| `gpt_hi` contrast | 2.1 | 2.1 | 0.0 | 1.0 | 3.1 | **32.3** [23.3, 41.3] |
| `gpt_hi` delta | | 0.0 | -2.1 | -1.0 | 1.0 | **+30.2** [17.3, 43.1] |
| `gemini` contrast | 46.9 | **96.9** | **99.0** | 45.8 | **100.0** | **100.0** |
| `gemini` delta | | **+50.0** [37.6, 62.4] | **+52.1** [39.0, 65.2] | -1.0 [-15.6, 13.5] | **+53.1** [40.7, 65.5] | **+53.1** [40.7, 65.5] |
| `claude_md` contrast | -10.4 | -14.6 | 0.0 | 6.3 | 0.0 | 0.0 |
| `claude_md` delta | | -4.2 | 10.4 | 16.7 | 10.4 | 10.4 |

**In `conflict_face`**, where the configuration has to override a false
supplied face:

| Model | N0 | N-A | N-C | N-order | N-D | N-CD |
|---|---|---|---|---|---|---|
| `gpt_hi` contrast | -89.6 | -80.2 | -88.5 | -86.5 | **-65.6** [-74.7, -56.6] | -84.4 |
| `gpt_hi` delta | | 9.4 [-0.01, 18.8] | 1.0 | 3.1 | **+24.0** [13.3, 34.6] | 5.2 |
| `gemini` contrast | -100.0 | -96.9 | -100.0 | -100.0 | -100.0 | -100.0 |
| `gemini` delta | | 3.1 [-0.3, 6.5] | 0.0 | 0.0 | 0.0 | 0.0 |
| `claude_md` contrast | 7.3 | -4.2 | **-66.7** | 1.0 | **-16.7** | **-53.1** |
| `claude_md` delta | | -11.5 | **-74.0** [-89.7, -58.2] | -6.2 | **-24.0** [-42.3, -5.6] | **-60.4** [-78.4, -42.5] |

What the three repeats changed against the pilot. GPT's `dims` `N-CD` result
grew from 18.8 to 32.3 and its movement now clearly resolves. GPT's
`conflict_face` `N-D` gain shrank from +39.6 to +24.0 and still resolves.
Gemini's `N-C` in `dims` is 99.0 rather than a flat 100.0, at 31 of 32
positions. Claude's `N-C` collapse in `conflict_face` is -74.0 rather than
-79.2. The shape of every finding survived; the magnitudes moved.

What is resolvable:

1. **Order is inert.** `N-order` spans zero for every model in both
   conditions. The one wide value, Claude in `dims` at 16.7 [-4.9, 38.2], is
   unresolved rather than null. Everything read off `N-D` is therefore
   attributable to the wording rather than to the schema.
2. **Gemini in `dims` moves under attention, derivation and elicitation
   alike**, and not under order. Attention alone takes it from 46.9 to 96.9.
3. **GPT in `dims` moves only under the combination.** A, C and D each do
   nothing alone (0.0, -2.1, 1.0). `N-CD` gives +30.2. No single position
   flips completely, so this is a shift spread across repeats.
4. **Elicitation partially remediates GPT's precedence failure.** `N-D` in
   `conflict_face` moves it +24.0, from -89.6 to -65.6, and positions that
   reverse completely towards the text fall from 22 to 9.
5. **Adding the derivation rule cancels that.** `N-CD` returns GPT to -84.4,
   delta +5.2 spanning zero. C plus D is not the sum of C and D.
6. **Derivation drives Claude towards the text, hard.** `N-C` in
   `conflict_face` moves it -74.0, from a null +7.3 to -66.7. Telling a model
   that cannot derive how to derive hands it a procedure to run on the text it
   was given.
7. **Gemini in `conflict_face` is immovable.** Every ladder configuration sits
   at or beside -100.0. Section 9.6 shows that this is not an absence of an
   arbitration step.

**Attribution**, `tab_ex2_q3_attribution.csv`:

| Condition | Model | `N-D` minus `N-C` | `N-D` minus `N-order` |
|---|---|---|---|
| dims | `gemini` | 1.0, spans zero | **+54.2 [42.2, 66.2]** |
| dims | `gpt_hi` | 3.1, spans zero | 2.1, spans zero |
| dims | `claude_md` | 0.0, spans zero | -6.2, spans zero |
| conflict_face | `gpt_hi` | **+22.9 [12.2, 33.7]** | **+20.8 [12.2, 29.5]** |
| conflict_face | `gemini` | 0.0 | 0.0 |
| conflict_face | `claude_md` | **+50.0 [35.6, 64.4]** | -17.7, spans zero |

`N-D` minus `N-order` is the one that matters: it says GPT's `conflict_face`
gain and Gemini's `dims` gain are the **instruction**, not the field order the
schema also changes.

**The reported opening**, `tab_ex2_q3_reported.csv`. Across every `dims` cell
the Franka share on `large_face` sits close to the complement of the opening
accuracy on that face, so the arm follows the opening the model itself
reported. GPT at `N-CD` is exact: 32.3% correct openings on `large_face` and a
UR named on exactly those 32.3%.

The sharpest single row is `N-C`. In `dims`, GPT and Claude report the correct
opening on 100% of `small_face` replies and **0% of `large_face` replies**.
They are saying 0.050 everywhere, which is the smallest dimension of the
cuboid rather than the smaller of its two horizontal extents in the pose it is
in. Both applied the stated rule to the object instead of to the scene, and
one number on every trial removes the contrast, which is why both sit at 0.0
saturated. Gemini under the same instruction reports 100% and 99.0%.

**The face the model names**, `tab_ex2_q3_face.csv`, asked only at `N-D` and
`N-CD`, 192 replies per cell:

| Condition | Model | Rung | Correct | Face right, opening wrong |
|---|---|---|---|---|
| dims | `gemini` | N-D, N-CD | 100.0 both | 0 |
| dims | `gpt_hi` | N-D | 56.8 [49.7, 63.6] | 38 |
| dims | `gpt_hi` | N-CD | 66.1 [59.2, 72.5] | 0 |
| dims | `claude_md` | N-D | 50.5 [43.5, 57.5] | 31 |
| dims | `claude_md` | N-CD | 50.5 [43.5, 57.5] | 5 |
| conflict_face | all three | N-D, N-CD | **0.0 [0.0, 2.0]** | 0 |

This is what GPT's `N-CD` result consists of. At `N-D` it fails partly at
reading the pose and partly at converting a pose it read (38 replies). Adding
C removes the second failure entirely and lifts face accuracy to 66.1.

**In `conflict_face` not one model named the captured face on a single trial
of 192, at either rung, including Gemini which is at 100% in `dims`.** That is
not a perception limit. It is the text being reported back.

**The no-image control**, `tab_ex2_q3_noimage.csv`. `N-D` in `dims` with the
picture withheld, to show that the configuration moves a model *towards the
scene* rather than towards a better guess from the text. **Now collected for
all three models at three repeats**, 576 trials; the earlier note that only
Gemini was bought is superseded.

| Model | `N-D` no image | `N-D` with image | Paired difference |
|---|---|---|---|
| `gpt_hi` | -5.2 [-19.0, 8.6] | 3.1 | -8.3 [-27.1, 10.5] |
| `gemini` | 0.0 [-14.7, 14.7] | 100.0 | **-100.0 [-114.7, -85.3]** |
| `claude_md` | 5.2 [-7.6, 18.0] | 0.0 | 5.2 [-14.7, 25.1] |

Without the image Gemini reports the correct opening on 47.9% and 52.1% of the
two faces and names the correct face on 50.0% of replies, which is chance.
Its remediated result is obtained from the image.

---

### 9.6 The precedence directive, off the ladder

`X-image` is `A_ATTEND` plus one sentence, *where the image and the stated
resting face disagree, go by the image*, on the base schema, so `X-image`
minus `N-A` is that sentence and nothing else. **These cells are two repeats,
64 trials, against `N0` and `N-A` baselines at three.** They are the least
precise numbers in the chapter and are reported apart from the ladder.
`tab_ex2_q3_directive_gate.csv` holds the stage-1 read;
`tab_ex2_q3_directive.csv` still says "not run" for every row because cell 12b
has not been re-executed since the runs landed, and is stale.

| Cell | Model | small | large | contrast | delta vs `N0` | delta vs `N-A` |
|---|---|---|---|---|---|---|
| `conflict_face` @ `X-image` | `gpt_hi` | 40.6 | 42.2 | -1.6 | **+88.0 [72.3, 103.8]** | **+78.6 [60.0, 97.3]** |
| | `gemini` | 100.0 | 0.0 | **+100.0** | **+200.0 sat.** | **+196.9 [193.5, 200.3]** |
| | `claude_md` | 40.6 | 56.2 | -15.6 | -22.9 [-46.5, 0.7] | -11.5 [-35.3, 12.3] |
| `congruent_face` @ `X-image` | `gpt_hi` | 68.8 | 1.6 | 67.2 | **-22.4 [-37.1, -7.7]** | |
| | `gemini` | 100.0 | 0.0 | 100.0 | 0.0 sat. | |
| | `claude_md` | 60.9 | 59.4 | 1.6 | 6.8 [-21.0, 34.6] | |
| `conflict_face` @ `X-state` | `gpt_hi` | 1.6 | 71.9 | -70.3 | 19.3 [4.9, 33.7] | 9.9 [-5.1, 24.8] |
| | `gemini` | 0.0 | 100.0 | -100.0 | 0.0 sat. | -3.1 [-6.5, 0.3] |
| | `claude_md` | 40.4 | 65.9 | -29.7 | -37.0 [-63.9, -10.0] | -25.5 [-47.7, -3.3] |

1. **Gemini reverses completely.** -100.0 to +100.0 at all 32 positions, and
   it reports the scene-implied opening on all 128 replies. The model no
   ladder configuration moved by a single point follows the image immediately
   when told which source wins. An arbitration step exists and an instruction
   reaches it.
2. **GPT abandons the text without substituting the scene.** +88.0 against
   `N0`, but it lands at -1.6, which is no contrast in either direction. Its
   reported opening matches the scene on 40.6% and 50.0% of replies.
3. **Claude does not move.** -11.5 against `N-A`, spanning zero.
4. **The symmetry control holds.** `X-state` moves neither GPT (9.9, spans
   zero) nor Gemini (-3.1, spans zero) against `N-A`. Both sentences name the
   image and differ in one word, so `X-image` is a response to which source
   was named.
5. **The wording control mostly holds, with one cost.** In `congruent_face`,
   where the stated face is true, Gemini is unchanged at 100.0 and Claude
   unchanged. GPT loses 22.4 points, which is a real cost of the extra
   sentence and about a quarter of the 88.0 it buys under conflict.

**Incomplete cell.** `claude_md` at `conflict_face` `X-state` landed 47 of 64
`small_face` and 44 of 64 `large_face` trials. All 32 positions are
represented so the paired contrast computes, but it is the weakest row here.

**Predictions against outcomes**, from `prompts.PREDICTIONS`, recorded before
the first call. Order: predicted inert, is inert. Attention: predicted inert,
inert in `conflict_face` but moves Gemini 50.0 points in `dims`. Derivation:
predicted to move in conflict, does, for Claude, in the direction opposite to
remediation. Elicitation: predicted to move in both and by more than
derivation alone, holds for GPT in `conflict_face`, fails in `dims` where GPT
needs both. `precedence_image`: predicted to move toward the image short of
the `congruent_face` ceiling and to be inert in `congruent_face`; Gemini
exceeded it by reaching the ceiling, GPT fell short in an unanticipated way by
landing at no contrast, and it was not inert in `congruent_face` for GPT.
`precedence_state`: predicted inert in `conflict_face`, inert for GPT and
Gemini.

---

## 10. The figures

Both live figures are TikZ source plus a companion CSV of the plotted values,
meant to be included with `\input{}`. There are **no rendered chart images** in
the repository, by design: the notebook writes plotted values plus a
self-contained picture rather than a PNG.

| Figure | Files | Panels |
|---|---|---|
| Q1 share | `figures/ex2_q1/fig_ex2_q1_share.{tex,csv}` | 3: `congruent`, `congruent_face`, `dims` |
| Q2 share | `figures/ex2_q2/fig_ex2_q2_share.{tex,csv}` | 5: the three above plus `conflict`, `conflict_face` |

Both are the **same drawing routine**: Q2's figure cell is Q1's cell 13 with
declared string substitutions, so the two pictures are guaranteed to read as
one family.

**What they plot.**

- **y axis**: Franka share, %, 0 to 100, gridlines at 0/25/50/75/100
- **x axis**: resting face, two ticks per panel, `small_face` then `large_face`
- **bar colour**: model. `gpt_hi` teal, `gemini` blue, `claude_md` amber. The
  cell raises if two models share a colour, because a silent default would draw
  a legend naming three models over bars showing two
- **panels**: one per condition, left to right in the order above
- **error bars**: Wilson 95% intervals with caps
- **reference line**: dashed grey at 50%, annotated "indifferent". A model with
  no preference between the two arm types names a Franka half the time
- **legend**: colour swatches to the right of the last panel

**How to read them.** A panel where the two bars are far apart is a model
separating the faces. A panel where they are level is a model that cannot, or
that is not consulting the face. In `conflict` and `conflict_face` the bars
invert relative to `congruent`, and that inversion is the precedence finding.

**What each panel draws on.** `congruent` and `dims` from
`ex2_q1_congruent_N0.jsonl` and `ex2_q1_dims_N0.jsonl`; `congruent_face` from
`ex2_q1_congruent_face_N0.jsonl`; `conflict` and `conflict_face` from
`ex2_q2_conflict_N0.jsonl` and `ex2_q2_conflict_face_N0.jsonl`. Each figure CSV
must agree cell for cell with the corresponding share table, and does.

**Q3 has no figure, deliberately.** Its endpoint is a table of second-order
contrasts whose intervals are about thirty points wide by construction. Drawn
as bars they would imply a precision the design does not have.

---

## 11. Limitations the chapter must disclose

1. **Posture confounds geometry.** `small_face` stands and `large_face` lies,
   so a model can score the whole design on posture alone. The reading "obtains
   the opening from the geometry" is not separable from "reads posture and
   applies a rule". Q1 measures posture-plus-lookup.
2. **A second posture route.** The `dims` state names its extents
   `size_upright_m`, which states the frame the three numbers were taken in, so
   a two-way posture judgement fixes the opening without the model ever working
   out which two extents are horizontal. This is deliberately not patched: the
   extents reach the model as an unordered set whatever the field is called, so
   dropping the frame would add an ambiguity rather than restore a step.
3. **Why the third face was withdrawn, and what it cost.** `edge`
   (0.130 x 0.050 down) was the only contrast that separated deriving from
   geometry from reading posture, because `edge` and `large_face` are both flat
   and differ only in geometry. It was withdrawn on 2026-08-27 because no model
   read it: GPT separated `edge` from `large_face` on 58% of 81 answered trials,
   Fisher p = 0.76, while answering a plain standing-or-flat question about the
   same pictures 18 times out of 18. The two faces that remain were then
   checked directly as a two-way forced choice, Gemini 97% and GPT 75%, so the
   reduction is a retreat to the question both models demonstrably read, not to
   one nothing can answer.
4. **Why the prompt says nothing about the convention.** "An object resting
   flat lies on its largest face" would make the design sound, but with two
   faces that sentence reduces the derivation to *see flat, apply the rule,
   0.100*, which is a posture judgement models already perform perfectly, and
   the face-to-geometry mapping is reserved for factor C. The guarantee is
   enforced at capture instead: a scene that settles outside 0.005 m of an
   authored rest height fails rather than being relabelled.
5. **Effort is not matched across providers and cannot be.**
6. **One viewpoint.** Only `ex2_cam` was captured, so there is no viewpoint
   control.
7. **Rungs at one repeat against three-repeat baselines.** A rung's
   per-position share is 0 or 100 while the baseline's is one of four values, so
   every Q3 second-order contrast is noisier than Q1's and Q2's. Say so beside
   any number quoted from them.
8. **The Q3 `dims` gate file mixes two collection dates.** It is seeded from
   two 2026-08-27 pilot files at the same prompt version, with the seeding
   filter rebuilding the exact trial id so no other factor arm can enter. That
   is what resuming always does, and it is why the hash is recorded.
9. **The `N-D` no-image control exists for Gemini only.**

---

## 12. Discrepancy register

Where an older document, an older saved output or older prose disagrees with
the final data. Use the right-hand column.

| Where | Says | Use | Why it moved |
|---|---|---|---|
| `EX2_GUIDE.md` Q2 table | `gpt_hi` `conflict_face` **-84.4** [-97.2, -71.6] | **-89.6** [-95.0, -84.1] | Written at one repeat, 32 trials per cell; the condition is now at three |
| `EX2_GUIDE.md` Q2 table | `gpt_hi` `congruent_face` **+87.5** [75.9, 99.1] | **+89.6** [84.1, 95.0] | Same cause |
| `EX2_GUIDE.md` Q2 table | `claude_md` `conflict_face` **+15.6** [-10.9, +42.2] | **+7.3** [-6.7, 21.3] | Same cause. Still a null either way |
| `EX2_Q1_STATUS.md` §5.1 | Cue probe, east bank only: GPT 95.0, Gemini 100.0, Claude 75.0 | Both banks: GPT 89.2, Gemini 100.0, Claude 79.2 | The west bank was collected afterwards, removing a sampling objection to the gate that licenses Q1 |
| `EX2_Q1_STATUS.md` §5.5 | `gpt_hi` `congruent_face` **+87.5** | **+89.6** | As above |
| `nb_cells_a.py` comment | low-effort `gpt` scored **95%** on the cue probe | **93.3%** (56/60) | 95.0% is `gpt_hi`'s figure, not `gpt`'s. Reconcile before either reaches the chapter |
| `EX2_Q1_STATUS.md` §5.6 | "Declines were zero in every cell" | Still true, and now also true of the 576 no-image trials | Strengthened, not contradicted |
| `EX2_Q1_STATUS.md` §7 items 1, 3, 4, 5, 7 | Open items | Items 3 and 7 are resolved: the notebooks now carry current saved outputs, and the cue probe covers both banks. The rest stand | |
| Q3 notebook, saved output before 2026-08-29 | Attribution over Gemini only, two rows | Twelve rows over three models and both conditions | The `conflict_face` ladder landed after those cells last ran |
| Q2 notebook, saved output before 2026-08-29 | `conflict_face` at n=32 | n=96 | Same cause |
| Q1 and Q2 provenance tables before 2026-08-29 | 12 and 4 rows | 14 and 6 rows | Three roles were missing; see below |
| Anything written before the `congruent_face` top-up | `claude_md` `congruent_face` **+6.2** [-20.1, 32.6] | **-5.2** [-21.6, 11.2] | That figure was one repeat. At three it is still a null, and a tighter one |
| §9.5 of this document before 2026-09-01 | Q3 ladder at one repeat: GPT `dims` `N-CD` **18.8**, GPT `conflict_face` `N-D` **+39.6**, Claude `N-C` **-79.2** | **32.3**, **+24.0**, **-74.0**; §9.5 is rewritten in full | Repeat 3 of every ladder cell landed at `dd34691`. Every finding held its shape and the magnitudes moved |
| §9.5 of this document before 2026-09-01 | No-image control "collected for Gemini only" | All three models, three repeats, 576 trials | The GPT and Claude cells were bought afterwards |
| `tab_ex2_q3_directive.csv` | Every row "not run" | The directive runs are on disk; use `tab_ex2_q3_directive_gate.csv` and §9.6 | Cell 12b has not been re-executed since the `X-image` and `X-state` runs landed. Re-run it before quoting that file |
| Q3 notebook markdown, cell 1 | "One repeat per rung" | Three repeats per ladder rung, two per directive cell | Written for the staged pilot and never updated |

### Three defects found and fixed, 2026-08-29

Both were fixed in the notebook **source** cells, which are the authority, and
the notebooks were then rebuilt and re-executed. No run file was touched and no
reported number changed.

1. **The provenance tables omitted conditions the figures plot.** The
   provenance cell looped over a hardcoded tuple of roles that had not grown
   with the design. `tab_ex2_q1_provenance.csv` omitted `congruent_face`, and
   `tab_ex2_q2_provenance.csv` omitted both `congruent_face` and
   `conflict_face`, so two of the Q2 figure's five panels had no provenance row
   at all. A third gap turned up while fixing it: Q1 also omitted
   `dims_noimage`, the run behind the no-image floor in section 9.3.

   Fixed by adding the missing roles to the loop in `nb_cells_b.py` (cell 14)
   and `nb_q2_cells.py` (cell 13). Q1's provenance table went from 12 rows to
   14, Q2's from 4 to 6. **Every run file behind a published number now has a
   provenance row carrying its row count and sha256.**

2. **The Q2 figure header misnamed its own generator**, calling it
   `notebooks/ex2_q2_derivation.ipynb`, which does not exist. The file is
   `ex2_q2_precedence.ipynb`. Q2's figure is Q1's figure cell put through a
   substitution list, and the generic `ex2_q1` to `ex2_q2` rule rewrote
   `ex2_q1_derivation.ipynb` into a plausible but wrong filename.

   Fixed by adding an explicit substitution **ahead of** the generic rule in
   `build_q2_nb.py`, so the header now reads
   `Generated by notebooks/ex2_q2_precedence.ipynb`. Ordering is what makes it
   work: the specific rule consumes the string before the generic one sees it.

3. **The spend gate counted rows, not trials, and stopped a run short.** This
   is the one that cost data rather than tidiness. `answered()` counted every
   row that held a real answer, and a run file legitimately holds more than one
   row per trial: the runner re-asks an unparseable reply and appends the
   retry, and a cell re-run at a higher repeat count appends alongside what is
   already there. So the gate compared a **row** total against a **trial**
   total.

   `ex2_q1_congruent_face_N0.jsonl` had 678 rows for 455 distinct trials. The
   gate read `677 of 612`, declared the cell complete, and refused to buy the
   157 trials that were missing: Claude's repeats 2 and 3 entirely, and
   Gemini's repeat 3. That is the whole explanation for the imbalance this
   document previously reported as a limitation.

   Fixed in `analysis/ex2/ex2_q_common.py`: `answered()` now counts distinct
   `trial_id` (or `check_id`), falling back to a row count for the older probe
   shapes, which carry no id and where one row is one observation. Pinned in
   `harness/h_ex2_q_common.py`. The gate then reported `455 of 612` honestly,
   the 157 were collected, and `FACE_REPEATS` was raised from 1 to 3 in
   `nb_cells_b.py` so the design and the data agree.

   **Any spend gate on any file with retries was reading high.** The other
   cells happened to be complete anyway, so nothing else was cut short, but the
   same fault would have hidden a shortfall in any of them.

---

## 13. Version history

| Date | Change | What it invalidates |
|---|---|---|
| 2026-08-07e | Prompt version behind `All_conflict.jsonl` and the whole legacy set | Nothing collected then is comparable with anything reported here |
| 2026-08-26 | The synthetic block replaces the mustard bottle as the flip object | The mustard captures become a pilot record |
| 2026-08-26b | Prompt version for the first block runs | Superseded the next day |
| 2026-08-27 | The seven-step attention ladder `P0`-`P4` and the prose `why` block are removed, replaced by six rungs over three factors; the poses are renamed to `small_face` / `large_face` end to end; the third face is withdrawn | Any note describing P-rungs or a `why` block; any run file written before this date |
| 2026-08-27b | **The reported prompt version.** Every number in this document | |
| 2026-08-28 | Q1 and Q2 measured; Claude added as a third model; the cue probe extended to both banks | The three-face tables and figure, archived under `_archive/20260827_threeface/` |
| 2026-08-29 | The Q3 ladder completed; every table and figure regenerated | The saved notebook outputs and Q3 tables written on 2026-08-28 |
| 2026-08-29 | `answered()` fixed to count distinct trials; `FACE_REPEATS` raised from 1 to 3; the 157 missing `congruent_face` trials collected, taking that condition to 612 of 612 | `claude_md`'s `congruent_face` figure, and any prose resting on its one-repeat denominator |

---

## 14. How to regenerate

From `fourarm/`, with the project venv. None of this spends anything: the paid
cells print their cost and return when `CONFIRM_SPEND` is unset.

```bash
jupyter nbconvert --to notebook --inplace --execute notebooks/ex2_q1_derivation.ipynb
jupyter nbconvert --to notebook --inplace --execute notebooks/ex2_q2_precedence.ipynb
jupyter nbconvert --to notebook --inplace --execute notebooks/ex2_q3_remediation.ipynb
```

Outputs go to `tables/ex2_q{1,2,3}/` and `figures/ex2_q{1,2}/`. The notebooks
are generated from `nb_cells_a.py`, `nb_cells_b.py`, `nb_q2_cells.py` and
`nb_q3_cells.py` by the three `build_q*_nb.py` scripts, so a change belongs in
the source cells and not in the `.ipynb`.

The offline harness gates, from `harness/`, all currently pass:

```bash
python3 h_ex2_prompts.py h_ex2_labels.py h_ex2_q_common.py h_ex2_stats.py h_ex2_transforms.py
```

---

## 15. What is still buyable, and what it would settle

In descending order of what it adds to the chapter.

| Cell | Calls | Settles |
|---|---|---|
| `N-D` no-image control for `gpt_hi` and `claude_md` | 136 | Whether GPT's +39.6 remediation gain is towards the scene or towards a better guess from the text. This is the control for the strongest new Q3 result |
| The `conflict_face` ladder at a second repeat | 1,020 | Halves the width of every Q3 `conflict_face` interval, which would move several UNRESOLVED cells into a verdict |
| `congruent` top-up | ~14 | Equal denominators on the control |
