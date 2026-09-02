#!/usr/bin/env python3
"""Build the EX1 v2 probe set: harvest serialised states, stratify, freeze.

WHY THIS IS NOT build_master_set.py WITH A FLAG.

build_master_set harvests once and selects twice, for EX1 and EX3, and its
EX1 selection is "one state per option set, keep everything". That was the
right selection for a contended cell, where which states you get is
whatever the episode happened to produce, and it is the wrong one here.
Serialising changes what a state IS, so v2 states cannot be pooled with v1
states under any selection, and the v2 endpoint needs a set built toward a
declared composition rather than accepted as harvested.

The v1 builder is therefore left alone. It still reproduces the frozen v1
sets byte for byte, and this file never writes to their paths.

WHAT THE COMPOSITION IS FOR.

The primary endpoint lives on GRASP-BINDING states: the states where at
least one idle arm is excluded because its gripper does not open wide
enough. Interval width there scales as one over the square root of that
count, not of the total. On the v1 set 96 of 162 states qualified, so
two thirds of every model call bought nothing for the headline number.

Grasp binds exactly when the object is wider than the Franka aperture
(0.080 m) and a Franka is otherwise eligible for it. Under the serialised
cell every arm is idle at every decision, so the second half is nearly
always true and the composition of the set follows directly from which
objects its queued tasks carry. Six of the eleven objects are wider than
0.080 m and five are not.

That gives the whole selection its shape:

  OVERSAMPLE THE SIX WIDE OBJECTS, to lift the grasp-binding count toward
        the target, and BALANCE ACROSS THEM, so no single object carries
        the endpoint. Without the balance, mustard alone could supply most
        of the grasp-binding states and the chapter's central number would
        be a fact about mustard.

  HOLD A FLOOR OF NON-GRASP STATES. This is the one property most at risk
        in the redesign, and it is not optional. States where the opening
        binds nothing, at 100 percent legality, are what localise the
        width effect to the opening: they are the control column, and
        without them the specificity claim becomes an assertion. Filtering
        toward the endpoint would remove exactly those states. The floor
        is declared here, before any model is called, and recorded in the
        set.

  HOLD A FLOOR OF ZERO-LEGAL STATES. Correct refusal is a second endpoint,
        scored on the states where no arm can take the queued task, and it
        has its own reference line. A set with none of them cannot report
        it at all.

        AND SERIALISING MAKES THESE MUCH RARER, which is worth knowing
        before the episodes are run rather than after. Under the contended
        cell a state was zero-legal whenever the arms that happened to be
        FREE could not take any open task, and with two arms working that
        was common: the v1 set carries 36 of them in 162. Serialised, a
        zero-legal state needs the one queued object to be unservable by
        ALL FOUR arms at once. No object in the cast is intrinsically
        unservable, since the URs cover every width and mass and the
        Frankas cover every delicate object, so the only routes to a
        refusal state left are geometric: an object no capable arm can
        reach, or one with no delivery route to any basket. Those states
        exist and the relay_heavy and capability_trap layouts produce them,
        but they have to be harvested deliberately. If the floor cannot be
        met, harvest those layouts rather than dropping the endpoint: a
        correct-refusal rate with no refusal states is not a weaker
        measurement, it is no measurement.

WHAT IS CHECKED BEFORE ANYTHING IS WRITTEN.

  Every state is serialised: one queued task, every non-disabled arm idle.
  A set harvested from a contended cell renders perfectly well under the
  v2 prompt and would be reported under a serialised label, understating
  how often the opening can bind. This is the one failure that cannot be
  left to inspection, so it raises.

  One object cast. The two casts are disjoint and a set mixing them
  describes neither. build_master_set records having produced exactly that
  once, 21 distinct objects from both casts in one set.

  The floors are met. If the pool cannot meet a declared floor the build
  FAILS and says what is missing, rather than quietly writing a set whose
  composition does not match the numbers recorded beside it. Harvest more
  episodes; selection is the cheap part.

DETERMINISM. Selection is a seeded shuffle inside each object bucket, and
the seed is recorded. The same pool and the same seed give the same set,
so the hash is reproducible from the trails.

WHAT HAPPENS NEXT, AND IN THIS ORDER. The reference lines are recomputed on
the set this writes, before any model is called:

    python3 analysis/ex1/ex1_chance_floor.py --probes probes/ex1_v2_serial.json \\
        --out out/ex1_v2_chance_floor.json

Usage:
    python3 analysis/build_ex1_set_v2.py --dry-run \\
        --trails ser_rich:random:decision_rich
    python3 analysis/build_ex1_set_v2.py \\
        --trails ser_rich:random:decision_rich \\
        --trails ser_wide:random:capability_trap \\
        --n 200 --out probes/ex1_v2_serial.json
"""

