#!/usr/bin/env python3
"""Build every Experiment 1 results table and figure from the run files.

WHAT IT DOES
    Computes the five results tables and the convergence figure agreed in the
    results map, prints them to the screen, and writes LaTeX into tables/ and
    CSV into figures/. Every number traces to a run file. Nothing is typed in.

HOW TO RUN
    python3 ex1_results.py                  from anywhere inside the repo
    python3 ex1_results.py --root ~/Downloads/thesis-repo-recent-version/fourarm

    Standard library only. pandas is NOT needed. matplotlib is optional: if it
    is missing the tables are still built and only the figure is skipped.

    Useful flags:
        --list-files    show which run files were found, then stop
        --no-figure     skip the plot
        --no-write      print only, write nothing to disk
        --quiet         write the files without printing the tables

NAMING
    Works with either naming scheme. It prefers the new names

        out/ex1_<cast>_<model>_<condition>_r<repeats>.jsonl

    and falls back to the old ones (ex1_gpt_L3nw_r3.jsonl and so on) if the
    rename has not been applied. Run with --list-files to see which it picked.

WHAT IT DELIBERATELY OMITS
    Latency, per-object error rates, and per-constraint legality at No Rules.
    All three were cut in the results map: latency answers no research
    question, the width-ordering reading was withdrawn after cast B failed to
    reproduce it, and delicacy falls to n=3 at No Rules.
"""

import argparse
import collections
import json
import math
import os
import re
import sys

# ===========================================================================
# SECTION 1.  Configuration
# ===========================================================================

MODELS = ["gemini", "gpt", "qwen"]
MODEL_LABEL = {"gemini": "Gemini", "gpt": "GPT", "qwen": "Qwen"}

# Each condition: prose name, file-name word, and the rung code recorded inside
# every row of the data. The rung code is what prompts.py keys on and it never
# changes. The file-name word is what the run file is called.
CONDITIONS = {
    "full":         ("Full Information",   "L3"),
    "anon":         ("Anonymous",          "L3-anon"),
    "swap":         ("Swapped Names",      "L3-swap"),
    "nowidth":      ("No Width",           "L3-nowidth"),
    "nowidth-anon": ("No Width + Anon.",   "L1-nowidth"),
    "nowidth-swap": ("No Width + Swapped", "L1-swap"),
    "norules":      ("No Rules",           "L2"),
    "givenset":     ("Legal-Arm Control",  "L4"),
}

# The 2 x 3 crossed design, then the two off-design controls.
DESIGN = ["full", "anon", "swap", "nowidth", "nowidth-anon", "nowidth-swap"]
CONTROLS = ["norules", "givenset"]
ORDER = DESIGN + CONTROLS

REPEATS = {"givenset": 1}          # every other condition is three

# Old file names, used only if the new ones are absent. Note ex1_gpt_L1nw_r3b:
# the "b" is there because the original run was destroyed by a --force in
# August and had to be rerun.
OLD_NAMES = {
    ("casta", "full"):         "ex1_{model}_L3_r3.jsonl",
    ("casta", "anon"):         "ex1_{model}_L3anon_r3.jsonl",
    ("casta", "swap"):         "ex1_{model}_L3swap.jsonl",
    ("casta", "nowidth"):      "ex1_{model}_L3nw_r3.jsonl",
    ("casta", "nowidth-anon"): "ex1_{model}_L1nw_r3.jsonl",
    ("casta", "nowidth-swap"): "ex1_{model}_L1swap.jsonl",
    ("casta", "norules"):      "ex1_{model}_L2_r3.jsonl",
    ("casta", "givenset"):     "ex1_{model}_L4.jsonl",
    ("castb", "full"):         "ex1_setb_{model}_L3_r3.jsonl",
    ("castb", "nowidth"):      "ex1_setb_{model}_L3nw_r3.jsonl",
    ("castb", "nowidth-anon"): "ex1_setb_{model}_L1nw_r3.jsonl",
}
OLD_SPECIAL = {("casta", "gpt", "nowidth-anon"): "ex1_gpt_L1nw_r3b.jsonl"}
OLD_IMAGE = "runs/ex1_L1-nowidth_V_gpt.jsonl"
NEW_IMAGE = "out/ex1_casta_gpt_nowidth-anon_r3_image.jsonl"

CASTB_CONDITIONS = ["full", "nowidth", "nowidth-anon"]

# Cast B was also run once at a single repeat, separately, at the SAME prompt
# version (2026-08-16b) on the same 108 states. Verified 21 August: GPT answered
# 25, 19 and 21 of the 108 states differently from repeat 1 of the three-repeat
# run, so these trials exist nowhere else. They are reported as a run-to-run
# stability check and are NOT pooled into the headline cast-B figures, because
# cast A is three repeats throughout and a four-repeat cast B would need a tie
# rule for per-scene majority to buy 0.2 of a point.
CASTB_R1 = {cond: "out/ex1_castb_gpt_%s_r1.jsonl" % cond
            for cond in CASTB_CONDITIONS}


# ===========================================================================
# SECTION 2.  Finding the repository and the run files
# ===========================================================================

def _is_package_root(path):
    """The fourarm package directory is the one holding out/ and probes/."""
    return (os.path.isdir(os.path.join(path, "out"))
            and os.path.isdir(os.path.join(path, "probes")))


def _walk_up(start):
    """Every directory from start up to the filesystem root, and a fourarm/
    subdirectory of each. Walking up rather than checking a fixed number of
    levels is what lets this script live anywhere in the tree: beside out/, in
    analysis/, in analysis/ex1/, or anywhere deeper."""
    seen, here = [], os.path.abspath(start)
    while True:
        seen.append(here)
        seen.append(os.path.join(here, "fourarm"))
        parent = os.path.dirname(here)
        if parent == here:
            return seen
        here = parent


def find_root(given=None):
    """Locate the fourarm package directory.

    Tried in order: what the user passed, then every directory from the script
    upwards, then every directory from the working directory upwards. No path
    is hardcoded, so the script survives being moved and survives the tree
    being cloned somewhere else.
    """
    candidates = []
    if given:
        candidates.append(os.path.abspath(os.path.expanduser(given)))
    candidates += _walk_up(os.path.dirname(os.path.abspath(__file__)))
    candidates += _walk_up(os.getcwd())

    tried = []
    for c in candidates:
        if c in tried:
            continue
        tried.append(c)
        if _is_package_root(c):
            return c

    print("ERROR: could not find the fourarm package directory.")
    print("It is the directory that contains out/ and probes/.")
    print("\nLooked in %d places, starting from:" % len(tried))
    print("    script    %s" % os.path.dirname(os.path.abspath(__file__)))
    print("    working   %s" % os.getcwd())
    print("\nand walking up from each. Nothing above either holds both out/ "
          "and probes/.")
    print("\nRun again with the package directory named explicitly:")
    print("    python3 %s --root /path/to/fourarm"
          % os.path.basename(__file__))
    sys.exit(1)


def resolve_one(root, cast, model, cond):
    """Return (relative path, scheme) for one cell, or (None, None)."""
    new = "out/ex1_%s_%s_%s_r%d.jsonl" % (cast, model, cond,
                                          REPEATS.get(cond, 3))
    if os.path.exists(os.path.join(root, new)):
        return new, "new"
    old = OLD_SPECIAL.get((cast, model, cond))
    if old is None:
        template = OLD_NAMES.get((cast, cond))
        old = template.format(model=model) if template else None
    if old and os.path.exists(os.path.join(root, "out", old)):
        return "out/" + old, "old"
    return None, None


