"""Refreeze a probe set with one or more harvest sources excluded.

WHY THIS EXISTS

harvest/frozen_coord.py rebuilds each object's capability spec FROM THE
SAVED STATE, and refuses to register an object twice with different
numbers. The registry is process-global, so a set containing two harvests
that disagree about one object cannot be replayed at all: whichever value
registers first wins and every probe carrying the other one raises. The
failure is order-dependent, which means it can look like a flaky run.

Found on ex1_v1: 23 probes from source probe_seed_v3 declare ycb_mustard
at grasp_m 0.058, while the other 162 declare 0.096. ycb_objects.py
records the reason at the mustard entry: the value was corrected on
2026-08-02 from 0.058 to 0.096, because the row had the UPRIGHT grasp
width sitting against the LYING rest_z and height, mixing two poses. The
23 were harvested before the correction.

The crash is the smaller half of the problem. On those states a Franka at
0.080 m is judged able to grasp a bottle that actually presents 0.096 m,
so the legality ground truth is wrong in precisely the dimension EX1
measures. They are excluded rather than repaired: rewriting a harvested
state would break the property that a probe is a replay of a decision
that really happened, which is what the byte-identity acceptance test
buys.

WHAT IT DOES NOT DO

It does not edit states, recompute derived fields, or re-harvest. It
selects whole sources, records the reason in the set's own note field so
the write-up can quote it, and lets probe_store.save recompute the hash.
Excluding a source is a decision about provenance, and provenance is the
one thing a frozen set should be filtered on.

Usage:

    python3 harvest/refreeze_probe_set.py --in probes/ex1_v1.json \\
        --out probes/ex1_v2.json --exclude-source probe_seed_v3 \\
        --reason "stale ycb_mustard grasp_m 0.058, corrected to 0.096 on
                  2026-08-02; states predate the fix"

    python3 harvest/refreeze_probe_set.py --in probes/ex1_v1.json --check
"""

import argparse
import collections
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from harvest.probe_store import load, save, content_hash    # noqa: E402

SPEC_FIELDS = ("grasp_m", "mass_kg", "delicate")


def spec_conflicts(probes):
    """Objects declared with more than one spec across the set.

    The general form of the defect. Returns

        {object: {(grasp_m, mass_kg, delicate): {source: count}}}

    for every object with more than one distinct spec. Empty means the set
    can be replayed in one process without a registry conflict.
    """
    seen = collections.defaultdict(lambda: collections.defaultdict(
        collections.Counter))
    for p in probes:
        src = (p.get("provenance") or {}).get("source")
        for ob in (p.get("state") or {}).get("objects", []):
            key = tuple(ob.get(f) for f in SPEC_FIELDS)
            seen[ob.get("name")][key][src] += 1
    return {name: {k: dict(v) for k, v in variants.items()}
            for name, variants in seen.items() if len(variants) > 1}


def census(probes):
    """Counts a reader needs to judge what an exclusion costs."""
    src = collections.Counter()
    any_pair = collections.Counter()
    pairs = collections.Counter()
    true_refusal = no_derived = 0
    for p in probes:
        src[(p.get("provenance") or {}).get("source")] += 1
        d = p.get("derived") or {}
        for c, n in (d.get("binding_causes") or {}).items():
            any_pair[c] += 1
            pairs[c] += n
        if d.get("n_rejected_pairs") is None:
            no_derived += 1
        elif d.get("n_legal_pairs", 0) == 0 and d["n_rejected_pairs"] > 0:
            # Options existed and none of them were legal. This is the
            # refusal probe. A state with NO options is a different thing
            # and must not be pooled with it: declining when there was
            # nothing to decline is not the behaviour being measured.
            true_refusal += 1
    return {"n": len(probes), "sources": dict(src),
            "true_refusal_probes": true_refusal,
            "probes_without_derived": no_derived,
            "binding_any_pair": dict(any_pair),
            "binding_pairs": dict(pairs)}


