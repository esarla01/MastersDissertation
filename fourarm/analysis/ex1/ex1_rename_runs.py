#!/usr/bin/env python3
"""Put the Experiment 1 run files under names a reader can decode.

WHY. The original names carried three traps.

  1. L1-swap has names PRESENT but false, while L1-nowidth has names WITHHELD.
     The shared L1 prefix invites pairing a swap run with the anonymised run
     instead of with L3-nowidth, which confounds anonymisation with the swap.
     That mistake is already written into ex1_check_swap.py's own docstring.
  2. The repeat count was encoded inconsistently: _r3, _r3b, bare, and _repair.
     Nothing in a name said whether a file held one repeat or three, so
     ex1_effects.py carried a hardcoded exception for a single model.
  3. Live, superseded and partial files sat in one directory under names that
     sort next to each other. Globbing out/ therefore read a 10-row smoke file
     over a 486-row result, which is exactly the 16 August bucket collision.

THE SCHEME.

    ex1_<cast>_<model>_<condition>_r<repeats>[_image].jsonl

Condition names are the chapter's, so a file name and a table row read alike:

    full            width and true names            (was L3)
    anon            width, names withheld           (was L3-anon)
    swap            width, names swapped            (was L3-swap)
    nowidth         no width, true names            (was L3-nowidth)
    nowidth-anon    no width, names withheld        (was L1-nowidth)
    nowidth-swap    no width, names swapped         (was L1-swap)
    norules         width, R3 and R4 neutralised    (was L2)
    givenset        the legal arm set printed       (was L4)

Every name states its repeat count, so a one-repeat cell can never be read as
three by accident. Files that are not results move to out/attic/ so that a
careless glob cannot reach them at all, rather than relying on discipline.

CORRECTION, 21 August. The first pass filed the three cast-B single-repeat runs
in the attic as superseded. That was wrong and is fixed here. Those files are
independent runs of the same cells at the SAME prompt version (2026-08-16b) on
the same 108 states, and GPT answered about a fifth of the states differently,
so their trials are present nowhere else. They are live. Two attic reasons were
also inaccurate and are corrected below.

WHAT THIS DOES NOT TOUCH. The rung identifiers inside the data (L3, L3-nowidth
and so on) stay exactly as they are. They are recorded in every row and in
prompts.py, and renaming them would break the match between a file and its own
contents for no gain. This changes file names only.

SAFETY. The tree is not under version control, so a move is unrecoverable. This
tool therefore copies, verifies the md5 of the copy against its source, and only
then removes the source. It refuses to overwrite an existing destination.
Nothing happens without --apply.

IDEMPOTENT. The plan is computed from what is on disk, not from an assumed
starting point. Each destination lists every name it may currently be under, in
history order. A destination that already holds a file is left alone. So this is
safe to run on a tree that is untouched, half moved, or already moved by the
earlier version of this tool.

    python3 analysis/ex1/ex1_rename_runs.py                 # dry run, prints the plan
    python3 analysis/ex1/ex1_rename_runs.py --apply         # do it
    python3 analysis/ex1/ex1_rename_runs.py --verify-only   # check a finished move
"""

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sys

# ---------------------------------------------------------------------------
# The mapping. Written out in full rather than generated, so every move is
# reviewable line by line before it happens.
#
#   destination : [candidate sources, oldest first]
#
# A second candidate, where present, is the name the earlier version of this
# tool produced. Listing it is what makes the correction re-runnable.
# ---------------------------------------------------------------------------