import argparse
import collections
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.build_master_set import collapse, option_set_key   # noqa: E402
from analysis.probe_store import (harvest_trail, legal_options,  # noqa: E402
                                  load, make_set, save)
from core.cell import cell_config as C                            # noqa: E402
from experiments.ex1 import prompts_v2 as EX1P2                   # noqa: E402

# The aperture that decides whether the opening can bind at all. Read from
# the arm tables, so a change there moves the stratifier with it.
FRANKA_APERTURE = C.ARM_TYPES["franka"]["max_grasp_m"]

# Defaults, all declared here so a run that changes one has to say so on
# the command line and the change lands in the set's own record.
#
# GRASP_TARGET 0.80. The redesign's estimate: serialising should lift the
# grasp-binding share from the v1 set's 59 percent to around 80. At 200
# states that is about 160 grasp-binding states against the 96 the chapter
# currently reports, which narrows the null intervals by roughly a quarter.
# It is a target, not a promise: the achieved share is recomputed from the
# selected states and reported beside it.
GRASP_TARGET = 0.80
# NONGRASP_FLOOR 0.15. The negative control. At 200 states that is 30
# states where the opening binds nothing, which is enough for the control
# column of the specificity table to carry an interval rather than a point.
NONGRASP_FLOOR = 0.15
# REFUSAL_FLOOR 0.08. The v1 set carried 36 refusal states in 162, about 22
# percent, which is more than the endpoint needs. Eight percent of 200 is
# 16 states, enough to report a correct-refusal rate against the floor.
REFUSAL_FLOOR = 0.08


# ---------------------------------------------------------------------------
# Reading a state
# ---------------------------------------------------------------------------

def queued_tasks(state):
    """The tasks the allocator is being offered on this state."""
    return [t for t in state.get("tasks", [])
            if str(t.get("status", "")).startswith("queued")]


def queued_object(probe):
    """The object of the one queued task, or None.

    Serialised states carry exactly one, which is what makes an object the
    stratifier's unit. assert_states_are_serialised has already refused
    anything else by the time this is called.
    """
    q = queued_tasks(probe["state"])
    if len(q) != 1:
        return None
    return q[0].get("object") or q[0].get("obj")


def object_width(probe, obj):
    """The declared opening for an object, read from the STATE.

    Not from cell_config.OBJECT_SPECS. That table is populated when the
    SCENE is built, so an offline process that builds no scene finds every
    YCB object missing and falls back to a small cube. frozen_coord records
    the same trap costing a 0.122 m clamp its rejection. The state records
    the property as it was at that tick, which is also the right source
    when a frozen set outlives a registry edit.
    """
    for o in probe["state"].get("objects", []):
        if (o.get("name") or o.get("object")) == obj:
            return o.get("grasp_m")
    return None


def widths_in(probes):
    """object -> declared opening, over a list of probes."""
    out = {}
    for p in probes:
        for o in p["state"].get("objects", []):
            n = o.get("name") or o.get("object")
            if n and o.get("grasp_m") is not None:
                out.setdefault(n, o["grasp_m"])
    return out


def binds_grasp(probe):
    """True when the opening excludes at least one arm on this state.

    Read from the probe's own derived block, which probe_store computed
    with the same decomposition the validator uses, rather than recomputed
    here. Two implementations of the same predicate is how a selection and
    a results table come to disagree about what a stratum is.
    """
    return (probe.get("derived", {}).get("binding_causes", {})
            .get("grasp", 0) > 0)


