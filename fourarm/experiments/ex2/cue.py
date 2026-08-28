"""EX2, smallest runnable form: three conditions, one prompt, one view.

WHAT THIS IS. A thin driver. Every piece of logic it needs already exists
and is harnessed, so this file imports it rather than writing it again:

    transforms.transform    builds the congruent, conflict and dims states
    run.legal_arms          asks the REAL validator which arms are legal
    run.flip_task_id        finds the flip object's task in a captured state
    run.queue_flip_only     drops the partner task, via run.render
    grade.grade              scores the reply
    prompts.build_ex2_prompt  renders the prompt

If any of those change, this file changes with them. A second copy of the
legality rules or the grader would drift from the ones the rest of EX2
uses, and the two would disagree without either being obviously wrong.

WHAT IT DOES. For each captured pair scene it asks the same question three
times, changing only what the text claims about the bottle:

    congruent   text matches the picture. A correct answer proves nothing
                about which source was used, so this is the floor, not a
                finding: it says whether the model can allocate at all.
    conflict    text describes the OTHER pose, completely and
                consistently. Only the picture reveals the disagreement,
                so following one source or the other is now visible.
    dims        resting face and opening withheld. The object's own
                dimensions remain, so the face has to come from the image
                and the opening has to be derived from it.

DEFAULTS, so the ordinary run needs no flags:

    pairs only  every null is a lying bottle, so including them weights
                the sample three to one toward one pose.
    ex2_cam     the overhead camera scored below chance on pose in all
                four model-by-format cells, so a conflict result there
                could not be interpreted.
    N0          one rung. The base prompt with no factor block, which is
                where Q1 and Q2 are read: what the model does when nothing
                points at the image, states the relation or asks for a
                report.
    both models the comparison is the point; neither is a baseline.

Usage:
    python3 -m experiments.ex2.cue --dry-run
    python3 -m experiments.ex2.cue --out runs/ex2_cue.jsonl
    python3 -m experiments.ex2.cue --out runs/ex2_cue.jsonl --repeats 3
"""

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.decision.vlm_allocator import chat              # noqa: E402
from experiments.ex2 import grade as G                           # noqa: E402
from experiments.ex2.prompts import EX2_PROMPT_VERSION           # noqa: E402
from experiments.ex2.run import (flip_task_id, legal_arms,       # noqa: E402
                                 load_scenes, render, select_scenes)

CONDITIONS = ("congruent", "conflict", "dims")
DEFAULT_MODELS = ("qwen", "gpt")
VIEW = "ex2_cam"
RUNG = "N0"


def scenes_for(capture_dir, kind="pair"):
    """Captured scenes to run, nulls dropped by default."""
    out = [s for s in load_scenes(capture_dir)
           if kind is None or s["kind"] == kind]
    if not out:
        raise SystemExit(f"no {kind!r} scenes in {capture_dir}")
    return out


def one_trial(scene, condition, model, model_fn=chat, timeout=90.0):
    """Ask once and grade. Nothing here decides anything on its own."""
    messages, meta = render(scene, condition, RUNG, VIEW)

    text, error = "", None
    for attempt in (1, 2):
        try:
            text = model_fn(messages, timeout=timeout, alias=model)
            error = None
            break
        except Exception as exc:                       # noqa: BLE001
            error = "%s: %s" % (type(exc).__name__, exc)
            if attempt == 2:
                break
            time.sleep(2.0)

    task_id = flip_task_id(scene["state"], meta["flip_prim"])
    legal_true = legal_arms(scene, meta["flip_prim"], task_id)

    # The declared legal set is the same question asked of the pose the
    # TEXT claims. Under congruent and dims the text claims nothing
    # different, so it is the same set: computing it from the other pose
    # would score a correct assignment as wrong.
    declared = meta["declared_pose"]
    if declared is None or declared == meta["true_pose"]:
        legal_decl = legal_true
    else:
        from experiments.ex2.labels import pose_prim
        legal_decl = legal_arms(scene, pose_prim(meta["flip_label"],
                                                 declared), task_id)

    # One task, one arm: the prompt asks for a single assignment, so the
    # round grader would file every reply as an incomplete round.
    row = G.grade(text, meta, legal_true, legal_decl,
                  limits=G.arm_limits(scene["state"]))
    row.update({"seq": scene["seq"], "condition": condition, "model": model,
                "view": VIEW, "rung": RUNG, "error": error,
                "ex2_prompt_version": EX2_PROMPT_VERSION,
                "true_pose": meta["true_pose"],
                "declared_pose": meta["declared_pose"],
                "true_grasp_m": meta["true_grasp_m"],
                "declared_grasp_m": meta.get("declared_grasp_m"),
                "flip_task": task_id,
                "legal_true": sorted(legal_true),
                "legal_declared": sorted(legal_decl)})
    return row


