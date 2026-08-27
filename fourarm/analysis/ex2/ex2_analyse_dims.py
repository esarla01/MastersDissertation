"""EX2 dimension-only analysis, from the run file.

Recomputes every number reported in the dims section: hygiene, the
by-pose width table, positions resolved in both poses, stability across
repeats, the failure taxonomy, qwen's legality, and the stated-width
distributions behind the fallback claim.

Usage:
    python3 analysis/ex2/ex2_analyse_dims.py runs/piece_dims_N0.jsonl
"""

import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from experiments.ex2 import labels as L                           # noqa: E402

MODELS = ("gpt", "qwen", "gemini")

# Rungs are read off the file. It is run over whichever results file it is
# given, and those span two designs: the P-rung attention ladder (P2a was
# excluded from the dims sweep by design) and the N-rung factor set. A
# fixed tuple printed empty rows for the other design and silently omitted
# any rung it did not name.
RUNG_ORDER = ("P0", "P1", "P2a", "P2", "P3a", "P3", "P4",
              "N0", "N-A", "N-C", "N-order", "N-D", "N-CD")

# The failure taxonomy, over whatever the reply carries. On a current run
# the resting face is a TYPED field, so it is read directly; on a
# pre-2026-08-26 file it has to be inferred from the prose, which is what
# these patterns are for.
UP = re.compile(r"upright|standing", re.I)
LY = re.compile(r"lying|on its side|flat", re.I)


def rungs_in(rows):
    """Rungs present in the data, in declaration order, unknown ones last."""
    seen = {r.get("rung") for r in rows if r.get("rung")}
    known = [x for x in RUNG_ORDER if x in seen]
    return known + sorted(seen - set(known))


def scene(r):
    return r["trial_id"].split("|", 1)[0]


def ok(r):
    """Did the model report the opening the object actually needs.

    Compared with a tolerance rather than for equality: the schema asks for
    three decimals and a model that answers 0.1 for 0.100 has reported the
    right number. An exact comparison scored those as wrong.
    """
    w, t = r.get("believed_width_m"), r.get("true_grasp_m")
    return w is not None and t is not None and abs(w - t) <= 0.006


def legal(r):
    a = r.get("arm")
    return a is not None and a in (r.get("legal_true") or [])


def maj(sub, pred):
    b = collections.defaultdict(list)
    for r in sub:
        b[scene(r)].append(bool(pred(r)))
    k = sum(1 for v in b.values() if sum(v) * 2 > len(v))
    return k, len(b)


def cell(rows, m, rung, pose=None):
    return [r for r in rows if r["model"] == m and r["rung"] == rung
            and (pose is None or r["true_pose"] == pose)]


def poses_in(rows):
    """The true poses present. The block has three where the mustard had
    two, so a hardcoded ("lying", "upright") dropped every block row."""
    return sorted({r["true_pose"] for r in rows if r.get("true_pose")})


def main(path):
    raw = [json.loads(l) for l in open(path) if l.strip()]
    rows = [r for r in raw if not r.get("error")]
    pairs = [r for r in rows if r["seq"][0] in ("p", "e")]
    print("rows %d | errors dropped %d | null scenes dropped %d"
          % (len(raw), len(raw) - len(rows), len(rows) - len(pairs)))
    rows = pairs
    moved = L.modernise_poses(rows)
    if moved:
        print("translated %d pre-2026-08-27 block rows to the resting-face "
              "vocabulary" % moved)
    rungs = rungs_in(rows)
    poses = poses_in(rows)
    print()
    print("rungs %s | poses %s" % (", ".join(rungs), ", ".join(poses)))
    print()
    print("CELL COMPLETENESS (the pilot expected 66; 33 per pose)")
    for m in MODELS:
        line = "%-7s" % m
        for rung in rungs:
            n = len(cell(rows, m, rung))
            line += "%s %d  " % (rung, n)
        print(line)

    print()
    print("CORRECT OPENING, per-scene majority, one figure per pose")
    print("poses in order: %s" % ", ".join(poses))
    print("%-8s %-18s %-18s %s" % ("rung", "gpt", "qwen", "gemini"))
    for rung in rungs:
        line = "%-8s" % rung
        for m in MODELS:
            parts = []
            for pose in poses:
                k, n = maj(cell(rows, m, rung, pose), ok)
                parts.append("%d/%d" % (k, n) if n else "--")
            line += "%-18s" % (" ".join(parts))
        print(line)

    print()
    print("POSITIONS RESOLVED IN BOTH POSES (prose figure, n=11)")
    for rung in rungs:
        line = "%-8s" % rung
        for m in MODELS:
            sub = cell(rows, m, rung)
            b = collections.defaultdict(list)
            for r in sub:
                b[scene(r)].append(ok(r))
            mj = {s: (sum(v) * 2 > len(v)) for s, v in b.items()}
            byp = collections.defaultdict(list)
            for s, v in mj.items():
                byp[s.rsplit("_", 1)[0]].append(v)
            k = sum(1 for v in byp.values() if len(v) == 2 and all(v))
            line += "%-10s" % ("%d/%d" % (k, len(byp)) if byp else "--")
        print(line)

    print()
    print("UNANIMOUS SCENES ACROSS 3 REPEATS, hardest pose (%s)"
          % (poses[0] if poses else "none"))
    for rung in rungs:
        line = "%-8s" % rung
        for m in MODELS:
            sub = cell(rows, m, rung, poses[0] if poses else None)
            b = collections.defaultdict(list)
            for r in sub:
                b[scene(r)].append(ok(r))
            u = sum(1 for v in b.values() if all(v) or not any(v))
            line += "%-10s" % ("%d/%d" % (u, len(b)) if b else "--")
        print(line)

    print()
    print("FAILURE TAXONOMY: %s trials with the wrong opening"
          % (poses[0] if poses else "none"))
    print("%-7s %-8s %5s %8s %10s %7s"
          % ("model", "rung", "wrong", "says-up", "says-flat", "silent"))
    for m in MODELS:
        for rung in rungs:
            hard = poses[0] if poses else None
            sub = [r for r in cell(rows, m, rung, hard) if not ok(r)]
            u = ly_n = 0
            for r in sub:
                # Typed field first, prose second. On a current run the
                # face is reported outright at N-D and N-CD and the regex
                # never runs; on a prose file it is all there is.
                face = r.get("resting_face")
                if face:
                    # small_face is the only one that is not flat, so it is
                    # the "says it is standing" column.
                    if face == "small_face":
                        u += 1
                    else:
                        ly_n += 1
                    continue
                t = str((r.get("why") or {}).get("grasp", ""))
                if UP.search(t):
                    u += 1
                elif LY.search(t):
                    ly_n += 1
            print("%-7s %-8s %5d %8d %10d %7d"
                  % (m, rung, len(sub), u, ly_n, len(sub) - u - ly_n))

    print()
    print("QWEN LEGALITY, %s scenes, per-scene majority"
          % (poses[0] if poses else "none"))
    for rung in rungs:
        k, n = maj(cell(rows, "qwen", rung, poses[0] if poses else None),
                   legal)
        print("  %-8s %d/%d" % (rung, k, n))

    print()
    print("STATED OPENING DISTRIBUTIONS (fallback claim; rungs pooled)")
    for m in MODELS:
        for pose in poses:
            sub = [r for r in rows if r["model"] == m
                   and r["true_pose"] == pose]
            d = collections.Counter(r.get("believed_width_m") for r in sub)
            print("  %-7s %-18s %s" % (m, pose, dict(d)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])