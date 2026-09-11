# Instrument validation: source pack

Everything needed to write the two subsections **Cue validation** (what the
models can and cannot see) and **Ground truth and stability** (bounding-box
check, resting stability). Every number below was recomputed from the run
files and captures on disk on 2026-08-29, not copied from an earlier
document. Where a number here disagrees with `EX2_FINAL_RESULTS.md` or
`EX2_Q1_STATUS.md`, section 6 says so.

---

## 0. What the two subsections are claiming

The chapter's Q1/Q2/Q3 numbers are all claims about **which source a model
believed**, the picture or the text. That claim is empty in two distinct
ways, and each subsection closes one of them:

| Subsection | The failure it rules out | The evidence |
|---|---|---|
| Cue validation | The image does not carry the cue at all, so a low image-following rate measures the render rather than the model | A forced-choice perception probe, run before any paid cell, on the same frames the experiment uses |
| Ground truth and stability | The label attached to a frame is not what the frame shows, so the "truth" the model is scored against is wrong | An authored-geometry check plus a physics settle check, both enforced at capture and re-asserted where the data is read |

Both are **preconditions, not results**. The design point worth stating in
prose: the cue probe is a gate that licenses the spend, and it was run and
read before cells 6 and 7 were paid for.

---

## 1. Cue validation: the probe

**Module.** `fourarm/experiments/ex2/mancheck.py`, question built by
`prompts.manipulation_check()`.

**Exact question put to the model** (`prompts.py:751-775`), one image
attached, system message `"Answer with one word and nothing else."`:

> The block on the table is resting on one of two faces. They measure
> 0.130 x 0.100 m (the larger) and 0.100 x 0.050 m (the smaller). Which one
> is it resting on? Answer `large_face` or `small_face`.

**Design choices worth reporting, each with its reason:**

| Choice | Reason |
|---|---|
| Two-way forced choice, chance 50% | The third face was withdrawn on 2026-08-27; see §3.1. `CHANCE` is derived from `len(RESTING_FACES)`, never typed, so a vocabulary change cannot leave a stale chance level behind |
| No state, no rules, no allocation | The probe asks only whether the cue is legible. Anything else would confound perception with the reasoning under test |
| One word, matched whole and case-folded | A reply that buries the word in a sentence is recorded as **unparseable**, not wrong. Counting a hedge as a perception success would let a chatty model look more grounded than a terse one |
| No retry on a wrong-but-legible answer | Re-asking until the model agrees is how a control stops being one. Transport errors are retried (2 attempts, 2 s apart); a legible wrong answer is kept |
| Null scenes not excluded | Dropping them would bias the sample toward whichever face is easier to see |
| The third face is not named, not even to exclude it | Mentioning it would make this a three-way question with one option discouraged, which is a different measurement |
| Filenames name the vocabulary (`cue2way_`) | `check_id` is `seq|view|model` with no vocabulary field, so a two-way run resuming into a three-way file would find every id present, make no calls, and report the old answers as new. `assert_same_probe` also refuses it |

**Sample.** 20 positions (the first ten usable in each bank, east and west)
x 2 faces x 3 repeats x 3 models = **360 calls, all answered, zero
unparseable, zero errors**. Both banks are covered deliberately: the banks
differ in which UR is idle and in how the block sits relative to the camera,
and this probe licenses every paid cell below it, so it should not rest on
half the workspace.

Positions used: `e00, e01, e03, e04, e05, e06, e07, e08, e09, e11` and
`w00`-`w09`. Repeats go to separate files because `check_id` has no repeat
field.

---

## 2. Cue validation: results

### Table IV.1 — Two-way face discrimination, Wilson 95%

Source: `fourarm/tables/ex2_q1/tab_ex2_q1_cue.csv`. n = 60 trials per cell
(20 images x 3 repeats). Chance 50%.

| Model | `small_face` | `large_face` | Overall |
|---|---|---|---|
| `gpt_hi` | 95.0 [86.3, 98.3] | 83.3 [72.0, 90.7] | 107/120 = 89.2% |
| `gemini` | 100.0 [94.0, 100.0] | 100.0 [94.0, 100.0] | 120/120 = 100.0% |
| `claude_md` | 63.3 [50.7, 74.4] | 95.0 [86.3, 98.3] | 95/120 = 79.2% |

**Verdict.** The Wilson **lower** bound is above 50% in every cell, so all
three models separate the two faces above chance. Q1's contrast is
measurable and the paid cells were justified. This is the sentence the gate
exists to produce.

