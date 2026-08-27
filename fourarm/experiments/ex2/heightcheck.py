"""EX2 probe: how TALL the model thinks the block is, with no face named.

WHY THIS EXISTS. mancheck asks which of three faces is down and GPT scores
41 percent over 99 trials, but the shape of those errors does not say what
failed. Two very different things produce it:

  - the model cannot resolve 0.100 m of vertical extent from 0.050 m in
    this render, in which case the picture is short and no wording will
    fix it; or
  - it resolves them and cannot map the answer onto a face name, in which
    case the render is fine and the three-way naming was the obstacle.

mancheck cannot separate those, because a forced choice among three words
collapses everything the model saw into one of three buckets. A model that
reads 70 mm and must pick from large_face, edge and small_face is
indistinguishable from one that reads 50 mm. This probe asks for the
number instead.

WHAT IS DIFFERENT, AND WHY EACH PART.

  no face names anywhere.  Not in the question and not in the answer. The
        naming step is the thing under test, so leaving a single face word
        in the prompt would put it back.
  a FREE number, not a choice of three.  A three-way choice over
        130 / 100 / 50 would be isomorphic to mancheck and could not show
        WHERE the estimate sits. The free number is the whole point: it
        shows the direction and the size of the error, not just its
        presence.
  the three edge lengths ARE given.  Nothing in the render carries a
        metric scale, so without them the number is unscorable and the
        probe would measure whether the model can guess absolute size from
        a picture of a table. They are given as a set of lengths, never as
        faces, so no face vocabulary leaks in.
  millimetres, not metres.  A model asked for metres answers 0.13 and 0.1,
        and a dropped trailing zero is then a factor of ten. Integers in
        millimetres have no such failure.

HOW IT IS SCORED. Two ways, reported together and never one instead of
the other:

  raw       the signed error in millimetres. This is what mancheck cannot
            show, and it is what says whether the model is reading height
            at all.
  snapped   the reported height rounded to the nearest of the three true
            heights, which is exactly mancheck's three-way call. Reported
            so the two probes sit side by side on one scale; chance is one
            in three. A snapped score is a DERIVED number and is never
            recorded as if the model had named a face.

WHAT IS NOT DONE HERE, DELIBERATELY. The same rules mancheck states, for
the same reasons: transport errors are retried and a legible but wrong
number is not; a reply that is prose rather than a number is recorded as
unparseable rather than wrong, because failing to follow a format is not
failing to see; and this is a SEPARATE script, so a control that already
has results is never quietly replaced by its successor.

Usage:
    python3 -m experiments.ex2.heightcheck --probes out/ex2_capture_block \\
        --dry-run
    python3 -m experiments.ex2.heightcheck --probes out/ex2_capture_block \\
        --model gpt --view ex2_cam --out runs/ex2_q1_height_gpt_r1.jsonl
    # the same ten positions the cue check used
    python3 -m experiments.ex2.heightcheck --probes out/ex2_capture_block \\
        --model gpt --view ex2_cam --seqs e00_U,e00_L,e00_S \\
        --out runs/ex2_q1_height_gpt_r1.jsonl
"""

import argparse
import base64
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.decision.vlm_allocator import openai_chat              # noqa: E402
from experiments.ex2 import prompts as P                         # noqa: E402
from experiments.ex2 import transforms as T                      # noqa: E402
from experiments.ex2.labels import describe, require_face        # noqa: E402
from experiments.ex2.run import VIEWS, load_scenes               # noqa: E402

LABEL = "ycb_block"

# Snapping the free number to the nearest true height reproduces mancheck's
# forced choice, so the two probes can be read on one scale. Derived from
# the vocabulary so it follows RESTING_FACES; two-way since 2026-08-27.
CHANCE = 100.0 / len(P.RESTING_FACES)


def edges_mm(label=LABEL):
    """The block's three edge lengths in millimetres, longest first.

    From the registry rather than typed here. The dimensions are the thing
    an experimenter is most likely to change -- widening the gap between
    the three heights is one of the open fixes -- and a second copy would
    make this probe score against the old block without looking wrong.
    """
    d = T.DIMS_M[label]
    return sorted((round(d["height"] * 1000), round(d["width"] * 1000),
                   round(d["depth"] * 1000)), reverse=True)