LIVE = {
    # cast A, the live set, three repeats
    "out/ex1_casta_gemini_full_r3.jsonl":          ["out/ex1_gemini_L3_r3.jsonl"],
    "out/ex1_casta_gemini_anon_r3.jsonl":          ["out/ex1_gemini_L3anon_r3.jsonl"],
    "out/ex1_casta_gemini_swap_r3.jsonl":          ["out/ex1_gemini_L3swap.jsonl"],
    "out/ex1_casta_gemini_nowidth_r3.jsonl":       ["out/ex1_gemini_L3nw_r3.jsonl"],
    "out/ex1_casta_gemini_nowidth-anon_r3.jsonl":  ["out/ex1_gemini_L1nw_r3.jsonl"],
    "out/ex1_casta_gemini_nowidth-swap_r3.jsonl":  ["out/ex1_gemini_L1swap.jsonl"],
    "out/ex1_casta_gemini_norules_r3.jsonl":       ["out/ex1_gemini_L2_r3.jsonl"],
    "out/ex1_casta_gemini_givenset_r1.jsonl":      ["out/ex1_gemini_L4.jsonl"],

    "out/ex1_casta_gpt_full_r3.jsonl":             ["out/ex1_gpt_L3_r3.jsonl"],
    "out/ex1_casta_gpt_anon_r3.jsonl":             ["out/ex1_gpt_L3anon_r3.jsonl"],
    "out/ex1_casta_gpt_swap_r3.jsonl":             ["out/ex1_gpt_L3swap.jsonl"],
    "out/ex1_casta_gpt_nowidth_r3.jsonl":          ["out/ex1_gpt_L3nw_r3.jsonl"],
    # _r3b, not _r3. The _r3 run was destroyed by a --force on 16 August.
    "out/ex1_casta_gpt_nowidth-anon_r3.jsonl":     ["out/ex1_gpt_L1nw_r3b.jsonl"],
    "out/ex1_casta_gpt_nowidth-swap_r3.jsonl":     ["out/ex1_gpt_L1swap.jsonl"],
    "out/ex1_casta_gpt_norules_r3.jsonl":          ["out/ex1_gpt_L2_r3.jsonl"],
    "out/ex1_casta_gpt_givenset_r1.jsonl":         ["out/ex1_gpt_L4.jsonl"],

    "out/ex1_casta_qwen_full_r3.jsonl":            ["out/ex1_qwen_L3_r3.jsonl"],
    "out/ex1_casta_qwen_anon_r3.jsonl":            ["out/ex1_qwen_L3anon_r3.jsonl"],
    "out/ex1_casta_qwen_swap_r3.jsonl":            ["out/ex1_qwen_L3swap.jsonl"],
    "out/ex1_casta_qwen_nowidth_r3.jsonl":         ["out/ex1_qwen_L3nw_r3.jsonl"],
    "out/ex1_casta_qwen_nowidth-anon_r3.jsonl":    ["out/ex1_qwen_L1nw_r3.jsonl"],
    "out/ex1_casta_qwen_nowidth-swap_r3.jsonl":    ["out/ex1_qwen_L1swap.jsonl"],
    "out/ex1_casta_qwen_norules_r3.jsonl":         ["out/ex1_qwen_L2_r3.jsonl"],
    "out/ex1_casta_qwen_givenset_r1.jsonl":        ["out/ex1_qwen_L4.jsonl"],

    # cast B, the object-set generalisation check, GPT only.
    "out/ex1_castb_gpt_full_r3.jsonl":             ["out/ex1_setb_gpt_L3_r3.jsonl"],
    "out/ex1_castb_gpt_nowidth_r3.jsonl":          ["out/ex1_setb_gpt_L3nw_r3.jsonl"],
    "out/ex1_castb_gpt_nowidth-anon_r3.jsonl":     ["out/ex1_setb_gpt_L1nw_r3.jsonl"],

    # The cast-B single-repeat runs. LIVE, not superseded. Verified 21 August:
    # same probe set, same prompt version 2026-08-16b, and GPT answered 25, 19
    # and 21 of the 108 states differently from repeat 1 of the three-repeat
    # run, so these trials exist nowhere else. They are an independent
    # execution of the same three cells and are reported as a run-to-run
    # stability check. They are NOT pooled into the headline cast-B figures,
    # because cast A is three repeats throughout and a four-repeat cast B would
    # need a tie rule for per-scene majority to buy 0.2 of a point.
    "out/ex1_castb_gpt_full_r1.jsonl": [
        "out/ex1_setb_gpt_L3.jsonl",
        "out/attic/ex1_castb_gpt_full_r1_SUPERSEDED.jsonl"],
    "out/ex1_castb_gpt_nowidth_r1.jsonl": [
        "out/ex1_setb_gpt_L3nw.jsonl",
        "out/attic/ex1_castb_gpt_nowidth_r1_SUPERSEDED.jsonl"],
    "out/ex1_castb_gpt_nowidth-anon_r1.jsonl": [
        "out/ex1_setb_gpt_L1nw.jsonl",
        "out/attic/ex1_castb_gpt_nowidth-anon_r1_SUPERSEDED.jsonl"],

    # The image-on cell, moved out of runs/ so that every EX1 result is in out/.
    # runs/ holds EX2. The old split had one EX1 file living on the EX2 side and
    # that exception had to be explained every time it came up.
    "out/ex1_casta_gpt_nowidth-anon_r3_image.jsonl": ["runs/ex1_L1-nowidth_V_gpt.jsonl"],
}

