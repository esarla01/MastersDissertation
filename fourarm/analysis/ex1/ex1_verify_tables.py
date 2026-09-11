#!/usr/bin/env python3
"""Regenerate every Experiment 1 table from raw data and diff against the thesis.

Every expected value below is transcribed from the thesis source. The script
recomputes each one from probes/*.json and out/*.jsonl using only the standard
library, so it is an independent check on analysis/ex1/ex1_report.py rather than a
re-run of it. A green line means the number in the thesis is reproducible from
the frozen data.

Usage
-----
    python3 analysis/ex1/ex1_verify_tables.py                 # from fourarm/
    python3 analysis/ex1/ex1_verify_tables.py --root /path/to/fourarm
    python3 analysis/ex1/ex1_verify_tables.py --table spine   # one table only
    python3 analysis/ex1/ex1_verify_tables.py --quiet         # failures only

Exit status is 0 when every check passes and 1 otherwise, so it can be used as
a pre-submission gate.
"""

import argparse
import collections
import json
import math
import os
import statistics
import sys

# ---------------------------------------------------------------------------
# Run files. Taken from run_files.py, the single manifest, so this script and
# ex1_reproduce_tables.ipynb cannot drift onto different inputs -- which is the
# whole point of running both. run_files.audit() additionally fails if a
# .jsonl appears under out/ that no list mentions.
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import run_files                                                # noqa: E402

# Keyed by the thesis's condition codes, which the expected values below use.
_CODE = {"L3": "full", "L3anon": "anon", "L3nw": "nowidth",
         "L1nw": "nowidth-anon", "L2": "norules", "L4": "givenset"}

CAST_A = {(m, t): run_files.CAST_A[(m, _CODE[t])]
          for m in run_files.EX1_MODELS for t in _CODE}
CAST_B = {("gpt", t): run_files.CAST_B[("gpt", _CODE[t])]
          for t in ("L3", "L3anon", "L3nw", "L1nw")}
IMAGE_ON = run_files.IMAGE_ON

PROBES_A = run_files.PROBES["casta"][0]
PROBES_B = run_files.PROBES["castb"][0]
FLOORS_A = run_files.FLOORS["casta"]
FLOORS_B = run_files.FLOORS["castb"]


NAME = {"L3": "Full Information", "L3anon": "Anonymous", "L3nw": "No Width",
        "L1nw": "No Width + Anonymous", "L2": "No Rules", "L4": "Legal-Arm Control"}

# ---------------------------------------------------------------------------
# Statistics. Wilson for a proportion, Newcombe for a difference of two
# independent proportions, matching the convention stated in the thesis.
# ---------------------------------------------------------------------------


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * max(0.0, centre - half), 100 * min(1.0, centre + half))


def newcombe(k1, n1, k2, n2, z=1.96):
    """Difference (group 1 minus group 2) with a Newcombe hybrid-score interval."""
    l1, u1 = (x / 100 for x in wilson(k1, n1, z))
    l2, u2 = (x / 100 for x in wilson(k2, n2, z))
    p1, p2 = k1 / n1, k2 / n2
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (100 * d, 100 * lo, 100 * hi)


# ---------------------------------------------------------------------------
# Loading and the primitive measures.
# ---------------------------------------------------------------------------


def load_rows(root, path):
    full = os.path.join(root, path)
    with open(full) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def scene_key(r):
    p = r["provenance"]
    return (p["source"], p["seq"], p["round"])


def legality(rows, grasp_binding=True):
    """Proposals accepted over proposals made, on picking states. Declines excluded."""
    k = n = 0
    for r in rows:
        if r.get("zero_legal"):
            continue
        if grasp_binding is not None and bool(r.get("binds_grasp")) != grasp_binding:
            continue
        if r.get("result") not in ("valid", "rejected"):
            continue
        n += 1
        k += r["result"] == "valid"
    return k, n


def scene_legality(rows, grasp_binding=True):
    """Per-scene majority over repeats. The unit of analysis is the scene."""
    groups = collections.defaultdict(list)
    for r in rows:
        if r.get("zero_legal"):
            continue
        if grasp_binding is not None and bool(r.get("binds_grasp")) != grasp_binding:
            continue
        if r.get("result") not in ("valid", "rejected"):
            continue
        groups[scene_key(r)].append(r["result"] == "valid")
    k = sum(1 for v in groups.values() if sum(v) * 2 > len(v))
    return k, len(groups)


