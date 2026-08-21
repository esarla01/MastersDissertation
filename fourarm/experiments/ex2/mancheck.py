"""EX2 control: can the model read the pose when asked about nothing else.

WHY THIS EXISTS. Every conflict number in EX2 is a claim about which source
the model believed, the image or the text. That claim is only meaningful if
the image carries the cue at all. If the model cannot tell an upright bottle
from a lying one when asked directly, with no state, no rules and no
allocation to perform, then a low image-following rate says nothing about
the model's cue weighting and everything about the render. The check is a
precondition, not a result.

PER VIEW, NOT PER SCENE. ex2_cam looks at the table obliquely and table_cam
looks straight down. The two poses of a mustard bottle differ mainly in
vertical extent, which a top-down projection largely discards, so the two
views are not interchangeable and each needs its own accuracy. If pose is
legible under one view and not the other, that is the viewpoint result the
design was built to capture, and it is reported rather than engineered
away.

WHAT IS NOT DONE HERE, DELIBERATELY.

  - No retry on a valid but wrong answer. Re-asking until the model agrees
    is how a control stops being one. Transport errors are retried; a
    legible 'upright' for a lying bottle is recorded and kept.
  - No grading of near-misses as correct. The reply is matched exactly
    against the two words the prompt asked for. Anything else is recorded
    as unparseable, because a model that hedges has failed to comply, not
    failed to see, and merging those two would hide a real difference.
  - No exclusion of null scenes. Every null is a lying bottle, so dropping
    them would leave the sample biased toward the pose that happens to be
    easier to see.

RESUMABLE. 88 paid calls should survive a dropped connection, so rows
stream to disk as they are produced and an existing output file is read
back and skipped on restart.

Usage:
    python3 -m experiments.ex2.mancheck --probes out/ex2_capture --dry-run
    python3 -m experiments.ex2.mancheck --probes out/ex2_capture \\
        --model qwen --out runs/ex2_mancheck.jsonl
"""

import argparse
import base64
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.decision.vlm_allocator import openai_chat              # noqa: E402
from experiments.ex2 import prompts as P                         # noqa: E402
from experiments.ex2.labels import describe                      # noqa: E402
from experiments.ex2.run import VIEWS, load_scenes               # noqa: E402

# The two words the prompt asks for. Nothing else counts as an answer.
ANSWERS = ("upright", "lying")


def normalise(reply):
    """The pose the model named, or None if it did not name one.

    Deliberately strict. The prompt says to answer with one word, so the
    reply is stripped of punctuation and whitespace and matched whole. A
    reply that buries the word in a sentence is not scored as correct: it
    is a compliance failure, and counting it as a perception success would
    let a chatty model look more grounded than a terse one.
    """
    if not isinstance(reply, str):
        return None
    word = reply.strip().strip(".,!'\"").lower()
    return word if word in ANSWERS else None


def checks(scenes, views=VIEWS):
    """Every (scene, view) pair to ask about, in a stable order."""
    out = []
    for scene in scenes:
        truth = describe({"state": scene["state"]})
        for view in views:
            if view not in scene["images"]:
                continue
            out.append({"seq": scene["seq"],
                        "view": view,
                        "kind": scene["kind"],
                        "flip_prim": truth["flip_prim"],
                        "true_pose": truth["true_pose"],
                        "image": scene["images"][view]})
    return out


def check_id(row, model):
    """Stable identity for one check, so a restart can skip what is done."""
    return "%s|%s|%s" % (row["seq"], row["view"], model or "none")


def done_ids(out_path):
    """Ids already written, so a resumed run does not pay for them twice."""
    seen = set()
    if not out_path or not os.path.exists(out_path):
        return seen
    for line in open(out_path):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("check_id"):
            seen.add(rec["check_id"])
    return seen


