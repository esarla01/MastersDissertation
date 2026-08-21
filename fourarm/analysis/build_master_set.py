#!/usr/bin/env python3
"""Merge harvested trails into ONE frozen master probe set, then record
the EX1 and EX3 selections over it.

WHY ONE MASTER SET. EX1 and EX3 need overlapping but different slices:
EX1 wants states across the whole legality range, INCLUDING the zero-legal
ones that serve as refusal probes, while EX3 needs states with two or more
legal pairs, since a state with one option scores every allocator alike.
Harvesting twice would cost a second round of episodes and would leave the
two experiments running on sets that cannot be compared. Harvesting once
and selecting twice keeps them on shared ground and makes the difference
between them a documented filter rather than an accident of collection.

WHY DEDUPLICATION HAPPENS AT SELECTION, NOT AT HARVEST. The recorder
already gates on the allocator's own (idle arms, ready tasks) signature,
so no state is written twice for the same situation. But object positions
keep changing underneath a stable option set, so one situation can still
span several records: rnd_relay wrote 105 records covering about 30
distinct option sets. For LEGALITY that redundancy is harmful, because a
rate computed over the raw rows is weighted by how long each situation
happened to persist. For JUDGEMENT it is not redundancy at all: choosing
well within a fixed option set as arms move is exactly what EX3 measures.
So the master keeps every record and each experiment applies the collapse
that suits its question.

WHAT THE HASH GUARANTEES. content_hash covers the states, exact positions
and provenance, not the derived counts. Adding a new metric therefore
never invalidates a frozen set, while any change to the states themselves
does. That is what makes a cross-rung comparison genuinely paired: every
rung is answered on demonstrably the same states.

Usage:
    python3 analysis/build_master_set.py
    python3 analysis/build_master_set.py --out probes/master_v1.json
"""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.probe_store import (harvest_trail, load, make_set,  # noqa: E402
                                  save, select)

# The harvest. random is the backbone: it has no systematic arm preference,
# so it belongs to no allocator's strategy, which matters because b1 and
# b2 are themselves scored columns in EX3 and a set drawn mainly from one
# of them would evaluate that column on its own home ground. b1 and the
# two VLM-sourced sets are kept as a documented minority: random explores
# broadly but reaches late-episode states, where the easy work is done and
# one scarce arm remains, less often than an allocator that plays well.
TRAILS = [
    ("rnd_decision_rich", "random", "decision_rich"),
    ("rnd_relay",         "random", "relay_heavy"),
    ("rnd_captrap",       "random", "capability_trap"),
    ("rnd_contention",    "random", "contention"),
    ("rnd_balanced",      "random", "balanced"),
    ("rec_decision_rich", "b1",     "decision_rich"),
]

# Already-frozen sets folded in as-is. seed_v3 predates the binding-cause
# fields and its source trail no longer exists, so it carries legality
# counts but no cause tally; it is kept because it is a real VLM-sourced
# episode and dropping it would leave the set purely non-model in origin.
FROZEN = [("probes/seed_v3.json", "seed_v3", "vlm", "unknown")]


def option_set_key(p):
    """Identity of the DECISION, ignoring where things happen to sit.

    Two records share a key when the same tasks are open to the same idle
    arms with the same legal pairings. Positions are deliberately excluded:
    they move constantly and do not change which assignments the validator
    would accept.
    """
    d = p["derived"]
    key = (tuple(sorted(d.get("legal_per_task", {}).items())),
           d.get("n_idle_arms"),
           tuple(sorted(str(x) for x in d.get("legal_pairs", []))))
    return hashlib.md5(str(key).encode()).hexdigest()[:12]