def correct_refusal(rows):
    """Declines over refusal states, where declining is the right answer."""
    groups = collections.defaultdict(list)
    for r in rows:
        if not r.get("zero_legal"):
            continue
        declined = r.get("result") == "declined" or (r.get("decision") or {}).get("task_id") == -1
        groups[scene_key(r)].append(bool(declined))
    k = sum(1 for v in groups.values() if sum(v) * 2 > len(v))
    return k, len(groups)


def consistency(rows):
    """Stable right, stable wrong, flickering, over the 126 picking states.

    Flickering is defined on the RAW outcome, not on correctness, matching the
    terms table: a state flickers when its three repeats did not return the
    same result. Two consequences worth knowing, because both are easy to get
    wrong:

      * A decline is recorded as ``noop`` and is a wrong answer on a picking
        state, so it is scored, not dropped. Dropping it would change the
        denominator for any model that declines.
      * A state answered wrongly three times in two different ways (say
        rejected, rejected, noop) counts as flickering, not stable wrong,
        because the repeats disagree. Scoring on correctness instead moves two
        GPT No Width states from flickering to stable wrong.
    """
    groups = collections.defaultdict(list)
    for r in rows:
        if r.get("zero_legal"):
            continue
        groups[scene_key(r)].append(r.get("result"))
    right = sum(1 for v in groups.values() if len(set(v)) == 1 and v[0] == "valid")
    wrong = sum(1 for v in groups.values() if len(set(v)) == 1 and v[0] != "valid")
    flick = sum(1 for v in groups.values() if len(set(v)) > 1)
    return right, wrong, flick


# ---------------------------------------------------------------------------
# Check bookkeeping.
# ---------------------------------------------------------------------------

RESULTS = []


def check(table, label, computed, expected, tol=0.05):
    if isinstance(expected, (int, float)) and isinstance(computed, (int, float)):
        ok = abs(computed - expected) <= tol
    else:
        ok = str(computed) == str(expected)
    RESULTS.append((table, label, computed, expected, ok))
    return ok


def check_interval(table, label, k, n, exp_pt, exp_lo, exp_hi):
    pt = 100 * k / n
    lo, hi = wilson(k, n)
    check(table, label, round(pt, 1), exp_pt)
    check(table, label + " lo", round(lo, 1), exp_lo)
    check(table, label + " hi", round(hi, 1), exp_hi)


# ---------------------------------------------------------------------------
# Table 4.2, binding constraints.
# ---------------------------------------------------------------------------


