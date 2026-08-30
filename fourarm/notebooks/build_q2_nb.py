"""Build ex2_q2_precedence.ipynb from the cell sources beside it.

    python3 notebooks/build_q2_nb.py notebooks/ex2_q2_precedence.ipynb

Q2 SHARES CELLS WITH Q1 RATHER THAN COPYING THEM. The key paste, the block
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
import nb_q2_cells as Q

SUBS_C1 = [
    # Q2 writes to its own directories.
    ('TABLES   = ROOT / "tables" / "ex2_q1"',
     'TABLES   = ROOT / "tables" / "ex2_q2"'),
    ('FIGURES  = ROOT / "figures" / "ex2_q1"',
     'FIGURES  = ROOT / "figures" / "ex2_q2"'),
    # The third condition. transforms.CONDITIONS has carried it all along;
    # Q1 simply did not run it.
    ('CONDITIONS  = ("congruent", "congruent_face", "dims")',
     'CONDITIONS  = ("congruent", "congruent_face", "conflict",'
     ' "conflict_face", "dims")'),
    ('RUNG        = "N0"                       # Q1 is read here and nowhere else',
     'RUNG        = "N0"                       # Q2 is read here too: the'
     '\n                                         # ladder is Q3'),
]

# Q1's cells 2 and 3 write their own tables, and reusing them verbatim put
# files named tab_ex2_q1_* into Q2's directory. They belong here -- the
# geometry and the inventory are part of Q2's provenance too, since they are
# what fixes its 32 usable positions -- but under Q2's names. "geometry"
# rather than "design", because Q2's own cell 4 writes tab_ex2_q2_design.csv
# for the conflict design and the two must not collide.
SUBS_C2 = [('write_csv("tab_ex2_q1_design.csv"',
            'write_csv("tab_ex2_q2_geometry.csv"')]
SUBS_C3 = [('write_csv("tab_ex2_q1_inventory.csv"',
            'write_csv("tab_ex2_q2_inventory.csv"')]

# The figure is Q1's, pointed at Q2's filenames. It loops over CONDITIONS and
# MODELS and reads share_rows, all of which Q2 builds in Q1's column order
# precisely so that this stays a substitution rather than a second copy.
SUBS_FIG = [# Before the generic ex2_q1 -> ex2_q2 rule, which would other-
            # wise leave the header naming a notebook that does not exist.
            ("ex2_q1_derivation.ipynb", "ex2_q2_precedence.ipynb"),
            ("ex2_q1", "ex2_q2"), ("Q1.", "Q2."),
            # It is cell 13 in Q1 and cell 12 here, and Q2 already has
            # a cell 13.
            ("Cell 13. Figure", "Cell 12. Figure")]


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
C12 = apply(B.C13, SUBS_FIG, "figure")
MD12 = apply(B.MD13, SUBS_FIG, "figure markdown")

CELLS = [
    ("md", A.MD0),  ("code", A.C0),      # keys, Q1's, verbatim
    ("md", Q.MD1),  ("code", C1),        # setup, Q1's, three substitutions
    ("md", A.MD2),  ("code", C2),        # block geometry, Q1's, renamed
    ("md", A.MD3),  ("code", C3),        # capture inventory, Q1's, renamed
    ("md", Q.MD4),  ("code", Q.C4),      # conflict design check
    ("md", Q.MD5),  ("code", Q.C5),      # prompt inspection
    ("md", Q.MD6),  ("code", Q.C6),      # PAID: conflict at N0
    ("md", Q.MD6A), ("code", Q.C6A),     # the withheld-number prompt
    ("md", Q.MD6B), ("code", Q.C6B),     # PAID: conflict_face at N0
    ("md", Q.MD6C), ("code", Q.C6C),     # PAID: congruent_face, its ceiling
    ("md", Q.MD7),  ("code", Q.C7),      # load, validate, coupling
    ("md", Q.MD8),  ("code", Q.C8),      # franka share
    ("md", Q.MD9),  ("code", Q.C9),      # paired contrasts, the endpoint
    ("md", Q.MD10), ("code", Q.C10),     # which source the opening came from
    ("md", Q.MD11), ("code", Q.C11),     # declines by direction
    ("md", MD12),   ("code", C12),       # figure, Q1's, repointed
    ("md", Q.MD13), ("code", Q.C13),     # provenance
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