def resolve_files(root):
    """Build the whole file map, and report clearly on anything missing."""
    files, schemes, missing = {}, collections.Counter(), []
    for model in MODELS:
        for cond in ORDER:
            rel, scheme = resolve_one(root, "casta", model, cond)
            if rel is None:
                missing.append(("casta", model, cond))
            else:
                files[("casta", model, cond)] = rel
                schemes[scheme] += 1
    for cond in CASTB_CONDITIONS:
        rel, scheme = resolve_one(root, "castb", "gpt", cond)
        if rel is None:
            missing.append(("castb", "gpt", cond))
        else:
            files[("castb", "gpt", cond)] = rel
            schemes[scheme] += 1
    for cond, rel in CASTB_R1.items():
        if os.path.exists(os.path.join(root, rel)):
            files[("castb_r1", "gpt", cond)] = rel
            schemes["new"] += 1
    image = None
    for cand in (NEW_IMAGE, OLD_IMAGE):
        if os.path.exists(os.path.join(root, cand)):
            image = cand
            break
    return files, image, schemes, missing


def report_missing(root, missing):
    print("\nERROR: %d run file(s) could not be found.\n" % len(missing))
    for cast, model, cond in missing:
        print("  %s %s %s" % (cast, model, CONDITIONS[cond][0]))
        print("      looked for  out/ex1_%s_%s_%s_r%d.jsonl"
              % (cast, model, cond, REPEATS.get(cond, 3)))
        old = OLD_SPECIAL.get((cast, model, cond)) or \
            (OLD_NAMES.get((cast, cond)) or "").format(model=model)
        if old:
            print("             and  out/%s" % old)
    print("\nWhat is actually in out/ that looks like an EX1 run:")
    outdir = os.path.join(root, "out")
    names = sorted(n for n in os.listdir(outdir) if n.startswith("ex1_")
                   and n.endswith(".jsonl"))
    for n in names[:40]:
        print("   ", n)
    if len(names) > 40:
        print("    ... and %d more" % (len(names) - 40))
    sys.exit(1)


# ===========================================================================
# SECTION 3.  Loading, and the integrity gate
# ===========================================================================

_CACHE = {}


def load(root, rel):
    if rel not in _CACHE:
        with open(os.path.join(root, rel)) as fh:
            _CACHE[rel] = [json.loads(line) for line in fh if line.strip()]
    return _CACHE[rel]


CHECKS = []


def check(block, name, got, want):
    CHECKS.append((block, name, got, want, got == want))
    return got == want


def integrity_gate(root, files, verbose=True):
    """Refuse to continue if a file is the wrong shape.

    Nothing downstream is trustworthy if the conditions are not being compared
    on the same states, so the probe hash is checked across every cast-A file.
    """
    rows_out = []
    hashes = collections.defaultdict(set)
    for (cast, model, cond), rel in sorted(files.items()):
        rs = load(root, rel)
        reps = collections.Counter(r.get("repeat", 1) for r in rs)
        rungs = {r.get("rung") for r in rs}
        want_rung = CONDITIONS[cond][1]
        errs = sum(1 for r in rs if r.get("error"))
        hashes[cast] |= {r.get("probe_set_hash") for r in rs}
        balanced = len(set(reps.values())) == 1
        rows_out.append([cast, model, CONDITIONS[cond][0], os.path.basename(rel),
                         len(rs), len(reps), "yes" if balanced else "NO",
                         errs, "ok" if rungs == {want_rung} else "WRONG"])
        check("integrity", "%s %s %s repeats balanced" % (cast, model, cond),
              balanced, True)
        check("integrity", "%s %s %s rung is %s" % (cast, model, cond, want_rung),
              rungs == {want_rung}, True)
    for cast, hs in hashes.items():
        check("integrity", "cast %s shares one probe hash" % cast, len(hs), 1)

    if verbose:
        print_table("Integrity gate",
                    ["cast", "model", "condition", "file", "rows", "repeats",
                     "balanced", "errors", "rung"], rows_out)
        bad = {r[3]: r[7] for r in rows_out if r[7]}
        print("errored rows:", bad if bad else "none")

    failures = [c for c in CHECKS if c[0] == "integrity" and not c[4]]
    if failures:
        print("\nINTEGRITY GATE FAILED. Do not use any number below.")
        for block, name, got, want, ok in failures:
            print("   %s: got %r, expected %r" % (name, got, want))
        sys.exit(1)
    if verbose:
        print("integrity gate passed\n")


# ===========================================================================
# SECTION 4.  Metrics
#
# PRIMARY ENDPOINT
#   Grasp-binding legality: the proportion of trials returning a legal
#   assignment, restricted to states where the grasp constraint binds and at
#   least one legal option exists. The restriction is what makes the measure
#   sensitive to the manipulation.
#
# UNIT OF ANALYSIS
#   Per-scene majority. 288 trials in a cell are 96 scenes by 3 repeats, not
#   288 independent observations. Trial level is reported for precision and
#   scene level is authoritative.
# ===========================================================================

# A reason "admits the gap" if it says the width is unknown, unstated, missing
# or not provided. Deliberately generous: a loose pattern that still finds
# nothing is stronger evidence than a strict one that finds nothing.
MISSING_INFO = re.compile(
    r"(unknown|unstated|not stated|missing|unspecified|no (?:declared )?width"
    r"|not (?:given|provided|specified|declared)|absent)", re.I)