def t_binding(root):
    """Check Table 4.2: how often each constraint blocks a candidate pair.

    WHAT IS BEING COUNTED

    A candidate pair is one open task offered to one idle arm. Across the 162
    frozen states there are 1732 of them. The validator accepts 536, so 1196
    are rejected, and this table breaks those 1196 down by cause. No model is
    involved at any point: these are verdicts on hypothetical pairs, computed
    when the probe set was frozen. The same word "rejected" is used elsewhere
    for a model proposal the validator turned down, which is a far smaller
    number, so the two must not be read together.

    ONE CAUSE PER REJECTED PAIR, AND WHOSE ORDERING IT IS

    A pair can fail several checks at once, yet each is counted once. That is
    not a convention chosen here. validate_decision is a chain of early
    returns, so the deployed validator itself reports one reason and stops:
    can_grasp gives CAPABILITY, then reachable(arm, object) gives
    REACH_OBJECT, then the router gives NO_ROUTE. Inside can_grasp, delicacy
    is tested before size and mass. probe_store.capability_cause only splits
    the single CAPABILITY code into delicate, grasp and payload, re-reading
    the tables can_grasp reads in the order can_grasp reads them, so it
    cannot drift from the validator.

    WHICH ROWS ARE EXACT AND WHICH ARE FLOORS

    Because the chain stops at the first failure, a constraint tested late is
    recorded only when nothing earlier fired:

        delicate   Exact. Nothing precedes it.
        grasp      Exact HERE. Only delicacy precedes it, and no object in
                   this cast is both delicate and wider than an aperture, so
                   nothing ever hides grasp. That is a property of the object
                   cast, not a structural guarantee. Add one fragile wide
                   object and this row becomes a floor, and this comment
                   becomes wrong.
        reach      Floor. 516 recorded here, 869 pairs fail reach when reach
                   is evaluated on its own.
        no_route   Floor, and the largest one, since route is last and is
                   pre-empted by capability and by reach. Its isolated figure
                   is not computed here; that needs the router re-run.

    The thesis caption states this, so the reader is not left to infer it.

    WHAT THIS IS AND IS NOT INDEPENDENT OF

    binding_causes is precomputed at freeze time by probe_store.legal_options
    and stored in each probe's derived block. This function only aggregates
    and totals it. So it is an independent check on the REPORTING, but not on
    the cause derivation: a bug inside capability_cause would pass every check
    below. What guards the derivation is that capability_cause reads the same
    tables as can_grasp, not anything asserted here.
    """
    probes = json.load(open(os.path.join(root, PROBES_A)))["probes"]

    # Two different units. pairs[c] totals the rejected pairs attributed to
    # cause c. states[c] counts states where c fired at least once, so a
    # state contributes 1 whether it lost one pair to c or twenty.
    pairs, states = collections.Counter(), collections.Counter()
    for p in probes:
        for cause, n in (p["derived"].get("binding_causes") or {}).items():
            if n:
                pairs[cause] += n
                states[cause] += 1

    # (states, pairs, pairs per binding state), transcribed from the thesis.
    expected = {"reach": (146, 516, 3.5), "grasp": (122, 493, 4.0),
                "delicate": (80, 135, 1.7), "no_route": (44, 52, 1.2)}
    for cause, (s, pr, per) in expected.items():
        check("binding", cause + " states", states[cause], s)
        check("binding", cause + " pairs", pairs[cause], pr)
        # Published to one decimal, so compare at that precision rather than
        # letting float noise fail a row that is in fact correct.
        check("binding", cause + " per state",
              round(pairs[cause] / states[cause], 1), per)

    # Payload is published as an explicit zero rather than omitted, because a
    # missing row reads as untested rather than as tested and inert. It is
    # structurally zero here: the heaviest object in the set is 1.58 kg
    # against a 3.0 kg Franka limit and 10.0 kg for the UR10.
    check("binding", "payload states", states["payload"], 0)

    # Two structural checks that catch errors the per-row checks cannot.
    #
    # The pairs column must total the rejected pairs, since every rejected
    # pair carries exactly one cause: 1196 = 1732 candidates - 536 legal. A
    # cause double-counted or silently dropped shows up here and nowhere else.
    check("binding", "pairs column sums to rejected", sum(pairs.values()), 1196)
    # The states column deliberately does NOT total 162. Several constraints
    # can bind in one state, so the column overlaps and sums higher. Asserting
    # the overlap total pins that as intended, rather than leaving a later
    # reader to wonder whether the column was meant to partition and failed to.
    check("binding", "states column does not partition", sum(states.values()), 392)


# ---------------------------------------------------------------------------
# Table 3.3, option space, and Table 3.4, the worked example.
# ---------------------------------------------------------------------------


def t_optionspace(root):
    probes = json.load(open(os.path.join(root, PROBES_A)))["probes"]
    d = [p["derived"] for p in probes]
    rows = {
        "Idle arms":       ([x["n_idle_arms"] for x in d], 1, 2, 4, 374),
        "Open tasks":      ([x["n_tasks_open"] for x in d], 1, 4, 11, 763),
        "Candidate pairs": ([x["n_idle_arms"] * x["n_tasks_open"] for x in d], 1, 8, 44, 1732),
        "Legal pairs":     ([x["n_legal_pairs"] for x in d], 0, 2, 18, 536),
    }
    for name, (v, mn, md, mx, tot) in rows.items():
        check("optionspace", name + " min", min(v), mn)
        check("optionspace", name + " median", int(statistics.median(v)), md)
        check("optionspace", name + " max", max(v), mx)
        check("optionspace", name + " total", sum(v), tot)
    check("optionspace", "legal share (%)",
          round(100 * sum(rows["Legal pairs"][0]) / sum(rows["Candidate pairs"][0]), 1), 30.9)

    tasks = collections.Counter()
    for x in d:
        for _, k in x["legal_per_task"].items():
            tasks[min(k, 2)] += 1
    check("optionspace", "tasks with no legal arm", tasks[0], 275)
    check("optionspace", "tasks with one legal arm", tasks[1], 448)
    check("optionspace", "tasks with two or more", tasks[2], 40)


def t_worked(root):
    probes = json.load(open(os.path.join(root, PROBES_A)))["probes"]
    p = next(q for q in probes
             if q["provenance"]["source"] == "rnd_captrap" and q["provenance"]["seq"] == 15)
    x = p["derived"]
    check("worked", "idle arms", x["n_idle_arms"], 2)
    check("worked", "open tasks", x["n_tasks_open"], 4)
    check("worked", "candidate pairs", x["n_idle_arms"] * x["n_tasks_open"], 8)
    check("worked", "legal pairs", x["n_legal_pairs"], 3)
    check("worked", "binding causes", sorted((x.get("binding_causes") or {}).items()),
          [("delicate", 2), ("reach", 3)])
    check("worked", "no task has arm choice", max(x["legal_per_task"].values()), 1)