def is_refusal(probe):
    """True when no legal (task, arm) pair exists: declining is correct."""
    return probe.get("derived", {}).get("n_legal_pairs", 0) == 0


def verify_derived(probes, sample=None):
    """The stored legality counts still describe the stored states.

    THE STRATIFIER READS derived.binding_causes AND NOTHING ELSE, so a
    derived block that no longer matches its state would build a set whose
    composition is a fiction, and every number recorded beside it would be
    wrong in a way nothing downstream could see. ex1_chance_floor.py runs
    the same check before it prints a reference line, for the same reason.

    The usual cause is a state edited after harvest without re-deriving.
    Re-harvest rather than patch: the derived block is computed by
    probe_store from the state, so the state is the thing to fix.
    """
    probes = probes[:sample] if sample else probes
    for p in probes:
        pairs, _per_task, causes = legal_options(p, with_causes=True)
        stored = p.get("derived", {}).get("n_legal_pairs")
        if stored is not None and stored != len(pairs):
            raise ValueError(
                f"seq {p['provenance'].get('seq')}: recomputed {len(pairs)} "
                f"legal pairs but the state stores {stored}. The derived "
                f"block does not describe this state, and the stratifier "
                f"reads it, so the set's composition would be a fiction. "
                f"Re-harvest the trail rather than patching the block.")
    return len(probes)


def cast_of(probes):
    """Every object named by any state, for the one-cast check."""
    names = set()
    for p in probes:
        for o in p["state"].get("objects", []):
            n = o.get("name") or o.get("object")
            if n:
                names.add(n)
    return names


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def stratify(pool, n, grasp_target=GRASP_TARGET, nongrasp_floor=NONGRASP_FLOOR,
             refusal_floor=REFUSAL_FLOOR, seed=0):
    """Choose n states toward the declared composition.

    Returns (selected, report). Raises when a floor cannot be met, because
    a set whose composition does not match the numbers recorded beside it
    is worse than no set.

    THE ORDER OF THE THREE DEMANDS MATTERS. The floors are filled FIRST,
    from their own strata, and the grasp target takes what is left. A
    target that ate into a floor would remove the control the endpoint is
    read against, and the endpoint is the thing that would then look best.
    """
    rng = random.Random(seed)

    refusal = [p for p in pool if is_refusal(p)]
    picking = [p for p in pool if not is_refusal(p)]
    grasp = [p for p in picking if binds_grasp(p)]
    nongrasp = [p for p in picking if not binds_grasp(p)]

    n_refusal = int(round(refusal_floor * n))
    n_nongrasp = int(round(nongrasp_floor * n))
    n_grasp = n - n_refusal - n_nongrasp

    want_grasp = int(round(grasp_target * n))
    if n_grasp > want_grasp:
        # The floors leave room for more grasp-binding states than the
        # target asks for. Spend the surplus on the negative control rather
        # than on the endpoint: the control is the scarcer thing and the
        # target is a target.
        n_nongrasp += n_grasp - want_grasp
        n_grasp = want_grasp

    short = []
    if len(refusal) < n_refusal:
        short.append(f"refusal states: have {len(refusal)}, need {n_refusal}")
    if len(nongrasp) < n_nongrasp:
        short.append(f"non-grasp states: have {len(nongrasp)}, "
                     f"need {n_nongrasp}")
    if len(grasp) < n_grasp:
        short.append(f"grasp-binding states: have {len(grasp)}, "
                     f"need {n_grasp}")
    if short:
        raise ValueError(
            "the pool cannot meet the declared composition:\n    "
            + "\n    ".join(short)
            + "\n  Harvest more serialised episodes rather than lowering a "
              "floor after seeing the pool. Selection is the cheap part, and "
              "a floor chosen to fit the data it is applied to is not a "
              "floor. The capability_trap and decision_rich layouts are the "
              "ones that produce wide-object states.")

    selected = (_balanced(grasp, n_grasp, rng)
                + _balanced(nongrasp, n_nongrasp, rng)
                + _balanced(refusal, n_refusal, rng))

    report = {
        "n_requested": n,
        "pool": {"total": len(pool), "grasp": len(grasp),
                 "nongrasp": len(nongrasp), "refusal": len(refusal)},
        "targets": {"grasp_target": grasp_target,
                    "nongrasp_floor": nongrasp_floor,
                    "refusal_floor": refusal_floor,
                    "n_grasp": n_grasp, "n_nongrasp": n_nongrasp,
                    "n_refusal": n_refusal},
        "seed": seed,
    }
    return selected, report


