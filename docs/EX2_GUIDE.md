# Experiment 2: cue conflict and grounding

The pipeline in running order, with the commands that were used. Every command
assumes you are in `fourarm/`. The instructions here are consolidated from the
module docstrings, which remain the authority for options this guide does not
cover.

Prompt version: `2026-08-26b`. The prompt module was replaced on 2026-08-27:
the seven-step attention ladder `P0`-`P4` is gone and so is the prose `why`
block. See **The 2026-08-27 prompt change** below before reading any older
note or run file.

Historical dataset: `runs/All_conflict.jsonl`, 2,827 rows across three models,
seven P-rungs, 22 scenes and three repeats. Chats cite 2,772 usable rows, so
roughly 55 are filtered in hygiene. Those rows were collected under prompt
version `2026-08-07e` and are **not comparable** with anything collected now.

---

## Stage 0: capture the scenes

Requires Isaac Lab. Skip this unless you are building a new scene set.

```bash
# current: the synthetic block, 34 positions x 2 poses -> 68 captures
python3 ycb/capture_ex2_scene.py --spec ycb/ex2_block.txt   # -> out/ex2_capture_block/
```

Scene lists: `ycb/ex2_block.txt` (the block; requires `--spec`). The older
`ycb/ex2_scenes.txt`, `ycb/ex2_east.txt`, `ycb/ex2_west.txt` drove the
mustard/sugar-box pilots and are kept for provenance.

The flip object is the synthetic **block** (2026-08-26), which replaced the
mustard bottle. It is a plain procedural cuboid (0.130 x 0.100 x 0.050 m)
with two resting poses in use — `block_upright` (0.050 across, all arms,
recorded as `small_face`) and `block_large` (0.100, URs only, `large_face`).
Each position is captured in both, so the categories get equal counts and
every contrast is paired within a position. The mustard captures stay on disk
as the pilot record.

A third pose, `block_small` (0.130 x 0.050 down, recorded as `edge`), was
**withdrawn on 2026-08-27** — see *Two faces, not three* below.

The prim names do **not** match the face names the experiment uses: see
**Resting-face names** below. `ex2.resting_face` in the capture trail is
provenance only and nothing reads it.

---

## Stage 1 to 3: build the trials

These modules are imported by the runners rather than invoked directly.

| Step | Module | Does |
|---|---|---|
| 1 | `experiments/ex2/labels.py` | Pose-neutral object labels |
| 2 | `experiments/ex2/transforms.py` | The three state transforms |
| 3 | `experiments/ex2/prompts.py` | The factor rungs, the field aliases and the typed answer schema |

---

## Stage 4: run

Always dry-run first. It renders the trials without spending a model call.

All three runners now send the SAME prompt shape: one queued task, one idle
arm, typed answer fields. They differ in what they sweep, not in what they
ask. The batch round is gone.

```bash
# smallest runnable form: three conditions, one prompt, one view
python3 -m experiments.ex2.cue --dry-run
python3 -m experiments.ex2.cue --out runs/ex2_cue.jsonl --repeats 3

# the main runner: every rung x condition x view
python3 -m experiments.ex2.run --probes out/ex2_capture --dry-run
python3 -m experiments.ex2.run --probes out/ex2_capture \
    --model qwen --limit 12 --out runs/ex2_smoke.jsonl

# the solo design: counterbalanced preference, repeatable rungs
python3 -m experiments.ex2.solo --dry-run
python3 -m experiments.ex2.solo --out runs/ex2_solo.jsonl --repeats 3
python3 -m experiments.ex2.solo --out runs/ex2_nd.jsonl --rung N-CD --rung N0
```

**Flag trap.** `--models` takes a comma list. In `solo.py`, `--condition`,
`--rung`, `--preference` and `--modality` all append. Mixing the two
conventions silently halved one run. `run.py`'s `--preference` takes a single
value, not a list.