def wilson(k, n, z=1.96):
    """Wilson score interval, returned as a percentage pair."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, centre - half), 100 * min(1.0, centre + half))


def newcombe(k1, n1, k2, n2, z=1.96):
    """Group 1 minus group 2, Newcombe hybrid-score interval, percentages."""
    l1, u1 = (x / 100 for x in wilson(k1, n1, z))
    l2, u2 = (x / 100 for x in wilson(k2, n2, z))
    p1, p2 = k1 / n1, k2 / n2
    d = p1 - p2
    return (100 * d,
            100 * (d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)),
            100 * (d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)))


def diff_of_diffs(a, b):
    """Difference between two Newcombe differences, normal approximation.

    Used for the interaction and for the swap separation. Adequate here because
    both inputs sit well away from 0 and 100.
    """
    se = math.sqrt(((a[2] - a[1]) / 3.92) ** 2 + ((b[2] - b[1]) / 3.92) ** 2)
    d = a[0] - b[0]
    return d, d - 1.96 * se, d + 1.96 * se


def scene_key(r):
    p = r["provenance"]
    return (p["source"], p["seq"], p["round"])


def legality(rs, grasp=True):
    """(legal, scored). grasp=False gives the negative control."""
    k = n = 0
    for r in rs:
        if r.get("zero_legal") or bool(r.get("binds_grasp")) != grasp:
            continue
        if r.get("result") not in ("valid", "rejected"):
            continue
        n += 1
        k += r["result"] == "valid"
    return k, n


def scene_legality(rs, grasp=True):
    """Per-scene majority: a scene is legal if most of its repeats are."""
    g = collections.defaultdict(list)
    for r in rs:
        if r.get("zero_legal") or bool(r.get("binds_grasp")) != grasp:
            continue
        if r.get("result") not in ("valid", "rejected"):
            continue
        g[scene_key(r)].append(r["result"] == "valid")
    return sum(1 for v in g.values() if sum(v) * 2 > len(v)), len(g)


def refusal_trial(rs):
    """Correct refusal at trial level, over states with no legal option."""
    k = n = 0
    for r in rs:
        if not r.get("zero_legal"):
            continue
        n += 1
        k += r.get("result") == "noop"
    return k, n


def refusal_scene(rs):
    """Correct refusal at scene level. THIS is the reported figure.

    The published harness takes a per-scene majority here while taking trial
    level for legality, so the two columns of the results table do not share a
    denominator. That is defensible but it must be stated, because the two
    differ: Gemini at No Rules is 107/108 at trial level and 36/36 at scene
    level, and quoting one under the other's label is a real error.
    """
    g = collections.defaultdict(list)
    for r in rs:
        if not r.get("zero_legal"):
            continue
        g[scene_key(r)].append(r.get("result") == "noop")
    return sum(1 for v in g.values() if sum(v) * 2 > len(v)), len(g)


def franka_share(rs):
    """Share of proposals sent to a Franka. The attribution measure."""
    k = n = 0
    for r in rs:
        arm = (r.get("decision") or {}).get("arm")
        if not arm:
            continue
        n += 1
        k += arm.startswith("franka")
    return k, n


def consistency(rs):
    """(stable right, stable wrong, flickering) over the picking states.

    Flickering is defined on the RAW result, matching the terms table and the
    published harness. Defining it on (task, arm) instead roughly doubles every
    count and would silently contradict every flickering figure already in the
    chapter.
    """
    g = collections.defaultdict(list)
    for r in rs:
        if r.get("zero_legal"):
            continue
        g[scene_key(r)].append(r.get("result"))
    right = sum(1 for v in g.values() if len(set(v)) == 1 and v[0] == "valid")
    wrong = sum(1 for v in g.values() if len(set(v)) == 1 and v[0] != "valid")
    flick = sum(1 for v in g.values() if len(set(v)) > 1)
    return right, wrong, flick


def violations_by_cause(rs):
    return collections.Counter(r.get("violation_cause") for r in rs
                               if r.get("violation_cause"))


def pct(k, n):
    return float("nan") if n == 0 else 100.0 * k / n


def fmt_ci(k, n):
    lo, hi = wilson(k, n)
    return "%.1f [%.1f, %.1f]" % (pct(k, n), lo, hi)


def fmt_gap(base, manip):
    """Cost of the manipulation: base minus manipulated, with an interval."""
    d, lo, hi = newcombe(base[0], base[1], manip[0], manip[1])
    return "%+.1f [%+.1f, %+.1f]" % (d, lo, hi)


def spans_zero(lo, hi):
    return lo <= 0 <= hi


# ===========================================================================
# SECTION 5.  Printing and LaTeX
# ===========================================================================

def print_table(title, headers, rows):
    cells = [[str(c) for c in row] for row in rows]
    widths = [max(len(str(headers[i])), *(len(r[i]) for r in cells))
              if cells else len(str(headers[i])) for i in range(len(headers))]
    line = "  ".join("-" * w for w in widths)
    print("\n" + title)
    print(line)
    print("  ".join(str(h).ljust(w) for h, w in zip(headers, widths)))
    print(line)
    for r in cells:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
    print(line)


def latex_table(headers, rows, caption, label, colspec=None, note=None):
    """Booktabs table with [H] placement, the standing convention."""
    colspec = colspec or ("l" + "r" * (len(headers) - 1))

    def esc(s):
        s = str(s)
        for a, b in (("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#")):
            s = s.replace(a, b)
        return s

    out = [r"\begin{table}[H]", r"  \centering",
           r"  \caption{%s}" % caption, r"  \label{%s}" % label, r"  \small",
           r"  \begin{tabular}{%s}" % colspec, r"    \toprule",
           "    " + " & ".join(esc(h) for h in headers) + r" \\",
           r"    \midrule"]
    for row in rows:
        out.append("    " + " & ".join(esc(c) for c in row) + r" \\")
    out += [r"    \bottomrule", r"  \end{tabular}"]
    if note:
        out.append(r"  \begin{minipage}{\linewidth}\vspace{2pt}"
                   r"\footnotesize %s\end{minipage}" % note)
    out.append(r"\end{table}")
    return "\n".join(out) + "\n"


def blank_repeats(rows, column=0):
    """Blank a repeated label so the table reads as blocks."""
    seen, out = set(), []
    for row in rows:
        row = list(row)
        if row[column] in seen:
            row[column] = ""
        else:
            seen.add(row[column])
        out.append(row)
    return out


WRITTEN = []


def stem_from_label(label):
    """Filename stem from the artefact's LaTeX label, so the two cannot drift.

    tab:ex1:gaps -> ex1_gaps, so the input and the ref always name the same
    artefact. Numbering files t1, t2 and so on goes stale
    the moment the results order changes and tells a reader nothing.
    """
    m = re.match(r"^(tab|fig):ex1:([a-z0-9]+)$", label)
    if not m:
        raise ValueError("label %r is not tab:ex1:<name> or fig:ex1:<name>" % label)
    return "ex1_%s" % m.group(2)


def emit_table(root, label, headers, rows, caption, colspec=None, note=None,
               write=True):
    """Write one table's LaTeX under the name its own label implies."""
    stem = stem_from_label(label)
    write_text(root, "tables/%s.tex" % stem,
               latex_table(headers, rows, caption, label, colspec, note), write)
    return stem


def write_text(root, relpath, text, enabled):
    if not enabled:
        return
    full = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as fh:
        fh.write(text)
    WRITTEN.append(relpath)


def write_csv(root, relpath, headers, rows, enabled):
    body = ",".join(headers) + "\n"
    for row in rows:
        body += ",".join('"%s"' % str(c).replace('"', '""') for c in row) + "\n"
    write_text(root, relpath, body, enabled)


# ===========================================================================
# SECTION 6.  Reference lines
#
# Read from the floor files rather than typed in, so a re-harvest of the probe
# set cannot leave a stale number in the chapter. The width-blind line is the
# score a model achieves by applying every constraint except grasp. It is what
# converts "the score dropped" into "the score fell exactly to the level of a
# model with no width information".
# ===========================================================================

def reference_lines(root):
    ref = {}
    for cast, fname in (("casta", "out/ex1_chance_floor.json"),
                        ("castb", "out/ex1_setb_floors.json")):
        path = os.path.join(root, fname)
        if not os.path.exists(path):
            print("WARNING: %s is missing, reference lines unavailable" % fname)
            ref[cast] = {"width_blind": float("nan"), "chance": float("nan")}
            continue
        d = json.load(open(path))["by_cause"]["grasp"]
        ref[cast] = {"width_blind": 100 * d["width_blind"]["mean"],
                     "chance": 100 * d["uniform"]["mean"]}
    return ref


# ===========================================================================
# SECTION 7.  tab:ex1:design  --  Q2 and Q4
#
# Legality across the 2 x 3 crossed design, plus the negative control that
# localises the effect. Legality ONLY. The supporting measures live in
# tab:ex1:signatures, because the point of that table is that the three of them
# converge on one claim. Splitting them back out into columns here would undo
# that.
# ===========================================================================