def _balanced(probes, k, rng):
    """k states from `probes`, spread as evenly as possible over objects.

    Round robin over the object buckets, each bucket shuffled first. This
    is what stops one object supplying most of a stratum: without it the
    endpoint could be a fact about whichever object the episodes happened
    to queue most often, and nothing in the output would show it.
    """
    if k <= 0:
        return []
    buckets = collections.defaultdict(list)
    for p in probes:
        buckets[queued_object(p) or "?"].append(p)
    for key in buckets:
        # Sorted before shuffling so the shuffle is the only source of
        # order and the seed fully determines the result. Harvest order
        # depends on the filesystem, and a set whose hash moved with it
        # would not be reproducible from the trails.
        buckets[key].sort(key=lambda p: str(p["provenance"].get("seq")))
        rng.shuffle(buckets[key])
    out, keys = [], sorted(buckets)
    while len(out) < k:
        took = False
        for key in keys:
            if buckets[key] and len(out) < k:
                out.append(buckets[key].pop())
                took = True
        if not took:
            break
    return out


def composition(probes):
    """The achieved composition, recomputed from the selected states."""
    n = len(probes)
    refusal = [p for p in probes if is_refusal(p)]
    picking = [p for p in probes if not is_refusal(p)]
    # GRASP-BINDING IS COUNTED AMONG PICKING STATES, not among all of them.
    # Legality is scored on trials where the model PROPOSED something, so
    # the endpoint's denominator is the picking states, and a zero-legal
    # state that happens to bind the opening belongs to the refusal
    # endpoint instead. Counting it in both would make the three shares sum
    # past 100 and would overstate how much the set buys the headline.
    grasp = [p for p in picking if binds_grasp(p)]
    nongrasp = [p for p in picking if not binds_grasp(p)]
    by_object = collections.Counter(queued_object(p) or "?" for p in probes)
    widths = widths_in(probes)
    wide = {o for o in by_object
            if (widths.get(o) or 0) > FRANKA_APERTURE}
    causes = collections.Counter()
    for p in probes:
        causes.update(p.get("derived", {}).get("binding_causes", {}))
    return {
        "n": n,
        "n_grasp_binding": len(grasp),
        "n_nongrasp_picking": len(nongrasp),
        "n_refusal": len(refusal),
        "n_picking": len(picking),
        # Also carried, because the refusal reference line is computed per
        # binding cause too and needs the count over the whole set.
        "n_grasp_binding_any": sum(1 for p in probes if binds_grasp(p)),
        "grasp_binding_share": (len(grasp) / n) if n else None,
        "nongrasp_share": (len(nongrasp) / n) if n else None,
        "refusal_share": (len(refusal) / n) if n else None,
        "queued_objects": dict(sorted(by_object.items())),
        "n_wide_objects_used": len(wide),
        "queued_object_widths": {o: widths.get(o) for o in sorted(by_object)},
        "binding_causes": dict(sorted(causes.items())),
        "franka_aperture_m": FRANKA_APERTURE,
    }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def gather(trails, frozen_paths=()):
    """Harvest the named trails into one pool, with provenance attached."""
    probes, sources, report = [], [], []
    for stem, alloc, layout in trails:
        path = f"out/{stem}_frames/consults.jsonl"
        try:
            ps = harvest_trail(path, source=stem)
        except Exception as e:                            # noqa: BLE001
            report.append((stem, "SKIP", str(e)[:120], 0, 0, 0))
            continue
        P = ps["probes"]
        for p in P:
            p["provenance"]["allocator"] = alloc
            p["provenance"]["layout"] = layout
            p["provenance"]["serialised"] = True
        probes.extend(P)
        sources.append(stem)
        report.append((stem, alloc, layout, len(P),
                       sum(1 for p in P if binds_grasp(p)),
                       sum(1 for p in P if is_refusal(p))))
    for path in frozen_paths:
        ps = load(path)
        P = ps["probes"]
        probes.extend(P)
        sources.append(os.path.basename(path))
        report.append((os.path.basename(path), "frozen", "-", len(P),
                       sum(1 for p in P if binds_grasp(p)),
                       sum(1 for p in P if is_refusal(p))))
    return probes, sources, report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--trails", action="append", metavar="STEM:ALLOC:LAYOUT",
                    default=None, required=False,
                    help="a harvested serialised trail, repeatable. Reads "
                         "out/STEM_frames/consults.jsonl. The allocator and "
                         "layout are recorded as provenance on every state, "
                         "so guessing them would mislabel the set")
    ap.add_argument("--pool", default=None,
                    help="an already-frozen set to select from instead of, "
                         "or as well as, harvesting trails")
    ap.add_argument("--out", default="probes/ex1_v2_serial.json")
    ap.add_argument("--n", type=int, default=200,
                    help="total states. Pick it from the grasp-binding "
                         "count you want, not from the total: 200 at an 80 "
                         "percent share gives about 160 grasp-binding "
                         "states against the 96 the v1 chapter reports")
    ap.add_argument("--grasp-target", type=float, default=GRASP_TARGET)
    ap.add_argument("--nongrasp-floor", type=float, default=NONGRASP_FLOOR,
                    help="minimum share of states where the opening binds "
                         "nothing. THE NEGATIVE CONTROL: without it the "
                         "specificity claim has no control column")
    ap.add_argument("--refusal-floor", type=float, default=REFUSAL_FLOOR,
                    help="minimum share of zero-legal states, where "
                         "declining is the correct answer")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-collapse", action="store_true",
                    help="keep every harvested record instead of one per "
                         "option set. Only for diagnosing a thin pool: "
                         "duplicates weight a rate by how long a situation "
                         "persisted")
    ap.add_argument("--allow-contended", action="store_true",
                    help="skip the serialisation check. For inspecting a "
                         "pre-v2 pool only; a set built this way must never "
                         "be reported as v2")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the pool and the composition it could "
                         "reach, and write nothing")
    args = ap.parse_args(argv)

    trails = []
    for t in (args.trails or []):
        parts = t.split(":")
        if len(parts) != 3:
            raise SystemExit(f"--trails {t!r}: expected STEM:ALLOC:LAYOUT")
        trails.append(tuple(parts))
    if not trails and not args.pool:
        raise SystemExit("nothing to build from: give --trails or --pool")

    probes, sources, report = gather(trails,
                                     [args.pool] if args.pool else [])

    # The table is printed BEFORE the empty check. A trail that failed to
    # harvest carries its reason in this table, and bailing first hid it:
    # the message said "check the trail paths" when the real cause was a
    # record missing positions_exact.
    print("=" * 70)
    print("HARVEST")
    print("=" * 70)
    print(f"{'source':22s} {'alloc':8s} {'layout':16s} "
          f"{'n':>4s} {'grasp':>6s} {'zero':>5s}")
    for row in report:
        layout = str(row[2])
        print(f"{row[0]:22s} {str(row[1]):8s} {layout[:16]:16s} "
              f"{row[3]:>4d} {row[4]:>6d} {row[5]:>5d}")
        if row[1] == "SKIP":
            print(f"    {layout}")

    if not probes:
        raise SystemExit(
            "\nno states harvested. Every source above is marked SKIP with "
            "its reason; a missing file and a malformed record fail "
            "differently and the reason says which.")

    if not args.allow_contended:
        EX1P2.assert_states_are_serialised(probes)
        print("\n  serialisation check PASSED on all "
              f"{len(probes)} harvested states")
    else:
        print("\n  serialisation check SKIPPED (--allow-contended). This set "
              "must not be reported as v2.")

    verify_derived(probes)
    print(f"  derived-block check PASSED on all {len(probes)} states")

    cast = cast_of(probes)
    print(f"  distinct objects in the pool: {len(cast)}")
    if len(cast) > 12:
        raise SystemExit(
            f"the pool names {len(cast)} distinct objects, which is more "
            f"than one cast: {sorted(cast)}. The casts are disjoint and a "
            f"set mixing them describes neither. Build one set per cast.")

    for p in probes:
        p["derived"]["option_set_key"] = option_set_key(p)
    pool = probes if args.no_collapse else collapse(probes)
    print(f"  pool after collapse: {len(pool)} states "
          f"(from {len(probes)} records)")

    before = composition(pool)
    print(f"\n  POOL COMPOSITION  grasp-binding "
          f"{100 * (before['grasp_binding_share'] or 0):.1f}%   "
          f"non-grasp {100 * (before['nongrasp_share'] or 0):.1f}%   "
          f"refusal {100 * (before['refusal_share'] or 0):.1f}%")

    selected, sel_report = stratify(
        pool, args.n, grasp_target=args.grasp_target,
        nongrasp_floor=args.nongrasp_floor,
        refusal_floor=args.refusal_floor, seed=args.seed)
    after = composition(selected)

    print("\n" + "=" * 70)
    print("SELECTION")
    print("=" * 70)
    t = sel_report["targets"]
    print(f"  asked for {sel_report['n_requested']} states: "
          f"{t['n_grasp']} grasp-binding, {t['n_nongrasp']} non-grasp, "
          f"{t['n_refusal']} refusal   (seed {sel_report['seed']})")
    print(f"  got {after['n']}: {after['n_grasp_binding']} grasp-binding "
          f"({100 * after['grasp_binding_share']:.1f}%), "
          f"{after['n_nongrasp_picking']} non-grasp "
          f"({100 * after['nongrasp_share']:.1f}%), "
          f"{after['n_refusal']} refusal "
          f"({100 * after['refusal_share']:.1f}%)")
    print(f"\n  {'queued object':18s} {'states':>6s} {'opening':>8s}")
    for obj, k in after["queued_objects"].items():
        w = after["queued_object_widths"].get(obj)
        wide = "  wide" if (w or 0) > FRANKA_APERTURE else ""
        print(f"  {obj:18s} {k:6d} "
              f"{('%8.3f' % w) if w is not None else '       -'}{wide}")
    print(f"\n  binding causes: {after['binding_causes']}")

    if args.dry_run:
        print("\nDRY RUN: nothing written.")
        return 0

    out = make_set(selected, sources=sources,
                   note=("EX1 v2, serialised cell. One task at a time in "
                         "pool order, every arm idle at every decision. "
                         "Stratified toward grasp-binding states with a "
                         "declared floor of non-grasp states (the negative "
                         "control) and of zero-legal states (the refusal "
                         "endpoint). Composition targets were set before "
                         "any model call and are recorded in this file."))
    # The record that makes the set reproducible and its composition
    # auditable without recomputing anything.
    out["selection"] = {
        "design": "v2",
        "serialised": True,
        "builder": os.path.basename(__file__),
        "ex1_v2_prompt_version": EX1P2.EX1_V2_PROMPT_VERSION,
        "pool": sel_report["pool"],
        "targets": sel_report["targets"],
        "seed": sel_report["seed"],
        "collapsed": not args.no_collapse,
        "achieved": after,
    }
    h = save(out, args.out)
    print(f"\nWROTE {args.out}")
    print(f"  states {out['n']}  hash {h}")
    print("\nNEXT, before any model call:")
    print(f"  python3 analysis/ex1/ex1_chance_floor.py --probes {args.out} \\")
    print("      --out out/ex1_v2_chance_floor.json")
    print("The chance floor and the width-blind line do not transfer from "
          "the v1 set:\nserialising changes the arms surviving every "
          "non-grasp check on every state,\nand the width-blind line is "
          "defined against exactly that count.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
