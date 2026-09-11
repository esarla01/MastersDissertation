"""Compare a generated LaTeX table against the one the thesis prints.

Two sources for "what the thesis prints", in this order of preference:

  the thesis LaTeX at THESIS_REPO, which is authoritative; and
  a committed JSON of the numeric tokens each table carried when it was last
  read, which is what lets a clone without the thesis tree still check.

When both are present they must agree. A vendored copy that has drifted from
the thesis is worse than no vendored copy at all, because it would let a
notebook pass against a number the thesis no longer prints.

The comparison is on the ordered sequence of numeric tokens rather than on the
text, so it is immune to spacing and to caption edits and sensitive to exactly
what it should be sensitive to: a changed number. Only the rows between
\\midrule and \\bottomrule are read, so a number in a caption or a note is
ignored -- that is prose about the table, not a cell of it.

Used by ex1_reproduce_tables.ipynb and by the appendix notebooks.
"""

import datetime
import json
import os
import re

NUMBER = re.compile(r"-?\d+\.?\d*")

# Macros that wrap a cell without being part of its value. Stripped before the
# numbers are read so that a table-format option or a \multicolumn span does
# not enter the token sequence as data.
_MACROS = re.compile(r"\\(num|SI|si|texttt|textbf|emph|quad)")
_FORMAT = re.compile(r"table-format=[\d.]+")

# Structural macros whose ARGUMENTS are layout, not data. \multicolumn{6}{l}
# would otherwise contribute a 6, and \tnote{b} marks a footnote on a cell
# rather than being a cell. Both are removed whole.
_STRUCT = re.compile(r"\\multicolumn\{\d+\}\{[^}]*\}|\\tnote\{[^}]*\}"
                     r"|\\cmidrule\([^)]*\)\{[^}]*\}|\\cmidrule\{[^}]*\}")


def thesis_repo():
    """The thesis tree. Absent is not an error; the vendored copy covers it."""
    return os.path.expanduser(os.environ.get("THESIS_REPO", "~/Desktop/msc-paper"))


def thesis_source(label, repo=None):
    """The LaTeX of one thesis table, from its own file or from main.tex.

    Some tables live in their own file under tables/, the rest are written
    inline; both are found by the \\label the table carries.
    """
    repo = repo or thesis_repo()
    if not os.path.isdir(repo):
        return None
    stem = label.replace("tab:", "").replace(":", "_")
    own = os.path.join(repo, "tables", stem + ".tex")
    if os.path.exists(own):
        return open(own).read()
    main_path = os.path.join(repo, "main.tex")
    if not os.path.exists(main_path):
        return None
    main = open(main_path).read()
    at = main.find("\\label{%s}" % label)
    if at < 0:
        return None
    start = main.rfind("\\begin{table}", 0, at)
    end = main.find("\\end{table}", at)
    return main[start:end + len("\\end{table}")]


def table_body(tex):
    """The row block: everything between the FIRST \\midrule and \\bottomrule.

    Splitting on the last \\midrule instead would silently reduce a table with
    an internal rule to its final block, and a check that compares three rows
    out of nine is not a check.
    """
    after = tex.split("\\midrule", 1)[1]
    return after.split("\\bottomrule")[0].replace("\\midrule", " ")


def table_numbers(tex):
    """Every number in the body rows of a LaTeX table, in order."""
    out = []
    for line in table_body(tex).splitlines():
        line = _STRUCT.sub(" ", line)
        line = _FORMAT.sub(" ", _MACROS.sub(" ", line))
        out += [float(x) for x in NUMBER.findall(line)]
    return out