def table_design(root, files, ref, show, write):
    headers = ["Model", "Condition", "Width", "Identity", "Legality", "n",
               "Scene", "Neg. control"]
    rows, data = [], []
    for model in MODELS:
        for cond in DESIGN + CONTROLS:
            rs = load(root, files[("casta", model, cond)])
            kl, nl = legality(rs)
            ks, ns = scene_legality(rs)
            kn, nn = legality(rs, grasp=False)
            width = "absent" if cond.startswith("nowidth") else "present"
            ident = ("swapped" if cond.endswith("swap")
                     else "withheld" if cond.endswith("anon") else "true")
            if cond in CONTROLS:
                width, ident = "--", "--"
            rows.append([MODEL_LABEL[model], CONDITIONS[cond][0], width, ident,
                         fmt_ci(kl, nl), nl, "%.1f" % pct(ks, ns),
                         "%.1f" % pct(kn, nn)])
            data.append([MODEL_LABEL[model], cond, CONDITIONS[cond][0], width,
                         ident, kl, nl, "%.2f" % pct(kl, nl),
                         "%.2f" % pct(ks, ns), kn, nn, "%.2f" % pct(kn, nn)])

    if show:
        print_table("tab:ex1:design   Legality across the design, cast A",
                    headers, rows)
        print("width-blind line %.1f, chance floor %.1f"
              % (ref["casta"]["width_blind"], ref["casta"]["chance"]))

    caption = ("Experiment 1, cast A. Grasp-binding legality with Wilson "
               "95\\%% intervals across the crossed design and the two "
               "off-design controls. Width-blind reference line %.1f\\%%, "
               "chance floor %.1f\\%%. Scene is the per-scene majority. "
               "Neg.\\ control is legality on states where grasp binds "
               "nothing, which localises the effect to the grasp constraint."
               % (ref["casta"]["width_blind"], ref["casta"]["chance"]))
    note = ("All conditions are three repeats of 162 frozen states except "
            "Legal-Arm Control, which is one repeat. Denominators differ "
            "between conditions because a declined reply is scored on neither "
            "side.")
    emit_table(root, "tab:ex1:design", headers, blank_repeats(rows), caption,
               "llllrrrr", note, write)
    write_csv(root, "figures/ex1_design_data.csv",
              ["model", "cond", "condition", "width", "identity", "legal",
               "scored", "legality_pct", "scene_pct", "negctrl_legal",
               "negctrl_scored", "negctrl_pct"], data, write)
    return data


# ===========================================================================
# SECTION 7b.  tab:ex1:signatures  --  Q3
#
# Does the model register that the width has gone? The question has three
# readings and the data answers all three, so they belong in one table rather
# than scattered across three subsections.
#
#   Does it SAY so?    reasons that admit the gap
#   Does it ACT so?    correct refusal. A model with less information should
#                      abstain MORE. These abstain less.
#   What INSTEAD?      Franka share. Two Franka and two UR, so 50.0 is what
#                      pure arm-indifference looks like.
# ===========================================================================

ARM_INDIFFERENT = 50.0          # two Franka, two UR


def _reason_admits(text):
    return bool(MISSING_INFO.search(text or ""))


def table_signatures(root, files, show, write):
    headers = ["Model", "Signature", "Width shown", "Width absent",
               "Change [95% CI]"]
    rows, data = [], []
    for model in MODELS:
        shown = load(root, files[("casta", model, "full")])
        absent = load(root, files[("casta", model, "nowidth")])

        # 1. Does it say so? Counted over BOTH width-absent design conditions
        #    and pooled across models further down, but shown per model here.
        adm = ex = 0
        for cond in ("nowidth", "nowidth-anon"):
            for r in load(root, files[("casta", model, cond)]):
                if r.get("violation_cause") != "grasp":
                    continue
                ex += 1
                adm += _reason_admits(r.get("model_reason"))
        say = ("--", "%d/%d" % (adm, ex), "--")

        # 2. Does it act so?
        rb, nb = refusal_scene(shown)
        rm, nm = refusal_scene(absent)
        act = ("%.1f" % pct(rb, nb), "%.1f" % pct(rm, nm),
               fmt_gap((rb, nb), (rm, nm)))

        # 3. What instead?
        fb, nfb = franka_share(shown)
        fm, nfm = franka_share(absent)
        sub = ("%.1f" % pct(fb, nfb), fmt_ci(fm, nfm),
               fmt_gap((fm, nfm), (fb, nfb)))

        rows.append([MODEL_LABEL[model], "Reasons admitting the gap",
                     say[0], say[1], say[2]])
        rows.append(["", "Correct refusal", act[0], act[1], act[2]])
        rows.append(["", "Franka share", sub[0], sub[1], sub[2]])
        data.append([MODEL_LABEL[model], adm, ex, "%.2f" % pct(rb, nb),
                     "%.2f" % pct(rm, nm), "%.2f" % pct(fb, nfb),
                     "%.2f" % pct(fm, nfm)])

        # Is the width-absent Franka share consistent with treating the four
        # arms as interchangeable? Checked rather than asserted.
        lo, hi = wilson(fm, nfm)
        check("signatures", "%s franka share vs arm-indifference" % model,
              lo <= ARM_INDIFFERENT <= hi,
              lo <= ARM_INDIFFERENT <= hi)

    if show:
        print_table("tab:ex1:signatures   Three signatures of an unregistered "
                    "loss", headers, rows)
        print("Refusal change is Full Information minus No Width, so a "
              "positive value means the model abstains LESS with less "
              "information.")
        print("Franka share: two Franka and two UR, so %.1f is pure "
              "arm-indifference." % ARM_INDIFFERENT)
        for model in MODELS:
            fm, nfm = franka_share(load(root, files[("casta", model,
                                                     "nowidth")]))
            lo, hi = wilson(fm, nfm)
            print("  %-7s width absent %5.1f [%.1f, %.1f]  %s %.1f"
                  % (MODEL_LABEL[model], pct(fm, nfm), lo, hi,
                     "INCLUDES" if lo <= ARM_INDIFFERENT <= hi else "excludes",
                     ARM_INDIFFERENT))

    caption = ("Three readings of the same question, cast A, Full Information "
               "against No Width. A model that registered the loss of the "
               "declared width would say so, abstain more, or both. Refusal "
               "and Franka share are per-scene and per-proposal respectively. "
               "The refusal change is Full Information minus No Width, so a "
               "positive value means the model abstains less when it knows "
               "less. Two Franka arms and two UR arms, so a Franka share of "
               "%.1f\\%% is what treating the four arms as interchangeable "
               "looks like." % ARM_INDIFFERENT)
    note = ("Reasons are counted over both width-absent design conditions, so "
            "the denominator is larger than a single cell. The one-sided 95\\% "
            "upper bound on the pooled rate is given in the text.")
    emit_table(root, "tab:ex1:signatures", headers, rows, caption,
               "llrrr", note, write)
    write_csv(root, "figures/ex1_signatures_data.csv",
              ["model", "reasons_admitting", "reasons_examined",
               "refusal_shown_pct", "refusal_absent_pct",
               "franka_shown_pct", "franka_absent_pct"], data, write)
    return data


# ===========================================================================
# SECTION 8.  tab:ex1:gaps  --  Q2, Q4 and Q5
#
# Sign convention: BASE MINUS MANIPULATED, so a positive gap is the cost of the
# manipulation. A width gap of 24.0 means removing the width cost 24 points.
# ===========================================================================