def true_height_mm(face, label=LABEL):
    """The vertical extent, in mm, when the block rests on `face`.

    DERIVED, not tabulated. Each face is named by the RANK of its area, so
    with edges a > b > c the largest face is a x b, the edge is a x c and
    the smallest is b x c -- and the vertical extent is always the edge
    the resting face does not use. Deriving it means a change to DIMS_M
    carries through here on its own; a hardcoded 130/100/50 would keep
    scoring the old block against the new renders.
    """
    a, b, c = edges_mm(label)
    # b, the middle edge, is the vertical extent of the retired "edge"
    # face and is deliberately unmapped: no face rests on a x c any more.
    table = {"large_face": c, "small_face": a}
    if face not in table:
        raise ValueError(
            f"{face!r} is not a resting face of {label!r}; expected one of "
            f"{sorted(table)}. A mustard capture reaches here if it is run "
            f"through the block design, and its postures have no height.")
    return table[face]


def heights_mm(label=LABEL):
    """The three true heights, ascending. The snap targets."""
    return sorted(true_height_mm(f, label) for f in P.RESTING_FACES)


def build(image_b64, label=LABEL):
    """The probe. One number, no face words anywhere in it."""
    a, b, c = edges_mm(label)
    return [
        {"role": "system",
         "content": "Answer with one number and nothing else."},
        {"role": "user", "content": [
            {"type": "text",
             # "edge lengths" would leak a face name: "edge" is one of
             # the three words this probe exists to avoid using.
             "text": ("The block on the table is a rectangular box "
                      "measuring %d mm x %d mm x %d mm. It is resting flat "
                      "on the table. How tall is it as it sits -- the "
                      "vertical distance from the table surface to its "
                      "highest point? Answer with one number in "
                      "millimetres and nothing else." % (a, b, c))},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + image_b64}},
        ]},
    ]


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def normalise(reply, label=LABEL):
    """The height in mm the model reported, or None.

    Tolerant about unit, punctuation and surrounding prose, strict about
    there being exactly ONE number. "100", "100mm", "100 mm", "~100" and
    "about 100 mm tall" are the same reply; "100 or 130" is unparseable,
    because picking one of them would be the grader deciding what the
    model meant.

    This is deliberately LOOSER than mancheck, which scores a face name
    buried in a sentence as unparseable. The two cases are not alike. A
    face word in prose can be one of several the model was weighing, so
    reading it out is a guess; a single number in prose is the answer with
    words around it, and there is nothing to guess. Scoring it unparseable
    would throw away a perception this probe exists to measure. The cost
    is that the two probes' unparseable rates are not comparable, which is
    why neither script reports the other's.

    A reply in metres is converted rather than discarded: 0.10 is a
    correctly perceived height reported in the wrong unit, and scoring it
    as unparseable would count a compliance slip as a perception failure.
    The cut is at 3, safely below the smallest edge in mm and above the
    largest in m for any block this design would use.
    """
    if not isinstance(reply, str):
        return None
    nums = _NUM.findall(reply.replace(",", ""))
    if len(nums) != 1:
        return None
    val = float(nums[0])
    if val <= 0:
        return None
    if val < 3.0:                       # answered in metres
        val *= 1000.0
    return val


def snap(mm, label=LABEL):
    """The nearest true height. mancheck's three-way call, derived.

    Ties go to the TALLER height, so the rounding never invents the flat
    answer the model is already biased toward. With the current block no
    tie is reachable, but the block's dimensions are one of the things
    under revision and a silent tie-break would be a thumb on the scale.
    """
    if mm is None:
        return None
    hs = heights_mm(label)
    return min(hs, key=lambda h: (abs(h - mm), -h))


def checks(scenes, views=VIEWS, seqs=None):
    """Every (scene, view) to ask about, in a stable order.

    The same shape mancheck builds, so the two files can be joined on
    seq and view without a translation step.
    """
    out = []
    for scene in scenes:
        if seqs is not None and scene["seq"] not in seqs:
            continue
        truth = describe({"state": scene["state"]})
        face = require_face(truth["true_pose"], P.RESTING_FACES)
        for view in views:
            if view not in scene["images"]:
                continue
            out.append({"seq": scene["seq"], "view": view,
                        "kind": scene["kind"],
                        "flip_prim": truth["flip_prim"],
                        "true_pose": truth["true_pose"],
                        "true_face": face,
                        "true_height_mm": true_height_mm(face),
                        "image": scene["images"][view]})
    return out