### Table IV.2 — Confusion, true face against named face

Source: `tab_ex2_q1_cue_confusion.csv`.

| Model | true `small_face` -> `small_face` | -> `large_face` | true `large_face` -> `small_face` | -> `large_face` |
|---|---|---|---|---|
| `gpt_hi` | 57 | 3 | 10 | 50 |
| `gemini` | 60 | 0 | 0 | 60 |
| `claude_md` | 38 | **22** | 3 | 57 |

**The shape of Claude's error matters more than its accuracy.** It is a
bias, not blindness: 22 of 60 `small_face` trials named `large_face`,
against 3 of 60 in the other direction. A prior of the form *blocks lie
flat* is the natural reading. The `claude_md` alias exists because that
hypothesis predicted lowering the effort would help; it moved the score and
**did not change the shape of the error**, which is evidence against the
hypothesis that motivated the alias rather than for it. Report it that way.

### Effort is not the explanation

| Comparison | Result |
|---|---|
| `gpt` (low effort) vs `gpt_hi` (high), east bank only, 60 trials each | 56/60 = 93.3% vs 57/60 = 95.0% |
| `claude` (default effort) vs `claude_md` (medium), east bank | 65% -> 75% |

Raising GPT's effort bought essentially nothing on this probe. This
supports the Limitations point that effort is not matched across providers
and cannot be.

### A caveat that belongs beside the verdict

The probe **cannot** distinguish a model that derives the opening from
geometry from one that reads posture and applies a rule: `small_face` stands
and `large_face` lies, so posture alone scores here. The face that separated
those two readings was withdrawn (§3.1). This is Limitation 1 in
`EX2_FINAL_RESULTS.md` and the cue cell prints it in those words.

---

## 3. What the models cannot see

Four documented perception limits. Together they are the honest half of the
subsection: the gate passed, but only after the design had been cut back to
the question the models demonstrably read.

### 3.1 The third resting face

The design carried a third face, `edge` (0.130 x 0.050 down, 0.100 m
vertical). It was the **only** contrast that separated deriving-from-
geometry from reading-posture, because `edge` and `large_face` are both flat
and differ only in geometry. It was withdrawn on 2026-08-27 because no model
read it.

Recomputed from `runs/_archive/20260827_cue_prerender/` (the three-way
probe, 90 GPT rows over 3 repeats, 83 answered):

| Cell | GPT, three-way |
|---|---|
| `edge` | 8/28 = 28.6% [15.3, 47.1] |
| `large_face` | 22/28 = 78.6% [60.5, 89.8] |
| `small_face` | 7/27 = 25.9% [13.2, 44.7] |
| Overall | 37/83 = 44.6% (chance 33.3%) |
| `edge` against `large_face`, restricted 2x2 | 30/55 = **54.5%**, Fisher exact two-sided **p = 0.53** |

The dominant error is directional: 20 of 28 `edge` trials were named
`large_face`, and 15 of 27 `small_face` trials were named `edge`.

Against that, the same model answered a **plain standing-or-flat** question
about the same pictures correctly on **18 of 20 trials**
(`runs/ex2_q1_2way_posture_gpt_r1.jsonl`): posture is legible, the
face-level geometry is not.

The two faces that remain were then checked directly as a two-way choice
before the design was committed (`runs/ex2_q1_2way_*`, low-effort aliases,
60 trials per model): Gemini 58/60 = 96.7% [88.6, 99.1], GPT 45/60 = 75.0%
[62.8, 84.2]. **So the reduction is a retreat to a question both models
demonstrably read, not to one nothing can answer** — that is the sentence
to use, and it is what makes the withdrawal defensible rather than a
convenience.

The captures of the retired face stay on disk (34 of them) as the evidence.
`run.load_scenes` drops them by prim, **prints the count**, and refuses to
proceed if a directory contains nothing else.

### 3.2 The overhead viewpoint inverts the cue

The final capture set uses one camera, `ex2_cam`, an oblique view from the
south of the table. That was a decision, and the evidence is a pilot on the
earlier mustard-bottle capture set (`out/ex2_capture`, both cameras
rendered, Qwen, prompt version `2026-08-07e`):