# ---------------------------------------------------------------------------
# Table 3.5, terms: the state counts quoted in the definitions.
# ---------------------------------------------------------------------------


def t_terms(root):
    d = [p["derived"] for p in json.load(open(os.path.join(root, PROBES_A)))["probes"]]
    picking = sum(1 for x in d if x["n_legal_pairs"] > 0)
    check("terms", "states", len(d), 162)
    check("terms", "picking states", picking, 126)
    check("terms", "refusal states", len(d) - picking, 36)
    gb = [x for x in d if (x.get("binding_causes") or {}).get("grasp")]
    check("terms", "grasp-binding states", len(gb), 122)
    check("terms", "grasp-binding picking", sum(1 for x in gb if x["n_legal_pairs"] > 0), 96)
    check("terms", "grasp-binding refusal", sum(1 for x in gb if x["n_legal_pairs"] == 0), 26)


# ---------------------------------------------------------------------------
# Tables 3.6 and 3.13, the computed reference lines.
# ---------------------------------------------------------------------------


def _floors(root, path, table, expected):
    """Reference lines are stored as fractions of 1, keyed by subset.

    Structure: uniform/mean and width_blind/mean for all picking states, and
    by_cause/<cause>/{uniform,width_blind}/mean for each binding subset.
    """
    blob = json.load(open(os.path.join(root, path)))

    def pct(node, branch):
        return None if node is None else round(100 * node[branch]["mean"], 1)

    for subset, (chance, blind) in expected.items():
        node = blob if subset == "all" else blob["by_cause"].get(subset)
        check(table, subset + " chance floor", pct(node, "uniform"), chance)
        check(table, subset + " width-blind", pct(node, "width_blind"), blind)


def t_floors(root):
    _floors(root, FLOORS_A, "floors", {
        "all": (35.5, 80.9), "grasp": (30.5, 74.9),
        "reach": (34.1, 81.9), "delicate": (35.9, 85.7)})


def t_setbfloors(root):
    _floors(root, FLOORS_B, "setb_floors", {
        "all": (36.5, 81.0), "grasp": (34.6, 69.2),
        "reach": (33.5, 81.5), "delicate": (35.9, 87.5)})


# ---------------------------------------------------------------------------
# Table 3.7, the two controls.
# ---------------------------------------------------------------------------


def t_offspine(root):
    # Legality is the SCENE majority, as Table 4.7 reports it for every
    # condition. This measured the trial rate until 2026-09-10, which agreed
    # only while No Rules was a single repeat and trial and scene coincide.
    # At three repeats the trial denominator triples and the interval narrows,
    # so Gemini's No Rules read 100.0 [98.7, 100.0] against the thesis's
    # 100.0 [96.2, 100.0]. Values below are Table 4.7's own.
    expected = {
        ("gemini", "L4"): (100.0, 96.2, 100.0, 100.0, 90.4, 100.0),
        ("gemini", "L2"): (100.0, 96.2, 100.0, 100.0, 90.4, 100.0),
        ("gpt", "L4"):    (100.0, 96.1, 100.0, 100.0, 90.4, 100.0),
        ("gpt", "L2"):    (94.7, 88.1, 97.7, 77.8, 61.9, 88.3),
        ("qwen", "L4"):   (95.8, 89.8, 98.4, 5.6, 1.5, 18.1),
        ("qwen", "L2"):   (72.9, 63.3, 80.8, 0.0, 0.0, 9.6),
    }
    for (m, t), (lp, llo, lhi, rp, rlo, rhi) in expected.items():
        rows = load_rows(root, CAST_A[(m, t)])
        k, n = scene_legality(rows)
        check_interval("offspine", f"{m} {NAME[t]} legality", k, n, lp, llo, lhi)
        k, n = correct_refusal(rows)
        check_interval("offspine", f"{m} {NAME[t]} refusal", k, n, rp, rlo, rhi)


# ---------------------------------------------------------------------------
# Table 3.8, legality on the four main conditions, trial and scene level.
# ---------------------------------------------------------------------------