class Checker:
    """Checks generated tables against the thesis, with a vendored fallback.

    expected_path: the committed JSON. It carries "tables" (label -> ordered
    numeric tokens) for tables checked on numbers, and "bodies" (label -> row
    text) for tables checked on names or on quoted counts.

    Results accumulate in .checks as (label, status, detail) for an audit, and
    a disagreement raises rather than being collected.
    """

    def __init__(self, expected_path, repo=None):
        self.expected_path = expected_path
        self.repo = repo or thesis_repo()
        blob = self._load()
        self.expected = blob.get("tables", {})
        self.expected_bodies = blob.get("bodies", {})
        self.from_thesis = {}          # filled only when the thesis was read
        self.from_thesis_body = {}
        self.checks = []

    def _load(self):
        try:
            with open(self.expected_path) as fh:
                return json.load(fh)
        except (IOError, OSError, ValueError):
            return {}

    def have_thesis(self):
        return os.path.isdir(self.repo)

    def body(self, label):
        """(row text, origin) for one thesis table, or (None, None).

        Raises if a vendored body disagrees with the thesis.
        """
        published = thesis_source(label, self.repo)
        if published is not None:
            body = table_body(published)
            self.from_thesis_body[label] = body
            if label in self.expected_bodies and self.expected_bodies[label] != body:
                raise AssertionError(
                    "%s: the vendored body disagrees with the thesis. Re-run "
                    "the refresh cell with THESIS_REPO set." % label)
            return body, "thesis"
        if label in self.expected_bodies:
            return self.expected_bodies[label], "vendored"
        return None, None

    def check(self, label, tex, note=""):
        """Assert a generated table carries the numbers the thesis prints."""
        ours = table_numbers(tex)
        published = thesis_source(label, self.repo)
        vendored = self.expected.get(label)

        if published is not None:
            theirs = table_numbers(published)
            self.from_thesis[label] = theirs
            origin = "thesis"
            if vendored is not None and vendored != theirs:
                self.checks.append((label, "DIFFERS", "vendored copy is stale"))
                raise AssertionError(
                    "%s: the vendored copy disagrees with the thesis. Re-run "
                    "the refresh cell with THESIS_REPO set." % label)
        elif vendored is not None:
            theirs, origin = vendored, "vendored"
        else:
            self.checks.append((label, "SKIPPED",
                                "no thesis source and no vendored copy"))
            print("%-24s SKIPPED  (no thesis source, no vendored copy)" % label)
            return False

        if ours == theirs:
            self.checks.append((label, "MATCHES", "%d numeric cells, against the %s%s"
                                % (len(ours), origin, (" - " + note) if note else "")))
            print("%-24s MATCHES the %s on all %d numeric cells"
                  % (label, origin, len(ours)))
            return True

        if len(ours) != len(theirs):
            detail = "computed %d numbers, %s has %d" % (len(ours), origin, len(theirs))
        else:
            detail = "; ".join(
                "pos %d: computed %s, %s %s" % (i, a, origin, b)
                for i, (a, b) in enumerate(zip(ours, theirs)) if a != b)[:400]
        self.checks.append((label, "DIFFERS", detail))
        raise AssertionError("%s does not match the %s: %s" % (label, origin, detail))

    def note(self, label, status, detail):
        """Record a check made some other way than on numeric tokens."""
        self.checks.append((label, status, detail))

    def refresh(self):
        """Write the vendored copy, and only from the authoritative source.

        A run that fell back to the vendored copy cannot refresh it: that would
        be the file certifying itself. Returns a one-line summary.
        """
        if not self.from_thesis and not self.from_thesis_body:
            return ("THESIS_REPO was not readable, so the vendored file is "
                    "left alone.")
        payload = {
            "note": ("Numeric tokens and body text of each thesis table, as "
                     "printed, in order. Written by the refresh cell of the "
                     "notebook that owns these tables, from the LaTeX at "
                     "THESIS_REPO. Do not hand-edit: it is checked against the "
                     "thesis whenever the thesis is present."),
            "written": datetime.date.today().isoformat(),
            "thesis_repo": self.repo,
            "tables": {k: self.from_thesis[k] for k in sorted(self.from_thesis)},
            "bodies": {k: self.from_thesis_body[k]
                       for k in sorted(self.from_thesis_body)},
        }
        changed = (payload["tables"] != self.expected
                   or payload["bodies"] != self.expected_bodies)
        with open(self.expected_path, "w") as fh:
            json.dump(payload, fh, indent=1)
            fh.write("\n")
        return ("wrote %s: %d numeric tables + %d body tables, %d numbers%s"
                % (os.path.basename(self.expected_path), len(payload["tables"]),
                   len(payload["bodies"]),
                   sum(len(v) for v in payload["tables"].values()),
                   "  (CHANGED - commit it)" if changed else "  (unchanged)"))

    def audit_rows(self, spec):
        """Rows for the closing audit table.

        spec: (number, label, section, reports, source) per table, in the order
        the chapter prints them.
        """
        status = {l: (s, d) for l, s, d in self.checks}
        return [[n, label, "§" + sec, reports, source,
                 status.get(label, ("NOT CHECKED", ""))[0]]
                for n, label, sec, reports, source in spec]

    def check_subsequence(self, label, values, note=""):
        """Assert transcribed values appear in the thesis in the right order.

        values: the numbers a notebook pins, in the order the thesis prints
        them. They need not be every cell of the table -- a notebook may not
        compute every column, and a row may come from a different run -- so
        this checks ORDER and MEMBERSHIP rather than equality, and reports how
        much of the table the values account for.

        Weaker than check(), which compares a generated table cell for cell.
        Used where the notebook holds transcribed constants rather than
        emitting LaTeX: it catches a mis-transcription and it catches the
        thesis changing, which is what those constants were exposed to.

        Returns (matched, total) for the coverage line.
        """
        published = thesis_source(label, self.repo)
        if published is not None:
            theirs = table_numbers(published)
            self.from_thesis[label] = theirs
            vendored = self.expected.get(label)
            if vendored is not None and vendored != theirs:
                self.checks.append((label, "DIFFERS", "vendored copy is stale"))
                raise AssertionError(
                    "%s: the vendored copy disagrees with the thesis. Re-run "
                    "the refresh cell with THESIS_REPO set." % label)
            origin = "thesis"
        elif label in self.expected:
            theirs, origin = self.expected[label], "vendored"
        else:
            self.checks.append((label, "SKIPPED",
                                "no thesis source and no vendored copy"))
            print("%-28s SKIPPED  (no thesis source, no vendored copy)" % label)
            return (0, 0)

        # Walk both in order. A value that is not found where it should be is
        # either mistyped or no longer what the thesis prints.
        i, missing = 0, []
        for v in values:
            while i < len(theirs) and abs(theirs[i] - v) > 1e-9:
                i += 1
            if i == len(theirs):
                missing.append(v)
                break
            i += 1
        if missing:
            detail = ("%s is not in the %s's sequence at or after the values "
                      "before it" % (missing[0], origin))
            self.checks.append((label, "DIFFERS", detail))
            raise AssertionError("%s: %s" % (label, detail))

        self.checks.append((label, "MATCHES", "%d of %d cells against the %s%s"
                            % (len(values), len(theirs), origin,
                               (" - " + note) if note else "")))
        print("%-28s MATCHES the %s on %d of its %d cells"
              % (label, origin, len(values), len(theirs)))
        return (len(values), len(theirs))
