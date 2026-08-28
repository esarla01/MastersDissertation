"""EX2 control: can the model read the resting face when asked about
nothing else.

WHY THIS EXISTS. Every conflict number in EX2 is a claim about which source
the model believed, the image or the text. That claim is only meaningful if
the image carries the cue at all. If the model cannot tell which face the
block is resting on when asked directly, with no state, no rules and no
allocation to perform, then a low image-following rate says nothing about
the model's cue weighting and everything about the render. The check is a
precondition, not a result.

TWO-WAY SINCE 2026-08-27. The probe asks which of the block's two faces is
down, so chance is one in two. It was three-way, and the third option was
the middle face: over 81 answered trials no model separated it from
large_face (58 percent, Fisher p = 0.76) while the same model answered a
plain standing-or-flat question 18 times out of 18. The design dropped the
face rather than keep a discrimination nothing could read; the evidence is
runs/ex2_q1_cue_*.jsonl.

What that costs is real and is stated where the results are read: this
probe can no longer tell a model that derives the opening from geometry
apart from one that reads posture and applies a rule. Both faces differ in
posture as well as geometry now.

PER VIEW, NOT PER SCENE. ex2_cam looks at the table obliquely and table_cam
looks straight down. The three resting faces differ mainly in vertical
extent, which a top-down projection largely discards, so the two views are
not interchangeable and each needs its own accuracy. If the face is legible
under one view and not the other, that is the viewpoint result the design
was built to capture, and it is reported rather than engineered away.

WHAT IS NOT DONE HERE, DELIBERATELY.

  - No retry on a valid but wrong answer. Re-asking until the model agrees
    is how a control stops being one. Transport errors are retried; a
    legible 'small_face' for a block on its large face is recorded and kept.
  - No grading of near-misses as correct. The reply is matched exactly
    against the three words the prompt asked for. Anything else is recorded
    as unparseable, because a model that hedges has failed to comply, not
    failed to see, and merging those two would hide a real difference.
  - No exclusion of null scenes. Dropping them would leave the sample
    biased toward whichever face happens to be easier to see.

RESUMABLE. 88 paid calls should survive a dropped connection, so rows
stream to disk as they are produced and an existing output file is read
back and skipped on restart. Skipped on ANSWERS, not on lines: a row that
errored is retried, or a missing API key turns into a file of failures
that reports itself as a finished run. The retry replaces the failure in
the summary rather than being counted beside it.

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

from core.decision.vlm_allocator import chat              # noqa: E402
from experiments.ex2 import prompts as P                         # noqa: E402
from experiments.ex2.labels import describe, require_face        # noqa: E402
from experiments.ex2.run import VIEWS, load_scenes               # noqa: E402

# The three words the prompt asks for. Nothing else counts as an answer.
# Taken from the prompt module rather than spelled out here, so the probe
# and the thing that grades it cannot drift apart.
ANSWERS = P.RESTING_FACES

# DERIVED from the vocabulary, never typed. It was 100.0/3.0 until
# 2026-08-27 and the probe is now two-way; a literal left behind would have
# reported a coin as a finding. A cell below chance is not merely
# uninformative: the view is inverting the cue.
CHANCE = 100.0 / len(ANSWERS)


def normalise(reply):
    """The resting face the model named, or None if it did not name one.

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


def checks(scenes, views=VIEWS, seqs=None):
    """Every (scene, view) pair to ask about, in a stable order.

    seqs restricts to named scenes, which is how a sample is drawn before
    the whole set is paid for. Filtering here rather than by `limit` means
    the sample is the one asked for: limit takes the first N in trail
    order, which is a different set and silently so.
    """
    out = []
    for scene in scenes:
        if seqs is not None and scene["seq"] not in seqs:
            continue
        truth = describe({"state": scene["state"]})
        for view in views:
            if view not in scene["images"]:
                continue
            out.append({"seq": scene["seq"],
                        "view": view,
                        "kind": scene["kind"],
                        "flip_prim": truth["flip_prim"],
                        "true_pose": truth["true_pose"],
                        "true_face": require_face(truth["true_pose"],
                                                  P.RESTING_FACES),
                        "image": scene["images"][view]})
    return out


def check_id(row, model):
    """Stable identity for one check, so a restart can skip what is done."""
    return "%s|%s|%s" % (row["seq"], row["view"], model or "none")


def assert_same_probe(out_path):
    """Refuse an output file that was written by a DIFFERENT question.

    The check_id is seq|view|model and carries no vocabulary, so a two-way
    run resuming into a three-way file finds every id already present,
    makes no calls at all, and reports the old answers as if they were
    new. Every id in runs/ex2_q1_cue_*.jsonl collides that way.

    Two signals, because rows written before 2026-08-27 carry no stamp:
    an explicit n_options that disagrees, or any face word outside the
    current vocabulary. Either means the file answers a different
    question, and the only safe move is to stop and let the caller choose
    a new path -- never to merge, and never to overwrite evidence.
    """
    if not out_path or not os.path.exists(out_path):
        return
    for line in open(out_path):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        n = rec.get("n_options")
        stale = [w for w in (rec.get("true_face"), rec.get("answer"))
                 if w is not None and w not in ANSWERS]
        if (n is not None and n != len(ANSWERS)) or stale:
            raise SystemExit(
                "%s was written by a different probe.%s%s This one offers "
                "%d options (%s). Resuming would find every check_id "
                "already present, make no calls, and report the old "
                "answers as new. Write to a new path and leave that file "
                "as it is."
                % (out_path,
                   (" It records %d options per question." % n)
                   if n is not None else "",
                   (" It contains the answer %r, which is not on offer."
                    % stale[0]) if stale else "",
                   len(ANSWERS), ", ".join(ANSWERS)))


