# notebooks/appendix/ — the tables that had no generator

`appendix_tables.ipynb` rebuilds six tables from the modules that define them
and checks each against the thesis. Before this they were typed by hand, and a
module could change under a typed table without anything noticing.

| Table | Reports | Authority |
|---|---|---|
| 3.1 | The capability fields distinguishing the two arm types | `core/cell/cell_config.py` |
| 3.2 | The five constraints the validator checks | `harvest/probe_store.py` |
| A.1 | Both object casts, with the arm column **derived** | `ycb/ycb_objects.py`, `ycb/layouts.py` |
| A.2 | The three name-swap pairs | `experiments/ex1/mislabel.py` |
| C.1 | The Experiment 2 field aliases | `experiments/ex2/prompts.py` |
| D.1 | Where the 162 frozen states came from | `probes/ex1_v2.json` |

`make appendix` runs it and requires 6 of 6. LaTeX lands in `tables/appendix/`.

A.1's **Arms** column is stored nowhere in the thesis's sources: it is derived
by applying the capability rule to each object, so it cannot disagree with the
validator. The same is true of D.1's allocator column, and the notebook asserts
no harvest ran under a VLM — a probe set shaped by a model's behaviour would
undercut the whole design.

## Still typed by hand

| Table | Reports | Why not yet |
|---|---|---|
| B.1 | The bodies of R3 and R4, enriched and eligible | Needs the rule variants pulled out of `experiments/ex1/prompts.py` in the form the appendix prints them |
| B.2 | The edit that produces each condition | Same |
| E.1–E.4 | One worked decision state and the nine model replies | Needs a state replayed and three run files read; §6 of `ex1_reproduce_tables.ipynb` already builds the closely related Table 4.1 |

## thesis_expected.json

A committed copy of what each table printed when the thesis was last read, so a
clone without the thesis tree still checks all six rather than skipping them.
Section 8 refreshes it, and only when the thesis was readable — a run that fell
back to the vendored copy cannot refresh it, which would be the file certifying
itself. When the thesis changes, re-run with `THESIS_REPO` set and commit the
result.
