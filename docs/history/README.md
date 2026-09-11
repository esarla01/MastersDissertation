# Superseded working notes

Kept because they record *why* decisions were made, which the chapters argue
from but do not restate. Nothing here is current, and nothing here is a
reference for how the code works now — for that see `docs/EX2_GUIDE.md`,
`docs/TABLE_PROVENANCE.md`, and the notebooks.

| File | What it is | Why it is not current |
|---|---|---|
| `EX1_REDESIGN.md` | A proposal to use mass rather than the object's name as the memorisation carrier | Its own header says "Proposal, not yet accepted". It was not taken: the thesis tests identity through the name swap |
| `EX2_FINAL_RESULTS.md` | The source pack written for drafting Chapter 5 | The chapter is written, and the tables it describes are now generated and asserted by the EX2 notebooks |
| `EX2_INSTRUMENT_VALIDATION.md` | The source pack for the cue-validation and ground-truth subsections | Same |
| `EX2_Q1_STATUS.md` | A dated status snapshot: 2026-08-28, rung `N0` only | Superseded by the finished Q1 run |
| `q3_repair_plan.md` | The locked plan for the Q3 repair cells | Executed; the result is Tables 5.12–5.14 |
| `ex2_snapshot_20260830/` | A dated snapshot of the EX2 tables | Superseded by `fourarm/tables/ex2_q*/` |

`ex2_chapter5_restructured.tex` was deleted rather than moved here. It was a
draft of Chapter 5 prose, and the finished chapter lives with the thesis
source, not in the code repository. `git log` has it.