def done_ids(out_path):
    """Ids already ANSWERED, so a resumed run does not pay for them twice.

    A row that errored is not an answer. It carries a check_id like any
    other, so counting it as done retires the check permanently and the
    call is never made: seven key-failure rows survived two reruns of
    runs/ex2_q1_cue_gpt_r1.jsonl that way, and the summary reported the
    remainder as if the sample were whole. solo.py and cue.py already
    exclude them on resume; this is the same rule.

    An UNPARSEABLE reply is left alone and stays done. It is a real
    observation about the model, not a lost call, and re-asking until the
    format is obeyed is the same as re-asking until the answer is right,
    which is what this control exists to avoid.
    """
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
        if not rec.get("check_id"):
            continue
        # The summariser's own definition of a failed call, so the two
        # cannot disagree about what a row is.
        if rec.get("error") and rec.get("answer") is None:
            continue
        seen.add(rec["check_id"])
    return seen


def ask(row, model, model_fn=chat, timeout=60.0, retry_errors=True):
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
    # One vocabulary: the registry, the state and the probe all say
    # small_face / edge / large_face. require_face is a guard, not a
    # translation, and it is checked against the SCHEMA's enum so a
    # divergence between the registry and what the model may reply with
    # surfaces here rather than as a cell of zeros.
    out["true_face"] = require_face(row["true_pose"], P.RESTING_FACES)
    out["correct"] = (answer == out["true_face"]) if answer else None
    out["error"] = error
    # The VOCABULARY the question was asked in, on every row. Without it a
    # file records only what the model said and not what it was offered,
    # and a three-way answer is indistinguishable from a two-way one. That
    # is not hypothetical: this probe was three-way until 2026-08-27 and
    # its runs are retained on disk.
    out["n_options"] = len(ANSWERS)
    out["chance_pct"] = CHANCE
    return out


def summarise(rows):
    """Accuracy per view, and per view crossed with the true face.

    Split by face because a model that answers one word for everything
    scores a third overall and 100/0/0 on the split, and those are very
    different findings.
    """
    tally = {}
    for r in rows:
        face = r.get("true_face") or r["true_pose"]
        for key in ((r["view"], "all"), (r["view"], face)):
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
    for (view, face) in sorted(tally):
        s = tally[(view, face)]
        scored = s["n"] - s["unparseable"] - s["error"]
        acc = (100.0 * s["correct"] / scored) if scored else float("nan")
        lines.append(
            "%-10s %-11s n=%-3d correct=%-3d acc=%5.1f%% "
            "unparseable=%d error=%d%s"
            % (view, face, s["n"], s["correct"], acc,
               s["unparseable"], s["error"],
               "  BELOW CHANCE" if scored and acc < CHANCE else ""))
    lines.append("chance is %.1f%%: a %d-way forced choice."
                 % (CHANCE, len(ANSWERS)))
    return "\n".join(lines)


def run(capture_dir, out_path=None, model=None, limit=None, dry_run=False,
        views=VIEWS, seqs=None, model_fn=chat, timeout=60.0,
        retry_errors=True):
    # present_ur=False: this probe shows a picture and asks one question.
    # It never assigns an arm, so the idle set means nothing to it, and
    # normalising one would be work that can fail on a scene built for
    # perception alone.
    scenes = load_scenes(capture_dir, present_ur=False)
    rows = checks(scenes, views=views, seqs=seqs)
    if seqs is not None:
        missing = set(seqs) - {r["seq"] for r in rows}
        if missing:
            raise SystemExit(
                f"asked for scenes {sorted(missing)} that are not in "
                f"{capture_dir}. A sample quietly reduced to what happened "
                f"to be present is not the sample that was chosen.")
    if limit:
        rows = rows[:limit]

    if dry_run:
        for row in rows:
            print("%-8s %-10s %-11s %s" % (row["seq"], row["view"],
                                           row["true_face"],
                                           os.path.basename(row["image"])))
        print("--- %d checks, no calls made" % len(rows))
        return []

    assert_same_probe(out_path)
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
            print("%-8s %-10s true=%-11s said=%-11s %s"
                  % (out["seq"], out["view"], out["true_face"],
                     out["answer"] or "?",
                     "ok" if out["correct"] else
                     ("ERROR" if out["error"] else "WRONG")))
    finally:
        if handle:
            handle.close()

    all_rows = produced
    if out_path and os.path.exists(out_path):
        # Later wins. A check that errored and was retried appears twice,
        # and reading both would count one scene as an error AND as an
        # answer, inflating n above the number of checks that exist.
        by_id = {}
        for x in open(out_path):
            if not x.strip():
                continue
            rec = json.loads(x)
            by_id[rec.get("check_id") or len(by_id)] = rec
        all_rows = list(by_id.values())
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
    ap.add_argument("--seqs", default=None,
                    help="comma list of scene ids, to probe a sample before "
                         "paying for the whole set")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    views = tuple(args.views) if args.views else VIEWS
    if not args.dry_run and not args.out:
        raise SystemExit("--out is required for a live run: 88 paid calls "
                         "that are not written down cannot be resumed.")

    run(args.probes, out_path=args.out, model=args.model, limit=args.limit,
        dry_run=args.dry_run, views=views, timeout=args.timeout,
        seqs=(tuple(x.strip() for x in args.seqs.split(",") if x.strip())
              if args.seqs else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())