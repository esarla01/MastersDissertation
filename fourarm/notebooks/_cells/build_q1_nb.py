"""Build ex2_q1_derivation.ipynb from the cell sources beside it.

    python3 notebooks/_cells/build_q1_nb.py notebooks/ex2/ex2_q1_derivation.ipynb


nbformat is not installed in either project venv, so the notebook is emitted
as the JSON it is. Keeping the sources in a script means the notebook can be
regenerated rather than hand-edited as JSON, which is how notebooks rot.
"""
import json, os, sys

dest = sys.argv[1]

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _nb_build
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
    ("md", B.MD7C), ("code", B.C7C),
    ("md", B.MD7D), ("code", B.C7D),
    ("md", B.MD8), ("code", B.C8),
    ("md", B.MD9), ("code", B.C9),
    ("md", B.MD10), ("code", B.C10),
    ("md", B.MD11), ("code", B.C11),
    ("md", B.MD12), ("code", B.C12),
    ("md", B.MD13), ("code", B.C13),
    ("md", B.MD14), ("code", B.C14),
    ("md", B.MD15), ("code", B.C15),
    ("md", B.MD16), ("code", B.C16),
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


# OUTPUTS SURVIVE A REBUILD. This script used to emit every cell with
# execution_count None and no outputs, so adding one cell threw away the
# stored results of the other thirty-seven -- including the paid cells,
# whose printed cost lines and "already answered" counts are the record of
# what was bought and when.
#
# Matched on the cell's SOURCE TEXT, not on its id or its position: ids are
# derived from position, so inserting a cell renames every cell after it,
# and matching on position would carry cell 8's output onto cell 7c. Source
# text is what the output is an output OF, so a cell whose source changed
# correctly loses its output and has to be re-run.
#
# First match wins and is then consumed, so two cells with identical source
# take the first and second stored outputs in order rather than both taking
# the first.
def stored_outputs(dest):
    """{source text: [(execution_count, outputs), ...]} from an existing nb."""
    try:
        with open(dest) as fh:
            old = json.load(fh)
    except (IOError, OSError, ValueError):
        return {}
    out = {}
    for cell in old.get("cells", []):
        if cell.get("cell_type") != "code" or not cell.get("outputs"):
            continue
        out.setdefault("".join(cell.get("source", [])), []).append(
            (cell.get("execution_count"), cell["outputs"]))
    return out

STORED = stored_outputs(dest)
CARRIED = 0


def build_cell(i, kind, src):
    body = lines(src)
    if kind == "md":
        return {"cell_type": "markdown", "id": cell_id(i, kind),
                "metadata": {}, "source": body}
    global CARRIED
    count, outputs = None, []
    have = STORED.get("".join(body))
    if have:
        count, outputs = have.pop(0)
        CARRIED += 1
    return {"cell_type": "code", "id": cell_id(i, kind),
            "execution_count": count, "metadata": {},
            "outputs": outputs, "source": body}


nb = {
    "cells": [build_cell(i, kind, s) for i, (kind, s) in enumerate(CELLS)],
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python",
                       "name": "python3"},
        "language_info": {"name": "python", "version": "3.13"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

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
_had = sum(len(v) for v in STORED.values()) + CARRIED
print("outputs carried over: %d of %d that were stored" % (CARRIED, _had))
for _src in STORED:
    for _ in STORED[_src]:
        print("   DROPPED, its source changed and it must be re-run: %s"
              % _src.split("\n")[0][:66])