def ask(row, model, model_fn=openai_chat, timeout=60.0, retry_errors=True):
    """One call. Returns the row with reply, answer and correct filled in."""
    with open(row["image"], "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    messages = P.manipulation_check(b64)

    reply, error = None, None
    for attempt in (1, 2):
        try:
            reply = model_fn(messages, timeout=timeout, alias=model)
            error = None
            break
        except Exception as exc:                       # noqa: BLE001
            error = "%s: %s" % (type(exc).__name__, exc)
            if not retry_errors or attempt == 2:
                break
            time.sleep(2.0)

    answer = normalise(reply)
    out = dict(row)
    out["reply"] = reply
    out["answer"] = answer
    out["correct"] = (answer == row["true_pose"]) if answer else None
    out["error"] = error
    return out


def summarise(rows):
    """Accuracy per view, and per view crossed with true pose.

    Split by pose because a model that answers one word for everything
    scores 50 percent overall and 100/0 on the split, and those are very
    different findings.
    """
    tally = {}
    for r in rows:
        for key in ((r["view"], "all"), (r["view"], r["true_pose"])):
            slot = tally.setdefault(key, {"n": 0, "correct": 0,
                                          "unparseable": 0, "error": 0})
            slot["n"] += 1
            if r.get("error") and r.get("answer") is None:
                slot["error"] += 1
            elif r.get("answer") is None:
                slot["unparseable"] += 1
            elif r.get("correct"):
                slot["correct"] += 1
    return tally


def format_summary(tally):
    lines = []
    for (view, pose) in sorted(tally):
        s = tally[(view, pose)]
        scored = s["n"] - s["unparseable"] - s["error"]
        acc = (100.0 * s["correct"] / scored) if scored else float("nan")
        lines.append(
            "%-10s %-8s n=%-3d correct=%-3d acc=%5.1f%% "
            "unparseable=%d error=%d"
            % (view, pose, s["n"], s["correct"], acc,
               s["unparseable"], s["error"]))
    return "\n".join(lines)


def run(capture_dir, out_path=None, model=None, limit=None, dry_run=False,
        views=VIEWS, model_fn=openai_chat, timeout=60.0, retry_errors=True):
    scenes = load_scenes(capture_dir)
    rows = checks(scenes, views=views)
    if limit:
        rows = rows[:limit]

    if dry_run:
        for row in rows:
            print("%-8s %-10s %-8s %s" % (row["seq"], row["view"],
                                          row["true_pose"],
                                          os.path.basename(row["image"])))
        print("--- %d checks, no calls made" % len(rows))
        return []

    seen = done_ids(out_path)
    handle = open(out_path, "a") if out_path else None
    produced = []
    try:
        for row in rows:
            cid = check_id(row, model)
            if cid in seen:
                continue
            out = ask(row, model, model_fn=model_fn, timeout=timeout,
                      retry_errors=retry_errors)
            out["check_id"] = cid
            out["model"] = model
            produced.append(out)
            if handle:
                handle.write(json.dumps(out) + "\n")
                handle.flush()
            print("%-8s %-10s true=%-8s said=%-10s %s"
                  % (out["seq"], out["view"], out["true_pose"],
                     out["answer"] or "?",
                     "ok" if out["correct"] else
                     ("ERROR" if out["error"] else "WRONG")))
    finally:
        if handle:
            handle.close()

    all_rows = produced
    if out_path and os.path.exists(out_path):
        all_rows = [json.loads(x) for x in open(out_path) if x.strip()]
    print("---")
    print(format_summary(summarise(all_rows)))
    return all_rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probes", required=True,
                    help="capture directory holding consults.jsonl")
    ap.add_argument("--out", default=None,
                    help="JSONL to append to; resumed if it exists")
    ap.add_argument("--model", default=None,
                    help="registry alias, e.g. qwen or gpt")
    ap.add_argument("--view", action="append", dest="views", default=None,
                    help="restrict to a view; repeatable")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    views = tuple(args.views) if args.views else VIEWS
    if not args.dry_run and not args.out:
        raise SystemExit("--out is required for a live run: 88 paid calls "
                         "that are not written down cannot be resumed.")

    run(args.probes, out_path=args.out, model=args.model, limit=args.limit,
        dry_run=args.dry_run, views=views, timeout=args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())