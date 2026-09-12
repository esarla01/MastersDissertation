# Experiment 2: table and figure provenance

Where every number in Chapter 5 comes from, and how to check it.

```bash
make verify-ex2
```

Each notebook ends in an audit section that does two things. It rebuilds its
tables and asserts every cell against the number the chapter prints — **216
checks across Tables 5.6 to 5.14**, Q1 90, Q2 60, Q3 66. Then it checks those
transcribed constants against the **thesis LaTeX itself**, in the order the
thesis prints them, pinning **229 of 341** thesis cells.

The second half matters because the constants are typed from the chapter: on
their own a mis-transcription would pass and an edit to the thesis would go
unnoticed. Coverage is reported per table rather than implied, since the
constants do not account for every cell — the shortfalls are Wilson bounds the
notebooks do not transcribe, and Gemini's rows in 5.12, which come from the
ladder rather than the repair run.

Tolerance is 0.06 throughout. Every published value is printed to one decimal,
so that is rounding, not slack on the result.

---

## Which notebook owns which table

| Table | Reports | Notebook | Emits |
|---|---|---|---|
| 5.1 | Decision logic for the target block | — | prose |
| 5.2 | The block's three resting faces | `notebooks/appendix/appendix_tables.ipynb` §12 | `tables/appendix/ex2_object.tex` |
| 5.3–5.5 | The condition and treatment definitions | — | **untraced**, `experiments/ex2/prompts.py` |
| 5.6 | Cue validation | `notebooks/ex2/ex2_q1_derivation.ipynb` | `tab_ex2_q1_cue.csv`, `..._cue_confusion.csv` |
| 5.7 | Franka share by face, paired contrast, complete flips | `notebooks/ex2/ex2_q1_derivation.ipynb` | `tab_ex2_q1_share.csv`, `..._contrasts.csv` |
| 5.8 | Accuracy of the reported opening | `notebooks/ex2/ex2_q1_derivation.ipynb` | `tab_ex2_q1_opening.csv` |
| 5.9 | The no-image floor | `notebooks/ex2/ex2_q1_derivation.ipynb` | `..._noimage_share.csv`, `..._noimage_contrast.csv` |
| 5.10 | The two conflict conditions | `notebooks/ex2/ex2_q2_precedence.ipynb` | `tab_ex2_q2_conflict_share.csv` |
| 5.11 | Where the reported opening came from | `notebooks/ex2/ex2_q2_precedence.ipynb` | `tab_ex2_q2_conflict_source.csv` |
| 5.12 | The two controls | `notebooks/ex2/ex2_q3_repair.ipynb` | `tab_ex2_q3_repair_cells.csv` |
| 5.13 | Step 2, mapping a face to an opening | `notebooks/ex2/ex2_q3_repair.ipynb` | the same CSV |
| 5.14 | Step 1, reading the face | **two notebooks** | see below |

All under `fourarm/notebooks/` and `fourarm/tables/`.

---

## Four things that are easy to get wrong

Each of these cost time to establish. They are recorded so the next reader does
not re-derive them.

### `direction` is the opposite of what Table 5.11's rows say

Rows carry a `direction` field valued `permissive` or `restrictive`. Table
5.11's rows are labelled "text permits Franka" and "text forbids Franka". They
look like the same distinction and are **exact opposites**: `direction` names
what the **scene** permits, so every `permissive` row declares 0.100 — which
forbids a Franka — on a capture of the small face, which allows one.

Keying an analysis on `direction` transposes the table, and because both halves
hold percentages in the same range the transposed version looks entirely
plausible. Split on the declared width against the 0.080 aperture instead.

### `N-CD` wears two labels

It is "+ derivation" in Table 5.13 and the **baseline** in Table 5.14 — the
same rows read for two different questions. Correct, and easy to misread as a
duplicate row.

### Table 5.14 is assembled from two notebooks

| Row | Rung | Source |
|---|---|---|
| baseline | `N-CD` | `tab_ex2_q3_repair_cells.csv`, from `ex2_q3_repair` |
| + description | `N-BCD` | the same CSV |
| + attention | `N-ACD` | `tab_ex2_q3_ceiling.csv` (face accuracy) and `tab_ex2_q3_ceiling_contrast.csv` (contrast), from `ex2_q3_remediation` |

`N-ACD`'s two Franka shares are tabled nowhere; the audit checks them against
their own difference, which is the contrast.

`notebooks/publish/ex2_q3_ceiling_contrast.py` writes that contrast CSV. It has
no caller — `ex2_q3_remediation` prints the figure but does not save it — so it
looks like dead code and is a live table generator.

### The conflict_face half had no generator until 2026-09-11

Tables 5.10 and 5.11 each have a `conflict` half and a `conflict_face` half.
Only `conflict` was emitted; every `conflict_face` row in the chapter was
transcribed by hand.

That is the half that carries the result. Under `conflict` the opening is
supplied and R3 tells the model to use it, so following the text shows
compliance with a stated value and settles nothing about precedence. Under
`conflict_face` nothing supplies it and the model must derive it from a face,
the text's or the image's — the direct test of which source governs, and what
Chapter 6 builds on.

---

## Populations and conventions

**The unit of analysis is the position.** Each of the 32 provides a matched
pair, its `small_face` and `large_face` captures, and the contrast is the
within-position difference. Proportions carry Wilson 95% intervals; the paired
contrast carries a **paired-t** interval, not the Newcombe intervals
Experiment 1 uses, because the two shares come from the same position.

The contrast CSVs carry both `newcombe_*` and `paired_*` columns. **The chapter
prints the paired pair.**

**34 positions, 32 usable.** `e02` is excluded because the Franka is never
legal there, so no arm choice arises; `e10` because the block is hidden behind
an arm. `ycb/screen_ex2_block.py` derives `e10` independently from the
reachability rasters, and the harness requires that it be the only position
failing the screen.

**Franka share excludes waits.** It is the proportion of *proposals*, not of
trials, that name a Franka. Ideal is 100% on `small_face` and 0% on
`large_face`, so a perfect allocator scores ∆ = 100 points.

**The reported opening is scored at 6 mm.** The scene-implied and text-implied
openings differ by 50 mm, so no reply can match both.

**Models are not matched.** Gemini Flash has no reasoning-effort control,
Claude was run at medium, GPT at its default. Results are reported per model
and no ranking is drawn.

---

## Figures

Chapter 5 prints one figure, **5.1**, the three resting faces. It is a
simulator capture from
`ycb/capture_ex2_scene.py --spec ycb/ex2_block.txt`, writing to
`out/ex2_capture_block/`.

`figures/ex2_q1/fig_ex2_q1_share.tex` and its Q2 counterpart were generated
and **cut before submission**. They plot verified numbers but appear nowhere in
the thesis.

---

## Data that is not a result

`runs/All_conflict.jsonl` and the `piece_dims_P2*` files are the earlier
**P-rung** design: 7 rungs (`P0`–`P4`), 22 scenes, qwen rather than claude, and
a mustard bottle rather than the block. They back no reported number and are
listed in `run_files.EXCLUDED` so the manifest audit will not let them be read
as one. `fourarm/runs/README.md` tables the two designs side by side.

Read 22 there as "the earlier design's scene count", never as the reported
one, which is 32 positions × 2 faces = 64.