# Not results. Moved out of reach rather than deleted, because a paid run is
# never thrown away. The reason travels with the file and must state WHY the
# file cannot be used, not merely that something newer exists.
ATTIC = {
    "out/attic/ex1_casta_gemini_norules_r3_DUPLICATE.jsonl": (
        ["out/ex1_gemini_L2.jsonl"],
        "byte-identical (md5) to the live three-repeat file. The extension was "
        "resumed in place instead of into a copy, so both names held the same "
        "486 rows."),
    "out/attic/ex1_casta_qwen_norules_r3_DUPLICATE.jsonl": (
        ["out/ex1_qwen_L2.jsonl"],
        "byte-identical (md5) to the live three-repeat file. The extension was "
        "resumed in place instead of into a copy, so both names held the same "
        "486 rows."),
    "out/attic/ex1_casta_gpt_norules_r1_SUPERSEDED.jsonl": (
        ["out/ex1_gpt_L2.jsonl"],
        "prompt version 2026-08-16b against 2026-08-19a in the live run, so it "
        "cannot be pooled with it. Not a repeat-count question."),
    "out/attic/ex1_casta_gpt_full_r1_SUPERSEDED.jsonl": (
        ["out/ex1_gpt_L3.jsonl"],
        "prompt version 2026-08-15b against 2026-08-16b in the live run, so it "
        "cannot be pooled with it. Not a repeat-count question."),
    "out/attic/ex1_casta_gemini_nowidth_PARTIAL_repair.jsonl": (
        ["out/ex1_gemini_L3nw_repair2.jsonl"],
        "133 retry-diagnostic rows from ex1_repair_failures.py. result and "
        "ex1_prompt_version are null and the schema is attempt1_*/history, so "
        "these are not result rows at all."),
    "out/attic/ex1_casta_gpt_nowidth_PARTIAL_repair.jsonl": (
        ["out/ex1_gpt_L3nw_repair2.jsonl"],
        "124 retry-diagnostic rows from ex1_repair_failures.py. result and "
        "ex1_prompt_version are null and the schema is attempt1_*/history, so "
        "these are not result rows at all."),
    "out/attic/ex1_casta_qwen_nowidth_PARTIAL_repair.jsonl": (
        ["out/ex1_qwen_L3nw_repair.jsonl"],
        "189 retry-diagnostic rows from ex1_repair_failures.py. result and "
        "ex1_prompt_version are null and the schema is attempt1_*/history, so "
        "these are not result rows at all."),
    "out/attic/ex1_casta_gpt_full_SMOKE.jsonl": (
        ["out/ex1_smoke_gpt_L3.jsonl"],
        "10 rows at prompt version 2026-08-15b, all ten states covered by the "
        "live run at a later version. A smoke test, never a result."),
}

# What each live file must contain afterwards. Checked, not assumed: a move that
# put the wrong contents under the right name would otherwise be invisible.
EXPECT_RUNG = {
    "full": "L3", "anon": "L3-anon", "swap": "L3-swap",
    "nowidth": "L3-nowidth", "nowidth-anon": "L1-nowidth",
    "nowidth-swap": "L1-swap", "norules": "L2", "givenset": "L4",
}
EXPECT_ROWS = {("casta", "r3"): 486, ("casta", "r1"): 162,
               ("castb", "r3"): 324, ("castb", "r1"): 108}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse(new_rel):
    """(cast, model, condition, repeats) from a new-scheme file name."""
    stem = os.path.basename(new_rel)[len("ex1_"):-len(".jsonl")]
    parts = stem.split("_")
    return parts[0], parts[1], parts[2], parts[3]


def inspect(path):
    with open(path) as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return len(rows), {r.get("rung") for r in rows}


def plan(root):
    """Work out from disk what still needs moving.

    A destination that already exists is done. Otherwise the first candidate
    source that exists is the one to move. A destination with no candidate on
    disk is unresolved and stops the run.
    """
    moves, done, unresolved = [], [], []
    entries = ([(dst, srcs, "live", "") for dst, srcs in LIVE.items()]
               + [(dst, srcs, "attic", why) for dst, (srcs, why) in ATTIC.items()])
    for dst, srcs, kind, why in entries:
        if (root / dst).exists():
            done.append(dst)
            continue
        found = [s for s in srcs if (root / s).exists()]
        if not found:
            unresolved.append((dst, srcs))
            continue
        moves.append((found[0], dst, kind, why))
    return moves, done, unresolved


