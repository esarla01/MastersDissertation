"""EX2 probe: what the model says it SEES, alongside the pose it names.

mancheck.py asks for one word and nothing else, which keeps it a clean
perception number. This asks the model to describe the bottle first and
then name the pose, which is a different question: not only whether it can
tell, but what it reports looking at.

The two are kept apart on purpose. Reasoning aloud can change the answer,
so a description-first accuracy is not comparable to the terse one, and
folding them into one script would quietly replace a control that already
has results.

WHAT IT IS FOR. Two things the terse check cannot show:

  - Whether the model is reading the object or guessing from context. A
    reply describing the cap and label is looking; one saying bottles
    usually stand up is not, and that would explain a lopsided score.
  - Whether the failures are all one kind. Describing the wrong object is
    occlusion; describing the bottle correctly and still naming the wrong
    pose is a perception limit.

REPLY FORMAT. Two lines, because free prose cannot be tallied and a JSON
schema invites the model to fill fields rather than look:

    SEES: <one sentence about the bottle>
    POSE: upright

Anything else is recorded as unparseable rather than wrong, since failing
to follow a format is not failing to see.

Usage:
    python3 -m experiments.ex2.seecheck --probes out/ex2_capture --dry-run
    python3 -m experiments.ex2.seecheck --probes out/ex2_capture \\
        --model qwen --out runs/ex2_seecheck.jsonl
    # only the scenes the terse check got wrong, plus a comparison set
    python3 -m experiments.ex2.seecheck --probes out/ex2_capture \\
        --model qwen --seqs p02_A,n02_A,m02_B --out runs/ex2_see_fail.jsonl
"""

import argparse
import math
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
from experiments.ex2 import prompts as P                          # noqa: E402
from experiments.ex2.labels import describe                      # noqa: E402
from experiments.ex2.run import VIEWS, load_scenes               # noqa: E402

ANSWERS = ("upright", "lying")

# Defaults chosen so the ordinary run needs no flags.
#
#   pairs only   every null is a LYING bottle, so the full set is 33 lying
#                against 11 upright and any overall accuracy is weighted
#                three to one toward the easier pose. Each pair has an _A
#                lying and a _B upright member, so pairs alone give 11 and
#                11, balanced by construction.
#   ex2_cam      the overhead camera scored 0 of 11 upright in the terse
#                check: a top-down projection discards the vertical extent
#                that separates the poses, so it carries no cue to probe.
#   both models  the comparison is the point, and one is not a baseline
#                for the other.
DEFAULT_KIND = "pair"
DEFAULT_VIEWS = ("ex2_cam",)
DEFAULT_MODELS = ("qwen", "gpt")
DEFAULT_FORMATS = ("terse", "describe")
DEFAULT_REPEATS = 1

# A two-way forced choice, so an uninformed guesser scores this. Cells
# BELOW it are not merely uninformative: the view is inverting the cue.
CHANCE = 50.0
DEFAULT_REPEATS = 1
DEFAULT_REPEATS = 1

PROMPT = ("Look at the mustard bottle on the table. Reply with exactly "
          "two lines and nothing else:\n"
          "SEES: <one sentence describing the bottle and how you can tell "
          "which way it is resting>\n"
          "POSE: <upright or lying>")


def messages_for(image_b64, fmt):
    """The probe for one reply format. Only the picture, never the state.

    terse     one word, nothing else. The REAL manipulation_check from
              prompts.py, so the two probes cannot drift apart.
    describe  a sentence about the bottle first, then the pose.

    These are not one probe refined. Generating a description first can
    change the answer, so each needs its own number and neither is a
    correction of the other.
    """
    if fmt == "terse":
        return P.manipulation_check(image_b64)
    if fmt != "describe":
        raise ValueError(f"unknown format {fmt!r}; expected one of "
                         f"{list(DEFAULT_FORMATS)}. Format is never "
                         f"defaulted: a terse row recorded as describe "
                         f"would merge two different measurements.")
    return [
        {"role": "system", "content": "Follow the reply format exactly."},
        {"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + image_b64}},
        ]},
    ]