TRIAL = {
    ("gemini", "L3"): (100.0, 98.7, 100.0), ("gemini", "L3anon"): (100.0, 98.7, 100.0),
    ("gemini", "L3nw"): (72.2, 66.8, 77.1), ("gemini", "L1nw"): (75.3, 70.1, 80.0),
    ("gpt", "L3"): (97.5, 95.0, 98.8), ("gpt", "L3anon"): (98.6, 96.4, 99.4),
    ("gpt", "L3nw"): (73.6, 68.1, 78.4), ("gpt", "L1nw"): (76.7, 71.4, 81.2),
    ("qwen", "L3"): (75.3, 70.1, 80.0), ("qwen", "L3anon"): (76.7, 71.5, 81.2),
    ("qwen", "L3nw"): (76.7, 71.5, 81.2), ("qwen", "L1nw"): (72.6, 67.1, 77.4),
}
SCENE = {
    ("gemini", "L3"): (100.0, 96.2, 100.0), ("gemini", "L3anon"): (100.0, 96.2, 100.0),
    ("gemini", "L3nw"): (71.9, 62.2, 79.9), ("gemini", "L1nw"): (77.1, 67.7, 84.4),
    ("gpt", "L3"): (97.9, 92.7, 99.4), ("gpt", "L3anon"): (98.9, 94.3, 99.8),
    ("gpt", "L3nw"): (71.6, 61.8, 79.7), ("gpt", "L1nw"): (77.9, 68.6, 85.1),
    ("qwen", "L3"): (77.1, 67.7, 84.4), ("qwen", "L3anon"): (76.0, 66.6, 83.5),
    ("qwen", "L3nw"): (78.1, 68.9, 85.2), ("qwen", "L1nw"): (72.9, 63.3, 80.8),
}


def t_spine(root):
    for (m, t), (pt, lo, hi) in TRIAL.items():
        k, n = legality(load_rows(root, CAST_A[(m, t)]))
        check_interval("spine", f"{m} {NAME[t]} trial", k, n, pt, lo, hi)
    for (m, t), (pt, lo, hi) in SCENE.items():
        k, n = scene_legality(load_rows(root, CAST_A[(m, t)]))
        check_interval("spine", f"{m} {NAME[t]} scene", k, n, pt, lo, hi)


# ---------------------------------------------------------------------------
# Table 3.9, the four design contrasts.
# ---------------------------------------------------------------------------


def t_gaps(root):
    expected = {
        ("width", "names present", "gemini"):    (27.8, 22.7, 33.2),
        ("width", "names present", "gpt"):       (24.0, 18.5, 29.6),
        ("width", "names present", "qwen"):      (-1.4, -8.3, 5.6),
        ("width", "names anonymised", "gemini"): (24.7, 19.8, 29.9),
        ("width", "names anonymised", "gpt"):    (21.9, 16.8, 27.2),
        ("width", "names anonymised", "qwen"):   (4.2, -2.9, 11.2),
        ("identity", "width present", "gemini"): (0.0, -1.3, 1.3),
        ("identity", "width present", "gpt"):    (-1.0, -3.7, 1.5),
        ("identity", "width present", "qwen"):   (-1.4, -8.3, 5.6),
        ("identity", "width absent", "gemini"):  (-3.1, -10.3, 4.1),
        ("identity", "width absent", "gpt"):     (-3.1, -10.2, 4.0),
        ("identity", "width absent", "qwen"):    (4.2, -2.9, 11.2),
    }
    # (from, to) per contrast. Positive means legality fell when removed.
    contrast = {
        ("width", "names present"):    ("L3", "L3nw"),
        ("width", "names anonymised"): ("L3anon", "L1nw"),
        ("identity", "width present"): ("L3", "L3anon"),
        ("identity", "width absent"):  ("L3nw", "L1nw"),
    }
    for (factor, level, model), (pt, lo, hi) in expected.items():
        a, b = contrast[(factor, level)]
        k1, n1 = legality(load_rows(root, CAST_A[(model, a)]))
        k2, n2 = legality(load_rows(root, CAST_A[(model, b)]))
        d, dlo, dhi = newcombe(k1, n1, k2, n2)
        tag = f"{model} {factor}, {level}"
        check("gaps", tag, round(d, 1), pt)
        check("gaps", tag + " lo", round(dlo, 1), lo)
        check("gaps", tag + " hi", round(dhi, 1), hi)


# ---------------------------------------------------------------------------
# Table 3.10, per-scene consistency over three repeats.
# ---------------------------------------------------------------------------