def _report(label, c):
    print(f"\n{label}")
    print(f"  n                      {c['n']}")
    print(f"  true refusal probes    {c['true_refusal_probes']}")
    print(f"  probes without derived {c['probes_without_derived']}")
    print(f"  sources                {c['sources']}")
    print(f"  binding, any pair      {c['binding_any_pair']}")
    print(f"  binding, pair totals   {c['binding_pairs']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", required=True, help="probe set JSON")
    ap.add_argument("--out", help="output path; omit with --check")
    ap.add_argument("--exclude-source", action="append", default=[],
                    help="harvest source to drop; repeatable")
    ap.add_argument("--reason", help="why, recorded in the set's note field")
    ap.add_argument("--check", action="store_true",
                    help="report conflicts and census, write nothing")
    args = ap.parse_args(argv)

    ps = load(args.src)
    probes = ps["probes"]
    print(f"{args.src}")
    print(f"  hash {ps.get('hash', '')[:16]}  n {len(probes)}")

    before = spec_conflicts(probes)
    print(f"\nSPEC CONFLICTS BEFORE: "
          f"{len(before)} object(s)" if before else
          "\nSPEC CONFLICTS BEFORE: none")
    for name, variants in before.items():
        print(f"  {name}")
        for spec, srcs in variants.items():
            print(f"    {dict(zip(SPEC_FIELDS, spec))}  {srcs}")

    _report("BEFORE", census(probes))

    if args.check:
        return 1 if before else 0

    if not args.exclude_source:
        ap.error("--exclude-source is required unless --check is given")
    if not args.out:
        ap.error("--out is required unless --check is given")
    if not args.reason:
        ap.error("--reason is required: an exclusion with no recorded "
                 "justification is indistinguishable from a mistake, and "
                 "this note is what the write-up quotes")
    if os.path.exists(args.out):
        raise ValueError(
            f"{args.out} already exists. A frozen set is never overwritten: "
            f"every row ever produced carries its hash, so replacing one "
            f"orphans those rows silently. Choose a new version.")

    drop = set(args.exclude_source)
    known = {(p.get("provenance") or {}).get("source") for p in probes}
    missing = drop - known
    if missing:
        raise ValueError(
            f"source(s) {sorted(missing)} are not in this set. Sources "
            f"present: {sorted(x for x in known if x)}. A typo here would "
            f"silently exclude nothing and produce a set that looks fixed.")

    kept = [p for p in probes
            if (p.get("provenance") or {}).get("source") not in drop]
    if not kept:
        raise ValueError("every probe was excluded")

    after = spec_conflicts(kept)
    print(f"\nSPEC CONFLICTS AFTER: "
          f"{len(after)} object(s)" if after else
          "\nSPEC CONFLICTS AFTER: none")
    for name, variants in after.items():
        print(f"  {name}")
        for spec, srcs in variants.items():
            print(f"    {dict(zip(SPEC_FIELDS, spec))}  {srcs}")

    _report("AFTER", census(kept))

    out = dict(ps)
    out["probes"] = kept
    out["sources"] = sorted({(p.get("provenance") or {}).get("source")
                             for p in kept} - {None})
    out["excluded_sources"] = sorted(drop)
    out["exclusion_reason"] = args.reason
    out["derived_from"] = {"path": args.src, "hash": ps.get("hash"),
                           "n": len(probes)}
    note = (ps.get("note") or "").strip()
    out["note"] = (note + " | " if note else "") + (
        f"refrozen from {os.path.basename(args.src)} "
        f"({len(probes)} -> {len(kept)}), excluded {sorted(drop)}: "
        f"{args.reason}")

    h = save(out, args.out)
    print(f"\nWROTE {args.out}")
    print(f"  hash {h}")
    print(f"  n    {len(kept)}")
    if after:
        print("\nWARNING: conflicts REMAIN. This set still cannot be "
              "replayed in one process.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
