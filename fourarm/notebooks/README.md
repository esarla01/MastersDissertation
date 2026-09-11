# notebooks/ — where every published number is produced

Grouped by role, after a period in which notebooks, the Python their cells are
built from, and two LaTeX generators all sat in one flat directory.

```
notebooks/
├── ex1/        Experiment 1: one notebook, all thirteen tables
├── ex2/        Experiment 2: one notebook per sub-question
├── appendix/   Chapter 3 and the appendix tables
├── _cells/     the cell sources the EX2 and appendix notebooks are BUILT from
└── publish/    CSV and run files -> the .tex the thesis inputs
```

Run everything with `make verify` from the repository root. It executes copies,
so the tracked notebooks keep the outputs of the runs that were actually paid
for.

## ex1/

| Notebook | Produces |
|---|---|
| `ex1_reproduce_tables.ipynb` | Tables 4.1–4.11, F.1 and G.1, each rebuilt from `probes/` and the run files and asserted against the thesis |

## ex2/

| Notebook | Sub-question | Produces |
|---|---|---|
| `ex2_q1_derivation.ipynb` | E2-A, can the model get the constraint from the scene | Tables 5.6–5.9 |
| `ex2_q2_precedence.ipynb` | E2-B, which source governs when text and image disagree | Tables 5.10, 5.11 |
| `ex2_q3_remediation.ipynb` | E2-C, the rung ladder and the ceiling | Table 5.12, and 5.14's `+attention` row |
| `ex2_q3_repair.ipynb` | E2-C, the four repair treatments | Tables 5.13, 5.14 |
| `ex2_frame_probe.ipynb` | The `extents` frame control | Not a published table |

Each ends in an audit pinning its tables to the numbers Chapter 5 prints: 216
checks in total. **Table 5.14 is assembled from two notebooks**, so both are
checked — a split table can drift in the half nobody looks at.

## appendix/

`appendix_tables.ipynb` rebuilds Tables 3.1, 3.2, A.1, A.2, B.1, B.2, C.1, D.1
and E.1–E.4 from the modules and data that define them. 12 of 12.

## _cells/

The EX2 and appendix notebooks are generated, not hand-edited:

```bash
python3 notebooks/_cells/build_q1_nb.py notebooks/ex2/ex2_q1_derivation.ipynb
```

`nb_*_cells.py` hold the cell sources; `build_*_nb.py` assemble them;
`_nb_build.py` holds what the builders share. Editing a notebook in Jupyter and
not the cell bank is how the two drift — which is exactly how six armed
`CONFIRM_SPEND` values reached git.

A rebuild carries stored outputs across, matched on cell source text, so a cell
whose source changed correctly loses its output and must be re-run. Three of the
builders lacked that and silently destroyed every output; they use the shared
implementation now.

`ex1_reproduce_tables.ipynb` is written directly and has no cell bank.

## publish/

| Script | Reads | Writes |
|---|---|---|
| `thesis_q3_tables.py` | `tables/ex2_q3/*.csv` | `$THESIS_REPO/tables/ex2_q3_*.tex` |
| `ex2_q3_ceiling_contrast.py` | `runs/`, the Q3 inventory | `tables/ex2_q3/tab_ex2_q3_ceiling_contrast.csv` |

`ex2_q3_ceiling_contrast.py` has no caller. It computes the `N-ACD` contrast
that `ex2_q3_remediation.ipynb` prints but does not save, and it backs Table
5.14's `+attention` row, so it is a table generator rather than dead code.

Only Q3 has a CSV-to-LaTeX step. Q1 and Q2 emit CSV and their tables were
typeset by hand — worth closing, and not yet closed.

## The spend gate

Cells are labelled `MAKES MODEL CALLS` or `No model calls`. The paid ones are
inert unless `CONFIRM_SPEND` is set to the exact call count the cell just
printed, and it must never be committed set — `make spend-check` fails if it is,
and so does a rebuild.
