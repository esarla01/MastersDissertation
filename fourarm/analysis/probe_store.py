"""Probe sets: frozen decision states, versioned and content-hashed.

A probe set is the raw material for EX1, EX2 and EX3. Each record is one
decision point lifted out of an episode's audit trail, carrying everything
needed to re-render the prompt at any rung and re-run the real validator
offline: the state dict, exact object positions, the camera frame, and the
provenance of where it came from.

WHY A CONTENT HASH. Every model experiment is a comparison across rungs,
prompt levels and models over ONE probe set. If the set changes between
runs, the comparison silently stops being paired and nothing in the output
would show it. save() writes the hash, load() recomputes and refuses a set
whose contents no longer match. The hash covers state, positions and
provenance, not the derived counts, so recomputing a metric never
invalidates a frozen set.

WHY LEGAL-OPTION COUNTS ARE COMPUTED AT HARVEST. The 2026-08-01 seed
episode ended 20 noops out of 33 consults, and reading the model's reasons
showed it was right almost every time: for most of those rounds NO legal
assignment existed at all. A state with zero legal options carries no
information about competence, and one with a single option carries very
little, because every allocator scores identically on it. Counting at
harvest turns that from a confound discovered during analysis into a
stratification variable declared in advance. Filtering happens at
selection, never silently: a set records what it excluded and why.

The counts come from the REAL validator over the frozen coordinator, not
from a reimplemented rule. That is slower than a bespoke check and it is
the point: whatever the validator would accept live is what gets counted.

Usage:

    from analysis.probe_store import harvest_trail, save, load, select
    ps = harvest_trail("out/probe_seed_v2_frames/consults.jsonl",
                       source="probe_seed_v2")
    save(ps, "probes/seed_v2.json")
    ps = load("probes/seed_v2.json")
    hard = select(ps, min_legal=2)
"""

import copy
import hashlib
import json
import os
import sys

from core.cell import cell_config as C
from core.cell.zones import ZoneMap
from core.decision.vlm_allocator import validate_decision
from analysis.frozen_coord import from_record, idle_arms

SCHEMA = 1

# Fields that define a probe's IDENTITY. Derived counts are excluded on
# purpose: adding a metric must not invalidate a frozen set.
_HASHED = ("state", "positions_exact", "provenance")

_ZM = None


def _zonemap():
    global _ZM
    if _ZM is None:
        _ZM = ZoneMap()
    return _ZM


def _baskets():
    """The basket table, imported lazily and self-sufficiently.

    ycb_scene is Isaac-free but lives under fourarm/ycb/, which is only on
    sys.path when the caller happens to have put it there. Harnesses do;
    a plain `python3 -c` from fourarm/ does not, and relying on the caller
    is how this module raised ModuleNotFoundError on its first real use.
    The path is derived from THIS file so it holds wherever it is invoked
    from.
    """
    ycb_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "ycb")
    if ycb_dir not in sys.path:
        sys.path.insert(0, ycb_dir)
    from ycb_scene import BASKETS
    return BASKETS