**Rung names.** `N0`, `N-A`, `N-C`, `N-order`, `N-D`, `N-CD`. A `P`-rung is
refused by name rather than defaulted, so an old command fails loudly instead
of recording an `N0` result under a `P2` label.

---

## Stage 5: grade and rescore

`experiments/ex2/grade.py` is invoked by the runners. To re-grade an existing
run with the self-contradiction detector:

```bash
python3 -m experiments.ex2.rescore --run runs/ex2_solo.jsonl \
    --probes out/ex2_capture
```

---

## Stage 6: analyse

```bash
# the four diagnostic views, from one instrument
python3 -m experiments.ex2.analyse --run runs/All_conflict.jsonl --view odd
python3 -m experiments.ex2.analyse --run runs/All_conflict.jsonl --view stable
python3 -m experiments.ex2.analyse --run runs/All_conflict.jsonl \
    --probes out/ex2_capture --view reason --model qwen --rung N-D

# the eight-step conflict analysis
python3 experiments/ex2/analyse_conflict.py runs/All_conflict.jsonl

# independent cross-check of the legality table
python3 experiments/ex2/verify_legality.py runs/All_conflict.jsonl

# the dimension-only condition
python3 analysis/ex2/ex2_analyse_dims.py runs/piece_dims_P2.jsonl
```

The three scripts above read their rungs and their candidate openings **off
the file**, so each works on a P-rung file and an N-rung file alike. They
print what they found at the top; check that line before reading a table.

**Run `--view extract` before quoting any width-derived number from a
P-rung file.** Three successive extractor rules each failed on an unseen
sentence shape and produced a false finding before being caught. Every
extraction fault returns 0.080 or 0.140, the two gripper apertures rather
than an object width, so that is the diagnostic tell.

On an N-rung file the opening is a typed JSON number and no extractor runs,
so the view reports how many off-candidate values came from the typed field.
Those are model faults, not instrument faults, and the distinction is printed
rather than left to be inferred.

**The dims file is `runs/piece_dims_P2.jsonl`**, 1,759 rows, with
`runs/piece_dims_P2_ur.jsonl` at 396 rows for the UR preference. Some earlier
notes name a `piece_dims_P2-2.jsonl`, which does not exist in this tree. Pair
scenes are filtered via `r['seq'][0] in ('p','e')`.

---

## Question 1: derivation

`notebooks/ex2/ex2_q1_derivation.ipynb` runs and analyses Q1 one cell at a time.
Regenerate it from source rather than hand-editing the JSON:

```bash
python3 notebooks/_cells/build_q1_nb.py notebooks/ex2/ex2_q1_derivation.ipynb
```

Cells that spend money print the call count and refuse to run until
`CONFIRM_SPEND` is set to that exact number. The runners resume, so re-running
a cell costs nothing and destroys nothing. Outputs go to `tables/ex2_q1/` and
`figures/ex2_q1/`.

## Question 2: precedence

`notebooks/ex2/ex2_q2_precedence.ipynb` asks which source governs when the text
states the capability-relevant quantity and the scene contradicts it. One new
condition, `conflict`, already implemented in `transforms.py`: each face
declares the other, so both the resting face and the opening are false and
every trial crosses the Franka aperture.

```bash
python3 notebooks/_cells/build_q2_nb.py notebooks/ex2/ex2_q2_precedence.ipynb
```

**It shares cells with Q1 rather than copying them.** The key paste, the block
geometry check and the capture inventory are Q1's own strings, spliced in by
the build script; cell 1 is Q1's cell 1 with four declared substitutions. Each
substitution must match exactly once or the build fails, so a rename in Q1
that would leave Q2 pointing at Q1's tables stops the build instead of
producing a wrong file quietly.

**The direction names.** `transforms.py` records `permissive` when the *true*
face is the all-arms one, so the text under-states the arms and forbids the
Franka, which is the opposite of what the word suggests. The stored field is
left alone, and every table names what the text does: `text_permits_franka`
and `text_forbids_franka`. Use those two in the chapter as well.