| View | `upright` | `lying` | Overall |
|---|---|---|---|
| `ex2_cam` (oblique) | 10/11 = 90.9% | 27/33 = 81.8% | 37/44 = 84.1% |
| `table_cam` (overhead) | **0/11 = 0.0%** [0.0, 25.9] | 23/33 = 69.7% | 23/44 = 52.3% |

Overhead, the model got **every** upright trial wrong: a top-down
projection discards the vertical extent that distinguishes the poses, so the
view does not merely fail to carry the cue, it **inverts** it. GPT on the
same oblique frames scored 41/44 = 93.2%.

Two caveats to state plainly:

1. This is **pilot evidence** — a different object (mustard bottle), a
   different model (Qwen), and a superseded prompt version. It justified
   the capture decision; it is not a result about the three reported models.
2. Because only `ex2_cam` was captured for the block set, **there is no
   viewpoint control in the reported experiment**. That is Limitation 6.

### 3.3 Occlusion: a picture that does not show the object

Legality and visibility are independent preconditions, and until 2026-08-27
only the first was checked. Position `e10` carries the full aperture
contrast and has the block hidden behind the Franka; GPT inverted both of
its posture trials, the only two it got wrong out of twenty.

`experiments/ex2/visibility.py` measures, from **pixels alone and never a
model reply**, the largest connected region of block colour in each frame,
scored against the median for its own pose and its own bank. Excluding a
position because it scored badly would be choosing the sample from the
answers; running this before the calls is what makes the exclusion a
precondition. Full per-position numbers are in §5.3.

### 3.4 Describing the object correctly and still misreading it

`seecheck.py` asks the model to describe the object first and then name the
pose, which separates *not looking* from *looking and misjudging*. On the
mustard pilot (44 trials, oblique view):

| Model | `upright` | `lying` |
|---|---|---|
| `gpt` | 11/11 | 10/11 |
| `qwen` | 11/11 | **2/11** |