def check_id(row, model):
    """Stable identity for one check, so a restart can skip what is done."""
    return "%s|%s|%s" % (row["seq"], row["view"], model or "none")


def done_ids(out_path):
    """Ids already ANSWERED. A row that errored is a call that never
    landed, so it is retried rather than retired; counting lines instead
    is how a file of key failures reports itself as a finished run."""
    seen = set()
    if not out_path or not os.path.exists(out_path):
        return seen
    for line in open(out_path):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not rec.get("check_id"):
            continue
        if rec.get("error") and rec.get("said_mm") is None:
            continue
        seen.add(rec["check_id"])
    return seen


def ask(row, model, model_fn=openai_chat, timeout=60.0, retry_errors=True):
    """One call. Returns the row with the reply and both scorings filled."""
    with open(row["image"], "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    messages = build(b64)

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

    said = normalise(reply)
    snapped = snap(said)
    true_mm = row["true_height_mm"]
    out = dict(row)
    out.update({
        "reply": reply,
        "said_mm": said,
        # Signed, and true is subtracted FROM said, so a negative error
        # means the model read the block as shorter than it is. That is
        # the direction mancheck's every error already pointed, and the
        # sign is the finding.
        "error_mm": (said - true_mm) if said is not None else None,
        "snapped_mm": snapped,
        # The face that height implies. DERIVED from the number, and named
        # so no reader mistakes it for a face the model uttered.
        "implied_face": (
            next((f for f in P.RESTING_FACES
                  if true_height_mm(f) == snapped), None)
            if snapped is not None else None),
        "correct": (snapped == true_mm) if snapped is not None else None,
        "error": error,
    })
    return out


def summarise(rows):
    """Per view, and per view crossed with the true resting face.

    Split by face for the reason mancheck states: a model answering one
    number for every picture scores a third overall, which reads as
    partial competence, and only the split shows it at 100 and 0.
    """
    tally = {}
    for r in rows:
        for key in ((r["view"], "all"), (r["view"], r["true_face"])):
            slot = tally.setdefault(key, {"n": 0, "correct": 0,
                                          "unparseable": 0, "error": 0,
                                          "said": []})
            slot["n"] += 1
            if r.get("error") and r.get("said_mm") is None:
                slot["error"] += 1
            elif r.get("said_mm") is None:
                slot["unparseable"] += 1
            else:
                slot["said"].append(r["said_mm"])
                if r.get("correct"):
                    slot["correct"] += 1
    return tally


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def format_summary(tally, label=LABEL):
    lines = []
    for (view, face) in sorted(tally):
        s = tally[(view, face)]
        scored = s["n"] - s["unparseable"] - s["error"]
        acc = (100.0 * s["correct"] / scored) if scored else float("nan")
        true_mm = (true_height_mm(face, label) if face != "all" else None)
        mean = _mean(s["said"])
        bias = ("%+6.1f" % (mean - true_mm)) if true_mm else "     -"
        lines.append(
            "%-10s %-11s n=%-3d snapped=%5.1f%% mean_said=%6.1fmm "
            "true=%s bias=%smm unparseable=%d error=%d%s"
            % (view, face, s["n"], acc, mean,
               ("%4dmm" % true_mm) if true_mm else "   -  ",
               bias, s["unparseable"], s["error"],
               "  BELOW CHANCE" if scored and acc < CHANCE else ""))
    lines.append("chance is %.1f%% once the number is snapped to the "
                 "nearest of %s mm." % (CHANCE, heights_mm(label)))
    lines.append("bias is the reading mancheck cannot produce: a negative "
                 "bias on every face is a render read as too flat, not a "
                 "model that cannot name faces.")
    return "\n".join(lines)


def ordering(rows, label=LABEL):
    """Does the mean reported height ORDER the three faces correctly.

    This is the question the whole probe exists to answer. mancheck showed
    edge and large_face producing the same reply distribution, which could
    mean the model cannot resolve them OR that it resolves them and names
    both the same. If the mean reported height separates them, it is the
    naming; if it does not, it is the picture.
    """
    out = []
    by_face = {}
    for r in rows:
        if r.get("said_mm") is not None:
            by_face.setdefault(r["true_face"], []).append(r["said_mm"])
    order = sorted(P.RESTING_FACES, key=lambda f: -true_height_mm(f, label))

    out.append("true height -> mean reported height")
    for f in order:
        xs = by_face.get(f, [])
        out.append("  %-11s %4dmm  ->  %s   (n=%d)"
                   % (f, true_height_mm(f, label),
                      ("%6.1fmm" % _mean(xs)) if xs else "no rows ",
                      len(xs)))

    # A face with no rows is a gap in the sample, not a break in the
    # ordering. Counting it as one reported a perfect reader as
    # non-monotone whenever a face was missing, which is exactly the
    # state a part-finished run is in.
    seen = [f for f in order if by_face.get(f)]
    if len(seen) < 2:
        out.append("  not testable: %d of the three faces have answers."
                   % len(seen))
        return "\n".join(out)
    means = [_mean(by_face[f]) for f in seen]
    monotone = all(x > y for x, y in zip(means, means[1:]))
    if len(seen) < len(order):
        out.append("  %s has no answers yet, so the ordering is judged on "
                   "the %d faces that do."
                   % (", ".join(f for f in order if f not in seen), len(seen)))

    # The two FLATTEST faces by geometry, always, never whichever two
    # happen to carry rows. This is the discrimination the capability
    # claim rests on -- the aperture crossing sits between them -- so it
    # is named even when the sample cannot speak to it.
    a, b = order[-2], order[-1]
    if by_face.get(a) and by_face.get(b):
        ma, mb = _mean(by_face[a]), _mean(by_face[b])
        out.append("  the pair the design rests on, %s vs %s: %.1f vs "
                   "%.1f mm (%s)"
                   % (a, b, ma, mb, "separated" if ma > mb
                      else "NOT separated"))
    else:
        out.append("  the pair the design rests on, %s vs %s: cannot be "
                   "read, one of them has no answers." % (a, b))
    out.append("  reported height is %s in true height."
               % ("monotone" if monotone else "NOT monotone"))
    return "\n".join(out)


def run(capture_dir, out_path=None, model=None, limit=None, dry_run=False,
        views=VIEWS, seqs=None, model_fn=openai_chat, timeout=60.0,
        retry_errors=True):
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
            print("%-8s %-10s %-11s true=%4dmm  %s"
                  % (row["seq"], row["view"], row["true_face"],
                     row["true_height_mm"], os.path.basename(row["image"])))
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
            print("%-8s %-10s true=%4dmm said=%-8s %s"
                  % (out["seq"], out["view"], out["true_height_mm"],
                     ("%gmm" % out["said_mm"]) if out["said_mm"] is not None
                     else "?",
                     "ok" if out["correct"] else
                     ("ERROR" if out["error"] else "WRONG")))
    finally:
        if handle:
            handle.close()

    all_rows = produced
    if out_path and os.path.exists(out_path):
        # Later wins. A check that errored and was retried appears twice,
        # and reading both would count one scene as an error AND as an
        # answer.
        by_id = {}
        for x in open(out_path):
            if not x.strip():
                continue
            rec = json.loads(x)
            by_id[rec.get("check_id") or len(by_id)] = rec
        all_rows = list(by_id.values())
    print("---")
    print(format_summary(summarise(all_rows)))
    print()
    print(ordering(all_rows))
    return all_rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probes", required=True,
                    help="capture directory holding consults.jsonl")
    ap.add_argument("--out", default=None,
                    help="JSONL to append to; resumed if it exists")
    ap.add_argument("--model", default=None,
                    help="registry alias, e.g. gpt or gemini")
    ap.add_argument("--view", action="append", dest="views", default=None,
                    help="restrict to a view; repeatable")
    ap.add_argument("--seqs", default=None,
                    help="comma list of scene ids, to probe the same sample "
                         "the cue check used")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    views = tuple(a.views) if a.views else VIEWS
    if not a.dry_run and not a.out:
        raise SystemExit("--out is required for a live run: paid calls that "
                         "are not written down cannot be resumed.")
    run(a.probes, out_path=a.out, model=a.model, limit=a.limit,
        dry_run=a.dry_run, views=views, timeout=a.timeout,
        seqs=(tuple(x.strip() for x in a.seqs.split(",") if x.strip())
              if a.seqs else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