**The measure is Q1's, always anchored to the image.** Franka share on the
`small_face` scene minus Franka share on the `large_face` scene, paired within
position. Positive means the scene governed, negative means the text did.
Negative is the expected result and is the finding.

**`congruent` and `conflict` send byte-identical instructions**, because
`prompts.CONDITIONS` maps both to the full glossary and the full R3. The whole
manipulation is in the state, so no prompt difference can explain the
contrast. Cell 5 asserts it rather than diffing it, and it belongs in the
chapter for the same reason Experiment 1's byte-identical Full Information
prompt does.

Cell 6 is the only paid cell: 68 scenes x 3 models x 3 repeats = 612 calls.

**The result, collected 2026-08-28.** Two conditions, and they must be read
together. The measure is Franka share on the `small_face` scene minus Franka
share on the `large_face` scene, paired within position, always anchored to the
face the image shows.

| model | congruent | congruent_face | conflict | conflict_face |
|---|---|---|---|---|
| `gpt_hi` | +100.0 | +87.5 [75.9, 99.1] | -100.0 | **-84.4 [-97.2, -71.6]** |
| `gemini` | +100.0 | +100.0 | -100.0 | **-100.0 [-100.0, -100.0]** |
| `claude_md` | +100.0 | +6.2 [-20.1, 32.6] | -100.0 | **+15.6 [-10.9, +42.2]** |

**`conflict` on its own cannot support a precedence claim, and an earlier
version of this section wrongly said it could.** R3 names `opening_needed_m`
verbatim and the state supplies it, so a model that reads the number and
applies the rule has broken nothing: it is complying. No rule mentions
`resting_face`, so the false face there is inert. `congruent` and `conflict`
send byte-identical instructions, so the model has no signal that the trial
differs from one where obeying R3 is correct.

**`conflict_face` removes that escape, and the effect survives.** With the
number withheld, R3 renders in the form that names no field, there is nothing
to comply with, and the only route to an opening is a face -- one asserted by
the text, one visible in the image. GPT still reads -84.4 and Gemini a complete
-100.0, against their own matched ceilings of +87.5 and +100.0 on
`congruent_face`, which renders a byte-identical prompt and differs only in
whether the stated face is true.

So the finding is real and the evidence for it is now sound: **when a supplied
face contradicts the scene, the two models that can derive an opening follow
the text, and they do so whether or not a rule directs them to the stated
field.**

**Claude dissociates, and needs its own sentence.** Its +6.2 on `congruent_face`
and +15.6 on `conflict_face` are both nulls: it cannot derive an opening from a
face even when the face is true, so it has no source to prefer. Its -100.0 in
`conflict` was pure R3 compliance -- hand it a number and it applies the rule,
take the number away and it is at chance. Reporting the three models as one
unanimous block, which the `conflict`-only result invited, would have been
wrong about one of them.

**Two supporting readings.** In `conflict`, every one of 576 analysed trials
reported an opening matching the **text**: zero matching the image, zero
matching neither, in both directions. And the `text_forbids_franka` direction
is what makes this more than caution -- there the model passes over a Franka
that would fit.

`gpt_hi`'s -84.4 rather than -100 is four positions of 32 that did not flip;
it also names a Franka on 3.1% of `small_face` trials in `congruent_face`, so
some of that is its own derivation noise rather than a partial escape from the
text.

---

## Question 3: remediation

`notebooks/ex2/ex2_q3_remediation.ipynb` asks which kind of instruction moves a
model from following the text to using the scene. The six rungs come from
`prompts.RUNGS` and are not redefined.

```bash
python3 notebooks/_cells/build_q3_nb.py notebooks/ex2/ex2_q3_remediation.ipynb
```

**The gate is N-D, not N-CD.** The 2026-08-27 pilots already show Gemini going
from 46.9 at N0 to a complete flip under elicitation alone, with the face
named correctly on all 64 trials, and GPT not moving. So elicitation is the
rung the evidence implicates, `N-D` minus `N0` is the contrast that matters,
and `N-C` becomes the informative comparison rather than an intermediate step.
`N-CD` is demoted to a sufficiency cell for a model `N-D` does not move.