def t_consistency(root):
    expected = {
        ("gemini", "L3"): (126, 0, 0), ("gemini", "L3nw"): (90, 17, 19),
        ("gemini", "L1nw"): (93, 16, 17),
        ("gpt", "L3"): (111, 1, 14), ("gpt", "L3nw"): (78, 10, 38),
        ("gpt", "L1nw"): (87, 12, 27),
        ("qwen", "L3"): (86, 22, 18), ("qwen", "L3nw"): (91, 21, 14),
        ("qwen", "L1nw"): (88, 26, 12),
    }
    for (m, t), (r, w, f) in expected.items():
        gr, gw, gf = consistency(load_rows(root, CAST_A[(m, t)]))
        check("consistency", f"{m} {NAME[t]} stable right", gr, r)
        check("consistency", f"{m} {NAME[t]} stable wrong", gw, w)
        check("consistency", f"{m} {NAME[t]} flickering", gf, f)


# ---------------------------------------------------------------------------
# Table 3.11, grasp errors per opportunity at No Width.
# ---------------------------------------------------------------------------


def t_objects(root):
    expected = {
        "ycb_mug":         (24, 0.0, 0.0, 0.0),
        "ycb_mug2":        (33, 0.0, 3.0, 9.1),
        "ycb_meat_can":    (135, 17.8, 12.6, 0.0),
        "ycb_wood_block":  (84, 6.0, 21.4, 6.0),
        "ycb_mustard":     (105, 30.5, 20.0, 7.6),
        "ycb_large_clamp": (138, 52.2, 46.4, 19.6),
    }
    errs = {m: collections.Counter() for m in ("gemini", "gpt", "qwen")}
    for m in errs:
        for r in load_rows(root, CAST_A[(m, "L3nw")]):
            if r.get("violation_cause") == "grasp":
                obj = (r.get("violation_fields") or {}).get("obj")
                if obj:
                    errs[m][obj] += 1
    for obj, (opps, gem, gpt, qwen) in expected.items():
        for m, exp in (("gemini", gem), ("gpt", gpt), ("qwen", qwen)):
            check("objects", f"{obj} {m} (%)", round(100 * errs[m][obj] / opps, 1), exp)


# ---------------------------------------------------------------------------
# In-text figures that carry an argument.
# ---------------------------------------------------------------------------


def t_intext(root):
    total = 0
    for m in ("gemini", "gpt", "qwen"):
        for t in ("L3nw", "L1nw"):
            total += sum(1 for r in load_rows(root, CAST_A[(m, t)])
                         if r.get("violation_cause") == "grasp")
    check("in-text", "grasp violations, width-absent, 3 models", total, 578)

    files = sum(1 for _ in CAST_A)
    rows = sum(len(load_rows(root, p)) for p in CAST_A.values())
    check("in-text", "cast A run files", files, 18)
    # 15 files at 3 repeats plus the 3 Legal-Arm Control files at 1.
    # Was 6804 while No Rules was also a single repeat.
    check("in-text", "cast A rows", rows, 7776)

    # Cast B at three repeats.
    k1, n1 = legality(load_rows(root, CAST_B[("gpt", "L3")]))
    k2, n2 = legality(load_rows(root, CAST_B[("gpt", "L3nw")]))
    d, lo, hi = newcombe(k1, n1, k2, n2)
    check("in-text", "cast B Full Information (%)", round(100 * k1 / n1, 1), 98.8)
    check("in-text", "cast B No Width (%)", round(100 * k2 / n2, 1), 90.1)
    check("in-text", "cast B width gap", round(d, 1), 8.7)
    check("in-text", "cast B width gap lo", round(lo, 1), 3.9)
    check("in-text", "cast B width gap hi", round(hi, 1), 14.3)

    # Image-on cell against text-only, same condition and model.
    kv, nv = legality(load_rows(root, IMAGE_ON))
    kt, nt = legality(load_rows(root, CAST_A[("gpt", "L1nw")]))
    d, lo, hi = newcombe(kv, nv, kt, nt)
    check("in-text", "image-on legality (%)", round(100 * kv / nv, 1), 75.4)
    check("in-text", "image minus text", round(d, 1), -1.3)
    check("in-text", "image minus text lo", round(lo, 1), -8.3)
    check("in-text", "image minus text hi", round(hi, 1), 5.7)



# ---------------------------------------------------------------------------
# Route rejections: how much of the R5 limitation is real.
#
# Two of the router's conditions are never stated in the prompt: the 0.05 m
# monotone-progress threshold, and the rule forbidding one arm from taking
# both legs of a handover. This rebuilds the DEPLOYED router from source with
# each rule disabled and re-runs every no_route rejection through it. A pair
# that becomes routable was decided by the unstated rule. A pair still blocked
# was decided by reachability, which the printed reach_ok_arms lists make
# determinable. The control variant must reproduce the deployed verdict on all
# 52, or the instrument is not measuring what it claims to.
# ---------------------------------------------------------------------------