def parse(reply, fmt="describe"):
    """(sees, pose) from a reply. Either may be None.

    A terse reply is one bare word and has no description, so it is matched
    whole. Anything longer is a compliance failure, not a perception one,
    and is recorded as unparseable rather than scored wrong.
    """
    if fmt == "terse":
        word = (reply or "").strip().strip(".,!'\"").lower()
        return None, (word if word in ANSWERS else None)
    sees, pose = None, None
    for line in (reply or "").splitlines():
        line = line.strip()
        low = line.lower()
        if low.startswith("sees:"):
            sees = line[5:].strip() or None
        elif low.startswith("pose:"):
            word = low[5:].strip().strip(".,!'\"")
            pose = word if word in ANSWERS else None
    return sees, pose


def probes(scenes, views, seqs=None, kind=None):
    """One probe per scene per view, in a stable order.

    kind='pair' drops the nulls, and that is what balances the sample.
    Every null is a LYING bottle, so the full set is 33 lying against 11
    upright and any overall accuracy is weighted three to one toward one
    pose. Each pair contributes an _A lying and a _B upright member, so
    restricting to pairs gives 11 and 11 with no subsetting.
    """
    out = []
    for scene in scenes:
        if seqs and scene["seq"] not in seqs:
            continue
        if kind and scene["kind"] != kind:
            continue
        truth = describe({"state": scene["state"]})
        for view in views:
            if view in scene["images"]:
                out.append({"seq": scene["seq"], "view": view,
                            "kind": scene["kind"],
                            "true_pose": truth["true_pose"],
                            "image": scene["images"][view]})
    return out