def content_hash(probes):
    """Stable hash over the identity fields of every probe, in order."""
    payload = [{k: p.get(k) for k in _HASHED} for p in probes]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def legal_options(record, baskets=None, with_causes=False):
    """Every (task, arm) the REAL validator would accept on this state.

    Returns (pairs, per_task) where pairs is a list of
    (task_id, arm, kind) with kind "direct" or "relay", and per_task maps
    task_id to {"n", "direct", "relay"}.

    The direct/relay split matters because Option 2 made an arm that can
    pick an object but not deliver it into a LEGAL proposal, with the
    router building the handover behind it. That is most of why this cell
    went from almost no allocation choice to a real one, so a legality
    number reported without the split cannot be read: it conflates "the
    model found a deliverer" with "the model found a picker and the cell
    rescued it". A task with BOTH kinds available is a judgement point,
    since the direct arm costs one trip and the relay costs two, and that
    is what avoidable_relay measures live.

    A fresh frozen coordinator is built per decision because
    validate_decision persists task.dest on success by design, so a reused
    coordinator would let an earlier accepted basket choice change the
    verdict of a later one.
    """
    baskets = baskets or _baskets()
    zm = _zonemap()
    probe_coord = from_record(record)
    arms = idle_arms(probe_coord)
    open_tasks = [t.id for t in probe_coord.pool
                  if not t.claimed and t.waiting_on is None]
    # For a task with no destination the basket is the model's choice, so
    # an arm counts as legal if ANY basket makes it legal. Trying only the
    # object's own category basket would undercount, and undercounting here
    # would quietly mark decision-rich states as trivial.
    names = list(baskets)

    pairs, per_task, causes = [], {}, []
    for tid in open_tasks:
        counts = {"n": 0, "direct": 0, "relay": 0}
        for a in arms:
            kind = None
            last_why = None
            probe = from_record(record)
            t = next(x for x in probe.pool if x.id == tid)
            candidates = [None] if t.dest is not None else names
            for b in candidates:
                fresh = from_record(record)
                ok, _, sub, why = validate_decision(
                    {"task_id": tid, "arm": a, "basket": b},
                    fresh, zm, baskets)
                if not ok:
                    # The LAST rejection is kept, not the first. With a
                    # dest-free task every basket is tried, and a pair is
                    # only illegal if every one of them failed, so any
                    # single attempt's reason is representative; keeping
                    # one costs nothing and avoids a list per pair.
                    last_why = why
                if ok:
                    # A returned subtask means the router inserted a pad
                    # leg, so this arm cannot deliver on its own.
                    kind = "relay" if sub is not None else "direct"
                    if kind == "direct":
                        break        # prefer the cheaper reading of an arm
            if kind is not None:
                counts["n"] += 1
                counts[kind] += 1
                pairs.append((tid, a, kind))
            elif with_causes:
                # An idle arm the validator would not accept for this task.
                # Capability is decomposed into its three sub-limits;
                # everything else is read off the reason string, which is
                # the validator's own wording and so cannot drift from it.
                obj = next((x.obj for x in probe.pool if x.id == tid), None)
                cause = capability_cause(a, obj)
                if cause is None:
                    w = (last_why or "").lower()
                    if "cannot reach the object" in w:
                        cause = "reach"
                    elif "no handover route" in w:
                        cause = "no_route"
                    elif "cannot grasp" in w:
                        # The validator says CAPABILITY but the three
                        # sub-checks all passed. That is a real
                        # disagreement between this module and
                        # cell_config, not a classification gap, so it is
                        # labelled rather than silently bucketed.
                        cause = "capability_unsplit"
                    else:
                        cause = "other"
                causes.append((tid, a, cause))
        per_task[tid] = counts
    if with_causes:
        return pairs, per_task, causes
    return pairs, per_task


def capability_cause(arm_name, obj_name):
    """Which of the three capability limits excludes this arm, or None.

    can_grasp folds size, mass and delicacy into ONE boolean and the
    validator reports all three as a single CAPABILITY code, so a rejection
    tally built from reason strings alone cannot say whether the cell's
    capability constraint is really a grasp-span constraint wearing two
    other hats. EX1 needs that split: a lookup-style limit (mass under a
    payload figure, a delicate flag) and a derived one (the width the
    object presents, which EX2 showed is where every interesting failure
    lives) are different cognitive demands, and reporting them pooled would
    hide the contrast.

    This reads the SAME tables can_grasp reads and applies the same
    comparisons in the same order, so it can only ever disagree with the
    validator if cell_config changes underneath both. It decomposes a
    conjunction; it does not restate a policy. Returns the FIRST binding
    limit, matching can_grasp's own short-circuit order.
    """
    try:
        t = C.ARM_TYPES[C.ARMS[arm_name]["type"]]
        spec = C.OBJECT_SPECS.get(obj_name, C.OBJECT_SPECS["_default"])
    except (KeyError, TypeError):
        return None
    if spec.get("delicate", False) and not t["delicate_ok"]:
        return "delicate"
    if spec["grasp_m"] > t["max_grasp_m"]:
        return "grasp"
    if spec["mass_kg"] > t["payload_kg"]:
        return "payload"
    return None