**Three verdicts, not two.** At one repeat over 32 positions an effect below
about 30 points cannot be told from zero, so the gate reports *moved*, *not
moved* and **unresolved**, the last meaning the cell needs more repeats before
it can be called either way. Exercised against the pilot files it reads Gemini
`MOVED` (+53.1 [40.7, 65.5]), gpt_hi `UNRESOLVED` (+13.5 [-9.3, 36.4]) and
claude_md `NOT RUN`, and narrows the later stages to Gemini alone.

**The staged spend.**

| Stage | Cell | Calls | Gated on |
|---|---|---|---|
| Gate: N-D in dims | 6 | 204 | nothing |
| Control: N-D with no image | 8 | 68 per model | models the gate moved |
| Stage 2: N-C, N-order, N-A, and N-CD where needed | 9 | up to 816 | the gate |
| Stage 3: the five rungs in conflict | 10 | 1,020 | stage 2 and Q2's N0 |

**The no-image control is the decisive one.** Q1's ablation answers the
question at `N0`; it cannot answer it at `N-D`, because a schema effect only
shows under the schema. Cell 8 runs `N-D` in dims with no image, and it must
land at zero or the rung is a text artefact and is withdrawn.

**No figure cell.** Q3's endpoint is a table of second-order contrasts whose
intervals are about thirty points wide by construction. Drawn as bars they
would imply a precision the design does not have.

---

**Three facts about the block captures that the chapter must disclose.**

1. **The idle UR is chosen per position.** Every capture was
   written with `--idle ur_w,franka_n`, capture_ex2_scene's default. That is
   right for the 15 west positions and wrong for the 15 east ones, where the
   object is reached by `ur_e`: there, idle-and-reachable collapsed to
   `franka_n` alone, so on `small_face` the only legal arm was also
   the preferred one and on `large_face` **no arm was legal at all**. The east
   half carried no contrast.

   `run.present_reachable_ur` fixes this at load time by presenting whichever
   UR is in the object's own reach list as the idle one. It is legitimate
   because capture_ex2_scene sets `ag.state` by attribute write *after* the
   frames are rendered and never commands an arm to move — all four `ee_xy`
   are symmetric rest positions, so the picture shows four parked arms
   whichever labels the text carries. Pass `present_ur=False` to read the
   captures exactly as written.

2. **32 of 34 positions carry the contrast and show the block.** Two
   independent preconditions, and a position must clear both.

   - **Legality.** `e02` is excluded: `franka_n` cannot reach it at all, so
     the Franka is never legal there whatever the idle set, and there is no
     arm choice to measure.
   - **Visibility.** `e10` is excluded: the block presents 3% of the median
     block area for its bank, against a next-worst 60%, because the Franka
     stands in front of it. A position can carry the full contrast with the
     object hidden, and until 2026-08-27 nothing checked for it —
     `experiments/ex2/visibility.py` now does, from pixels alone and blind
     to any model reply, so a position is never excluded for having scored
     badly. It runs per bank, since a `w` block renders about 10% larger
     than an `e` block in the same pose and one pooled median would compare
     the banks rather than test occlusion.

   Cell 3 prints both grids and fails loudly rather than letting the
   analysis assume a count.

3. **Only `ex2_cam` was captured**, so Q1 has no viewpoint control.

**On the intervals.** `analysis/ex2/ex2_stats.py` holds Wilson, Newcombe and
the paired-mean t interval, replacing two copies of Wilson and an absent
Newcombe. The contrasts are computed within position and averaged, so the unit
is the position and the interval to quote is the **paired** one; Newcombe is an
interval on a difference of *independent* proportions and is emitted alongside
as the conservative unpaired comparison. Both are in
`tab_ex2_q1_contrasts.csv`. `h_ex2_stats.py` pins Wilson against an independent
derivation rather than against a quoted table.