def collapse(probes):
    """One representative per option set, keeping the first seen."""
    seen, out = set(), []
    for p in probes:
        k = option_set_key(p)
        if k in seen:
            continue
        seen.add(k)
        p["derived"]["option_set_key"] = k
        out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="probes/master_v1.json")
    ap.add_argument("--ex1", default="probes/ex1_v1.json")
    ap.add_argument("--ex3", default="probes/ex3_v1.json")
    ap.add_argument("--cap-per-source", type=int, default=40,
                    help="max states any ONE source may contribute to the "
                         "EX3 selection. rnd_relay alone wrote 105 records "
                         "and would otherwise supply nearly half the set, "
                         "making a layout-specific quirk look like a "
                         "general result.")
    ap.add_argument("--trails", action="append", metavar="STEM:ALLOC:LAYOUT",
                    help="override TRAILS, repeatable. Used for a second "
                         "object cast: TRAILS stays hardcoded so the default "
                         "build reproduces the original set byte for byte, "
                         "and a new cast is a separate invocation with its "
                         "own --out/--ex1/--ex3 paths rather than an edit "
                         "that silently changes what the default produces.")
    ap.add_argument("--frozen", action="store_true",
                    help="fold in the FROZEN sets even when --trails is "
                         "given. Off by default with --trails: the frozen "
                         "sets hold a DIFFERENT object cast, and merging "
                         "them mixes casts silently. The first set_b build "
                         "did exactly that, producing 21 distinct objects "
                         "from both casts in one set.")
    args = ap.parse_args()

    trails = TRAILS
    if args.trails:
        trails = []
        for t in args.trails:
            parts = t.split(":")
            if len(parts) != 3:
                raise SystemExit(
                    f"--trails {t!r}: expected STEM:ALLOC:LAYOUT. The "
                    f"allocator and layout are recorded as provenance on "
                    f"every probe, so guessing them would mislabel the set.")
            trails.append(tuple(parts))

    all_probes, sources, report = [], [], []

    for stem, alloc, layout in trails:
        path = f"out/{stem}_frames/consults.jsonl"
        try:
            ps = harvest_trail(path, source=stem)
        except Exception as e:
            report.append((stem, "SKIP", str(e)[:60], 0, 0, 0))
            continue
        P = ps["probes"]
        # Provenance is what makes the mix reportable rather than hidden.
        for p in P:
            p["provenance"]["allocator"] = alloc
            p["provenance"]["layout"] = layout
        n2 = sum(1 for p in P if p["derived"]["n_legal_pairs"] >= 2)
        n0 = sum(1 for p in P if p["derived"]["n_legal_pairs"] == 0)
        all_probes.extend(P)
        sources.append(stem)
        report.append((stem, alloc, layout, len(P), n2, n0))

    frozen = FROZEN if (args.frozen or not args.trails) else []
    for path, name, alloc, layout in frozen:
        try:
            ps = load(path)
        except Exception as e:
            report.append((name, "SKIP", str(e)[:60], 0, 0, 0))
            continue
        P = ps["probes"]
        for p in P:
            p["provenance"].setdefault("allocator", alloc)
            p["provenance"].setdefault("layout", layout)
            p["provenance"].setdefault("source", name)
        n2 = sum(1 for p in P if p["derived"]["n_legal_pairs"] >= 2)
        n0 = sum(1 for p in P if p["derived"]["n_legal_pairs"] == 0)
        all_probes.extend(P)
        sources.append(name)
        report.append((name, alloc, layout, len(P), n2, n0))

    for p in all_probes:
        p["derived"]["option_set_key"] = option_set_key(p)

    master = make_set(all_probes, sources=sources,
                      note="EX1+EX3 master, harvested 2026-08-14")
    h = save(master, args.out)

    print("=" * 68)
    print("HARVEST")
    print("=" * 68)
    print(f"{'source':22s} {'alloc':8s} {'layout':16s} "
          f"{'n':>4s} {'>=2':>4s} {'zero':>5s}")
    for row in report:
        print(f"{row[0]:22s} {row[1]:8s} {str(row[2])[:16]:16s} "
              f"{row[3]:>4d} {row[4]:>4d} {row[5]:>5d}")
    print(f"\nMASTER  {args.out}")
    print(f"  states {master['n']}  distinct option sets "
          f"{len({p['derived']['option_set_key'] for p in all_probes})}")
    print(f"  hash {h}")

    # ---- EX1: one state per option set, whole legality range kept ----
    ex1_probes = collapse(all_probes)
    ex1 = make_set(ex1_probes, sources=sources,
                   note=("EX1 information ladder. One state per option "
                         "set: legality is a property of the option set, "
                         "so duplicates would weight a rate by how long a "
                         "situation persisted. Zero-legal states are KEPT "
                         "as refusal probes, where declining is correct."))
    h1 = save(ex1, args.ex1)
    z1 = sum(1 for p in ex1_probes if p["derived"]["n_legal_pairs"] == 0)
    print(f"\nEX1  {args.ex1}")
    print(f"  states {len(ex1_probes)}  (refusal probes: {z1})")
    print(f"  hash {h1}")
    c = Counter()
    for p in ex1_probes:
        c.update(p["derived"].get("binding_causes", {}))
    print(f"  binding causes: {dict(c)}")

    # ---- EX3: real choice only, capped per source ----
    pool = select(master, min_legal=2,
                  note="EX3 judgement: two or more legal pairs")["probes"]
    per_src, ex3_probes = Counter(), []
    for p in sorted(pool, key=lambda q: -q["derived"]["n_legal_pairs"]):
        s = p["provenance"].get("source", "?")
        if per_src[s] >= args.cap_per_source:
            continue
        per_src[s] += 1
        ex3_probes.append(p)
    ex3 = make_set(ex3_probes, sources=sources,
                   note=(f"EX3 judgement on frozen states. min_legal=2: a "
                         f"state with one option scores every allocator "
                         f"alike. Capped at {args.cap_per_source} per "
                         f"source so no single layout dominates."))
    h3 = save(ex3, args.ex3)
    print(f"\nEX3  {args.ex3}")
    print(f"  states {len(ex3_probes)}  from pool of {len(pool)}")
    print(f"  per source: {dict(per_src)}")
    print(f"  hash {h3}")
    print("\nRecord these three hashes. A results table can then always "
          "name the exact states it was computed over.")


if __name__ == "__main__":
    main()