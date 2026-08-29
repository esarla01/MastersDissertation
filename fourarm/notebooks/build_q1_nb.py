"""Build ex2_q1_derivation.ipynb from the cell sources beside it.

    python3 notebooks/build_q1_nb.py notebooks/ex2_q1_derivation.ipynb


nbformat is not installed in either project venv, so the notebook is emitted
as the JSON it is. Keeping the sources in a script means the notebook can be
regenerated rather than hand-edited as JSON, which is how notebooks rot.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nb_cells_a as A
import nb_cells_b as B

CELLS = [
    ("md", A.MD0), ("code", A.C0),
    ("md", A.MD1), ("code", A.C1),
    ("md", A.MD2), ("code", A.C2),
    ("md", A.MD3), ("code", A.C3),
    ("md", A.MD4), ("code", A.C4),
    ("md", A.MD5), ("code", A.C5),
    ("md", B.MD5B), ("code", B.C5B),
    ("md", B.MD6), ("code", B.C6),
    ("md", B.MD6B), ("code", B.C6B),
    ("code", B.C7),
    ("md", B.MD7B), ("code", B.C7B),
    ("md", B.MD8), ("code", B.C8),
    ("md", B.MD9), ("code", B.C9),
    ("md", B.MD10), ("code", B.C10),
    ("md", B.MD11), ("code", B.C11),
    ("md", B.MD12), ("code", B.C12),
    ("md", B.MD13), ("code", B.C13),
    ("md", B.MD14), ("code", B.C14),
    ("md", B.MD15), ("code", B.C15),
]

def lines(src):
    out = src.strip("\n").split("\n")
    return [l + "\n" for l in out[:-1]] + [out[-1]]

# nbformat 4.5 and later require a unique "id" on every cell. Emitting
# them is not optional politeness: nbformat warns today and the docs say
# it becomes a hard error, at which point this notebook stops opening.
#
# The id is derived from the cell's POSITION, not randomised, so that
# rebuilding an unchanged notebook produces an identical file. A random
# id would make every regeneration a diff touching all thirty cells and
# would hide the one cell that actually changed.
def cell_id(i, kind):
    return "%s-%02d" % ("md" if kind == "md" else "code", i)

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

dest = sys.argv[1]
with open(dest, "w") as fh:
    json.dump(nb, fh, indent=1)
    fh.write("\n")
print("wrote %s: %d cells (%d code, %d markdown)"
      % (dest, len(nb["cells"]),
         sum(1 for k, _ in CELLS if k == "code"),
         sum(1 for k, _ in CELLS if k == "md")))

# Every code cell must at least parse.
import ast
for i, (kind, src) in enumerate(CELLS):
    if kind == "code":
        try:
            ast.parse(src)
        except SyntaxError as e:
            raise SystemExit("cell %d does not parse: %s" % (i, e))
print("every code cell parses")