CONTRASTS = [
    ("Width removal",    "names true",       "full",    "nowidth"),
    ("Width removal",    "names anonymised", "anon",    "nowidth-anon"),
    ("Width removal",    "names swapped",    "swap",    "nowidth-swap"),
    ("Identity removed", "width present",    "full",    "anon"),
    ("Identity removed", "width absent",     "nowidth", "nowidth-anon"),
    ("Identity swapped", "width present",    "full",    "swap"),
    ("Identity swapped", "width absent",     "nowidth", "nowidth-swap"),
    ("Rules removed",    "width present",    "full",    "norules"),
]


def table_contrasts(root, files, show, write):
    headers = ["Family", "Level"] + [MODEL_LABEL[m] for m in MODELS]
    rows, scene_rows, flips = [], [], 0
    for family, level, base, manip in CONTRASTS:
        row = [family, level]
        srow = [family, level]
        for model in MODELS:
            b = load(root, files[("casta", model, base)])
            u = load(root, files[("casta", model, manip)])
            t = newcombe(*legality(b), *legality(u))
            s = newcombe(*scene_legality(b), *scene_legality(u))
            row.append("%+.1f [%+.1f, %+.1f]" % t)
            srow.append("%+.1f [%+.1f, %+.1f]" % s)
            if spans_zero(t[1], t[2]) != spans_zero(s[1], s[2]):
                flips += 1
        rows.append(row)
        scene_rows.append(srow)

    check("contrasts", "cells whose zero-inclusion changes at scene level",
          flips, 0)
    if show:
        print_table("tab:ex1:gaps   Contrasts, trial level (base minus manipulated)",
                    headers, rows)
        print_table("     the same contrasts at the scene denominator",
                    headers, scene_rows)
        print("cells whose conclusion changes between the two denominators: %d "
              "of %d" % (flips, len(CONTRASTS) * len(MODELS)))

    caption = ("Effect of each manipulation on grasp-binding legality, cast A. "
               "Base minus manipulated, so a positive value is the cost of the "
               "manipulation. Newcombe 95\\% intervals. Every contrast was "
               "recomputed at the per-scene denominator and no interval "
               "changed whether it includes zero.")
    emit_table(root, "tab:ex1:gaps", headers, blank_repeats(rows), caption,
               "llrrr", None, write)
    write_csv(root, "figures/ex1_gaps_trial.csv", headers, rows, write)
    write_csv(root, "figures/ex1_gaps_scene.csv", headers, scene_rows, write)


def report_interaction(root, files, show):
    """Width by identity. Tested, not asserted.

    The chapter must say "no interaction is detectable", not "the removals do
    not interact". The second claims more than an interval this wide supports.
    """
    if not show:
        return
    rows = []
    for model in MODELS:
        def g(base, manip):
            return newcombe(*legality(load(root, files[("casta", model, base)])),
                            *legality(load(root, files[("casta", model, manip)])))
        widths = g("full", "nowidth")
        a = diff_of_diffs(widths, g("anon", "nowidth-anon"))
        b = diff_of_diffs(widths, g("swap", "nowidth-swap"))
        rows.append([MODEL_LABEL[model],
                     "%+.1f [%+.1f, %+.1f]" % a,
                     "%+.1f [%+.1f, %+.1f]" % b,
                     "%.0f" % ((a[2] - a[1]) / 2)])
    print_table("Interaction, width gap by identity level",
                ["Model", "against anonymisation", "against swap",
                 "resolution +/- pts"], rows)
    print("Every interval spans zero, so no interaction is DETECTABLE at this "
          "resolution.\nThat is not the same as no interaction existing.")


# ===========================================================================
# SECTION 9.  tab:ex1:composition  --  Q5
# ===========================================================================

CAUSE_ORDER = ["grasp", "reach", "delicate", "arm_state", "no_route", "payload"]
COMP_CONDITIONS = ["full", "nowidth", "norules"]


def table_composition(root, files, show, write):
    raw = []
    for model in MODELS:
        for cond in COMP_CONDITIONS:
            v = violations_by_cause(load(root, files[("casta", model, cond)]))
            raw.append([MODEL_LABEL[model], CONDITIONS[cond][0]] +
                       [v.get(c, 0) for c in CAUSE_ORDER] + [sum(v.values())])
    keep = [i for i, c in enumerate(CAUSE_ORDER)
            if any(r[2 + i] for r in raw)]
    headers = ["Model", "Condition"] + [CAUSE_ORDER[i] for i in keep] + ["Total"]
    rows = [[r[0], r[1]] + [r[2 + i] for i in keep] + [r[-1]] for r in raw]

    # The load-bearing check: removing one field must affect one constraint.
    gem = next(r for r in raw if r[0] == "Gemini" and r[1] == "No Width")
    nonzero = {CAUSE_ORDER[i] for i in range(len(CAUSE_ORDER)) if gem[2 + i]}
    check("composition", "Gemini No Width causes are grasp only",
          nonzero == {"grasp"}, True)

    if show:
        print_table("T3  Violations by cause", headers, rows)
        print("Gemini at No Width, causes present: %s" % sorted(nonzero))

    caption = ("Violations by cause, cast A. Removing the declared width "
               "changes the composition on one constraint only. Removing the "
               "rules multiplies violations across every constraint.")
    emit_table(root, "tab:ex1:composition", headers, blank_repeats(rows),
               caption, "ll" + "r" * (len(headers) - 2), None, write)


# ===========================================================================
# SECTION 10.  tab:ex1:castb  --  Q6
# ===========================================================================

def table_castb(root, files, ref, show, write):
    headers = ["Condition", "Legality", "n", "Scene", "Independent run",
               "Gap from Full Info"]
    rows, base = [], None
    for cond in CASTB_CONDITIONS:
        rs = load(root, files[("castb", "gpt", cond)])
        kn = legality(rs)
        ks, ns = scene_legality(rs)
        if base is None:
            base, gap = kn, "--"
        else:
            gap = fmt_gap(base, kn)
        r1 = files.get(("castb_r1", "gpt", cond))
        r1cell = "--"
        if r1 is not None:
            k1, n1 = legality(load(root, r1))
            r1cell = "%.1f" % pct(k1, n1)
        rows.append([CONDITIONS[cond][0], fmt_ci(*kn), kn[1],
                     "%.1f" % pct(ks, ns), r1cell, gap])

    if show:
        print_table("tab:ex1:castb   Cast B, GPT only, 108 states", headers, rows)
        if any(("castb_r1", "gpt", c) in files for c in CASTB_CONDITIONS):
            print("The independent run is a separate single-repeat execution "
                  "of the same three cells at the same prompt version, not a "
                  "subset of the three-repeat run. Two executions agree to "
                  "within about a point on legality while disagreeing on "
                  "roughly a fifth of individual states.")
        a = newcombe(*legality(load(root, files[("casta", "gpt", "full")])),
                     *legality(load(root, files[("casta", "gpt", "nowidth")])))
        b = newcombe(*legality(load(root, files[("castb", "gpt", "full")])),
                     *legality(load(root, files[("castb", "gpt", "nowidth")])))
        print("width-removal gap, GPT")
        print("  cast A  %+.1f [%+.1f, %+.1f]   width-blind line %.1f"
              % (a[0], a[1], a[2], ref["casta"]["width_blind"]))
        print("  cast B  %+.1f [%+.1f, %+.1f]   width-blind line %.1f"
              % (b[0], b[1], b[2], ref["castb"]["width_blind"]))
        print("  both exclude zero: %s     intervals overlap: %s"
              % (not spans_zero(a[1], a[2]) and not spans_zero(b[1], b[2]),
                 not (a[1] > b[2] or b[1] > a[2])))
        print("  Direction reproduces, magnitude does not. This is a "
              "generalisation check, not a replication.")

    caption = ("Cast B, ten objects disjoint from cast A, GPT only, three "
               "repeats on 108 states. Width-blind reference line %.1f\\%%, "
               "chance floor %.1f\\%%. The direction of the width effect "
               "reproduces and the magnitude does not."
               % (ref["castb"]["width_blind"], ref["castb"]["chance"]))
    note = ("Reported as a generalisation check and not a replication. Cast B "
            "was run at one model for cost reasons, which is stated as a "
            "limitation rather than presented as a second experiment. The "
            "independent-run column is a separate single-repeat execution of "
            "the same three cells at the same prompt version. Its trials are "
            "not contained in the three-repeat run and it is not pooled with "
            "it, because cast A is three repeats throughout.")
    emit_table(root, "tab:ex1:castb", headers, rows, caption,
               "lrrrrr", note, write)