Qwen's failures are not occlusion: it describes the fallen bottle in
confident detail as standing ("*yellow and upright, with its cap at the top
and body vertical*"). That is a perception limit, not a compliance or
framing failure — which is exactly the distinction the probe was built to
draw, and it is the reason a description-first accuracy is never pooled
with the terse one.

---

## 4. Ground truth: the bounding-box check

**Where it runs.** Cell 2 of `ex2_q1_derivation.ipynb` (source:
`notebooks/nb_cells_a.py`). No model calls. It fails the notebook rather
than reporting a problem.

**What the cell is standing between.** The prompt states the apparatus
convention — *"The cell judges an object by the box that encloses it, so a
shape that tapers or curves counts as its full extent"* — and every arm
states only `opening_max_m`. If the authored geometry and the declared
opening ever disagreed, the prompt would be **wrong** rather than merely
silent, and nothing downstream would notice.

**The three assertions, and the failure each one guards:**

1. **The declared opening is the smaller horizontal extent.** For each face,
   the block prim's authored `size` is `(x, y, z)` pre-oriented to that
   pose, so the opening is `min(size[0], size[1])`. It is compared against
   what `transforms.POSE_FACTS_BY_LABEL` declares, to 1e-9.
2. **All three extents are a permutation of the block's dimensions.** This
   compared only the smallest extent until 2026-08-27, so a prim sized
   0.200 x 0.200 x 0.050 — not the block at all — would have passed a check
   whose message said it was verifying a permutation. Worth one sentence:
   with the design down to two faces there are fewer cross-checks left, and
   this cell is what stands between a mis-authored prim and the whole
   experiment.
3. **The contrast exists.** The Franka must be feasible on `small_face` and
   **only** on `small_face`, and a UR must be legal everywhere. Anything
   else and Q1 has no contrast to measure.

### Table IV.3 — Derived geometry and the capability flip

Source: `tab_ex2_q1_design.csv` (identical in
`tab_ex2_q2_geometry.csv` and `tab_ex2_q3_geometry.csv`). All metres.

| Resting face | Vertical | Horiz. a | Horiz. b | Opening needed | Franka max | UR max | Franka | UR | A deriving model picks |
|---|---|---|---|---|---|---|---|---|---|
| `small_face` | 0.130 | 0.100 | 0.050 | **0.050** | 0.080 | 0.140 | yes | yes | Franka, preference satisfied |
| `large_face` | 0.050 | 0.130 | 0.100 | **0.100** | 0.080 | 0.140 | **no** | yes | UR, preference overridden |

The flip is real and it crosses the Franka aperture in the middle: 0.050
against 0.100, either side of 0.080. The object is a **procedural cuboid**,
not a YCB asset, so it carries no branding and no recognisable identity a
model could lean on instead of looking; base dimensions upright are
0.130 (H) x 0.100 (W) x 0.050 (D), mass 0.500 kg, colour dark walnut
(0.40, 0.26, 0.14) against a medium-brown table (0.62, 0.46, 0.30).

**Anti-drift measures worth a sentence.** The cell reads the authored
dictionary (`ycb_objects.YCB`) rather than restating dimensions, and it
regex-checks `EX2_PROMPT_VERSION` against the source on disk before
asserting anything, so a stale kernel or a stale browser copy of the
notebook reports itself as staleness rather than as a design failure.

---

## 5. Stability: the resting-face guarantee

### 5.1 Why it carries weight

The prompt deliberately **does not** say which flat orientation to expect.
The convention sentence — *an object resting flat lies on its largest face*
— was left out, because with two faces it would reduce the derivation to
*see flat, apply the rule, 0.100*, a posture judgement models already
perform perfectly; the face-to-geometry mapping is reserved for factor C.
The guarantee is enforced **at capture** instead. So the settle check is not
housekeeping: it is the single thing standing behind the prompt's silence.

### 5.2 The check, and the two places it runs

**At capture** (`ycb/capture_ex2_scene.py`). A cuboid spawns already resting
on a named face with identity rotation, so it is stable by construction and
cannot settle into a fourth orientation the way a rounded YCB asset can.
After settling, the object's centre height above the table is compared with
the authored `rest_z` (half the vertical size). Outside `SETTLE_TOL_M`, the
capture **raises** — it does not relabel.

That distinction is the point to make in prose. Until 2026-08-27 this was a
printed warning nothing downstream read, which meant a block that toppled
onto a different face was written to disk **labelled with the face it was
asked for**. With two faces in the design and a third the block can
physically reach, that is the difference between a picture of the
experiment and a picture of something else.

**The tolerance is measured, not guessed.** Across the 102 captures then on
disk the block's centre height had **zero spread**: exactly 0.0650, 0.0500
and 0.0250, 34 of each. The tolerance was tightened from 0.010 to 0.005 on
that basis; it fails nothing that passed under 0.010 and still leaves the
retired face's 0.0500 a clear 0.010 outside the band around either kept
value. It guards a future change in spawn behaviour, not present noise.

**At analysis** (Cell 3 of the Q1 notebook). The capture-time assertion
post-dates most of the captures on disk, and the trail check beside it
compares only the recorded face **word** against the prim, never the height
that word describes. So the guarantee was being taken on trust at the point
where the data is actually read. Cell 3 re-asserts every recorded settle
height, and **reads `SETTLE_TOL_M` out of the capture script's source by
regex** rather than typing it, so the notebook cannot drift from the value
the captures were accepted under.

### Table IV.4 — Recorded settle heights, all 102 captures

Recomputed from `out/ex2_capture_block/consults.jsonl`. Metres above the
table surface. "Face (reported)" is the chapter's vocabulary; the trail
records a superseded word for two of them, and the notebook maps it — the
face is always derived from the **prim**, never from the word.

| Face (reported) | Prim | Trail word | n | Authored `rest_z` | Observed min | Observed max | Spread | Within 0.005 |
|---|---|---|---|---|---|---|---|---|
| `small_face` | `block_upright` | `upright` | 34 | 0.0650 | 0.0650 | 0.0650 | **0.0000** | 34/34 |
| `large_face` | `block_large` | `large_face` | 34 | 0.0250 | 0.0250 | 0.0250 | **0.0000** | 34/34 |
| `edge` (retired) | `block_small` | `small_face` | 34 | 0.0500 | 0.0500 | 0.0500 | **0.0000** | 34/34 |
| partner, `large_clamp` | — | — | 102 | 0.0180 | 0.0182 | 0.0182 | 0.0000 | 102/102 |

Every capture is on the face it claims. The block's spread is exactly zero
because it is teleported to rest height with zero velocity and is a stable
cuboid; the clamp, a real YCB mesh, settles 0.2 mm above its authored
height and is well inside tolerance. **No capture in the reported set was
ever relabelled, and none was rejected for settling wrong.**

### 5.3 The other capture-time guards

Report these as a group; each exists because something went wrong once.

| Guard | What it prevents | Observed |
|---|---|---|
| `park_everything` writes, steps, and **reads back** every pool prim's height, raising after 5 failed attempts | A prim never activated stays where the scene config first placed it, leaving a second, pale but plainly visible object in frame — a second thing the model can read | No capture failed it |
| `settle_until_still`: hold until two successive frames differ by fewer than 200 changed pixels | A fixed hold was not evidence the cell had stopped; arms micro-moving after `settle()` differed by ~15,500 px between frames whatever the object, which made every visibility fraction meaningless | Residual across 102 captures: median **0**, mean 3.4, max 135 px — all under the 200 px threshold |
| Post-capture table census: the table must hold exactly the two intended prims | An extra object makes the pair non-minimal | No capture failed it |
| Render warm-up of 180 rendered ticks before the frame is grabbed | The overhead camera only refreshes on a **rendered** step; stepping with `render=False` once produced an entire episode of identical frames | — |
| Per-capture scale record | Lets a pixel measurement be converted to metres | `px_per_m` = 710.79, constant across all 102 |

### Table IV.5 — Visibility, both banks

Largest connected region of block colour, in pixels, per pose; "worst" is
the smallest ratio to that pose's own bank median. Cut at 0.50.

| Bank | Positions | Worst ratio retained | Excluded | Excluded ratio |
|---|---|---|---|---|
| east | 17 | 0.60 (`e05`) | `e10` | **0.03** |
| west | 17 | 0.84 (`w01`) | none | — |

`e10` presents 45 visible pixels standing and 224 lying, against pose
medians of about 1518 and 720. **The threshold is a cliff, not a tuning:**
every retained position runs 0.60 to 1.14 of its pose median and the
excluded one sits at 0.03, so any cut between 0.05 and 0.55 excludes the
same single position. The default sits in the middle of that gap and the
report prints both margins, so a reader can see the cut did not decide a
close call.

Two further design points: the check is run **per bank**, because a west
block renders about 10% larger than an east block in the same pose and one
pooled median would compare banks rather than test occlusion; and the block
colour is a **stated constant validated before use** (sampled once from
`e08_U.png`), because two auto-detectors were tried and both silently
returned the table, at which point every position measures as fully visible
and the check passes while testing nothing.

### Table IV.6 — Capture inventory and exclusions

Source: `tab_ex2_q1_inventory.csv`.

| Quantity | Value |
|---|---|
| Positions captured | 34 (17 east, 17 west) |
| Captures on disk | 102 (34 positions x 3 poses) |
| Captures the current design uses | 68 (2 faces); the 34 retired-face captures are skipped by prim and the count is printed |
| Positions carrying the aperture contrast | 33 of 34 — `e02` excluded, the Franka is never legal there, so there is no arm choice to make |
| Positions also showing the block | 32 of 34 — `e10` further excluded as occluded |
| **Usable positions** | **32** |
| Legality pattern, every usable position | `small_face`: `franka_n` + the bank's UR; `large_face`: the bank's UR alone |

Both exclusions are **with cause and computed before any model call**:
legality from the real validator over the frozen state, occlusion from
pixels. Neither was chosen from the answers. The exclusions also predate
the analysis in the data itself: by default the paid cells ask about *every*
captured position and the excluded ones are dropped at analysis time, which
keeps the exclusion visible rather than implicit.

### 5.4 Provenance

The captures are frozen and hashed. There are **no RNG seeds anywhere in
the pipeline**; reproducibility rests on the frozen captures and their
content hash.

| Role | Path | Rows | sha256 (first 16) |
|---|---|---|---|
| captures | `out/ex2_capture_block/consults.jsonl` | 102 | `b1579d5d8d1fcb53` |
| `cue_gpt_hi_r1/r2/r3` | `runs/ex2_q1_cue2way_gpt_hi_r{1,2,3}.jsonl` | 40 each | `d50e8e30ba110783`, `d4043653bd8d4f99`, `84e8cc4365b8315c` |
| `cue_gemini_r1/r2/r3` | `runs/ex2_q1_cue2way_gemini_r{1,2,3}.jsonl` | 40 each | `0a15f4530c83ba79` (all three) |
| `cue_claude_md_r1/r2/r3` | `runs/ex2_q1_cue2way_claude_md_r{1,2,3}.jsonl` | 40 each | `d8fa86b049f1d710`, `5c680bf3a2fcdaaa`, `356beaa72edc110f` |

Full hashes in `tables/ex2_q1/tab_ex2_q1_provenance.csv`. Note the three
Gemini repeat files are **byte-identical**: Gemini returned the same reply
for all 40 items on all three repeats. That is consistent with its 120/120
score and with the provider exposing no temperature control, and it is
worth one sentence rather than being left for a reader to notice.

### 5.5 The harness

Both checks are pinned by unit tests that drive the **real** modules with
synthetic inputs, so the pins do not depend on a capture directory that may
be re-rendered: `harness/h_ex2_visibility.py` (8 pins, including that the
module never opens a run file, and that the colour constant is validated
before anything is measured), plus `h_ex2_mancheck.py`, `h_ex2_seecheck.py`,
`h_ex2_transforms.py`, `h_ex2_labels.py`.

---

## 6. Numbers to check before they reach the chapter

Three claims in the existing documents did **not** reproduce from the files
on disk. Resolve each before writing.

| Where | Document says | Recomputed from the files | Note |
|---|---|---|---|
| `EX2_FINAL_RESULTS.md` Limitation 3, `mancheck.py` and `prompts.py` docstrings, `nb_cells_a.py` Cell 5 markdown | GPT separated `edge` from `large_face` on **58%** of **81** answered trials, Fisher **p = 0.76** | **54.5%** of **55** answered `edge`/`large_face` trials; Fisher two-sided **p = 0.53**. GPT answered 83 of 90 trials in the probe overall, scoring 44.6% three-way | The conclusion is unchanged and if anything stronger — it is still indistinguishable from chance — but the figures should be recomputed rather than carried forward. The 81 may be an earlier file state |
| Same passages | "answered a plain standing-or-flat question **18 times out of 18**" | **18 of 20** (`ex2_q1_2way_posture_gpt_r1.jsonl`, 20 trials: 9/10 standing, 9/10 flat) | Still a decisive contrast against 54.5%, but it is 90%, not 100% |
| `EX2_FINAL_RESULTS.md` Limitation 3 | Two-way check "Gemini 97% and GPT 75%" | Confirmed: 58/60 = 96.7% and 45/60 = 75.0%, from the **low-effort pilot** files | Make clear in prose that these are the 2026-08-27 pilot aliases, not the reported `gemini` / `gpt_hi` numbers in Table IV.1 |

Also note, since two documents disagree and the chapter must pick one:
`EX2_Q1_STATUS.md` §5.1 reports the cue gate on the **east bank only**
(GPT 95.0, Gemini 100.0, Claude 75.0). Table IV.1 above is **both banks**
and supersedes it. The west bank was collected afterwards precisely to
remove a sampling objection to the gate.

---

## 7. File index

| Purpose | Path |
|---|---|
| Cue probe | `fourarm/experiments/ex2/mancheck.py`; question at `prompts.py:751` |
| Cue results cell | `notebooks/nb_cells_a.py` (Cell 5), `nb_cells_b.py` (Cell 5b) |
| Cue run files | `fourarm/runs/ex2_q1_cue2way_{gpt_hi,gemini,claude_md}_r{1,2,3}.jsonl` |
| Retired three-way probe | `fourarm/runs/_archive/20260827_cue_prerender/*.jsonl` |
| Two-way pilot + posture probe | `fourarm/runs/ex2_q1_2way_*.jsonl` |
| Viewpoint / description pilots | `fourarm/runs/ex2_mancheck.jsonl`, `ex2_mancheck_gpt.jsonl`, `ex2_seecheck.jsonl` |
| Perception floor probe | `fourarm/analysis/ex2/ex2_perception_floor.py`, `runs/ex2_floor*.jsonl` |
| Capture script and settle guard | `fourarm/ycb/capture_ex2_scene.py` (`SETTLE_TOL_M`, `settle_until_still`, `park_everything`) |
| Object registry | `fourarm/ycb/ycb_objects.py` (`block_upright`, `block_large`, `block_small`) |
| Declared pose facts | `fourarm/experiments/ex2/transforms.py` (`POSE_FACTS_BY_LABEL`) |
| Bounding-box + inventory cells | `notebooks/nb_cells_a.py` (Cells 2 and 3) |
| Occlusion check | `fourarm/experiments/ex2/visibility.py` |
| Tables | `fourarm/tables/ex2_q1/tab_ex2_q1_{cue,cue_confusion,design,inventory,provenance}.csv` |
| Harness pins | `harness/h_ex2_{visibility,mancheck,seecheck,transforms,labels}.py` |
