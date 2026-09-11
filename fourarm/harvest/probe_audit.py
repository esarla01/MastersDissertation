"""Check every frozen probe set against its own hash and against Appendix D.

The probe sets are the input to both experiments, and they cannot be
re-harvested without Isaac Lab. What CAN be checked offline is that each set
still holds what it claimed to hold when it was frozen, and that the
derivation the appendix describes actually produced the set the experiments
read. This does that.

Three things are checked, in order of how badly getting them wrong would hurt:

  1. Content hash. A probe set is content-addressed over the identity fields
     of every probe, in order. If a state were edited, the hash would move and
     every run made against that set would be invalid. A mismatch here means
     the run files no longer describe the states they were answered on.

  2. The derivation chain. Appendix D says 278 states were harvested, that
     deduplicating to one state per distinct option set removed 93, and that
     the result was refrozen from 185 to 162 once the seed set was dropped for
     predating a correction to the mustard bottle's grasp width. Each step is
     recomputed from the sets on disk.

  3. Per-source counts. Appendix D's table gives the six runs the 162 states
     came from and how many each contributed.

    python3 harvest/probe_audit.py        # print the audit, exit 1 on a problem
"""

import collections
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from harvest.probe_store import content_hash                    # noqa: E402

PROBES = os.path.join(ROOT, "probes")

# Appendix D, Table D.1: where the 162 cast A states came from. No run used a
# VLM allocator, so the set is not shaped by any model's behaviour.
APPENDIX_D_SOURCES = {
    "rnd_contention": 34,
    "rnd_balanced": 33,
    "rnd_relay": 31,
    "rnd_captrap": 31,
    "rnd_decision_rich": 20,
    "rec_decision_rich": 13,
}

# Every set on disk with the size it should hold. The two ex3_* sets were
# harvested and never used; they are checked so that "unused" stays a decision
# rather than becoming an excuse not to look at them.
EXPECTED_N = {
    "ex1_v2.json": 162,            # cast A, the reported set
    "ex1_setb_v1.json": 108,       # cast B
    "ex1_v1.json": 185,            # pre-refreeze, still carries seed_v3
    "ex1_v2_tablecam.json": 162,   # ex1_v2's states under the table camera
    "master_v1.json": 278,         # everything harvested, before deduplication
    "setb_master_v1.json": 118,
    "seed_v3.json": 29,            # dropped from ex1_v2; see below
    "ex3_v1.json": 135,            # harvested, unused
    "ex3_setb_v1.json": 72,        # harvested, unused
}


def load(name):
    with open(os.path.join(PROBES, name)) as fh:
        return json.load(fh)


def identity(probe):
    """The (source, seq, round) a probe came from. Not unique: one decision
    round can appear more than once, which is why deduplication counts records
    rather than these."""
    p = probe.get("provenance", {})
    return (p.get("source"), p.get("seq"), p.get("round"))


def audit(verbose=True):
    """Recompute what the probe sets claim. Returns a list of problem strings."""
    problems = []
    say = (lambda *a: print(*a)) if verbose else (lambda *a: None)

    on_disk = sorted(f for f in os.listdir(PROBES) if f.endswith(".json"))

    say("== content hashes ==")
    for name in on_disk:
        if name not in EXPECTED_N:
            problems.append("probe set on disk that this audit does not know: %s"
                            % name)
            continue
        d = load(name)
        stored, got = d.get("hash", ""), content_hash(d["probes"])
        n = len(d["probes"])
        ok = got.startswith(stored)
        if not ok:
            problems.append("%s: stored hash %s, content hashes to %s"
                            % (name, stored[:16], got[:16]))
        if n != EXPECTED_N[name]:
            problems.append("%s holds %d states, expected %d"
                            % (name, n, EXPECTED_N[name]))
        say("   %-24s n=%-4d %s %s" % (name, n, got[:16],
                                       "ok" if ok else "HASH MISMATCH"))
    for name in EXPECTED_N:
        if name not in on_disk:
            problems.append("expected probe set is missing: %s" % name)

    say("")
    say("== derivation chain, against Appendix D ==")
    try:
        master, v1, v2, seed = (load("master_v1.json"), load("ex1_v1.json"),
                                load("ex1_v2.json"), load("seed_v3.json"))
    except (IOError, OSError, ValueError) as exc:
        problems.append("cannot read the chain: %s" % exc)
        return _finish(problems, verbose)

    n_master, n_v1, n_v2 = (len(x["probes"]) for x in (master, v1, v2))
    removed_dedup, removed_seed = n_master - n_v1, n_v1 - n_v2

    say("   harvested                 %d   Appendix D: 278" % n_master)
    say("   after deduplication       %d   removed %d, Appendix D: 93"
        % (n_v1, removed_dedup))
    say("   after dropping seed_v3    %d   removed %d" % (n_v2, removed_seed))

    if removed_dedup != 93:
        problems.append("deduplication removed %d states, Appendix D says 93"
                        % removed_dedup)

    # ex1_v2 must be a subset of ex1_v1, which must be a subset of the master.
    # Refreezing is meant to drop states, never to introduce one.
    ids = {k: {identity(p) for p in x["probes"]}
           for k, x in (("master", master), ("v1", v1), ("v2", v2),
                        ("seed", seed))}
    if not ids["v1"] <= ids["master"]:
        problems.append("ex1_v1 holds states that are not in master_v1")
    if not ids["v2"] <= ids["v1"]:
        problems.append("ex1_v2 holds states that are not in ex1_v1")

    # The reason ex1_v2 exists: seed_v3 predates a correction to the mustard
    # bottle's grasp width, 0.058 -> 0.096 m. Any of its states surviving into
    # the reported set would carry the wrong width, and the grasp constraint
    # is what both experiments manipulate.
    leaked = ids["seed"] & ids["v2"]
    say("   seed_v3 states in ex1_v1  %d of %d" % (len(ids["seed"] & ids["v1"]),
                                                   len(ids["seed"])))
    say("   seed_v3 states in ex1_v2  %d   (must be 0)" % len(leaked))
    if leaked:
        problems.append("%d seed_v3 states survive into ex1_v2; they carry the "
                        "uncorrected mustard width" % len(leaked))

    say("")
    say("== per-source counts, Appendix D Table D.1 ==")
    counts = collections.Counter(p["provenance"]["source"] for p in v2["probes"])
    for source, want in sorted(APPENDIX_D_SOURCES.items(),
                               key=lambda kv: -kv[1]):
        got = counts.get(source, 0)
        say("   %-22s %4d   Appendix D: %d%s"
            % (source, got, want, "" if got == want else "   MISMATCH"))
        if got != want:
            problems.append("%s contributed %d states, Appendix D says %d"
                            % (source, got, want))
    for source in counts:
        if source not in APPENDIX_D_SOURCES:
            problems.append("ex1_v2 carries states from %r, which Appendix D "
                            "does not list" % source)
    if sum(counts.values()) != 162:
        problems.append("per-source counts sum to %d, not 162"
                        % sum(counts.values()))

    return _finish(problems, verbose)


def _finish(problems, verbose):
    if verbose:
        print("")
        for p in problems:
            print("   PROBLEM  %s" % p)
        print("probe audit: %s" % ("clean" if not problems
                                   else "%d problem(s)" % len(problems)))
    return problems


if __name__ == "__main__":
    sys.exit(1 if audit() else 0)
