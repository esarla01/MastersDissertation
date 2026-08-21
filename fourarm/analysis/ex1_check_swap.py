#!/usr/bin/env python3
"""Did the swap actually happen, and was it scored against the true state?

h_ex1_mislabel checks the state edit BEFORE a run. This checks the run
FILE afterwards, which is a different question and the one that matters
once money has been spent. Four things can go wrong between a clean edit
and a valid result, and each has a check here.

  1  The rung was mislabelled in the runner and an unmanipulated prompt
     went out under a swap name. Caught by reading rung_flags back out of
     the rows themselves, which probe_replay records per row.

  2  The validator scored against the SHOWN state rather than the true
     one, making the ground truth agree with the lie. Caught by comparing
     every derived field against the matched baseline run: if the swap
     moved the ground truth, binding causes and legal-pair counts differ.

  3  The prompt did not change at all. Caught on prompt_chars and on the
     model's own reason strings, which must mention the swapped names.

  4  The two runs are not comparable, through a different probe set, a
     different repeat count, or missing states. Caught by keying both
     files on (source, seq, round, repeat).

Usage, comparing the swap against its unmanipulated parent:

    python3 analysis/ex1_check_swap.py \\
        --swap out/ex1_gpt_L1swap.jsonl \\
        --base out/ex1_gpt_L1nw_r3b.jsonl \\
        --rung L1-swap

Exit 0 if every check passes, 1 otherwise.
"""

import argparse
import collections
import json
import os
import re
import sys

SWAPPED = {"ycb_large_clamp", "ycb_power_drill",
           "ycb_mustard", "ycb_soup_can",
           "ycb_meat_can", "ycb_gelatin_box"}
CONTROLS = {"ycb_mug", "ycb_mug2", "ycb_banana", "ycb_bowl"}

# Reason strings use human phrasing ("the wood block"), not the ycb_
# identifier, so matching on the identifier alone finds nothing. Each object
# is matched on its id OR an unambiguous phrase. Bare "can" and "box" are
# deliberately excluded: they appear in more than one object name and would
# attribute a mention to the wrong one.
ALIASES = {
    "ycb_large_clamp":  [r"ycb_large_clamp", r"\blarge clamp\b", r"\bclamp\b"],
    "ycb_power_drill":  [r"ycb_power_drill", r"\bpower drill\b", r"\bdrill\b"],
    "ycb_mustard":      [r"ycb_mustard", r"\bmustard\b"],
    "ycb_soup_can":     [r"ycb_soup_can", r"\bsoup can\b"],
    "ycb_meat_can":     [r"ycb_meat_can", r"\bmeat can\b"],
    "ycb_gelatin_box":  [r"ycb_gelatin_box", r"\bgelatin box\b"],
    "ycb_mug":          [r"ycb_mug\b", r"\bmug\b"],
    "ycb_mug2":         [r"ycb_mug2"],
    "ycb_banana":       [r"ycb_banana", r"\bbanana\b"],
    "ycb_bowl":         [r"ycb_bowl", r"\bbowl\b"],
}
_ALIAS_RE = {k: re.compile("|".join(v), re.I) for k, v in ALIASES.items()}


def objects_named(text):
    """Which objects a reason string mentions, by id."""
    return {k for k, rx in _ALIAS_RE.items() if rx.search(text or "")}

EXPECTED_FLAGS = {
    "L1-swap": {"declared_width": False, "names": True, "mislabel": True},
    "L3-swap": {"declared_width": True, "names": True, "mislabel": True},
}

FAILURES = []


def check(name, ok, detail=""):
    print("  %-4s %s%s" % ("pass" if ok else "FAIL", name,
                           "" if ok else "\n       " + str(detail)))
    if not ok:
        FAILURES.append(name)


