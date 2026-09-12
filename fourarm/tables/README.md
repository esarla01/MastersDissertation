# tables/ — generated, never hand-edited

One directory per experiment. Everything here is written by a notebook and
checked against the thesis; editing a file here changes nothing, because the
next `make verify` overwrites it.

| Directory | Written by | Backs |
|---|---|---|
| `ex1/` | `notebooks/ex1/ex1_reproduce_tables.ipynb` | Tables 4.1–4.11, F.1, G.1 |
| `appendix/` | `notebooks/appendix/appendix_tables.ipynb` | Tables 3.1, 3.2, 5.2, A.1, A.2, B.1, B.2, C.1, D.1, E.1–E.4 |
| `ex2_q1/` | `notebooks/ex2/ex2_q1_derivation.ipynb` | Tables 5.6–5.9 |
| `ex2_q2/` | `notebooks/ex2/ex2_q2_precedence.ipynb` | Tables 5.10, 5.11 |
| `ex2_q3/`, `ex2_q3_repair/` | the two Q3 notebooks | Tables 5.12–5.14 |

`ex1/` and `appendix/` hold `.tex` ready to `\input`. The Q1 and Q2 directories
hold CSV only — those tables were typeset by hand, and only Q3 has a
CSV-to-LaTeX step, in `notebooks/publish/thesis_q3_tables.py`.

Each `tab_*_provenance.csv` records every input file with its sha256 and row
count. `run_date` is when the **table** was regenerated, not when the run was
made.

`docs/TABLE_PROVENANCE.md` and `docs/PROVENANCE_EX2.md` map each published
table to the file and notebook behind it.
