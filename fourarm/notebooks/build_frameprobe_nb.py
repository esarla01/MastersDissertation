"""Build ex2_frame_probe.ipynb from the cell sources beside it.

    python3 notebooks/build_frameprobe_nb.py notebooks/ex2_frame_probe.ipynb

SHARES CELLS 0 TO 3 WITH Q1 rather than copying them, for the same reason
build_q3_nb.py does: a fix to the key loader, the root finder, the design check
or the visibility exclusion reaches every notebook and cannot reach one of them
only. It also means the probe pays for exactly the scenes Q1 paid for, because
CALL_SCENES is computed by Q1's cell 3 here and not re-derived.

Cells 2 and 3 are not decoration. Cell 2 is the guard against a stale kernel
holding an old prompts.py, which is the one failure that would make an extents
run silently render as named; cell 3 is where USABLE, CALL_SCENES and the
occlusion exclusion come from, and the read-out cell restricts to USABLE
exactly as Q1's analysis does.

FOUR SUBSTITUTIONS INTO CELL 1. The conditions narrow to the two the probe
buys, the repeat count drops to one, and TABLES and FIGURES are redirected to
a directory of this notebook's own so that cells 2 and 3 cannot overwrite the
CSVs Q1 owns. (The two files they write keep their q1 names inside that
directory: they are Q1's design and inventory tables, recomputed, and renaming
them would suggest they were something else.)

Each substitution must match exactly once or the build fails, so a rename in
Q1 stops the build instead of silently leaving this notebook pointing at the
wrong conditions or writing over Q1's tables.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nb_cells_a as A
import nb_frameprobe_cells as F

SUBS_C1 = [
    ('CONDITIONS  = ("congruent", "congruent_face", "dims")',
     'CONDITIONS  = ("congruent", "congruent_face")'),
    # One repeat. This is a presence test, not an estimate: under dims the
    # frame moved the anchor by ~90 points, and an effect that size does not
    # hide in 68 scenes. If nothing moves, the three-repeat named runs stand.
    ('REPEATS     = 3', 'REPEATS     = 1'),
    # Its own output directory. Cells 2 and 3 write tab_ex2_q1_design.csv and
    # tab_ex2_q1_inventory.csv, and a probe notebook must not be able to
    # rewrite the tables the Q1 chapter quotes -- not even with identical
    # content, because "identical" is a claim nobody would go and check.
    ('TABLES   = ROOT / "tables" / "ex2_q1"',
     'TABLES   = ROOT / "tables" / "ex2_frameprobe"'),
    ('FIGURES  = ROOT / "figures" / "ex2_q1"',
     'FIGURES  = ROOT / "figures" / "ex2_frameprobe"'),
]


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
    ("md", A.MD0),      ("code", A.C0),                       # keys, Q1's
    ("md", A.MD1),      ("code", apply(A.C1, SUBS_C1, "cell 1")),
    ("md", A.MD2),      ("code", A.C2),                       # design check
    ("md", A.MD3),      ("code", A.C3),                       # USABLE, CALL_SCENES
    ("md", F.MD_RUN),
    ("code", F.C_RUN_CONG),                                   # PAID
    ("code", F.C_RUN_FACE),                                   # PAID
    ("md", F.MD_READ),  ("code", F.C_READ),                   # read-out
]


def lines(src):
    out = src.strip("\n").split("\n")
    return [l + "\n" for l in out[:-1]] + [out[-1]]


def build(dest):
    nb = {"cells": [
            ({"cell_type": "markdown", "id": "%s-%02d" % (k, i),
              "metadata": {}, "source": lines(s)} if k == "md" else
             {"cell_type": "code", "id": "code-%02d" % i,
              "execution_count": None, "metadata": {},
              "outputs": [], "source": lines(s)})
            for i, (k, s) in enumerate(CELLS)],
          "metadata": {"kernelspec": {"display_name": "Python 3",
                                      "language": "python", "name": "python3"},
                       "language_info": {"name": "python", "version": "3.13"}},
          "nbformat": 4, "nbformat_minor": 5}
    with open(dest, "w") as fh:
        json.dump(nb, fh, indent=1)
        fh.write("\n")
    print("wrote %s: %d cells (%d code, %d markdown)"
          % (dest, len(nb["cells"]),
             sum(1 for k, _ in CELLS if k == "code"),
             sum(1 for k, _ in CELLS if k == "md")))

    import ast
    for i, (k, src) in enumerate(CELLS):
        if k == "code":
            try:
                ast.parse(src)
            except SyntaxError as e:
                raise SystemExit("cell %d does not parse: %s" % (i, e))
    print("every code cell parses")


if __name__ == "__main__":
    build(sys.argv[1])
