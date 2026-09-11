"""Build ex2_q3_repair.ipynb from the cell sources beside it.

    python3 notebooks/_cells/build_q3repair_nb.py notebooks/ex2/ex2_q3_repair.ipynb

SHARES CELLS 0 TO 3 WITH Q1 rather than copying them, for the same reason
build_q1_nb.py's siblings do: a fix to the key loader, the root finder, the
design check or the visibility exclusion reaches every notebook and cannot
reach one of them only. It also means this notebook pays for exactly the
scenes Q1 paid for, because CALL_SCENES is computed by Q1's cell 3 here and
not re-derived.

FIVE SUBSTITUTIONS INTO CELL 1. Gemini is dropped, since it reaches 100.0 from
N-D onward under dims and has nothing to repair. The conditions narrow to the
two this notebook buys. RUNG is unset, because every paid cell below names its
own and a stale N0 sitting in the namespace is the kind of thing a cell picks
up by accident. TABLES and FIGURES are redirected so that cells 2 and 3 cannot
overwrite the CSVs the Q1 chapter quotes.

Each substitution must match exactly once or the build fails, so a rename in
Q1 stops the build instead of silently leaving this notebook pointing at the
wrong models.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _nb_build
import nb_cells_a as A
import nb_q3repair_cells as Q

SUBS_C1 = [
    # Gemini is at ceiling under dims from N-D onward. Running it would buy
    # 408 calls that cannot move and would put a saturated row in every
    # table below it.
    ('_WANT = ("gpt_hi", "gemini", "claude_md")',
     '_WANT = ("gpt_hi", "claude_md")'),
    ('CONDITIONS  = ("congruent", "congruent_face", "dims")',
     'CONDITIONS  = ("congruent_face", "dims")'),
    # Every paid cell names its rung. A module-level RUNG would be a default
    # that no cell reads and one cell could pick up by mistake.
    ('RUNG        = "N0"                       # Q1 is read here and nowhere else',
     'RUNG        = None                       # each paid cell names its own'),
    ('TABLES   = ROOT / "tables" / "ex2_q1"',
     'TABLES   = ROOT / "tables" / "ex2_q3_repair"'),
    ('FIGURES  = ROOT / "figures" / "ex2_q1"',
     'FIGURES  = ROOT / "figures" / "ex2_q3_repair"'),
]

MD_TOP = r"""# Experiment 2, Q3 Repair

Two steps, each addressed twice: once by supplying information the model may be
missing, once by rephrasing the question while supplying nothing. Two of the
four cells are already on disk from the ladder; this notebook buys the other
two, plus two controls.

Run order is controls, read-out, then treatments. The read-out refuses to
report a treatment until both controls have landed and passed.

Cells 0 to 3 are Q1's, unchanged, so the sample and the exclusions are the
same ones every other Experiment 2 notebook uses."""


def apply(src, subs, what):
    for old, new in subs:
        n = src.count(old)
        if n != 1:
            raise SystemExit("%s: %r matched %d times, expected once. Q1's "
                             "source has changed under this build script."
                             % (what, old[:60], n))
        src = src.replace(old, new)
    return src


CELLS = [
    ("md", A.MD0),          ("code", A.C0),                    # keys, Q1's
    ("md", MD_TOP),         ("code", apply(A.C1, SUBS_C1, "cell 1")),
    ("md", A.MD2),          ("code", A.C2),                    # design check
    ("md", A.MD3),          ("code", A.C3),                    # USABLE, CALL_SCENES
    ("md", Q.MD_CONTROLS),
    ("code", Q.C_CTRL_A),                                      # PAID
    ("code", Q.C_CTRL_B),                                      # PAID
    ("md", Q.MD_READ),      ("code", Q.C_READ),                # read-out, gates
    ("md", Q.MD_TREAT),
    ("code", Q.C_TREAT_S),                                     # PAID
    ("code", Q.C_TREAT_B),                                     # PAID
    ("md", Q.MD_CEILING),   ("code", Q.C_CEILING),             # PAID, last
    ("md", Q.MD_PROV),      ("code", Q.C_PROV),                # the trail
    ("md", Q.MDAUDIT),     ("code", Q.CAUDIT),   # the audit against Chapter 5
]


def lines(src):
    out = src.strip("\n").split("\n")
    return [l + "\n" for l in out[:-1]] + [out[-1]]


def build(dest):
    # id from POSITION, not randomised, so rebuilding an unchanged
    # notebook produces an identical file rather than a diff touching
    # every cell.
    cells, carried, dropped = _nb_build.build_cells(
        CELLS, dest, lambda i, k: "%s-%02d" % ("md" if k == "md" else "code", i),
        lines)
    nb = {"cells": cells,
          "metadata": {"kernelspec": {"display_name": "Python 3",
                                      "language": "python", "name": "python3"},
                       "language_info": {"name": "python", "version": "3.13"}},
          "nbformat": 4, "nbformat_minor": 5}
    # Both guards run BEFORE the write, so a rejected notebook never
    # reaches disk. They were a post-write check until 2026-09-10.
    _nb_build.check_no_armed_spend(CELLS)
    _nb_build.check_cells_parse(CELLS)

    with open(dest, "w") as fh:
        json.dump(nb, fh, indent=1)
        fh.write("\n")
    print("wrote %s: %d cells (%d code, %d markdown)"
          % (dest, len(nb["cells"]),
             sum(1 for k, _ in CELLS if k == "code"),
             sum(1 for k, _ in CELLS if k == "md")))
    print("outputs carried over: %d" % carried)
    for _src in dropped:
        print("   DROPPED, its source changed and it must be "
              "re-run: %s" % _src)


if __name__ == "__main__":
    build(sys.argv[1])