def probe_from_consult(rec, source, frames_dir=None, baskets=None):
    """One consults.jsonl record into one probe."""
    frame = rec.get("image_file")
    frame_path = (os.path.join(frames_dir, frame)
                  if frame and frames_dir else None)
    if frame_path and not os.path.exists(frame_path):
        raise ValueError(
            f"consult seq {rec.get('seq')} names frame {frame!r} but "
            f"{frame_path} does not exist. A missing frame must fail loudly: "
            f"replaying it as text-only would silently turn condition V into "
            f"condition A.")

    probe = {
        "state": rec["state"],
        "positions_exact": rec.get("positions_exact"),
        "frame": frame,
        "frame_path": frame_path,
        # EVERY viewpoint saved for this consult, camera name -> filename.
        # frame stays the one the model was SENT, so nothing that reads it
        # changes. EX2 had to validate a viewpoint against a specific
        # visual requirement and the two cameras fail in opposite ways
        # (table_cam cannot resolve pose; ex2_cam occludes the region
        # between the Frankas), so which view an image condition should use
        # is decided per experiment at replay time. Harvesting both is what
        # makes that decision reversible without re-running Isaac.
        "frames": rec.get("frames") or ({"primary": frame} if frame else {}),
        "provenance": {
            "source": source,
            "seq": rec.get("seq"),
            "round": rec.get("round"),
            "condition": rec.get("condition"),
            "prompt_version": rec.get("prompt_version"),
            "enriched": rec.get("enriched"),
            "eligible": rec.get("eligible"),
            "model": (rec.get("model") or {}).get("model"),
            "model_alias": (rec.get("model") or {}).get("alias"),
        },
    }
    pairs, per_task, causes = legal_options(probe, baskets, with_causes=True)
    st = probe["state"]
    open_ids = set(per_task)
    with_dest = sum(1 for t in st.get("tasks", [])
                    if t["id"] in open_ids and t.get("dest_xy") is not None)
    probe["derived"] = {
        "n_legal_pairs": len(pairs),
        "n_legal_direct": sum(1 for p in pairs if p[2] == "direct"),
        "n_legal_relay": sum(1 for p in pairs if p[2] == "relay"),
        "legal_pairs": [list(p) for p in pairs],
        "legal_per_task": {str(k): v["n"] for k, v in per_task.items()},
        "legal_per_task_direct": {str(k): v["direct"]
                                  for k, v in per_task.items()},
        "legal_per_task_relay": {str(k): v["relay"]
                                 for k, v in per_task.items()},
        "n_tasks_open": len(per_task),
        "n_tasks_with_choice": sum(1 for v in per_task.values()
                                   if v["n"] >= 2),
        # Tasks offering BOTH a one-trip and a two-trip arm: the states
        # where preferring the direct arm is a real judgement rather than
        # the only option.
        "n_tasks_direct_and_relay": sum(
            1 for v in per_task.values() if v["direct"] and v["relay"]),
        # R5 only binds once a destination is FIXED. While a task is
        # destination-free the model picks the basket under R7, and in this
        # cell some basket is always routable, so the destination
        # constraint imposes nothing. A probe set drawn only from round 1
        # would therefore make R5 look inert when it is not: the live
        # episode produced two NO_ROUTE rejections.
        "n_tasks_with_dest": with_dest,
        "n_tasks_dest_free": len(per_task) - with_dest,
        "n_idle_arms": sum(1 for a in st.get("arms", [])
                           if a.get("state") == "IDLE"
                           and not a.get("disabled")),
        "n_objects": len(st.get("objects", [])),
        # WHY the idle arms that were excluded were excluded, tallied over
        # every rejected (task, idle arm) pair. EX1's ladder asks what the
        # model still knows as capability information is removed from the
        # prompt, and that question is only answerable per constraint type:
        # a payload figure is a lookup, the presented grasp width is a
        # derivation, and ViPlan's finding that derived predicates degrade
        # far faster than direct ones predicts they should separate. This
        # is also the census variable: quotas per cause can only be set
        # once it is known which causes this cell actually produces, and
        # the object registry suggests some may be near-absent.
        "binding_causes": {c: sum(1 for x in causes if x[2] == c)
                           for c in sorted({x[2] for x in causes})},
        "n_rejected_pairs": len(causes),
        # The cause that binds MOST on this state, for stratified
        # selection. None when every idle arm was legal for every task.
        "binding_cause": (max({c: sum(1 for x in causes if x[2] == c)
                               for c in {x[2] for x in causes}}.items(),
                              key=lambda kv: (kv[1], kv[0]))[0]
                          if causes else None),
    }
    return probe


def harvest_trail(path, source=None, baskets=None):
    """Build a probe set from one episode's consults.jsonl."""
    if not os.path.exists(path):
        raise ValueError(f"no such trail: {path}")
    frames_dir = os.path.dirname(os.path.abspath(path))
    source = source or os.path.basename(frames_dir)
    probes = []
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "state" not in rec:
                raise ValueError(
                    f"{path} line {i} has no 'state'. Trails written before "
                    f"2026-08-01 cannot be replayed; re-run the episode.")
            probes.append(probe_from_consult(rec, source, frames_dir,
                                             baskets))
    _tag_round_position(probes)
    return make_set(probes, sources=[source])


