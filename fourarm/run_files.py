"""The canonical list of which run file backs which published result.

Every consumer that reads Experiment 1 run files should take its paths from
here rather than globbing a directory. out/ holds smoke tests, repair runs and
superseded duplicates alongside the real runs, and several of them fall in the
same (model, condition) bucket as a run that IS published. A glob reads them in
alphabetical order and the last one wins, which once put a wrong figure in the
write-up for two days.

The audit below is the other half: it fails if a listed file is missing, and it
fails if a .jsonl appears under out/ or runs/ that is neither listed nor
explicitly accounted for. Table 4.11's Anonymous row went unverified for weeks
because a real 324-row run sat on disk that no manifest mentioned, and nothing
noticed.

    python3 run_files.py          # print the audit, exit 1 on any problem

Paths are relative to this file's directory, the fourarm package root.
"""

import collections
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def path(rel):
    """Absolute path for a manifest entry. rel is relative to fourarm/."""
    return os.path.join(ROOT, rel)


# ---------------------------------------------------------------------------
# Experiment 1. Eight conditions x three models on cast A, four conditions on
# cast B, each at three repeats except Legal-Arm Control at one.
# ---------------------------------------------------------------------------

# Condition key -> the rung code every run row records. The key is what this
# module is indexed by; the rung is what verifies a file is what it claims.
EX1_CONDITIONS = collections.OrderedDict([
    ("full",         "L3"),
    ("anon",         "L3-anon"),
    ("swap",         "L3-swap"),
    ("nowidth",      "L3-nowidth"),
    ("nowidth-anon", "L1-nowidth"),
    ("nowidth-swap", "L1-swap"),
    ("norules",      "L2"),
    ("givenset",     "L4"),
])

EX1_MODELS = ("gemini", "gpt", "qwen")

# Legal-Arm Control is read as a standalone check rather than entered into a
# contrast, so it was run once where everything else was run three times.
EX1_REPEATS = {c: (1 if c == "givenset" else 3) for c in EX1_CONDITIONS}

# Cast B is GPT only, and crosses width with the true and withheld identity
# levels. The swap conditions were run on cast A alone.
EX1_CASTB_CONDITIONS = ("full", "anon", "nowidth", "nowidth-anon")

CAST_A = {(m, c): "out/ex1_casta_%s_%s_r%d.jsonl" % (m, c, EX1_REPEATS[c])
          for m in EX1_MODELS for c in EX1_CONDITIONS}

CAST_B = {("gpt", c): "out/ex1_castb_gpt_%s_r3.jsonl" % c
          for c in EX1_CASTB_CONDITIONS}

# Cast B was also executed once as a separate single-repeat run at the same
# prompt version on the same states. Reported as a run-to-run stability column
# and never pooled with the three-repeat run.
CAST_B_R1 = {("gpt", c): "out/ex1_castb_gpt_%s_r1.jsonl" % c
             for c in EX1_CASTB_CONDITIONS}

# The one condition where GPT saw a rendered frame as well as the text. Used
# for a robustness check, not for a table.
IMAGE_ON = "out/ex1_casta_gpt_nowidth-anon_r3_image.jsonl"

PROBES = {
    "casta": ("probes/ex1_v2.json", "e23cd23479778f76", 162),
    "castb": ("probes/ex1_setb_v1.json", "b8abfb3391dd6d52", 108),
}

# Reference lines, precomputed from the probe sets by ex1_chance_floor.py and
# re-derived and asserted against in ex1_reproduce_tables.ipynb.
FLOORS = {"casta": "out/ex1_chance_floor.json",
          "castb": "out/ex1_setb_floors.json"}


# ---------------------------------------------------------------------------
# Files that exist but must never reach a report, with the reason. Listed so
# the audit can tell "accounted for" from "nobody has looked at this".
# ---------------------------------------------------------------------------

EXCLUDED = {
    "out/attic": "superseded duplicates and partial repair runs, kept for provenance",
    "out/ex2_capture": "raw scene captures, not model replies",
    "out/ex2_capture_block": "raw scene captures, not model replies",
    "out/ex2_capture_sugar_box": "raw scene captures, not model replies",
    "out/setb_s101_frames": "raw frame captures from a cast B episode",
    "out/setb_s102_frames": "raw frame captures from a cast B episode",
    "out/setb_s103_frames": "raw frame captures from a cast B episode",
    "out/setb_s104_frames": "raw frame captures from a cast B episode",
    "out/setb_s106_frames": "raw frame captures from a cast B episode",
    "runs/_archive": "the withdrawn three-face design, cited in sections 5.5 and 5.8",
    # These two exist and are real 108-row runs, but Appendix A.1 states the
    # swap conditions were run on cast A alone. They are single-repeat pilots
    # and the chapter deliberately excludes them, so they are named here to
    # stop anyone pooling them with the four reported cast B cells.
    "out/ex1_castb_gpt_swap_r1.jsonl":
        "single-repeat cast B swap pilot; Appendix A.1 reports cast A swaps only",
    "out/ex1_castb_gpt_nowidth-swap_r1.jsonl":
        "single-repeat cast B swap pilot; Appendix A.1 reports cast A swaps only",
    "runs/A0_textonly.jsonl": "earlier A/B/C naming, superseded by All_conflict.jsonl",
    "runs/A_conflict_gemini.jsonl": "earlier A/B/C naming, superseded",
    "runs/A_conflict_noimage_P4.jsonl": "earlier A/B/C naming, superseded",
    "runs/B_baseline.jsonl": "earlier A/B/C naming, superseded",
    "runs/B_baseline_gemini.jsonl": "earlier A/B/C naming, superseded",
    "runs/B_baseline_p3.jsonl": "earlier A/B/C naming, superseded",
    "runs/C_all_r2.jsonl": "earlier A/B/C naming, superseded",
    "runs/All_conflict.jsonl": "pooled conflict dataset from the earlier design",
    "runs/_check_A.jsonl": "text-only spot check",
    "runs/_check_V.jsonl": "image-on spot check",
    "runs/pose.jsonl": "early pose-reading probe",
    "runs/probe.jsonl": "early single-scene probe",
    "runs/smoke_check.jsonl": "smoke test",
    "runs/smoke_gemini.jsonl": "smoke test",
}