def t_route(root):
    import collections
    sys.path.insert(0, root)
    sys.path.insert(0, os.path.join(root, "ycb"))
    try:
        from harvest.probe_store import legal_options
        from core.cell.zones import ZoneMap
    except ImportError as exc:
        RESULTS.append(("route", "project imports", str(exc), "available", False))
        return

    src_path = os.path.join(root, "core/control/tasks.py")
    src = open(src_path).read()
    same_arm = "        second = [a for a in second if a not in first or len(first) > 1]\n"
    # The threshold appears twice in this module. Only the one inside
    # route_via_pad is on the validation path, so patch that function alone.
    start = src.index("def route_via_pad(")
    end = src.index("\ndef ", start)
    router = src[start:end]
    check("route", "threshold occurrences in router", router.count("d_dest - 0.05"), 1)
    check("route", "same-arm rule present in router", router.count(same_arm), 1)

    def build(thresh="0.05", drop_same=False):
        body = router.replace("d_dest - 0.05", "d_dest - %s" % thresh)
        if drop_same:
            body = body.replace(same_arm, "")
        ns = {}
        exec(compile(src[:start] + body + src[end:], "tasks_variant.py", "exec"), ns)
        return ns["route_via_pad"], ns["Task"]

    variants = {
        "deployed": build(),
        "no threshold": build(thresh="0.0"),
        "no same-arm rule": build(drop_same=True),
    }
    zm = ZoneMap()
    probes = json.load(open(os.path.join(root, PROBES_A)))["probes"]
    unblocked = collections.Counter()
    total = 0
    for p in probes:
        rejected = [(t, a) for t, a, c in legal_options(p, with_causes=True)[2]
                    if c == "no_route"]
        if not rejected:
            continue
        state = p["state"]
        tasks = {t["id"]: t for t in state["tasks"]}
        objects = {o["name"]: o for o in state["objects"]}
        for tid, arm in rejected:
            total += 1
            task = tasks[tid]
            obj = objects[task["object"]]
            xy = tuple((obj.get("xy") or [obj.get("x"), obj.get("y")])[:2])
            dest = tuple(task["dest_xy"])
            for name, (route, Task) in variants.items():
                first, _, _ = route(Task(obj=task["object"], dest=dest),
                                    xy, [arm], zm, ())
                if first is not None:
                    unblocked[name] += 1

    check("route", "no_route rejections", total, 52)
    check("route", "control reproduces deployed verdict", unblocked["deployed"], 0)
    check("route", "unblocked by removing the threshold", unblocked["no threshold"], 1)
    check("route", "unblocked by removing the same-arm rule",
          unblocked["no same-arm rule"], 0)



# ---------------------------------------------------------------------------
# Effect sizes the Results section quotes as contrasts rather than as bare
# percentages. Mirrors analysis/ex1/ex1_effects.py, which computes them for
# reporting; this block pins the published values.
# ---------------------------------------------------------------------------