---

## Instrument validation

| File | Checks |
|---|---|
| `runs/ex2_cue.jsonl` | Cue validation |
| `runs/ex2_mancheck.jsonl`, `runs/ex2_mancheck_gpt.jsonl` | Can the model read pose when asked about nothing else |
| `runs/ex2_seecheck.jsonl` | What the model says it sees, alongside the pose it names |
| `runs/ex2_floor*.jsonl` | Perception floor |

```bash
python3 -m experiments.ex2.mancheck --probes out/ex2_capture \
    --model qwen --out runs/ex2_mancheck.jsonl
python3 -m experiments.ex2.seecheck --probes out/ex2_capture \
    --model qwen --out runs/ex2_seecheck.jsonl
```

---

## Analysis discipline

Carried forward because each rule exists because something went wrong once.

- Prefer the physical infeasibility column over outcome labels for conflict
  trials. It is unaffected by the width extractor and by the grader's
  uninformative classification.
- Per-scene majority is the unit of analysis. 33 trials per cell are 11 scenes
  by 3 repeats, not 33 independent observations.
- Preserve binding cause against violation type. Binding cause is a property of
  the frozen state, computed before any model call. Violation type is a
  property of the model's reply.
- Wilson 95% for proportions, Newcombe 95% for differences. Flag any interval
  that spans zero.
- Never merge two files into one report bucket. Pass files explicitly.

---

## Superseded run files

`A_conflict_gemini.jsonl`, `A_conflict_noimage_P4.jsonl`, `A0_textonly.jsonl`,
`B_baseline*.jsonl` and `C_all_r2.jsonl` use an earlier condition-A/B/C naming
and are superseded by `All_conflict.jsonl`. They are retained for provenance.
The nine `ex2_solo*.jsonl` files are development and pilot runs of the solo
design.

---

## The 2026-08-27 prompt change

`experiments/ex2/prompts.py` was replaced. What changed, and what it means for
anything written before that date.

### Rungs

The attention ladder `P0, P1, P2a, P2, P3a, P3, P4` is gone. In its place are
six rungs over three factors, each naming a different hypothesis about why a
model follows a supplied opening instead of the scene:

| Rung | Adds | Factor |
|---|---|---|
| `N0` | nothing | the base prompt, where Q1 and Q2 are read |
| `N-A` | look at the object in the image | attention |
| `N-C` | the opening is the smaller horizontal extent | derivation |
| `N-order` | no wording; the schema reorders | order (the control for D) |
| `N-D` | report the face and opening before the arm | elicitation |
| `N-CD` | C and D together | sufficiency against `N0` |

`N-order` exists because `N-D` moves the report ahead of the arm *and* asks for
the face, and a model generates left to right. Without the control an `N-D`
effect could not be attributed to either. `N-CD` is a sufficiency cell against
`N0`, never a test of whether C and D interact.

The boundary between factors is checked mechanically by
`prompts.assert_rungs_isolated`, which the harness runs.

### Field names shown to the model

The state renders through an alias table. Nothing underneath changes: the
validator, the probe sets and the run files keep the deployed names.

| Deployed | Shown to the model |
|---|---|
| `grasp_m` | `opening_needed_m` |
| `max_grasp_m` | `opening_max_m` |
| `payload_kg` | `max_load_kg` |
| `delicate_ok` | `handles_delicate` |
| `dims_m` | `size_upright_m` |
| `reach_ok_arms` | `arms_that_can_reach` |
| `pose` | `resting_face` |

**EX2 therefore prints different field names from EX1, and the chapter must
say so.**

### Resting-face names

The block's poses were renamed on 2026-08-27. `upright`, `lying_small_face`
and `lying_large_face` are gone; `labels.TRUE_POSE`, `transforms`, the state
and the answer schema now all say `small_face`, `large_face`. One vocabulary
end to end, so nothing translates at render time. Since 2026-08-27 the capture
trail writes the same words, so `nb_cells_a`'s `TRAIL_FACE` map is only needed
to read captures written before that date.