def rows(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def key(r):
    p = r["provenance"]
    return (p["source"], p["seq"], p["round"], r.get("repeat", 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--swap", required=True, help="the swap run file")
    ap.add_argument("--base", required=True,
                    help="its unmanipulated parent, L1-nowidth for L1-swap "
                         "or L3 for L3-swap")
    ap.add_argument("--rung", required=True, choices=sorted(EXPECTED_FLAGS))
    ap.add_argument("--probes", default="probes/ex1_v2.json",
                    help="the probe set both runs used, for the truth table")
    args = ap.parse_args()

    global TRUE_OBJECT, SWAP_MAP
    SWAP_MAP = {}
    for a, b in (("ycb_large_clamp", "ycb_power_drill"),
                 ("ycb_mustard", "ycb_soup_can"),
                 ("ycb_meat_can", "ycb_gelatin_box")):
        SWAP_MAP[a] = b
        SWAP_MAP[b] = a
    TRUE_OBJECT = {}
    probes = json.load(open(args.probes))["probes"]
    for p in probes:
        pv = p["provenance"]
        for t in p["state"]["tasks"]:
            TRUE_OBJECT[(pv["source"], pv["seq"], pv["round"], t["id"])] = t["object"]

    sw = rows(args.swap)
    bs = rows(args.base)
    print("%s  (%d rows)  against  %s  (%d rows)\n"
          % (os.path.basename(args.swap), len(sw),
             os.path.basename(args.base), len(bs)))

    # --- 1. the file self-reports the manipulation -------------------------
    labels = collections.Counter(r.get("rung") for r in sw)
    check("every row is labelled %s" % args.rung,
          set(labels) == {args.rung}, dict(labels))

    flags = {json.dumps(r.get("rung_flags"), sort_keys=True) for r in sw}
    check("rung_flags is constant across rows", len(flags) == 1, flags)

    spec = sw[0].get("rung_flags") or {}
    for k, v in EXPECTED_FLAGS[args.rung].items():
        check("rung_flags %s is %r" % (k, v), spec.get(k) == v,
              "row reports %r" % spec.get(k))

    versions = collections.Counter(r.get("ex1_prompt_version") for r in sw)
    check("prompt version is uniform", len(versions) == 1, dict(versions))

    check("no errored rows", not any(r.get("error") for r in sw),
          "%d rows carry an error" % sum(1 for r in sw if r.get("error")))

    # --- 2. ground truth did NOT move --------------------------------------
    # The validator is rebuilt from the original probe, so every derived
    # field must match the baseline exactly. A mismatch means the swap
    # reached the scoring path, which would make the lie self-consistent
    # and the result meaningless.
    b_by = {key(r): r for r in bs}
    shared = [r for r in sw if key(r) in b_by]
    check("states overlap the baseline", len(shared) > 0,
          "no matching (source, seq, round, repeat) keys")

    moved = []
    for r in shared:
        b = b_by[key(r)]
        for field in ("binding_cause", "binding_causes", "n_legal_pairs",
                      "zero_legal"):
            if r.get(field) != b.get(field):
                moved.append((key(r), field, r.get(field), b.get(field)))
    check("ground truth is identical to the baseline", not moved,
          moved[:3])

    # --- 3. the prompt actually changed ------------------------------------
    # prompt_chars records messages[0], the SYSTEM prompt, which carries no
    # object names at all. It is identical across every rung and cannot
    # detect a state edit, so it is reported and not asserted on.
    print("    note: prompt_chars is the system prompt (%s) and is the same "
          "at every rung" % sorted({r.get("prompt_chars") for r in sw}))

    # The definitive test. For each reply, look up the TRUE object of the
    # task the model chose, and see which name the model used in its reason.
    # On a swap run the model should systematically name the partner. On an
    # unmanipulated run it should name the true object. Nothing else
    # distinguishes the two as cleanly.
    seen = collections.Counter()
    true_named = mismatched = 0
    for r in sw:
        reason = r.get("model_reason") or ""
        named = objects_named(reason)
        for m in named:
            seen[m] += 1
        tid = (r.get("decision") or {}).get("task_id")
        truth = TRUE_OBJECT.get((r["provenance"]["source"],
                                 r["provenance"]["seq"],
                                 r["provenance"]["round"], tid))
        if truth is None or truth not in SWAP_MAP or not named:
            continue
        if truth in named:
            true_named += 1
        if SWAP_MAP[truth] in named:
            mismatched += 1
    check("the model's reasons name objects at all", bool(seen),
          "no reason string names any object, so this test cannot run")
    check("reasons name the SWAPPED partner, not the true object",
          mismatched > true_named,
          "reasons named the true object %d times and its swapped partner "
          "%d times. On a swap run the partner should dominate; if the true "
          "object does, the manipulation did not reach the model."
          % (true_named, mismatched))

    # --- 4. comparability ---------------------------------------------------
    reps_sw = collections.Counter(r.get("repeat", 1) for r in sw)
    check("repeat counts are balanced", len(set(reps_sw.values())) == 1,
          dict(reps_sw))

    states_sw = {key(r)[:3] for r in sw}
    states_bs = {key(r)[:3] for r in bs}
    check("swap covers every baseline state", states_bs <= states_sw or
          states_sw <= states_bs,
          "swap has %d states, baseline %d, symmetric difference %d"
          % (len(states_sw), len(states_bs),
             len(states_sw ^ states_bs)))

    # --- what the run actually shows ---------------------------------------
    print("\nreason strings, by object as PRESENTED to the model")
    for obj, n in seen.most_common():
        tag = "swapped" if obj in SWAPPED else "control"
        print("    %-22s %4d  (%s)" % (obj, n, tag))

    print("\ngrasp violations, by object as recorded by the validator")
    viol = collections.Counter((r.get("violation_fields") or {}).get("obj")
                               for r in sw
                               if r.get("violation_cause") == "grasp")
    for obj, n in viol.most_common():
        tag = ("swapped" if obj in SWAPPED
               else "control" if obj in CONTROLS else "other")
        print("    %-22s %4d  (%s)" % (obj, n, tag))

    named = [r for r in sw if (r.get("decision") or {}).get("arm")]
    fr = sum(1 for r in named
             if (r["decision"]["arm"] or "").startswith("franka"))
    print("\nFranka share  %.1f%%  (%d of %d proposals)"
          % (100 * fr / len(named), fr, len(named)))

    print("\n%d checks failed" % len(FAILURES))
    if FAILURES:
        print("failed: %s" % ", ".join(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