# ===========================================================================
# SECTION 11.  tab:ex1:constraints  --  Q1
#
# Three constraints demanding three kinds of reasoning: a list lookup, a
# numeric comparison and a boolean check. If competence were a function of
# arithmetic difficulty the rows would separate. They do not.
#
# n is printed PER CELL, not per row. Denominators differ between models
# because a declined reply is scored on neither side, so GPT's delicacy cell
# rests on 6 trials and Gemini's on 9. A single row-level n would hide that.
# ===========================================================================

CONSTRAINTS = [("reach", "R4", "list lookup"),
               ("grasp", "R3", "numeric comparison"),
               ("delicate", "R3", "boolean check")]


def legality_any_cause(root, files, model):
    """Legality over every picking state at Full Information, any binding
    cause. The denominator for the 'all constraints' row."""
    k = n = 0
    for r in load(root, files[("casta", model, "full")]):
        if r.get("zero_legal") or r.get("result") not in ("valid", "rejected"):
            continue
        n += 1
        k += r["result"] == "valid"
    return k, n


def table_constraints(root, files, show, write):
    headers = ["Constraint", "Rule", "Reasoning demanded"] + \
        [MODEL_LABEL[m] for m in MODELS]
    rows, store = [], {}
    for cause, rule, kind in CONSTRAINTS:
        label = "Delicacy" if cause == "delicate" else cause.capitalize()
        row = [label, rule, kind]
        for model in MODELS:
            k = n = 0
            for r in load(root, files[("casta", model, "full")]):
                if r.get("zero_legal") or r.get("binding_cause") != cause:
                    continue
                if r.get("result") not in ("valid", "rejected"):
                    continue
                n += 1
                k += r["result"] == "valid"
            row.append("%.1f (n=%d)" % (pct(k, n), n))
            store[(cause, model)] = (k, n)
        rows.append(row)

    # The "all constraints" row is what makes this table answer both halves of
    # Q1 at once: the constraint rows give the uniformity null, this row gives
    # the three-way split between models that the rest of the chapter rests on.
    allrow = ["All constraints", "--", "--"]
    for model in MODELS:
        k, n = legality_any_cause(root, files, model)
        allrow.append("%.1f (n=%d)" % (pct(k, n), n))
        store[("all", model)] = (k, n)
    rows.append(allrow)

    if show:
        print_table("tab:ex1:constraints   Legality by constraint, Full Information",
                    headers, rows)
        print("reach minus grasp:")
        for model in MODELS:
            d = newcombe(*store[("reach", model)], *store[("grasp", model)])
            print("  %-7s %+.1f [%+.1f, %+.1f]%s"
                  % (MODEL_LABEL[model], d[0], d[1], d[2],
                     "" if spans_zero(d[1], d[2]) else "   EXCLUDES ZERO"))
        print("Delicacy binds only nine states. Draw no conclusion from that "
              "row.")

    caption = ("Legality at Full Information split by which constraint binds "
               "the state. Denominators differ between models because a "
               "declined reply is scored on neither side.")
    note = ("Delicacy binds only nine states in cast A, so that row is shown "
            "for completeness and no conclusion is drawn from it. A small "
            "number of trials have no single dominant binding cause and are "
            "excluded.")
    emit_table(root, "tab:ex1:constraints", headers, rows, caption,
               "lllrrr", note, write)


# ===========================================================================
# SECTION 12.  Prose numbers
#
# Findings that belong in sentences rather than tables, computed here so that
# the sentence and the number cannot drift apart.
# ===========================================================================


SWAP_PAIRS = [("ycb_large_clamp", 0.122), ("ycb_mustard", 0.096),
              ("ycb_meat_can", 0.084), ("ycb_power_drill", 0.050),
              ("ycb_soup_can", 0.068), ("ycb_gelatin_box", 0.073)]
SWAP_CONTROLS = ["ycb_mug", "ycb_mug2", "ycb_banana", "ycb_bowl"]
APERTURE = 0.080


def prose_reasons(root, files, show):
    """Zero grasp-error reasons admit the missing width."""
    admit = examined = 0
    for model in MODELS:
        for cond in ("nowidth", "nowidth-anon"):
            for r in load(root, files[("casta", model, cond)]):
                if r.get("violation_cause") != "grasp":
                    continue
                examined += 1
                admit += bool(MISSING_INFO.search(r.get("model_reason") or ""))
    check("prose", "grasp-error reasons examined", examined, 578)
    check("prose", "reasons admitting the missing width", admit, 0)
    if show:
        print("\nReasons bound")
        print("  grasp-error reasons examined        %d" % examined)
        print("  reasons admitting the missing width %d" % admit)
        if admit == 0:
            print("  one-sided 95%% upper bound           %.2f%%  "
                  "(rule of three)" % (300.0 / examined))


def prose_obedience(root, files, show):
    """Legal-Arm Control: does the model name an arm the prompt did not list?

    This is what licenses calling Qwen's problem constraint application rather
    than parsing. A model that produces a legal answer when the legal set is
    printed does not have an output-format problem.

    NOTE. The project record says "91 of 91". That does not reproduce. The
    figure computed from the frozen states is 36 of 160 for Qwen, and the
    validator's R2 rejections agree at 36. Trace the 91 and correct it.
    """
    probe_path = os.path.join(root, "probes/ex1_v2.json")
    if not os.path.exists(probe_path):
        if show:
            print("\nprobes/ex1_v2.json missing, skipping the obedience check")
        return
    idle = {}
    for p in json.load(open(probe_path))["probes"]:
        pv = p["provenance"]
        idle[(pv["source"], pv["seq"], pv["round"])] = {
            a["name"] for a in p["state"]["arms"]
            if a.get("state") == "IDLE" and not a.get("disabled")}

    rows = []
    for model in MODELS:
        rs = load(root, files[("casta", model, "givenset")])
        named = absent = 0
        for r in rs:
            arm = (r.get("decision") or {}).get("arm")
            if not arm:
                continue
            named += 1
            absent += arm not in idle[scene_key(r)]
        r2 = sum(1 for r in rs if r.get("violation_rule") == "R2")
        check("obedience", "%s R2 rejections match the state" % model, r2, absent)
        k, n = legality(rs)
        rows.append([MODEL_LABEL[model], named, absent,
                     "%.1f" % pct(absent, named), fmt_ci(k, n)])
    if show:
        print_table("Legal-Arm Control: proposals naming an unlisted arm",
                    ["Model", "proposals", "unlisted", "share %", "legality"],
                    rows)
        print("Legal-Arm Control is ONE repeat while everything else is three. "
              "Footnote it,\nor run at least Qwen at three repeats, since its "
              "cell carries the Qwen argument.")


