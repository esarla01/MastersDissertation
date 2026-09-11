# Errata: where the code is right and the thesis is not

Small errors found while making every table regenerable. **The thesis is not
being changed.** The code carries the correct figure, and each is recorded here
so the difference is a documented decision rather than a discrepancy someone
finds later and has to re-derive.

None of these changes a reported result. Every cell value in every table is
correct; what is wrong is two pieces of surrounding text.

Verified 11 September 2026 against `fourarm/analysis/ex1/ex1_reproduce_tables.ipynb`,
which regenerates all thirteen Experiment 1 tables from the frozen data.

---

## 1. Table 4.7's note misstates both the range and the cause

**The thesis says.** "Each cell is scored on 95 or 96 grasp-binding scenes, the
occasional shortfall from a single unparseable GPT reply."

**What the data shows.** The true range is **94 to 96**. GPT's No Rules and
Legal-Arm Control cells are scored on 94.

The cause is not unparseable replies. It is GPT **declining on every repeat of
a scene**. A decline is not a proposal, and legality is measured over proposals
made, so a scene whose three repeats are all declines has no majority to take
and leaves the scene-level denominator entirely.

There is exactly one genuinely unparseable reply in cast A. It is Gemini's, in
No Width + Swapped, and it costs a *trial*, not a scene.

**In the code.** Section 11 of the notebook establishes the range from the data
and the generated note in `tables/ex1/ex1_design.tex` states it correctly. The
two mechanisms are distinguishable in a run row: a decline is recorded as
`noop`, an unparseable reply is not.

---

## 2. Table 4.8's column header understates one denominator

**The thesis says.** `n = 126` over the all-picking column, for all three
models.

**What the data shows.** Gemini and Qwen are scored on 126. **GPT is scored on
125**, for the same reason as above: one scene has no majority-eligible repeat.

The printed cell values are correct. Only the header is one state optimistic.

**In the code.** Section 12 of the notebook computes the per-model denominators
and the generated `tables/ex1/ex1_baseline.tex` puts the true figures in the
table note.

---

## Not errata

Two things that look like disagreements and are not, recorded so they are not
re-investigated.

**Cast B figures appear twice at different values.** `docs/TABLE_PROVENANCE.md`
gives Full Information 98.8%, No Width 90.1%, gap 8.7 [3.9, 14.3]. Table 4.11
gives 100.0, 87.5, +12.5 [+3.6, +23.6]. Both are correct: the first is
**trial level**, the second the **per-scene majority**, which is the unit the
chapter reports throughout. The provenance document lists its figures without
naming the unit, which is what makes them look contradictory.

**Cast B swap runs exist on disk.** `out/ex1_castb_gpt_swap_r1.jsonl` and
`out/ex1_castb_gpt_nowidth-swap_r1.jsonl` are real 108-row runs, while
Appendix A.1 says the swap conditions were run on cast A alone. They are
single-repeat pilots the chapter deliberately excludes. They are named in
`run_files.EXCLUDED` with that reason, so the manifest audit will not let them
be pooled with the four reported cast B cells.