**Read the geometry, not the prim names.** The block is 0.130 x 0.100 x 0.050,
so its faces are 0.130 x 0.100 (largest, 0.0130 m²), 0.130 x 0.050 (middle,
0.0065 m²) and 0.100 x 0.050 (smallest, 0.0050 m²). Each prim is spawned
already resting on one of them:

| Prim | Face down | Which face | Vertical | Opening | Name |
|---|---|---|---|---|---|
| `ycb_block_upright` | 0.100 x 0.050 | smallest | 0.130 | 0.050 | `small_face` |
| `ycb_block_large` | 0.130 x 0.100 | largest | 0.050 | 0.100 | `large_face` |

`ycb_block_upright` is named for a posture but rests on the genuinely
**smallest** face — the prim names predate the geometric vocabulary and are
kept because they are written into the captures on disk. This is the one
pairing in EX2 that is easy to get backwards, so `h_ex2_labels.py` and
`h_ex2_prompts.py` both pin it explicitly.

Only `large_face` crosses the 0.080 Franka aperture, so the face determines
the arm and the contrast is the whole design. The conflict map is a strict
involution: each face declares the other, and every conflict is therefore a
capability flip.

### Two faces, not three

A third prim, `ycb_block_small`, rested on the middle face (0.130 x 0.050,
vertical 0.100, opening 0.050) and was named `edge`. It carried the *sharp*
contrast: `edge` and `large_face` are both flat and differ only in geometry,
so a difference between them could only come from reading the scene, not from
mapping a posture word to an opening.

It was withdrawn on **2026-08-27** because no model read it. Over 81 answered
trials GPT separated `edge` from `large_face` on 58% of them, Fisher
p = 0.76 — chance — while answering a plain standing-or-flat question about the
same pictures 18 times out of 18. Gemini managed 80% on the pair but only 60%
on `edge` overall, against 100% on both extremes. The evidence is retained in
`runs/ex2_q1_cue_*.jsonl`.

The two faces that remain were then checked directly, as a two-way forced
choice over 60 trials per model (`runs/ex2_q1_2way_*.jsonl`): Gemini 58/60 =
97%, GPT 45/60 = 75%, both far above the 50% floor. So the reduction is not a
retreat to a question nothing can answer — it is a retreat to the one both
models demonstrably read.

**What it costs, and where that is recorded.** `small_face` stands and
`large_face` lies, so a model can score the whole design on posture alone. The
reading "obtains the opening from the geometry" is therefore no longer
separable from "reads posture and applies a rule". Cell 10 prints this under
every verdict, `nb_cells_b`'s disclosure block lists it as design fact 6, and
it belongs in Limitations.

**Why the prompt says nothing about it.** The block can still physically settle
on the middle face, so the convention "an object resting flat lies on its
largest face" would make the design sound. It is deliberately *not* in the
prompt: with two faces that sentence reduces the `dims` derivation to
*see flat → apply the rule → 0.100*, which is the posture judgement models
already perform perfectly, and `prompts.py` reserves the face-to-geometry
mapping for factor C. The guarantee is enforced in **capture** instead —
`capture_ex2_scene.py` fails any scene that settles outside 0.005 m of an
authored rest height, rather than relabelling it. No capture shows the
orientation, so the model never needs to be told about it.

`prompts.validate_face` is a guard rather than a translation. It raises on a
pose that is not one of the two, which is what stops a mustard capture being
rendered through the block design: a bottle has no faces, and `upright` and
`lying` are words the schema does not list.

The capture trail's `ex2.resting_face` field still records `upright` /
`small_face` / `large_face` and has the same crossing problem. Nothing in the
pipeline reads it — `load_scenes` takes only `ex2.kind` and `ex2.images` — so
it is left as provenance. Do not use it to derive a face.

### Reading run files written before 2026-08-27