def prose_image(root, files, image_rel, show):
    if image_rel is None:
        if show:
            print("\nimage-on run not found, skipping")
        return
    rs = load(root, image_rel)
    k, n = legality(rs)
    txt = legality(load(root, files[("casta", "gpt", "nowidth-anon")]))
    d = newcombe(k, n, *txt)
    if show:
        print("\nImage on, GPT")
        print("  file                    %s" % os.path.basename(image_rel))
        print("  rung in the data        %s"
              % ",".join(sorted({r.get("rung") or "?" for r in rs})))
        print("  grasp-binding legality  %s  n=%d" % (fmt_ci(k, n), n))
        print("  image minus text-only   %+.1f [%+.1f, %+.1f]%s"
              % (d[0], d[1], d[2],
                 "  spans zero" if spans_zero(d[1], d[2]) else "  EXCLUDES ZERO"))
        print("  CHECK THE PAIRING. This file is the nowidth-anon condition, "
              "which withholds\n  names, so the matched text-only cell must be "
              "nowidth-anon and not nowidth.")


def table_swap(root, files, show, write):
    """The pre-registered directional test on the swap.

    The test is NOT whether an interval excludes zero. Name-following requires
    the two swapped groups to move in OPPOSITE directions, so the statistic is
    the separation between them. The untouched controls are the benchmark: a
    separation smaller than the drift on objects that were never manipulated is
    not evidence of anything.
    """
    probe_path = os.path.join(root, "probes/ex1_v2.json")
    if not os.path.exists(probe_path):
        return
    true_object = {}
    for p in json.load(open(probe_path))["probes"]:
        pv = p["provenance"]
        for t in p["state"]["tasks"]:
            true_object[(pv["source"], pv["seq"], pv["round"], t["id"])] = \
                t["object"]

    def by_object(rs):
        tot, fr = collections.Counter(), collections.Counter()
        for r in rs:
            dec = r.get("decision") or {}
            arm, tid = dec.get("arm"), dec.get("task_id")
            if not arm or tid is None:
                continue
            pv = r["provenance"]
            obj = true_object.get((pv["source"], pv["seq"], pv["round"], tid))
            if obj is None:
                continue
            tot[obj] += 1
            fr[obj] += arm.startswith("franka")
        return fr, tot

    rows = []
    for model in MODELS:
        for base, manip, label in (("full", "swap", "width present"),
                                   ("nowidth", "nowidth-swap", "width absent")):
            fb, tb = by_object(load(root, files[("casta", model, base)]))
            fs, ts = by_object(load(root, files[("casta", model, manip)]))
            acc = {"wide": [0, 0, 0, 0], "narrow": [0, 0, 0, 0],
                   "control": [0, 0, 0, 0]}
            for obj, w in SWAP_PAIRS:
                g = acc["wide" if w > APERTURE else "narrow"]
                g[0] += fs[obj]; g[1] += ts[obj]
                g[2] += fb[obj]; g[3] += tb[obj]
            for obj in SWAP_CONTROLS:
                g = acc["control"]
                g[0] += fs[obj]; g[1] += ts[obj]
                g[2] += fb[obj]; g[3] += tb[obj]
            ch = {k: newcombe(v[0], v[1], v[2], v[3]) for k, v in acc.items()}
            sep = diff_of_diffs(ch["wide"], ch["narrow"])
            check("swap", "%s %s separation spans zero" % (model, label),
                  spans_zero(sep[1], sep[2]), True)
            rows.append([MODEL_LABEL[model], label,
                         "%+.1f" % ch["wide"][0], "%+.1f" % ch["narrow"][0],
                         "%+.1f" % ch["control"][0],
                         "%+.1f [%+.1f, %+.1f]" % sep])
    headers = ["Model", "Width", "Wide obj, narrow name",
               "Narrow obj, wide name", "Untouched controls", "Separation"]
    if show:
        print_table("tab:ex1:swap   Change in Franka share by swap direction",
                    headers, rows)
        print("Name-following requires the two swapped columns to move in "
              "OPPOSITE directions.\nThe separation is the statistic. Compare "
              "it against the control drift beside it.")
    caption = ("The pre-registered directional test on the object-name swap, "
               "cast A. Change in Franka share, swapped condition minus its "
               "matched unmanipulated parent, pooled by the direction the name "
               "was moved across the Franka aperture. Name-following requires "
               "the two swapped columns to move in OPPOSITE directions, so "
               "the separation between them is the statistic rather than "
               "whether either column excludes zero. The untouched controls "
               "are the benchmark.")
    note = ("Three pairs swap across the aperture, category-matched, none "
            "delicate. Physical fields stay with the true object, so ground "
            "truth does not move. Four objects are left unmanipulated as "
            "in-prompt controls. The parent of No Width + Swapped is No "
            "Width, not No Width + Anonymous, because the swapped condition "
            "carries names that are present but false.")
    emit_table(root, "tab:ex1:swap", headers, blank_repeats(rows), caption,
               "llrrrr", note, write)
    write_csv(root, "figures/ex1_swap_separation.csv", headers, rows, write)


# ===========================================================================
# SECTION 13.  fig:ex1:convergence  --  Q3
#
# Three panels: legality, correct refusal, Franka share. The x axis is the six
# cells of the 2 by 3 design in design order, so the width axis is the left
# half against the right half and the identity axis is within each half.
#
# The CSV is always written. The plot needs matplotlib and is skipped without
# it, since the CSV feeds pgfplots just as well and the rest of the thesis
# draws in TikZ.
# ===========================================================================

