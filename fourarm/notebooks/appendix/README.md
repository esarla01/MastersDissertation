# notebooks/appendix/ — the tables that had no generator

`appendix_tables.ipynb` rebuilds **twelve** tables from the modules and data
that define them and checks each against the thesis. Before this they were
typed by hand, and a module could change under a typed table without anything
noticing.

| Table | Reports | Authority |
|---|---|---|
| 3.1 | The capability fields distinguishing the two arm types | `core/cell/cell_config.py` |
| 3.2 | The five constraints the validator checks | `harvest/probe_store.py` |
| A.1 | Both object casts, with the arm column **derived** | `ycb/ycb_objects.py`, `ycb/layouts.py` |
| A.2 | The three name-swap pairs | `experiments/ex1/mislabel.py` |
| C.1 | The Experiment 2 field aliases | `experiments/ex2/prompts.py` |
| D.1 | Where the 162 frozen states came from | `probes/ex1_v2.json` |
| B.1 | The four rule bodies R3 and R4 select between | `experiments/ex1/prompts.py` |
| B.2 | The edit that produces each condition | `experiments/ex1/prompts.py` `RUNGS` |
| E.1 | The arms in the worked state | `probes/ex1_v2.json`, `rec_decision_rich` seq 13 |
| E.2 | The open tasks in that state | the same state |
| E.3 | Both validator passes over the nine candidate pairs | the deployed validator, run twice |
| E.4 | The nine Full Information replies | 3 cast A run files |

`make appendix` runs it and requires 12 of 12. LaTeX lands in `tables/appendix/`.

A.1's **Arms** column is stored nowhere in the thesis's sources: it is derived
by applying the capability rule to each object, so it cannot disagree with the
validator. The same is true of D.1's allocator column, and the notebook asserts
no harvest ran under a VLM — a probe set shaped by a model's behaviour would
undercut the whole design.

E.3 is the one worth having. It runs the deployed validator twice over the same
state — once as posed, once with both apertures raised so grasp can never bind
— and reproduces Appendix E.3's worked figure, ℓ/b = 2/3 = 66.7%, from the
validator rather than from arithmetic repeated in prose.

B.1 and B.2 are prose, so they are checked on words rather than on a token
sequence: the four rule bodies must appear in the thesis exactly as the prompt
module sends them, and every condition in `RUNGS` must appear with its run code.
The thesis joins R3's clauses with commas where the module uses line breaks,
which is typesetting, so the comparison drops punctuation.

## What a numeric check cannot see

E.4's only numbers are task ids and repeat counts. An early version of its cell
read `reason` and `outcome` where the run rows carry `model_reason` and
`result`, produced a table with an empty reason column and `None` for every
verdict, and **passed** the numeric check on all 18 cells. The cell now asserts
both fields are present and that seven of nine replies are valid, as Appendix
E.4 reports.

## thesis_expected.json

A committed copy of what each table printed when the thesis was last read, so a
clone without the thesis tree still checks all six rather than skipping them.
Section 8 refreshes it, and only when the thesis was readable — a run that fell
back to the vendored copy cannot refresh it, which would be the file certifying
itself. When the thesis changes, re-run with `THESIS_REPO` set and commit the
result.
