"""Pre-write checks shared by the build_*_nb.py notebook builders.

Each takes the builder's CELLS list -- (kind, source) pairs, kind in
{"md", "code"} -- and raises SystemExit naming the offending cell rather
than returning a status, so a failing check stops the build.
"""
import ast
import re

# The spend gate reads CONFIRM_SPEND and refuses unless it equals the call
# count the cell just printed. Committing a notebook with the number filled
# in therefore turns "Run All" on a fresh clone into a paid sweep -- which is
# how 612, 1836 and 2448 reached git in the q1, q2 and q3 notebooks. The
# armed value belongs in the running kernel, never on disk.
ARMED_SPEND = re.compile(r"^\s*CONFIRM_SPEND\s*=\s*[0-9]+", re.M)


def check_no_armed_spend(cells):
    """Refuse to emit a notebook whose source arms a paid cell."""
    for i, (kind, src) in enumerate(cells):
        if kind == "code" and ARMED_SPEND.search(src):
            hit = ARMED_SPEND.search(src).group(0).strip()
            raise SystemExit(
                "cell %d arms the spend gate (%s). Set it back to None before "
                "rebuilding: the value belongs in the kernel, not on disk." % (i, hit))
    print("no cell arms the spend gate")


def check_cells_parse(cells):
    """Every code cell must at least compile."""
    for i, (kind, src) in enumerate(cells):
        if kind == "code":
            try:
                ast.parse(src)
            except SyntaxError as e:
                raise SystemExit("cell %d does not parse: %s" % (i, e))
    print("every code cell parses")


# OUTPUTS MUST SURVIVE A REBUILD. A code cell's stored output is the record of
# what a paid cell bought and when, so a builder that emits every cell with
# outputs=[] destroys that record the first time anyone regenerates. The q1 and
# q2 builders carry outputs over; build_q3_nb, build_q3repair_nb and
# build_frameprobe_nb did not, and rebuilding ex2_q3_remediation.ipynb dropped
# all 27 of its outputs. This is the shared implementation those three use.
def stored_outputs(dest):
    """Map an existing notebook's code-cell source text to its stored outputs.

    dest: path to the notebook about to be overwritten; missing or unreadable
    is not an error, it just means nothing to carry.
    Returns {source text: [(execution_count, outputs), ...]}, values in the
    order the cells appeared.

    Keyed on SOURCE TEXT, not on cell id or position: ids derive from position,
    so inserting a cell renames every cell after it and position-matching would
    carry one cell's output onto another. Source text is what the output is an
    output OF, so a cell whose source changed correctly loses its output and
    has to be re-run.
    """
    import json
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


def build_cells(cells, dest, cell_id, lines):
    """Build the notebook's cell list, carrying stored outputs across.

    cells: the builder's (kind, source) pairs. dest: the notebook being
    overwritten, read for outputs to carry. cell_id, lines: the builder's own
    id and line-splitting helpers, passed in so this does not fix their form.
    Returns (cell dicts, carried count, dropped source first-lines).
    """
    stored, carried = stored_outputs(dest), 0
    built = []
    for i, (kind, src) in enumerate(cells):
        body = lines(src)
        if kind == "md":
            built.append({"cell_type": "markdown", "id": cell_id(i, kind),
                          "metadata": {}, "source": body})
            continue
        count, outputs = None, []
        have = stored.get("".join(body))
        if have:
            # First match wins and is consumed, so two cells with identical
            # source take the first and second stored outputs in order.
            count, outputs = have.pop(0)
            carried += 1
        built.append({"cell_type": "code", "id": cell_id(i, kind),
                      "execution_count": count, "metadata": {},
                      "outputs": outputs, "source": body})
    dropped = [s.split("\n")[0][:66] for s, v in stored.items() for _ in v]
    return built, carried, dropped
