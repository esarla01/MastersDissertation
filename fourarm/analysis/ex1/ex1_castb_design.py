"""ex1_castb_design: the design table for cast B, all conditions run.

WHY THIS IS A SEPARATE SCRIPT. ex1_results.py resolves cast B through
CASTB_CONDITIONS and a global REPEATS map. Cast B's swap cells are single
repeat while cast A's are three, so adding them to REPEATS there would
change how cast A resolves and put the 320-check harness at risk two days
from submission. Nothing in this file recomputes a statistic: every
number comes from the helpers in ex1_results, so this table and the
published ones cannot drift apart.

WHAT IT REPORTS. One row per condition. Legality is the grasp-binding
subset at trial level with a Wilson interval taken at the SCENE
denominator, matching the chapter's convention, and the scene point
estimate is printed beside it. The negative control is legality on the
states where grasp binds nothing. Correct refusal is scene level on the
14 no-legal-arm states. Franka share is over every proposal made.

THE WIDE/NARROW SPLIT. Cast B holds ten objects and only four sit above
the 0.080 m Franka aperture, against a majority on cast A. Aggregate
legality is therefore diluted by decisions the width could never have
changed, which is why the aggregate cast B effect looks smaller than cast
A's while the per-object behaviour matches. The split is printed so the
dilution is visible rather than inferred. It conditions on the object the
model chose, which is post-treatment, so the counts per condition are
printed alongside it: if they move between conditions the comparison is
not clean and the table says so.

Run from the package directory:

    python3 analysis/ex1/ex1_castb_design.py

Add --latex to emit the table body.
"""

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(os.path.dirname(HERE))
for p in (PKG, os.path.join(PKG, "analysis"), os.path.join(PKG, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from analysis.ex1.ex1_results import (            # noqa: E402
    legality, scene_legality, refusal_scene, franka_share,
    violations_by_cause, consistency, wilson, pct)

PROBES = "probes/ex1_setb_v1.json"
APERTURE = 0.080

# (label, filename, repeats). Order follows the chapter: the crossed design
# first, then the width-absent swap. A missing file is reported, not
# skipped silently, because a table that quietly drops a condition looks
# like a condition that was never run.
CELLS = [
    ("Full Information",   "out/ex1_castb_gpt_full_r3.jsonl",          3),
    ("Swapped Names",      "out/ex1_castb_gpt_swap_r1.jsonl",          1),
    ("No Width",           "out/ex1_castb_gpt_nowidth_r3.jsonl",       3),
    ("No Width + Anon.",   "out/ex1_castb_gpt_nowidth-anon_r3.jsonl",  3),
    ("No Width + Swapped", "out/ex1_castb_gpt_nowidth-swap_r1.jsonl",  1),
]


def load_rows(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def object_widths(probes_path):
    """name -> grasp_m, and (source, seq) -> {task id: object}."""
    with open(probes_path) as f:
        ps = json.load(f)
    widths, tasks = {}, {}
    for pr in ps["probes"]:
        st = pr["state"]
        for o in st.get("objects", []):
            widths[o["name"]] = o.get("grasp_m")
        key = (pr["provenance"]["source"], pr["provenance"]["seq"])
        tasks[key] = {t["id"]: t["object"] for t in st.get("tasks", [])}
    return widths, tasks


def wide_narrow(rows, widths, tasks):
    """{'wide': (legal, scored), 'narrow': (legal, scored)}.

    Keyed on the object the model chose, so this conditions on a
    post-treatment variable. The scored counts are returned so a shift in
    what the model picks between conditions is visible.
    """
    out = {"wide": [0, 0], "narrow": [0, 0]}
    for r in rows:
        if r.get("zero_legal") or not r.get("binds_grasp"):
            continue
        if r.get("result") not in ("valid", "rejected"):
            continue
        key = (r["provenance"]["source"], r["provenance"]["seq"])
        tid = (r.get("decision") or {}).get("task_id")
        obj = tasks.get(key, {}).get(tid)
        if obj is None:
            continue
        band = "wide" if (widths.get(obj) or 0) > APERTURE else "narrow"
        out[band][1] += 1
        out[band][0] += r["result"] == "valid"
    return {k: tuple(v) for k, v in out.items()}


def declines(rows):
    """(declined, grasp-binding trials). Excluded from the legality
    denominator, so a condition that declines more is scored on an easier
    remainder and the count has to be visible."""
    n = k = 0
    for r in rows:
        if r.get("zero_legal") or not r.get("binds_grasp"):
            continue
        n += 1
        k += r.get("result") == "noop"
    return k, n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=PKG, help="the fourarm package directory")
    ap.add_argument("--latex", action="store_true", help="emit the table body")
    args = ap.parse_args(argv)

    widths, tasks = object_widths(os.path.join(args.root, PROBES))
    n_wide = sum(1 for w in widths.values() if (w or 0) > APERTURE)
    print("cast B, GPT, %d objects, %d above the %.3f m aperture\n"
          % (len(widths), n_wide, APERTURE))

    missing = [(lab, rel) for lab, rel, _ in CELLS
               if not os.path.exists(os.path.join(args.root, rel))]
    if missing:
        print("MISSING run files, table not built:")
        for lab, rel in missing:
            print("   %-20s %s" % (lab, rel))
        return 1

    rows_out, raw = [], {}
    for label, rel, reps in CELLS:
        rs = load_rows(os.path.join(args.root, rel))
        raw[label] = rs
        lk, ln = legality(rs)
        sk, sn = scene_legality(rs)
        nk, nn = legality(rs, grasp=False)
        rk, rn = refusal_scene(rs)
        fk, fn = franka_share(rs)
        lo, hi = wilson(sk, sn)          # interval at the scene denominator
        dk, dn = declines(rs)
        rows_out.append([
            label,
            "%.1f [%.1f, %.1f]" % (pct(lk, ln), lo, hi),
            "%d" % ln,
            "%.1f" % pct(sk, sn),
            "%.1f" % pct(nk, nn) if nn else "--",
            "%.1f" % pct(rk, rn) if rn else "--",
            "%.1f" % pct(fk, fn),
            "%d/%d" % (dk, dn),
            "%d" % reps,
        ])

    head = ["Condition", "Legality [95% CI]", "n", "Scene", "Neg. ctrl",
            "Refusal", "Franka", "Declines", "Reps"]
    w = [max(len(str(r[i])) for r in rows_out + [head]) for i in range(len(head))]
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(head)))
    print("  ".join("-" * w[i] for i in range(len(head))))
    for r in rows_out:
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))

    print("\nwide / narrow split, keyed on the object chosen")
    print("%-20s %-22s %-22s" % ("Condition", "wide (>0.080 m)", "narrow"))
    for label, _rel, _reps in CELLS:
        wn = wide_narrow(raw[label], widths, tasks)
        wk, wnn = wn["wide"]
        nk2, nn2 = wn["narrow"]
        print("%-20s %-22s %-22s"
              % (label,
                 "%5.1f%%  (%d/%d)" % (pct(wk, wnn), wk, wnn),
                 "%5.1f%%  (%d/%d)" % (pct(nk2, nn2), nk2, nn2)))

    print("\nviolation composition (grasp-binding, all causes)")
    for label, _rel, _reps in CELLS:
        c = violations_by_cause(raw[label])
        print("%-20s %s" % (label, dict(c) if c else "{}"))

    print("\nrepeat agreement (three-repeat cells only)")
    for label, _rel, reps in CELLS:
        if reps < 3:
            print("%-20s single repeat, agreement undefined" % label)
            continue
        right, wrong, flick = consistency(raw[label])
        print("%-20s stable right %d, stable wrong %d, flickering %d"
              % (label, right, wrong, flick))

    if args.latex:
        print("\n%% table body, cast B design")
        for r in rows_out:
            print("    " + " & ".join(str(c) for c in r) + r" \\")
    return 0


if __name__ == "__main__":
    sys.exit(main())