def write_attic_readme(root):
    (root / "out/attic").mkdir(parents=True, exist_ok=True)
    (root / "out/attic/README.md").write_text(
        "# Experiment 1 files that are not results\n\n"
        "Kept because a paid run is never thrown away. None of these is a "
        "result and nothing in the thesis cites any of them. The reason each "
        "one cannot be used is stated rather than implied.\n\n"
        "The cast-B single-repeat runs are NOT here. They were filed here by "
        "mistake on 21 August and moved back to `out/`. They are independent "
        "runs at the same prompt version and their trials exist nowhere else.\n\n"
        + "".join("- `%s`\n  %s\n" % (os.path.basename(dst), why)
                  for dst, (_, why) in sorted(ATTIC.items())))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="path to the fourarm package")
    ap.add_argument("--apply", action="store_true",
                    help="actually do it. Without this the tool only prints.")
    ap.add_argument("--verify-only", action="store_true",
                    help="check a finished move and exit")
    args = ap.parse_args()
    root = pathlib.Path(args.root)

    if args.verify_only:
        return verify(root)

    moves, done, unresolved = plan(root)
    print("%d destinations: %d already in place, %d to move, %d unresolved\n"
          % (len(LIVE) + len(ATTIC), len(done), len(moves), len(unresolved)))
    for src, dst, kind, why in moves:
        print("  %-54s -> %s" % (src, dst))
        if why:
            print("       %s" % why)
    if unresolved:
        print("\nUNRESOLVED, no candidate source exists on disk:")
        for dst, srcs in unresolved:
            print("  %s\n     looked for: %s" % (dst, ", ".join(srcs)))
        print("\nResolve these by hand before applying. Do not guess.")
        return 1
    if not moves:
        print("Nothing to move. Verifying instead.\n")
        return verify(root)
    if not args.apply:
        print("\nDry run. Nothing was changed. Add --apply to do it.")
        return 0

    # Manifest first, so the state is recoverable by hand if anything goes wrong.
    before = {src: md5(root / src) for src, _, _, _ in moves}
    (root / "out").mkdir(exist_ok=True)
    (root / "out/attic").mkdir(parents=True, exist_ok=True)
    manifest = root / "out/RENAME_MANIFEST.json"
    history = []
    if manifest.exists():
        old = json.loads(manifest.read_text())
        history = old.get("passes", [old])
    history.append({"before": before, "map": {s: d for s, d, _, _ in moves}})
    manifest.write_text(json.dumps({"passes": history}, indent=1) + "\n")
    print("\nwrote %s (%d passes recorded)" % (manifest, len(history)))

    # Copy, verify the copy, then remove the source. Never a bare rename: the
    # tree is not under version control and a half-finished move would be
    # unrecoverable.
    for src, dst, kind, why in moves:
        s, d = root / src, root / dst
        shutil.copy2(s, d)
        if md5(d) != before[src]:
            print("HASH MISMATCH on %s, stopping. The source is untouched." % src)
            d.unlink()
            return 1
        s.unlink()
    print("moved %d files, every copy hash-verified against its source" % len(moves))

    write_attic_readme(root)
    print("wrote out/attic/README.md")
    return verify(root)


def verify(root):
    """Every live file present, right size, right rung. Checked, not assumed."""
    fails = 0
    for dst in sorted(LIVE):
        p = root / dst
        if not p.exists():
            print("  MISSING  %s" % dst)
            fails += 1
            continue
        cast, model, cond, reps = parse(dst)
        n, rungs = inspect(p)
        want_rows = EXPECT_ROWS.get((cast, reps))
        want_rung = EXPECT_RUNG[cond]
        if not (n == want_rows and rungs == {want_rung}):
            print("  FAIL     %s: %d rows (want %s), rung %s (want %s)"
                  % (os.path.basename(dst), n, want_rows,
                     ",".join(sorted(x or "?" for x in rungs)), want_rung))
            fails += 1
    stray = sorted(p.name for p in (root / "out").glob("ex1_*L[0-9]*.jsonl"))
    if stray:
        print("\n  old-scheme files still loose in out/: %s" % ", ".join(stray))
        fails += len(stray)
    print("\n%d/%d live files verified" % (len(LIVE) - fails, len(LIVE)))
    if fails:
        print("Do not run any analysis until this is clean.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())