`labels.modernise_poses(rows)` translates a block file's old pose words and
returns how many rows it changed. It is wired into `rescore.py`,
`analyse_conflict.py` and `ex2_analyse_dims.py`, all of which print the count
rather than translating silently.

The translation is **conditional**, because `upright` is ambiguous:

- `lying_large_face` and `lying_small_face` only ever named the block, so they
  translate unconditionally to `large_face` and `edge`. `edge` is no longer a
  face of the design, and that is deliberate: the shim must still *read* the
  retained three-way runs, and a row translating to `edge` then fails loudly at
  `require_face` rather than being scored against a two-face design.
- `upright` is translated to `small_face` **only** in a file that also carries
  one of those two words, which makes it a block file.

Every EX2 results file in `runs/` is a mustard run whose `upright` means the
bottle standing. A blanket rule would have rewritten all of them. Verified:
`analyse_conflict.py runs/All_conflict.jsonl` reproduces 2,827 rows read /
2,772 analysed with poses untouched and no translation line.

### The answer schema

Typed fields, not a prose `why` block:

```json
{"task_id": 0, "resting_face": "small_face", "opening_needed_m": 0.050,
 "arm": "franka_n", "basket": "box_1"}
```

`opening_needed_m` is required at every rung. `resting_face` is asked for only
at `N-D` and `N-CD`: naming the face as something to report would otherwise
tell the model that the face matters. A wait may carry a null opening, which
reads as "I cannot tell" rather than as a missing answer.

No extractor now stands between the reply and the measurement. The
`classify_reasoning` column returns `none` for every current row because there
is no prose to keyword-match. **That is not a zero result.**

`grade.believed_width` reads the typed field first and falls back to mining
`why.grasp` only when there is none, so `rescore.py` and `analyse.py` still
work on the pre-2026-08-26 files.

### dims

`dims` now withholds `resting_face` as well as `opening_needed_m`. Stating the
face would let the opening be derived from `size_upright_m` by text alone and
the image would no longer be needed. `transforms.transform` already dropped
both at the state level; the render-time withholding is a second guard.

### One task, one arm

`solo` is the only mode. `build_ex2_prompt` no longer takes `solo`, `trim`,
`view` or `describe_scene`. Consequences:

- `run.py` and `cue.py` queue the flip task alone and grade with `grade.grade`.
  Grading them as rounds would have filed every trial as an incomplete round.
- `queue_flip_only` and `neutralise_baskets` moved from `solo.py` to `run.py`
  and are re-exported, so there is one copy.
- `grade.grade_round` and the batch outcomes are LEGACY. No driver calls them.
  They are kept, and kept harnessed, so the batch results files can still be
  rescored.
- The arm preference is `G1`, not `G6`: the four guidance lines it used to
  follow described a round that no longer exists.
- `run.py`'s trial id now carries the preference. It renders into `G1` on every
  prompt, so without it a UR run would resume onto a Franka file.

### The manipulation check

Two-way since 2026-08-27: `large_face` or `small_face`. Chance is one in two,
and `mancheck.CHANCE` is derived from the answer vocabulary rather than typed,
so it cannot be left behind if the vocabulary changes again. The withdrawn
middle face is **not named in the probe, not even to exclude it** — mentioning
it would make this a three-way question with one option discouraged, which is a
different measurement. `seecheck.py` follows, and its reply format's second
line is now `FACE:`, not `POSE:`.

`twoway.py` asks the same two orientations in plain words — "standing up on
end, or lying flat" — with no face vocabulary and no dimensions. That is the
probe that separated perception from naming and produced the 18/18 above.

### Removed from the harness

`h_ex2_run.py` section 3c checked a task-presentation-order factor
(`R.reorder_tasks`, a `task_order` key in meta, a fifth argument to
`R.render`). None of that exists in `run.py` and none of it ever did, so the
section raised `TypeError` and the whole file reported nothing — before the
prompt module was replaced. It is deleted rather than skipped. A trial now
queues one task, so an order over two tasks no longer describes anything the
model sees.
