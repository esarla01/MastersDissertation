"""Independent recomputation of the conflict legality table.

Deliberately does not share code with analyse_conflict.py. Legality is
derived here from the gripper geometry rather than read from the stored
legal_true field, and the two are compared. If they disagree, the stored
field and the geometry are inconsistent and the table cannot be trusted.

Usage:
    python3 verify_legality.py runs/All_conflict.jsonl
"""

import collections
import json
import sys

APERTURE = {"franka": 0.080, "ur": 0.140}
MODELS = ("gpt", "qwen", "gemini")

# The rungs are read OFF THE FILE, not hardcoded. This script is run over
# whichever results file it is given, and those span two designs: the
# P-rung attention ladder and the N-rung factor set. A fixed tuple printed
# seven empty rows for a file from the other design and, worse, silently
# omitted any rung the tuple did not name.
RUNG_ORDER = ("P0", "P1", "P2a", "P2", "P3a", "P3", "P4",
              "N0", "N-A", "N-C", "N-order", "N-D", "N-CD")


def rungs_in(rows):
    """Rungs present in the data, in declaration order, unknown ones last."""
    seen = {r.get("rung") for r in rows if r.get("rung")}
    known = [x for x in RUNG_ORDER if x in seen]
    return known + sorted(seen - set(known))


def over_aperture(row):
    """Is this trial one where the TRUE opening needs a UR.

    The informative cell. Under the Franka preference an object the Franka
    can take makes the guidance-consistent choice legal whatever the model
    believes, so only trials above the aperture cost anything.

    Read from the geometry rather than from a pose name. The mustard had
    two poses, "lying" and "upright"; the block has three and only one of
    them is over the aperture, so a filter on true_pose == "lying" matched
    no block row and printed an empty table.
    """
    tw = row.get("true_grasp_m")
    return tw is not None and tw > APERTURE["franka"]


def aperture(arm):
    for prefix, width in APERTURE.items():
        if arm and arm.startswith(prefix):
            return width
    return None


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = float(k) / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (100 * max(0.0, c - h), 100 * min(1.0, c + h))


def main(paths):
    rows = []
    for path in paths:
        for line in open(path):
            line = line.strip()
            if line:
                r = json.loads(line)
                if not r.get("error"):
                    rows.append(r)

    # deduplicate independently of the other script
    seen, uniq = set(), []
    for r in rows:
        key = (r["model"], r["preference"], r["rung"],
               r["trial_id"], r["repeat"])
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    print("rows after error removal and deduplication: %d" % len(uniq))

    # ---------------------------------------------------------------
    # Check A: does the stored legal_true agree with the geometry?
    # Every arm listed as legal must have an aperture at least the true
    # graspable width, and every arm named but absent from the list must
    # fail that test OR be excluded for a non-geometric reason (not idle,
    # not reachable). Only the first direction is checkable from the row.
    # ---------------------------------------------------------------
    bad = []
    for r in uniq:
        tw = r.get("true_grasp_m")
        for arm in (r.get("legal_true") or []):
            ap = aperture(arm)
            if ap is None or ap < tw:
                bad.append((r.get("trial_id"), arm, ap, tw))
    print("legal_true entries whose aperture is too small: %d" % len(bad))
    for b in bad[:5]:
        print("   ", b)

    # ---------------------------------------------------------------
    # Check B: recompute per-trial legality two ways and compare.
    #   stored   = named arm appears in legal_true
    #   geometry = named arm's aperture spans the TRUE width
    # These can differ legitimately if an arm is wide enough but not idle
    # or not reachable, so disagreements are printed rather than assumed
    # to be faults.
    # ---------------------------------------------------------------
    disagree = collections.Counter()
    for r in uniq:
        arm = r.get("arm")
        if arm is None:
            continue
        stored = arm in (r.get("legal_true") or [])
        geom = aperture(arm) is not None and aperture(arm) >= r["true_grasp_m"]
        if stored != geom:
            disagree[(r["model"], r["rung"], stored, geom)] += 1
    print("trials where stored legality and geometry disagree: %d"
          % sum(disagree.values()))
    for k in sorted(disagree, key=lambda x: tuple(str(i) for i in x)):
        print("    model=%s rung=%s stored=%s geometry=%s  n=%d"
              % (k[0], k[1], k[2], k[3], disagree[k]))

    # ---------------------------------------------------------------
    # Check C: rebuild the table from the geometry definition only.
    # ---------------------------------------------------------------
    print()
    print("LEGAL ASSIGNMENTS, scenes over the Franka aperture, "
          "franka preference")
    print("recomputed from gripper geometry, per-scene majority of 3 repeats")
    print("rung   " + "".join("%-22s" % m for m in MODELS))
    for rung in rungs_in(uniq):
        line = "%-8s" % rung
        for model in MODELS:
            sub = [r for r in uniq
                   if r["model"] == model
                   and r["preference"] == "franka"
                   and r["rung"] == rung
                   and over_aperture(r)]
            by_scene = collections.defaultdict(list)
            for r in sub:
                arm = r.get("arm")
                ok = (arm is not None
                      and aperture(arm) is not None
                      and aperture(arm) >= r["true_grasp_m"])
                by_scene[r["trial_id"].split("|", 1)[0]].append(ok)
            k = sum(1 for v in by_scene.values() if sum(v) * 2 > len(v))
            n = len(by_scene)
            ties = sum(1 for v in by_scene.values() if sum(v) * 2 == len(v))
            lo, hi = wilson(k, n)
            line += "%-22s" % ("%2d/%d [%2.0f-%3.0f]%s"
                               % (k, n, lo, hi, " TIE" if ties else ""))
        print(line)

    # ---------------------------------------------------------------
    # Check D: scene counts and repeat counts per cell.
    # ---------------------------------------------------------------
    print()
    print("scenes and repeats per reported cell (expect 11 scenes x 3)")
    print("(the expectation is the pilot's; a differently sized capture "
          "set reports every cell as a fault and that is the flag, not a "
          "bug)")
    for model in MODELS:
        for rung in rungs_in(uniq):
            sub = [r for r in uniq if r["model"] == model
                   and r["preference"] == "franka"
                   and r["rung"] == rung and over_aperture(r)]
            per = collections.Counter(
                r["trial_id"].split("|", 1)[0] for r in sub)
            sizes = set(per.values())
            if len(per) != 11 or sizes != {3}:
                print("   FAULT %s %s: %d scenes, repeat counts %s"
                      % (model, rung, len(per), sorted(sizes)))
    print("(no output above means every cell is 11 scenes at 3 repeats)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1:])
