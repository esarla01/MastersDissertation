"""Build ex2_q3_remediation.ipynb from the cell sources beside it.

    python3 notebooks/build_q3_nb.py notebooks/ex2_q3_remediation.ipynb

Q3 SHARES CELLS WITH Q1 RATHER THAN COPYING THEM. The key paste, the block
geometry check and the capture inventory are Q1's own strings, used here
verbatim, so a fix to the inventory reaches both notebooks and cannot reach
one of them only.

Cell 1 is Q1's cell 1 with the substitutions in SUBS_C1 applied. They are
declared here, in one visible list, rather than being buried in a second copy
of two hundred lines: what Q2 changes about the setup is exactly this list.
Each one must match exactly once or the build fails, so a rename in Q1 that
would silently leave Q2 pointing at Q1's tables stops the build instead.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nb_cells_a as A
import nb_cells_b as B
import nb_q3_cells as Q

SUBS_C1 = [
    ('TABLES   = ROOT / "tables" / "ex2_q1"',
     'TABLES   = ROOT / "tables" / "ex2_q3"'),
    ('FIGURES  = ROOT / "figures" / "ex2_q1"',
     'FIGURES  = ROOT / "figures" / "ex2_q3"'),
    # Q3 runs the ladder in both conditions that have an N0 baseline.
    ('CONDITIONS  = ("congruent", "congruent_face", "dims")',
     'CONDITIONS  = ("dims", "conflict_face")'),
    # THREE repeats, matching Q1 and Q2 rather than contradicting them.
    # This substitution said 1 until 2026-08-31, and by then every file in
    # runs/ held 612 distinct trials across repeats 1, 2 and 3 -- the ladder
    # had been re-run and the build script never caught up. A source that
    # rebuilds the notebook with a REPEATS the data does not have makes
    # every cost line and every gate arithmetic wrong.
    ('REPEATS     = 3', 'REPEATS     = 3'),
    ('RUNG        = "N0"                       # Q1 is read here and nowhere else',
     'RUNG        = "N0"                       # the BASELINE rung. The ladder'
     '\n                                         # is cell 4, from prompts.RUNGS'),
]

# Q1's cells 2 and 3 write their own tables, and reusing them verbatim put
# files named tab_ex2_q1_* into Q2's directory. They belong here -- the
# geometry and the inventory are part of Q2's provenance too, since they are
# what fixes its 32 usable positions -- but under Q2's names. "geometry"
# rather than "design", because Q2's own cell 4 writes tab_ex2_q2_design.csv
# for the conflict design and the two must not collide.
SUBS_C2 = [('write_csv("tab_ex2_q1_design.csv"',
            'write_csv("tab_ex2_q3_geometry.csv"')]
SUBS_C3 = [('write_csv("tab_ex2_q1_inventory.csv"',
            'write_csv("tab_ex2_q3_inventory.csv"')]

# NO FIGURE CELL. Q3's endpoint is a table of second-order contrasts whose
# intervals are about thirty points wide by construction. Drawn as bars with
# error bars they would read as a precision the design does not have, and the
# honest presentation is the table with its resolution stated above it.
SUBS_FIG = []


def apply(src, subs, what):
    for old, new in subs:
        n = src.count(old)
        if n != 1 and (old, new) not in SUBS_FIG:
            raise SystemExit("%s: %r matched %d times, expected once. Q1's "
                             "source has changed under this build script."
                             % (what, old[:60], n))
        src = src.replace(old, new)
    return src


C1 = apply(A.C1, SUBS_C1, "cell 1")
C2 = apply(A.C2, SUBS_C2, "cell 2")
C3 = apply(A.C3, SUBS_C3, "cell 3")

CELLS = [
    ("md", A.MD0),  ("code", A.C0),      # keys, Q1's, verbatim
    ("md", Q.MD1),  ("code", C1),        # setup, Q1's, per SUBS_C1
    ("md", A.MD2),  ("code", C2),        # block geometry, Q1's, renamed
    ("md", A.MD3),  ("code", C3),        # capture inventory, Q1's, renamed
    ("md", Q.MD4),  ("code", Q.C4),      # the rung design
    ("md", Q.MD4B), ("code", Q.C4B),     # the off-ladder directives
    ("md", Q.MD5),  ("code", Q.C5),      # what each rung adds
    ("md", Q.MD6),  ("code", Q.C6),      # PAID: the gate, N-D in dims
    ("md", Q.MD7),  ("code", Q.C7),      # gate read-out
    ("md", Q.MD8),  ("code", Q.C8),      # PAID: the no-image control
    ("md", Q.MD9),  ("code", Q.C9),      # PAID: the rest of the dims ladder
    ("md", Q.MD10), ("code", Q.C10),     # PAID: the conflict_face ladder
    ("md", Q.MD10B), ("code", Q.C10B),   # PAID: stage 1, X-image
    ("md", Q.MD10C), ("code", Q.C10C),   # stage 1 read-out, gates stage 2
    ("md", Q.MD10D), ("code", Q.C10D),   # PAID: stage 2, the two controls
    ("md", Q.MD11), ("code", Q.C11),     # what is on disk
    ("md", Q.MD12), ("code", Q.C12),     # each rung against N0
    ("md", Q.MD12B), ("code", Q.C12B),   # the directives, read
    ("md", Q.MD13), ("code", Q.C13),     # attribution
    ("md", Q.MD14), ("code", Q.C14),     # reported opening by rung
    ("md", Q.MD15), ("code", Q.C15),     # the face the model names
    ("md", Q.MD16), ("code", Q.C16),     # provenance
]


def lines(src):
    out = src.strip("\n").split("\n")
    return [l + "\n" for l in out[:-1]] + [out[-1]]


def cell_id(i, kind):
    return "%s-%02d" % ("md" if kind == "md" else "code", i)


def build(dest):
    """Emit the notebook. Behind a function so this module can be IMPORTED
    for its CELLS list -- a driver that executes the cells wants the same
    composition the notebook has, and importing a script that writes a file
    as a side effect is how a test ends up clobbering its own argument."""
    nb = {
        "cells": [
            ({"cell_type": "markdown", "id": cell_id(i, kind),
              "metadata": {}, "source": lines(s)}
             if kind == "md" else
             {"cell_type": "code", "id": cell_id(i, kind),
              "execution_count": None, "metadata": {},
              "outputs": [], "source": lines(s)})
            for i, (kind, s) in enumerate(CELLS)
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.13"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    with open(dest, "w") as fh:
        json.dump(nb, fh, indent=1)
        fh.write("\n")
    print("wrote %s: %d cells (%d code, %d markdown)"
          % (dest, len(nb["cells"]),
             sum(1 for k, _ in CELLS if k == "code"),
             sum(1 for k, _ in CELLS if k == "md")))

    import ast
    for i, (kind, src) in enumerate(CELLS):
        if kind == "code":
            try:
                ast.parse(src)
            except SyntaxError as e:
                raise SystemExit("cell %d does not parse: %s" % (i, e))
    print("every code cell parses")


if __name__ == "__main__":
    build(sys.argv[1])