def is_excluded(rel):
    """True when rel is covered by an EXCLUDED file or directory prefix."""
    return any(rel == k or rel.startswith(k + "/") for k in EXCLUDED)


# ---------------------------------------------------------------------------
# The audit.
# ---------------------------------------------------------------------------


def _rows(rel):
    with open(path(rel)) as fh:
        return [json.loads(l) for l in fh if l.strip()]


def audit(verbose=True):
    """Check the manifest against the disk. Returns a list of problem strings.

    Three questions, in order of how badly getting them wrong would hurt:
    is every published file present, does each hold what it claims (rung,
    probe set, row count), and is anything on disk unaccounted for.
    """
    problems = []

    listed = set(CAST_A.values()) | set(CAST_B.values()) \
        | set(CAST_B_R1.values()) | {IMAGE_ON} \
        | {p for p, _, _ in PROBES.values()} | set(FLOORS.values())

    for rel in sorted(listed):
        if not os.path.exists(path(rel)):
            problems.append("listed but missing: %s" % rel)

    for name, (rel, want_hash, want_n) in sorted(PROBES.items()):
        if not os.path.exists(path(rel)):
            continue
        d = json.load(open(path(rel)))
        # Content-addressed: changing a state changes the hash and invalidates
        # every run made against it, so this is what ties runs to states.
        if not d.get("hash", "").startswith(want_hash):
            problems.append("%s hash is %s, manifest says %s"
                            % (rel, d.get("hash", "")[:16], want_hash))
        if len(d.get("probes", [])) != want_n:
            problems.append("%s holds %d states, manifest says %d"
                            % (rel, len(d.get("probes", [])), want_n))

    for (model, cond), rel in sorted(CAST_A.items()):
        if not os.path.exists(path(rel)):
            continue
        rows = _rows(rel)
        want = 162 * EX1_REPEATS[cond]
        if len(rows) != want:
            problems.append("%s has %d rows, expected %d" % (rel, len(rows), want))
        rungs = {r.get("rung") for r in rows}
        if rungs != {EX1_CONDITIONS[cond]}:
            problems.append("%s records rung %s, expected %s"
                            % (rel, sorted(rungs), EX1_CONDITIONS[cond]))

    for group, reps in ((CAST_B, 3), (CAST_B_R1, 1)):
        for (model, cond), rel in sorted(group.items()):
            if not os.path.exists(path(rel)):
                continue
            rows = _rows(rel)
            if len(rows) != 108 * reps:
                problems.append("%s has %d rows, expected %d"
                                % (rel, len(rows), 108 * reps))

    # Anything on disk that is neither published nor explicitly excluded. This
    # is the check that would have caught the unread cast B Anonymous run.
    for abspath in sorted(glob.glob(os.path.join(ROOT, "out", "**", "*.jsonl"),
                                    recursive=True)
                          + glob.glob(os.path.join(ROOT, "runs", "**", "*.jsonl"),
                                      recursive=True)):
        rel = os.path.relpath(abspath, ROOT)
        if rel in listed or is_excluded(rel):
            continue
        # Experiment 2 names its files by condition and rung, and the notebooks
        # build those names from the design rather than a list, so they are
        # accounted for by their prefix rather than enumerated here.
        if os.path.basename(rel).startswith(("ex2_q1_", "ex2_q2_", "ex2_q3_",
                                             "ex2_cue", "ex2_floor", "ex2_mancheck",
                                             "ex2_seecheck", "ex2_solo", "ex2_smoke",
                                             "ex2_reps", "ex2_formats", "ex2_quota",
                                             "piece_dims")):
            continue
        problems.append("on disk but in no list: %s" % rel)

    if verbose:
        print("manifest: %d Experiment 1 run files, %d probe sets"
              % (len(listed) - len(PROBES) - len(FLOORS), len(PROBES)))
        for p in problems:
            print("  PROBLEM  %s" % p)
        print("audit: %s" % ("clean" if not problems
                             else "%d problem(s)" % len(problems)))
    return problems


if __name__ == "__main__":
    sys.exit(1 if audit() else 0)