def _tag_round_position(probes):
    """Index each probe within its allocation round.

    The allocator consults once per idle arm per round, so an episode's
    OPENING round contributes one consult per arm (four, in a four-arm
    cell) while later rounds contribute one or two as arms free up. Those
    opening consults are not duplicates, since each sees one fewer idle arm
    and one fewer open task than the last, but they are not independent
    either: the second decision's option set is a consequence of the first.

    Two things follow, and both need the position recorded rather than
    inferred later. Every episode contributes a full opening round, so any
    harvest over-represents states with a full task pool and every arm
    free. And EX3's scarcity question reads differently mid-round, where
    the scarce arm may already have been consumed, than it does at round
    start. Recorded here, so selection can balance or filter on it without
    a re-harvest.
    """
    seen = {}
    for p in probes:
        r = p["provenance"].get("round")
        seen[r] = seen.get(r, 0) + 1
        p["derived"]["round_position"] = seen[r]
        p["derived"]["is_round_opening"] = (seen[r] == 1)
    for p in probes:
        p["derived"]["round_size"] = seen[p["provenance"].get("round")]


def make_set(probes, sources=(), note=""):
    return {"schema": SCHEMA,
            "sources": list(sources),
            "note": note,
            "n": len(probes),
            "hash": content_hash(probes),
            "probes": probes}


def save(probe_set, path):
    probe_set = dict(probe_set)
    probe_set["hash"] = content_hash(probe_set["probes"])
    probe_set["n"] = len(probe_set["probes"])
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w") as f:
        json.dump(probe_set, f, indent=1, default=str)
    return probe_set["hash"]


def load(path, verify=True):
    """Load a probe set and refuse it if the contents no longer match.

    A silently mutated set turns a paired comparison into an unpaired one
    with nothing in the output to show it, which is the single worst
    failure this module can have.
    """
    with open(path) as f:
        ps = json.load(f)
    if ps.get("schema") != SCHEMA:
        raise ValueError(f"{path}: schema {ps.get('schema')}, expected "
                         f"{SCHEMA}")
    if verify:
        got = content_hash(ps["probes"])
        if got != ps.get("hash"):
            raise ValueError(
                f"{path}: content hash mismatch. Recorded {ps.get('hash')}, "
                f"recomputed {got}. This set has changed since it was frozen; "
                f"do not compare results across it.")
    return ps


def select(probe_set, min_legal=0, max_legal=None, require_choice=False,
           condition=None, require_direct_vs_relay=False,
           require_fixed_dest=False, note=""):
    """A filtered subset, recording what was dropped and why.

    Never filters silently. The returned set carries a "selection" block
    naming the criteria and the counts, so a results table can always say
    which states it was computed over.
    """
    kept, dropped = [], 0
    for p in probe_set["probes"]:
        d = p.get("derived", {})
        n = d.get("n_legal_pairs", 0)
        if n < min_legal:
            dropped += 1
            continue
        if max_legal is not None and n > max_legal:
            dropped += 1
            continue
        if require_choice and d.get("n_tasks_with_choice", 0) < 1:
            dropped += 1
            continue
        if condition and p["provenance"].get("condition") != condition:
            dropped += 1
            continue
        if require_direct_vs_relay and d.get("n_tasks_direct_and_relay", 0) < 1:
            dropped += 1
            continue
        if require_fixed_dest and d.get("n_tasks_with_dest", 0) < 1:
            dropped += 1
            continue
        kept.append(copy.deepcopy(p))
    out = make_set(kept, sources=probe_set.get("sources", []), note=note)
    out["selection"] = {"from": probe_set.get("hash"),
                        "from_n": len(probe_set["probes"]),
                        "kept": len(kept), "dropped": dropped,
                        "min_legal": min_legal, "max_legal": max_legal,
                        "require_choice": require_choice,
                        "condition": condition,
                        "require_direct_vs_relay": require_direct_vs_relay,
                        "require_fixed_dest": require_fixed_dest}
    return out


def summarise(probe_set):
    """One-line-per-bucket census of how much decision content a set holds."""
    buckets = {}
    for p in probe_set["probes"]:
        n = p.get("derived", {}).get("n_legal_pairs", 0)
        key = "0" if n == 0 else "1" if n == 1 else "2-3" if n <= 3 else "4+"
        buckets[key] = buckets.get(key, 0) + 1
    def tot(key):
        return sum(p.get("derived", {}).get(key, 0)
                   for p in probe_set["probes"])

    def any_of(key):
        return sum(1 for p in probe_set["probes"]
                   if p.get("derived", {}).get(key, 0) >= 1)

    return {"n": len(probe_set["probes"]),
            "hash": probe_set.get("hash", "")[:12],
            "legal_pair_buckets": buckets,
            "legal_pairs_direct": tot("n_legal_direct"),
            "legal_pairs_relay": tot("n_legal_relay"),
            "with_choice": any_of("n_tasks_with_choice"),
            "with_direct_vs_relay_choice": any_of("n_tasks_direct_and_relay"),
            "states_with_a_fixed_dest_task": any_of("n_tasks_with_dest")}
