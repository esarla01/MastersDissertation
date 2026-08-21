"""EX2 dimension-only analysis, from the run file.

Recomputes every number reported in the dims section: hygiene, the
by-pose width table, positions resolved in both poses, stability across
repeats, the failure taxonomy, qwen's legality, and the stated-width
distributions behind the fallback claim.

Usage:
    python3 analysis/ex2_analyse_dims.py runs/piece_dims_P2.jsonl
"""

import collections
import json
import re
import sys

MODELS = ("gpt", "qwen", "gemini")
RUNGS = ("P0", "P1", "P2", "P3a", "P3", "P4")   # P2a excluded by design
UP = re.compile(r"upright|standing", re.I)
LY = re.compile(r"lying|on its side|flat", re.I)


def scene(r):
    return r["trial_id"].split("|", 1)[0]


def ok(r):
    return r.get("believed_width_m") == r.get("true_grasp_m")


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


def main(path):
    raw = [json.loads(l) for l in open(path) if l.strip()]
    rows = [r for r in raw if not r.get("error")]
    pairs = [r for r in rows if r["seq"][0] in ("p", "e")]
    print("rows %d | errors dropped %d | null scenes dropped %d"
          % (len(raw), len(raw) - len(rows), len(rows) - len(pairs)))
    rows = pairs

    print()
    print("CELL COMPLETENESS (expect 66; 33 per pose)")
    for m in MODELS:
        line = "%-7s" % m
        for rung in RUNGS:
            n = len(cell(rows, m, rung))
            line += "%s %d  " % (rung, n)
        print(line)

    print()
    print("CORRECT WIDTH, per-scene majority (n=11 per pose)")
    print("%-5s %-14s %-14s %s" % ("rung", "gpt ly/up", "qwen ly/up",
                                   "gemini ly/up"))
    for rung in RUNGS:
        line = "%-5s" % rung
        for m in MODELS:
            parts = []
            for pose in ("lying", "upright"):
                k, n = maj(cell(rows, m, rung, pose), ok)
                parts.append("%d/%d" % (k, n) if n else "--")
            line += "%-14s" % (" ".join(parts))
        print(line)

    print()
    print("POSITIONS RESOLVED IN BOTH POSES (prose figure, n=11)")
    for rung in RUNGS:
        line = "%-5s" % rung
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
    print("UNANIMOUS LYING SCENES ACROSS 3 REPEATS (out of 11)")
    for rung in RUNGS:
        line = "%-5s" % rung
        for m in MODELS:
            sub = cell(rows, m, rung, "lying")
            b = collections.defaultdict(list)
            for r in sub:
                b[scene(r)].append(ok(r))
            u = sum(1 for v in b.values() if all(v) or not any(v))
            line += "%-10s" % ("%d/%d" % (u, len(b)) if b else "--")
        print(line)

    print()
    print("FAILURE TAXONOMY: lying trials with wrong width (out of 33)")
    print("%-7s %-4s %5s %8s %10s %7s" % ("model", "rung", "wrong",
                                          "says-up", "says-lying", "silent"))
    for m in MODELS:
        for rung in RUNGS:
            sub = [r for r in cell(rows, m, rung, "lying") if not ok(r)]
            u = ly_n = 0
            for r in sub:
                t = str((r.get("why") or {}).get("grasp", ""))
                if UP.search(t):
                    u += 1
                elif LY.search(t):
                    ly_n += 1
            print("%-7s %-4s %5d %8d %10d %7d"
                  % (m, rung, len(sub), u, ly_n, len(sub) - u - ly_n))

    print()
    print("QWEN LEGALITY, lying scenes, per-scene majority")
    for rung in RUNGS:
        k, n = maj(cell(rows, "qwen", rung, "lying"), legal)
        print("  %-4s %d/%d" % (rung, k, n))

    print()
    print("STATED WIDTH DISTRIBUTIONS (fallback claim; all rungs pooled)")
    for m in MODELS:
        for pose in ("lying", "upright"):
            sub = [r for r in rows if r["model"] == m
                   and r["true_pose"] == pose]
            d = collections.Counter(r.get("believed_width_m") for r in sub)
            print("  %-7s %-8s %s" % (m, pose, dict(d)))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])