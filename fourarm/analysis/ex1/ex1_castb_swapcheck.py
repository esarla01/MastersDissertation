"""ex1_castb_swapcheck: the directional swap statistic, per object.

WHAT THIS IS FOR. The design table reports legality over every object at
once. The swap renames two of cast B's ten, so eight of the objects in
that aggregate are controls and the informative signal is diluted to
invisibility. The pre-registered statistic for the swap is Franka share
per object, split into swapped and unswapped, and this prints it.

WHAT COUNTS AS EVIDENCE. Names inert means the swapped objects behave as
they did under the matching unswapped condition, and the controls do not
move either. Names used means the wide object relabelled with a narrow
name draws MORE Frankas, and the narrow object relabelled with a wide
name draws fewer. Cast B admits one pair, sugar_box against tuna_can, and
tuna_can appears as a queued task 23 times against sugar_box's 69, so
only the sugar_box direction can resolve. The tuna_can row is printed for
completeness and should be read as unresolvable, not as a null.

Objects are resolved through the FROZEN probe set, never through the
name printed in the prompt, so a swapped run is scored against the true
object exactly as the validator scored it.

Run from the package directory:

    python3 analysis/ex1/ex1_castb_swapcheck.py
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

from analysis.ex1.ex1_results import wilson, pct        # noqa: E402
from experiments.ex1.mislabel import (                  # noqa: E402
    SWAP_PAIRS_SETB, CONTROLS_SETB)

PROBES = "probes/ex1_setb_v1.json"
APERTURE = 0.080

SWAPPED = {n for pair in SWAP_PAIRS_SETB for n in pair}

# (label, file, matching unswapped baseline). The baseline is the cell
# with the same information EXCEPT that the names are true, so any
# difference is attributable to the false name and nothing else.
PAIRS = [
    ("Swapped Names", "out/ex1_castb_gpt_swap_r1.jsonl",
     "Full Information", "out/ex1_castb_gpt_full_r3.jsonl"),
    ("No Width + Swapped", "out/ex1_castb_gpt_nowidth-swap_r1.jsonl",
     "No Width", "out/ex1_castb_gpt_nowidth_r3.jsonl"),
]


def load_probes(root):
    with open(os.path.join(root, PROBES)) as f:
        ps = json.load(f)
    widths, tasks = {}, {}
    for pr in ps["probes"]:
        st = pr["state"]
        for o in st.get("objects", []):
            widths[o["name"]] = o.get("grasp_m")
        key = (pr["provenance"]["source"], pr["provenance"]["seq"])
        tasks[key] = {t["id"]: t["object"] for t in st.get("tasks", [])}
    return widths, tasks


def per_object(path, tasks):
    """object -> [franka proposals, proposals, legal, scored]."""
    out = collections.defaultdict(lambda: [0, 0, 0, 0])
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("zero_legal"):
                continue
            key = (r["provenance"]["source"], r["provenance"]["seq"])
            d = r.get("decision") or {}
            obj = tasks.get(key, {}).get(d.get("task_id"))
            if obj is None:
                continue
            arm = d.get("arm")
            if arm:
                out[obj][1] += 1
                out[obj][0] += str(arm).startswith("franka")
            if r.get("result") in ("valid", "rejected"):
                out[obj][3] += 1
                out[obj][2] += r["result"] == "valid"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=PKG)
    args = ap.parse_args(argv)

    widths, tasks = load_probes(args.root)
    print("swapped pair: %s" % ", ".join("%s <-> %s" % p
                                         for p in SWAP_PAIRS_SETB))
    print("controls:     %s\n" % ", ".join(CONTROLS_SETB))

    for slabel, spath, blabel, bpath in PAIRS:
        for path in (spath, bpath):
            if not os.path.exists(os.path.join(args.root, path)):
                print("MISSING %s" % path)
                return 1
        sw = per_object(os.path.join(args.root, spath), tasks)
        ba = per_object(os.path.join(args.root, bpath), tasks)

        print("=" * 78)
        print("%s   against   %s" % (slabel, blabel))
        print("=" * 78)
        print("%-22s %-5s %-20s %-20s %s"
              % ("object", "w", "Franka share " + blabel[:8],
                 "Franka share swap", "shift"))
        order = sorted(set(sw) | set(ba), key=lambda o: -(widths.get(o) or 0))
        for obj in order:
            bf, bn = ba[obj][0], ba[obj][1]
            sf, sn = sw[obj][0], sw[obj][1]
            if bn == 0 and sn == 0:
                continue
            tag = "SWAPPED" if obj in SWAPPED else ""
            shift = (pct(sf, sn) - pct(bf, bn)) if bn and sn else float("nan")
            print("%-22s %.3f %6.1f%% (%2d/%2d)      %6.1f%% (%2d/%2d)      "
                  "%+6.1f  %s"
                  % (obj, widths.get(obj) or 0,
                     pct(bf, bn), bf, bn, pct(sf, sn), sf, sn, shift, tag))

        # Aggregate the controls, which is where drift shows up.
        for band, keep in (("swapped", lambda o: o in SWAPPED),
                           ("controls", lambda o: o in CONTROLS_SETB)):
            bf = sum(ba[o][0] for o in ba if keep(o))
            bn = sum(ba[o][1] for o in ba if keep(o))
            sf = sum(sw[o][0] for o in sw if keep(o))
            sn = sum(sw[o][1] for o in sw if keep(o))
            if not bn or not sn:
                continue
            blo, bhi = wilson(bf, bn)
            slo, shi = wilson(sf, sn)
            print("  %-10s Franka  baseline %.1f [%.1f, %.1f]  "
                  "swap %.1f [%.1f, %.1f]"
                  % (band, pct(bf, bn), blo, bhi, pct(sf, sn), slo, shi))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