def ask(row, model, fmt, model_fn=openai_chat, timeout=60.0):
    with open(row["image"], "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    reply, error = None, None
    for attempt in (1, 2):
        try:
            reply = model_fn(messages_for(b64, fmt), timeout=timeout,
                             alias=model)
            error = None
            break
        except Exception as exc:                       # noqa: BLE001
            error = "%s: %s" % (type(exc).__name__, exc)
            if attempt == 2:
                break
            time.sleep(2.0)
    sees, pose = parse(reply, fmt)
    out = dict(row)
    out.update({"format": fmt, "reply": reply, "sees": sees, "pose": pose,
                "correct": (pose == row["true_pose"]) if pose else None,
                "error": error})
    return out


def summarise(rows):
    """Counts per view and per view crossed with true pose.

    Split by pose because a model answering one word for everything scores
    near half overall, which reads as partial competence, and only the
    split shows it at 100 and 0.
    """
    tally = {}
    for r in rows:
        for key in ((r["view"], "all"), (r["view"], r["true_pose"])):
            slot = tally.setdefault(key, {"n": 0, "correct": 0,
                                          "unparseable": 0, "error": 0,
                                          "described": 0})
            slot["n"] += 1
            if r.get("sees"):
                slot["described"] += 1
            if r.get("error") and r.get("pose") is None:
                slot["error"] += 1
            elif r.get("pose") is None:
                slot["unparseable"] += 1
            elif r.get("correct"):
                slot["correct"] += 1
    return tally


def format_summary(tally):
    lines = []
    for key in sorted(tally):
        view, pose = key
        s = tally[key]
        scored = s["n"] - s["unparseable"] - s["error"]
        acc = (100.0 * s["correct"] / scored) if scored else float("nan")
        lines.append("%-10s %-8s n=%-3d correct=%-3d acc=%5.1f%% "
                     "described=%-3d unparseable=%d error=%d"
                     % (view, pose, s["n"], s["correct"], acc,
                        s["described"], s["unparseable"], s["error"]))
    return "\n".join(lines)


def wilson(k, n, z=1.96):
    """Wilson score interval for k successes in n trials, as percentages.

    Wilson rather than the normal approximation because several cells sit
    at exactly 0 or 100 percent, where the normal interval runs outside
    [0, 100] and reports impossible bounds. Wilson stays inside and stays
    sensible at n around ten, which is what every cell here has.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return (100.0 * max(0.0, centre - half), 100.0 * min(1.0, centre + half))


def majority(answers):
    """The answer an image gave most often, or None if it never gave one.

    Ties break to None rather than to either label: an image that split
    evenly across repeats has no stable answer, and calling it correct
    half the time would smuggle repeat noise into the image-level count.
    """
    counts = {}
    for a in answers:
        if a is not None:
            counts[a] = counts.get(a, 0) + 1
    if not counts:
        return None
    best = max(counts.values())
    winners = [a for a, c in counts.items() if c == best]
    return winners[0] if len(winners) == 1 else None


def cell_stats(rows):
    """Image-level accuracy, its interval, and the spread across repeats.

    TWO uncertainties, kept apart because they answer different questions.

      interval  over IMAGES, using each image's majority answer. Pooling
                every repeat would treat three calls on one picture as
                three independent observations and report more confidence
                than the design earns.
      spread    the per-run accuracies. This is the one that moves: the
                same cell gave 2 of 11 and later 4 of 11 on identical
                images, and no interval over images would have shown it.
    """
    by_image, by_run = {}, {}
    for r in rows:
        by_image.setdefault(r["seq"], []).append(r["pose"])
        by_run.setdefault(r.get("repeat", 0), []).append(r)

    scored = [(seq, majority(a)) for seq, a in by_image.items()]
    truth = {r["seq"]: r["true_pose"] for r in rows}
    usable = [(s, m) for s, m in scored if m is not None]
    k = sum(1 for s, m in usable if m == truth[s])
    n = len(usable)

    runs = []
    for _, rr in sorted(by_run.items()):
        got = [x for x in rr if x["pose"] is not None]
        if got:
            runs.append(100.0 * sum(1 for x in got if x["correct"]) / len(got))
    return {"k": k, "n": n, "images": len(by_image),
            "unstable": len(scored) - len(usable),
            "ci": wilson(k, n), "runs": runs}


def wilson(correct, n, z=1.96):
    """95 percent interval for a proportion, Wilson score.

    Wilson rather than the normal approximation because several cells sit
    at exactly 0 or 100 percent, where the normal interval runs outside
    the range and reports impossible bounds, and because n is 11 per pose,
    which is small enough for the approximation to be poor everywhere.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = correct / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def majority(answers, truth):
    """Per-image verdict across repeats: correct if MOST repeats were.

    The interval is computed over IMAGES, not over trials. Pooling repeats
    would treat three answers about one picture as three independent
    observations and report more confidence than the sample carries.
    Repeat spread is reported separately as the stability measure.
    """
    scored = [a for a in answers if a is not None]
    if not scored:
        return None
    hits = sum(1 for a in scored if a == truth)
    return hits * 2 > len(scored)


def cell_stats(rows):
    """(images, correct_images, lo, hi, per_run_pcts, unusable)."""
    by_image = {}
    by_run = {}
    unusable = 0
    for r in rows:
        by_image.setdefault(r["seq"], []).append(r["pose"])
        by_run.setdefault(r.get("repeat", 0), []).append(r)
        if r["pose"] is None:
            unusable += 1
    truth = {r["seq"]: r["true_pose"] for r in rows}
    verdicts = [majority(v, truth[k]) for k, v in by_image.items()]
    verdicts = [v for v in verdicts if v is not None]
    n, ok = len(verdicts), sum(1 for v in verdicts if v)
    lo, hi = wilson(ok, n)

    runs = []
    for _, sub in sorted(by_run.items()):
        scored = [r for r in sub if r["pose"] is not None]
        if scored:
            runs.append(100.0 * sum(1 for r in scored if r["correct"])
                        / len(scored))
    return n, ok, lo, hi, runs, unusable


def wilson(correct, n, z=1.96):
    """95 percent interval for a proportion, Wilson rather than normal.

    The normal approximation puts bounds outside 0 to 100 when a cell sits
    at or near either end, and several cells here are exactly 0 or 100.
    Wilson stays inside the range and behaves at small n, which is what
    eleven images per pose is.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = correct / n
    d = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z / d) * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return (100.0 * max(0.0, centre - half), 100.0 * min(1.0, centre + half))


def majority(votes):
    """The answer an image got most often, or None if unusable or tied.

    Repeats of one image are not independent trials, so the image is the
    unit and its repeats collapse to one verdict. Pooling them instead
    would treat three looks at the same picture as three pictures and
    report an interval far tighter than the evidence supports.
    """
    usable = [v for v in votes if v is not None]
    if not usable:
        return None
    counts = {v: usable.count(v) for v in set(usable)}
    best = max(counts.values())
    winners = [v for v, c in counts.items() if c == best]
    return winners[0] if len(winners) == 1 else None


def cell_stats(rows):
    """Per-image majority verdicts, plus per-run accuracy for the spread."""
    by_image = {}
    by_run = {}
    for r in rows:
        by_image.setdefault(r["seq"], []).append(r)
        by_run.setdefault(r.get("repeat", 1), []).append(r)

    images, correct, unusable = 0, 0, 0
    for seq, votes in by_image.items():
        verdict = majority([v["pose"] for v in votes])
        if verdict is None:
            unusable += 1
            continue
        images += 1
        if verdict == votes[0]["true_pose"]:
            correct += 1

    spread = []
    for rep in sorted(by_run):
        scored = [r for r in by_run[rep] if r["pose"] is not None]
        if scored:
            spread.append(100.0 * sum(1 for r in scored if r["correct"])
                          / len(scored))
    return {"images": images, "correct": correct, "unusable": unusable,
            "spread": spread}


def table(rows):
    """One line per cell per pose, with an interval and the run spread.

    TWO uncertainties, kept apart because they answer different questions.
    The interval covers sampling across IMAGES: with eleven per pose it is
    wide, and no number of repeats narrows it. The spread covers run to run
    variability of the MODEL on the same pictures, which is the thing that
    moved between two runs of the same cell and which only repeats can
    measure. Reporting one and not the other would hide half the story.
    """
    keys = sorted({(r["model"], r.get("format", "describe"), r["view"])
                   for r in rows})
    head = ("%-6s %-9s %-10s %-8s %-7s %-8s %-15s %-9s %s"
            % ("model", "format", "view", "pose", "images", "acc",
               "95% CI", "unusable", "runs"))
    out = [head, "-" * len(head)]
    for model, fmt, view in keys:
        base = [r for r in rows if r["model"] == model
                and r.get("format", "describe") == fmt and r["view"] == view]
        for pose in ("lying", "upright", "ALL"):
            sub = base if pose == "ALL" else [r for r in base
                                              if r["true_pose"] == pose]
            if not sub:
                continue
            st = cell_stats(sub)
            n, ok = st["images"], st["correct"]
            acc = (100.0 * ok / n) if n else float("nan")
            lo, hi = wilson(ok, n)
            flag = ""
            if n and hi < CHANCE:
                flag = "  below chance"
            out.append("%-6s %-9s %-10s %-8s %2d/%-4d %6.1f%% %6.1f-%-8.1f %-9d %s%s"
                       % (model, fmt, view, pose, ok, n, acc, lo, hi,
                          st["unusable"],
                          ",".join("%.0f" % x for x in st["spread"]), flag))
        out.append("")
    return "\n".join(out).rstrip()


def run(capture_dir, out_path=None, models=DEFAULT_MODELS,
        formats=DEFAULT_FORMATS, views=DEFAULT_VIEWS, seqs=None,
        kind=DEFAULT_KIND, repeats=DEFAULT_REPEATS, limit=None,
        dry_run=False, model_fn=openai_chat, timeout=60.0):
    plan = probes(load_scenes(capture_dir), views, seqs, kind)
    if limit:
        plan = plan[:limit]

    if dry_run:
        for r in plan:
            print("%-8s %-10s %-8s %s" % (r["seq"], r["view"], r["true_pose"],
                                          os.path.basename(r["image"])))
        print("--- %d scenes x %d model(s) x %d format(s) x %d repeat(s) "
              "= %d calls, none made"
              % (len(plan), len(models), len(formats), repeats,
                 len(plan) * len(models) * len(formats) * repeats))
        return []

    # A row that ERRORED is not an answer. Skipping it on resume is how a
    # whole run of missing-key rows survived a re-run and reported itself
    # as complete, having made no calls at all.
    done = set()
    if out_path and os.path.exists(out_path):
        for line in open(out_path):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("error") is None and r.get("reply") is not None:
                done.add(r.get("probe_id"))

    handle = open(out_path, "a") if out_path else None
    try:
        for rep in range(repeats):
            for model in models:
                for fmt in formats:
                    for r in plan:
                        pid = "%s|%s|%s|%s|%d" % (r["seq"], r["view"],
                                                  model, fmt, rep)
                        if pid in done:
                            continue
                        out = ask(r, model, fmt, model_fn=model_fn,
                                  timeout=timeout)
                        out["probe_id"] = pid
                        out["model"] = model
                        out["repeat"] = rep
                        if handle:
                            handle.write(json.dumps(out) + "\n")
                            handle.flush()
                        print("%-5s %-9s r%d %-8s true=%-8s said=%-8s %s"
                              % (model, fmt, rep, out["seq"],
                                 out["true_pose"], out["pose"] or "?",
                                 (out["sees"] or "")[:40]))
    finally:
        if handle:
            handle.close()

    all_rows = []
    if out_path and os.path.exists(out_path):
        # Later rows win: a retried probe replaces the errored one it
        # replaced, rather than both appearing in the table.
        seen = {}
        for line in open(out_path):
            if line.strip():
                r = json.loads(line)
                seen[r.get("probe_id")] = r
        # Keyed on probe_id, so a retried answer REPLACES the error it
        # supersedes instead of both appearing. Rows that only ever
        # errored stay visible in the unusable column rather than being
        # dropped, since a silently shrinking denominator is worse than a
        # visible failure.
        all_rows = list(seen.values())
    print()
    print(table(all_rows))
    return all_rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probes", default="out/ex2_capture")
    ap.add_argument("--out", default="runs/ex2_seecheck.jsonl")
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS),
                    help="registry aliases, comma separated")
    ap.add_argument("--formats", default=",".join(DEFAULT_FORMATS),
                    help="terse, describe, or both")
    ap.add_argument("--repeats", type=int, default=DEFAULT_REPEATS,
                    help="ask each image this many times. Repeats measure "
                         "run to run variability of the model; they do NOT "
                         "narrow the interval, which is set by how many "
                         "images there are.")
    ap.add_argument("--view", action="append", dest="views", default=None,
                    help="default is the oblique camera only")
    ap.add_argument("--kind", default=DEFAULT_KIND,
                    choices=("pair", "null", "all"),
                    help="default 'pair' keeps the two poses balanced")
    ap.add_argument("--seqs", default=None,
                    help="comma separated scene ids, overrides --kind")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    run(a.probes, out_path=None if a.dry_run else a.out,
        models=tuple(x.strip() for x in a.models.split(",") if x.strip()),
        formats=tuple(x.strip() for x in a.formats.split(",") if x.strip()),
        views=tuple(a.views) if a.views else DEFAULT_VIEWS,
        seqs=set(a.seqs.split(",")) if a.seqs else None,
        kind=None if (a.kind == "all" or a.seqs) else a.kind,
        repeats=a.repeats, limit=a.limit, dry_run=a.dry_run,
        timeout=a.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())