def figure_convergence(root, files, ref, show, write, draw):
    headers = ["model", "condition_key", "condition", "width", "identity",
               "measure", "k", "n", "value", "lo", "hi"]
    rows = []
    for model in MODELS:
        for cond in DESIGN:
            rs = load(root, files[("casta", model, cond)])
            width = "absent" if cond.startswith("nowidth") else "present"
            identity = ("swapped" if cond.endswith("swap")
                        else "anonymised" if cond.endswith("anon") else "true")
            for measure, (k, n) in (("legality", legality(rs)),
                                    ("refusal", refusal_scene(rs)),
                                    ("franka", franka_share(rs))):
                lo, hi = wilson(k, n)
                rows.append([MODEL_LABEL[model], cond, CONDITIONS[cond][0],
                             width, identity, measure, k, n,
                             round(pct(k, n), 2), round(lo, 2), round(hi, 2)])
    write_csv(root, "figures/ex1_convergence_data.csv", headers, rows, write)
    if show:
        print("\nF1  convergence figure data: %d rows "
              "(3 models x 6 conditions x 3 measures)" % len(rows))
    if not draw:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\nmatplotlib is not installed, so the plot was skipped. The CSV "
              "is written,\nand pgfplots can draw from it. To install:  "
              "pip3 install matplotlib")
        return

    labels = ["Full\nInfo", "Anon.", "Swapped", "No\nWidth",
              "No Width\n+ Anon.", "No Width\n+ Swapped"]
    marks = {"Gemini": "o", "GPT": "s", "Qwen": "^"}
    panels = [("legality", "Grasp-binding legality (%)"),
              ("refusal", "Correct refusal (%)"),
              ("franka", "Franka share (%)")]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    xs = list(range(len(DESIGN)))
    for ax, (measure, title) in zip(axes, panels):
        for model in MODELS:
            name = MODEL_LABEL[model]
            sub = {r[1]: r for r in rows if r[0] == name and r[5] == measure}
            vals = [sub[c][8] for c in DESIGN]
            los = [vals[i] - sub[c][9] for i, c in enumerate(DESIGN)]
            his = [sub[c][10] - vals[i] for i, c in enumerate(DESIGN)]
            ax.errorbar(xs, vals, yerr=[los, his], marker=marks[name],
                        capsize=3, lw=1.2, ms=5, label=name)
        if measure == "legality":
            for y, text, style in ((ref["casta"]["width_blind"], "width-blind", "--"),
                                   (ref["casta"]["chance"], "chance", ":")):
                ax.axhline(y, ls=style, lw=0.9, color="0.35")
                ax.annotate(text, (-0.45, y - 1.5), fontsize=7, color="0.35",
                            va="top", ha="left")
        ax.axvline(2.5, lw=0.8, color="0.8")
        ax.set_title(title, fontsize=10)
        ax.set_ylim(-5, 105)
        ax.set_xlim(-0.6, 5.4)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, fontsize=7)
        ax.grid(axis="y", lw=0.4, alpha=0.4)
    axes[0].set_ylabel("per cent")
    axes[0].legend(fontsize=8, frameon=False, loc="lower left")
    fig.text(0.5, -0.02, "width present            |            width absent",
             ha="center", fontsize=8, color="0.35")
    fig.tight_layout()
    if write:
        os.makedirs(os.path.join(root, "figures"), exist_ok=True)
        for ext in ("pdf", "png"):
            fig.savefig(os.path.join(root, "figures/ex1_convergence.%s" % ext),
                        dpi=150, bbox_inches="tight")
            WRITTEN.append("figures/ex1_convergence.%s" % ext)
    plt.close(fig)


# ===========================================================================
# SECTION 14.  Reconciliation and the check summary
# ===========================================================================

PINNED = {
    ("gemini", "width gap, names true"):  (27.8, 22.7, 33.2),
    ("gpt",    "width gap, names true"):  (24.0, 18.5, 29.6),
    ("qwen",   "width gap, names true"):  (-1.4, -8.3, 5.6),
    ("gemini", "width gap, anonymised"):  (24.7, 19.8, 29.9),
    ("gpt",    "width gap, anonymised"):  (21.9, 16.8, 27.2),
    ("qwen",   "width gap, anonymised"):  (4.2, -2.9, 11.2),
    ("gemini", "identity removed, width present"): (0.0, -1.3, 1.3),
    ("gpt",    "identity removed, width present"): (-1.0, -3.7, 1.5),
    ("gemini", "no rules"): (0.0, -1.3, 1.3),
    ("gpt",    "no rules"): (2.4, -0.9, 5.9),
    ("qwen",   "no rules"): (3.1, -4.1, 10.3),
}
PINNED_PAIRS = {
    "width gap, names true": ("full", "nowidth"),
    "width gap, anonymised": ("anon", "nowidth-anon"),
    "identity removed, width present": ("full", "anon"),
    "no rules": ("full", "norules"),
}


def reconcile(root, files, show):
    """Against the values recorded in the 21 August project status.

    A disagreement means one of the two is wrong and must be resolved before
    drafting, not after.
    """
    rows = []
    for (model, name), want in PINNED.items():
        base, manip = PINNED_PAIRS[name]
        got = newcombe(*legality(load(root, files[("casta", model, base)])),
                       *legality(load(root, files[("casta", model, manip)])))
        agree = all(abs(g - w) <= 0.15 for g, w in zip(got, want))
        check("reconciliation", "%s %s" % (model, name), agree, True)
        rows.append([MODEL_LABEL[model], name,
                     "%+.1f [%+.1f, %+.1f]" % got,
                     "%+.1f [%+.1f, %+.1f]" % want,
                     "yes" if agree else "NO"])
    if show:
        print_table("Reconciliation against the project status",
                    ["Model", "Contrast", "computed here", "status doc",
                     "agree"], rows)


def summarise_checks():
    failed = [c for c in CHECKS if not c[4]]
    print("\n%d/%d checks passed" % (len(CHECKS) - len(failed), len(CHECKS)))
    for block, name, got, want, ok in failed:
        print("  FAIL  [%s] %s: got %r, expected %r" % (block, name, got, want))
    if failed:
        print("\nDo not draft from this output until every check passes.")
    return 1 if failed else 0


# ===========================================================================
# SECTION 15.  Main
# ===========================================================================

def banner(show, text):
    if show:
        print("\n" + "=" * 74)
        print(text)
        print("=" * 74)


def main():
    ap = argparse.ArgumentParser(
        description="Build the Experiment 1 results tables and figure.")
    ap.add_argument("--root", default=None,
                    help="the fourarm package directory (found automatically "
                         "if omitted)")
    ap.add_argument("--list-files", action="store_true",
                    help="show which run files were found, then stop")
    ap.add_argument("--no-figure", action="store_true", help="skip the plot")
    ap.add_argument("--no-write", action="store_true",
                    help="print only, write nothing to disk")
    ap.add_argument("--quiet", action="store_true",
                    help="write the files without printing the tables")
    args = ap.parse_args()

    root = find_root(args.root)
    show = not args.quiet
    write = not args.no_write
    print("root: %s" % root)

    files, image_rel, schemes, missing = resolve_files(root)
    if missing:
        report_missing(root, missing)
    print("run files: %d found (%s)"
          % (len(files), ", ".join("%d %s-scheme" % (v, k)
                                   for k, v in sorted(schemes.items()))))
    print("image-on:  %s" % (image_rel or "not found"))

    if args.list_files:
        for key in sorted(files):
            print("  %-8s %-7s %-20s %s"
                  % (key[0], key[1], CONDITIONS[key[2]][0], files[key]))
        return 0

    integrity_gate(root, files, show)
    ref = reference_lines(root)

    # Ordered by the question each artefact answers, not by measure. The
    # section headings in the chapter follow this order.
    banner(show, "Q1  Can the model apply a stated constraint, and does the "
                 "kind of comparison matter?")
    table_constraints(root, files, show, write)
    prose_obedience(root, files, show)

    banner(show, "Q2  What happens when the declared width is withheld?")
    table_design(root, files, ref, show, write)
    table_contrasts(root, files, show, write)
    report_interaction(root, files, show)

    banner(show, "Q3  Does the model register the loss?")
    table_signatures(root, files, show, write)
    prose_reasons(root, files, show)
    figure_convergence(root, files, ref, show, write, not args.no_figure)

    banner(show, "Q4  Can the object's name supply what the number supplied?")
    table_swap(root, files, show, write)

    banner(show, "Q5  Can the rule text supply it?")
    table_composition(root, files, show, write)

    banner(show, "Q6  Which parts of the effect are object-set dependent?")
    table_castb(root, files, ref, show, write)

    banner(show, "Robustness checks, not research questions")
    prose_image(root, files, image_rel, show)
    reconcile(root, files, show)

    if write and WRITTEN:
        print("\nwrote %d files:" % len(WRITTEN))
        for p in WRITTEN:
            print("   ", p)
        print("\nIn main.tex:")
        for p in WRITTEN:
            if p.endswith(".tex"):
                print("    \\input{%s}" % p[:-len(".tex")])
    return summarise_checks()


if __name__ == "__main__":
    sys.exit(main())