def table(rows):
    """Outcome counts per model per condition.

    Congruent and dims are scored right or wrong against the truth, since
    nothing disagrees with the picture and 'which source' has no meaning.
    Only conflict gets the image and state labels.
    """
    out = []
    head = ("%-6s %-10s %-4s %s" % ("model", "condition", "n", "outcomes"))
    out += [head, "-" * max(len(head), 64)]
    for model in sorted({r["model"] for r in rows}):
        for cond in CONDITIONS:
            sub = [r for r in rows
                   if r["model"] == model and r["condition"] == cond]
            if not sub:
                continue
            counts = {}
            for r in sub:
                counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
            shown = "  ".join("%s=%d" % (k, counts[k])
                              for k in sorted(counts))
            out.append("%-6s %-10s %-4d %s" % (model, cond, len(sub), shown))
        # width_belief only distinguishes anything when the two sources
        # give different numbers, which is conflict alone. Elsewhere it is
        # a tie by construction and reporting it would invent a signal.
        sub = [r for r in rows
               if r["model"] == model and r["condition"] == "conflict"]
        if sub:
            wb = {}
            for r in sub:
                wb[r["width_belief"]] = wb.get(r["width_belief"], 0) + 1
            out.append("%-6s %-10s %-4s %s"
                       % (model, "  width", "",
                          "  ".join("%s=%d" % (k, wb[k])
                                    for k in sorted(wb))))
        out.append("")
    return "\n".join(out).rstrip()


def run(capture_dir, out_path=None, models=DEFAULT_MODELS,
        conditions=CONDITIONS, kind="pair", repeats=1, pair=None,
        limit=None, dry_run=False, model_fn=chat, timeout=90.0):
    scenes = select_scenes(scenes_for(capture_dir, kind), pair)
    # A null has no conflict to declare: its job is to say how much the
    # answer moves when nothing meaningful does, and a null with a
    # falsified state would be measuring something else entirely.
    plan = [(s, c) for s in scenes for c in conditions
            if not (s["kind"] == "null" and c != "congruent")]
    if limit:
        plan = plan[:limit]

    if dry_run:
        for scene, cond in plan:
            print("%-8s %-10s true=%s" % (scene["seq"], cond,
                                          scene["seq"].endswith("_B")))
        print("--- %d scene-conditions x %d model(s) x %d repeat(s) = %d "
              "calls, none made"
              % (len(plan), len(models), repeats,
                 len(plan) * len(models) * repeats))
        return []

    # A row that ERRORED is not an answer. Skipping it on resume is how a
    # run of missing-key rows once re-reported itself as complete having
    # made no calls at all.
    done = set()
    if out_path and os.path.exists(out_path):
        for line in open(out_path):
            if line.strip():
                r = json.loads(line)
                if r.get("error") is None and r.get("outcome") != "unparseable":
                    done.add(r.get("trial_id"))

    handle = open(out_path, "a") if out_path else None
    try:
        for model in models:
            for rep in range(1, repeats + 1):
                for scene, cond in plan:
                    tid = "%s|%s|%s|r%d" % (scene["seq"], cond, model, rep)
                    if tid in done:
                        continue
                    row = one_trial(scene, cond, model, model_fn=model_fn,
                                    timeout=timeout)
                    row["trial_id"] = tid
                    row["repeat"] = rep
                    if handle:
                        handle.write(json.dumps(row) + "\n")
                        handle.flush()
                    print("%-5s r%d %-8s %-10s -> %-16s %s"
                          % (model, rep, scene["seq"], cond, row["outcome"],
                             json.dumps(row.get("assignments"))))
    finally:
        if handle:
            handle.close()

    all_rows = []
    if out_path and os.path.exists(out_path):
        seen = {}
        for line in open(out_path):
            if line.strip():
                r = json.loads(line)
                seen[r.get("trial_id")] = r      # later wins on retry
        all_rows = list(seen.values())
    print()
    print(table(all_rows))
    return all_rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probes", default="out/ex2_capture")
    ap.add_argument("--out", default=None)
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--condition", action="append", dest="conditions",
                    default=None, choices=CONDITIONS)
    ap.add_argument("--kind", default="pair", choices=("pair", "null", "all"))
    ap.add_argument("--pair", default=None, help="one pair id, e.g. p03")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if not a.dry_run and not a.out:
        raise SystemExit("--out is required for a live run: paid calls that "
                         "are not written down cannot be resumed.")
    run(a.probes, out_path=a.out,
        models=tuple(x.strip() for x in a.models.split(",") if x.strip()),
        conditions=tuple(a.conditions) if a.conditions else CONDITIONS,
        kind=None if a.kind == "all" else a.kind,
        repeats=a.repeats, pair=a.pair, limit=a.limit, dry_run=a.dry_run,
        timeout=a.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())