def t_effects(root):
    import re

    def refusal(rs):
        k = n = 0
        for r in rs:
            if not r.get("zero_legal"):
                continue
            n += 1
            k += r.get("result") == "noop"
        return k, n

    def franka(rs):
        k = n = 0
        for r in rs:
            arm = (r.get("decision") or {}).get("arm")
            if not arm:
                continue
            n += 1
            k += arm.startswith("franka")
        return k, n

    # Interaction: the difference of the two width gaps, per model.
    for model, exp, lo_e, hi_e in (("gemini", 3.1, -4.1, 10.4),
                                   ("gpt", 2.1, -5.5, 9.6),
                                   ("qwen", -5.6, -15.5, 4.4)):
        a = legality(load_rows(root, CAST_A[(model, "L3")]))
        b = legality(load_rows(root, CAST_A[(model, "L3nw")]))
        c = legality(load_rows(root, CAST_A[(model, "L3anon")]))
        d = legality(load_rows(root, CAST_A[(model, "L1nw")]))
        g1 = newcombe(a[0], a[1], b[0], b[1])
        g2 = newcombe(c[0], c[1], d[0], d[1])
        se = math.sqrt(((g1[2] - g1[1]) / 3.92) ** 2 + ((g2[2] - g2[1]) / 3.92) ** 2)
        diff = g1[0] - g2[0]
        check("effects", model + " interaction", round(diff, 1), exp)
        check("effects", model + " interaction lo", round(diff - 1.96 * se, 1), lo_e)
        check("effects", model + " interaction hi", round(diff + 1.96 * se, 1), hi_e)

    # Correct refusal, Full Information to No Width.
    for model, exp, lo_e, hi_e in (("gemini", 42.6, 31.4, 52.5),
                                   ("gpt", 35.2, 23.5, 45.6),
                                   ("qwen", 0.0, -3.4, 3.4)):
        a = refusal(load_rows(root, CAST_A[(model, "L3")]))
        b = refusal(load_rows(root, CAST_A[(model, "L3nw")]))
        d, lo, hi = newcombe(a[0], a[1], b[0], b[1])
        check("effects", model + " refusal fall", round(d, 1), exp)
        check("effects", model + " refusal fall lo", round(lo, 1), lo_e)
        check("effects", model + " refusal fall hi", round(hi, 1), hi_e)

    # Franka share, the mechanism measure.
    for model, exp, lo_e, hi_e in (("gemini", 20.0, 13.4, 26.3),
                                   ("gpt", 19.7, 13.1, 26.1),
                                   ("qwen", 0.8, -4.3, 6.0)):
        a = franka(load_rows(root, CAST_A[(model, "L3")]))
        b = franka(load_rows(root, CAST_A[(model, "L3nw")]))
        d, lo, hi = newcombe(b[0], b[1], a[0], a[1])
        check("effects", model + " franka rise", round(d, 1), exp)
        check("effects", model + " franka rise lo", round(lo, 1), lo_e)
        check("effects", model + " franka rise hi", round(hi, 1), hi_e)

    # A count of zero bounded, rather than reported as an absence.
    pattern = re.compile(
        r"(unknown|unstated|not stated|missing|unspecified|no (?:declared )?width"
        r"|not (?:given|provided|specified|declared)|absent)", re.I)
    total = hits = 0
    for model in ("gemini", "gpt", "qwen"):
        for cond in ("L3nw", "L1nw"):
            for r in load_rows(root, CAST_A[(model, cond)]):
                if r.get("violation_cause") == "grasp":
                    total += 1
                    hits += bool(pattern.search(r.get("model_reason") or ""))
    check("effects", "reasons admitting the gap", hits, 0)
    check("effects", "reasons examined", total, 578)
    check("effects", "one-sided upper bound (%)", round(100 * 3 / total, 2), 0.52)

    # The width-ordering violation the errors subsection rests on.
    counts = collections.Counter()
    for r in load_rows(root, CAST_A[("gemini", "L3nw")]):
        if r.get("violation_cause") == "grasp":
            obj = (r.get("violation_fields") or {}).get("obj")
            if obj:
                counts[obj] += 1
    d, lo, hi = newcombe(counts["ycb_meat_can"], 135, counts["ycb_wood_block"], 84)
    check("effects", "gemini meat can minus wood block", round(d, 1), 11.8)
    check("effects", "gemini ordering lo", round(lo, 1), 2.7)
    check("effects", "gemini ordering hi", round(hi, 1), 19.9)


# ---------------------------------------------------------------------------

TABLES = {
    "binding": t_binding, "optionspace": t_optionspace, "worked": t_worked,
    "terms": t_terms, "floors": t_floors, "offspine": t_offspine,
    "spine": t_spine, "gaps": t_gaps, "consistency": t_consistency,
    "objects": t_objects, "setb_floors": t_setbfloors, "in-text": t_intext,
    "route": t_route,
    "effects": t_effects,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="path to the fourarm package")
    ap.add_argument("--table", action="append", choices=sorted(TABLES),
                    help="verify one table only, repeatable")
    ap.add_argument("--quiet", action="store_true", help="show failures only")
    args = ap.parse_args()

    wanted = args.table or list(TABLES)
    for name in wanted:
        try:
            TABLES[name](args.root)
        except FileNotFoundError as exc:
            RESULTS.append((name, "input file", str(exc), "present", False))

    width = max(len(r[1]) for r in RESULTS) if RESULTS else 10
    current = None
    for table, label, got, exp, ok in RESULTS:
        if args.quiet and ok:
            continue
        if table != current:
            print(f"\n{table}")
            current = table
        mark = "pass" if ok else "FAIL"
        line = f"  {mark}  {label:<{width}}  {got}"
        if not ok:
            line += f"   expected {exp}"
        print(line)

    failed = [r for r in RESULTS if not r[4]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed", end="")
    print("" if not failed else f", {len(failed)} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
