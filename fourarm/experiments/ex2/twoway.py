"""EX2 probe: standing or flat, in plain words, with no face vocabulary.

WHY THIS EXISTS. The control (prompts.manipulation_check, driven by
mancheck) asks the model to NAME the face the block rests on. That mixes
two abilities: seeing the block's orientation, and mapping what it sees
onto a face word. When the control scores badly, it cannot say which one
failed.

This probe removes the second. Same pictures, same two orientations, but
the question is "standing up on end, or lying flat" and the answer is a
plain word. If a model answers this well and the control badly, the
perception is intact and the vocabulary was the obstacle.

It has already done its job once. On 2026-08-27, with the design still
three-way, GPT named the face correctly on 43 percent of trials and
answered this question correctly on 18 of 18 of the same pictures. That is
what retired the middle face and reduced the design to two.

WHAT IT CANNOT SHOW, WHICH IS THE POINT OF SAYING SO. small_face stands and
large_face lies, so a model scores here on posture alone without reading
any geometry. That is exactly what makes it a clean diagnostic of
perception, and exactly why a score here is never evidence of derivation.
The summary prints that caveat on every run.

The `face` form this module used to carry was retired with the third face.
Once the design had two faces, asking "which of these two" was word for
word the control's job, and two probes asking one question is how two
numbers drift apart. mancheck is the survivor, being the one with results.

CHANCE IS ONE IN TWO, derived from the answer vocabulary rather than typed,
so it cannot be left behind if the vocabulary changes again.

WHAT IT REUSES. The scene walk, the check identity and the resume rule come
from mancheck itself rather than being written again, so the two probes
cannot drift about which scenes they cover or what counts as done. Only the
question, the answer words and the truth mapping are this file's own.

Usage:
    python3 -m experiments.ex2.twoway --probes out/ex2_capture_block \\
        --form posture --view ex2_cam --dry-run
    python3 -m experiments.ex2.twoway --probes out/ex2_capture_block \\
        --form posture --model gpt --view ex2_cam \\
        --out runs/ex2_q1_2way_posture_gpt_r1.jsonl
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
from experiments.ex2 import mancheck as MC                       # noqa: E402
from experiments.ex2 import transforms as T                      # noqa: E402
from experiments.ex2.run import VIEWS, load_scenes               # noqa: E402

LABEL = "ycb_block"

# The two resting faces the design uses. Everything below is keyed on
# these, whichever words the model is asked to reply in.
FACES = ("small_face", "large_face")

# The `face` form was retired on 2026-08-27, when the design itself dropped
# to two faces: asking "which of these two faces" became word-for-word the
# job of prompts.manipulation_check, and two probes asking one question is
# how two numbers drift apart. mancheck is the survivor because it is the
# control with results.
#
# `posture` survives because it asks something mancheck cannot. Plain words
# against face names is a real difference and it is what this module found:
# GPT named the face correctly on 43 percent of trials and answered
# standing-or-flat on 18 of 18 of the same pictures.
FORMS = ("posture",)

ANSWERS_BY_FORM = {
    "posture": ("standing", "flat"),
}

# The truth, per form. One to one with FACES, which is what lets a posture
# score be read against a face score on the same images.
TRUTH_BY_FORM = {
    "posture": {"small_face": "standing", "large_face": "flat"},
}

# Nothing is excluded any more. The middle face was dropped from the design
# on 2026-08-27, so there is no longer a face this probe covers less of
# than the control does; the capture script guarantees no scene shows it.
EXCLUDED = None

# Kept for readers and callers that only ever meant the face list.
ANSWERS = FACES

# ONE IN TWO, derived from the vocabulary rather than typed.
CHANCE = 100.0 / len(ANSWERS_BY_FORM["posture"])



def faces_mm(label=LABEL):
    """(largest, smallest) resting faces as (w, h) mm pairs, from the
    registry. Derived rather than typed, so the open fix of widening the
    block's dimensions carries through to the question the model is
    asked."""
    d = T.DIMS_M[label]
    a, b, c = sorted((round(d["height"] * 1000), round(d["width"] * 1000),
                      round(d["depth"] * 1000)), reverse=True)
    return (a, b), (b, c)          # largest face a x b, smallest b x c


def require_form(form):
    """Return `form` if it is one this probe asks, else raise.

    Never defaulted, for seecheck's reason: a posture row recorded as a
    face row would merge two different measurements into one accuracy and
    neither would be recoverable.
    """
    if form not in FORMS:
        raise ValueError(
            f"unknown form {form!r}; expected one of {list(FORMS)}. The "
            f"form is what the model was asked, so it is never inferred: "
            f"the two are separate measurements of the same pictures.")
    return form


def build(image_b64, form, label=LABEL):
    """The probe for one form. TWO options, and the third face is never
    mentioned in either.

    Naming it, even to exclude it, would put the word back in front of the
    model and make this a three-way question with one option discouraged,
    which is a different measurement.
    """
    require_form(form)
    # Deliberately bare. No face words, no dimensions, no metric matching:
    # standing versus flat is the block judged against itself, and any
    # measurement given here would rebuild the task this form exists to
    # strip away.
    text = ("Look at the block on the table. Is it standing up on end, "
            "or lying flat? Answer 'standing' or 'flat'.")
    return [
        {"role": "system",
         "content": "Answer with one word and nothing else."},
        {"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + image_b64}},
        ]},
    ]


def true_answer(face, form):
    """The word a correct reply uses, for this face under this form."""
    require_form(form)
    table = TRUTH_BY_FORM[form]
    if face not in table:
        raise ValueError(
            f"{face!r} is not one of the two poses this probe covers "
            f"({list(FACES)}). A scene resting on {EXCLUDED!r} reaches "
            f"here if the filter in checks() is bypassed, and it has no "
            f"correct answer in either form.")
    return table[face]


def normalise(reply, form):
    """The word the model said, or None. Strict, for mancheck's reason:
    a word buried in a sentence is a compliance failure, not a perception
    one, and scoring it correct would let a chatty model look more
    grounded than a terse one.

    Matched against THIS form's vocabulary only. A reply of "standing" to
    the face question is not a near-miss to be credited; it is the model
    answering a question it was not asked.
    """
    require_form(form)
    if not isinstance(reply, str):
        return None
    word = reply.strip().strip(".,!'\"").lower()
    return word if word in ANSWERS_BY_FORM[form] else None


def checks(scenes, views=VIEWS, seqs=None):
    """mancheck's scene walk, with the middle-face scenes removed.

    Reusing the walk rather than writing a second one is what keeps the
    two probes reading the same scenes with the same truth. The filter is
    the only difference, and how many scenes it drops is returned so the
    caller can say so rather than silently shrinking the sample.
    """
    rows = MC.checks(scenes, views=views, seqs=seqs)
    # Since 2026-08-27 the design has exactly these two faces, so this
    # drops nothing. It is kept, and its count still returned, because a
    # capture directory written before that date holds middle-face scenes
    # and they have no answer in either form. Silently scoring them would
    # mark every one wrong and read as blindness.
    kept = [r for r in rows if r["true_face"] in FACES]
    return kept, len(rows) - len(kept)


def check_id(row, model, form):
    """Stable identity for one check. mancheck's, plus the form.

    The form has to be in the key. Without it the two question forms
    collide on resume, and whichever ran second would be skipped as
    already answered by the first.
    """
    return "%s|%s" % (MC.check_id(row, model), require_form(form))


def ask(row, model, form, model_fn=openai_chat, timeout=60.0,
        retry_errors=True):
    """One call. Returns the row with reply, answer and correct filled."""
    require_form(form)
    with open(row["image"], "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    messages = build(b64, form)

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

    answer = normalise(reply, form)
    want = true_answer(row["true_face"], form)
    out = dict(row)
    out.update({"form": form, "reply": reply, "answer": answer,
                # The word a correct reply uses under THIS form, recorded
                # beside the face so a posture file can be read without
                # the mapping in front of you.
                "true_answer": want,
                "correct": (answer == want) if answer else None,
                "error": error,
                # Stamped on every row so a file of these can never be read
                # against the three-way probe's floor by accident.
                "n_options": len(ANSWERS_BY_FORM[form]), "chance_pct": CHANCE})
    return out


def summarise(rows):
    """Per view, and per view crossed with the true face. Split for
    mancheck's reason: a model answering one word for everything scores
    half here, which is exactly chance, and only the split shows it."""
    tally = {}
    for r in rows:
        for key in ((r["view"], "all"), (r["view"], r["true_face"])):
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


def format_summary(tally, form=None):
    lines = []
    for (view, face) in sorted(tally):
        s = tally[(view, face)]
        scored = s["n"] - s["unparseable"] - s["error"]
        acc = (100.0 * s["correct"] / scored) if scored else float("nan")
        lines.append("%-10s %-11s n=%-3d correct=%-3d acc=%5.1f%% "
                     "unparseable=%d error=%d%s"
                     % (view, face, s["n"], s["correct"], acc,
                        s["unparseable"], s["error"],
                        "  BELOW CHANCE" if scored and acc < CHANCE else ""))
    if form:
        lines.append("form: %s -- the model answered in %s."
                     % (form, " / ".join(ANSWERS_BY_FORM[form])))
    lines.append("chance is %.1f%%: a TWO-way forced choice, not the "
                 "three-way control's 33.3%%." % CHANCE)
    if form == "posture":
        lines.append("this form measures posture on purpose. A high score "
                     "says the picture supports standing-versus-flat, NOT "
                     "that the model derived anything from geometry; read "
                     "it against the face form on the same images.")
    else:
        lines.append("a score here is consistent with derivation but does "
                     "not show it: small_face stands and large_face lies, "
                     "so a posture heuristic scores the same as reading "
                     "the geometry. That is what dropping %r costs."
                     % EXCLUDED)
    return "\n".join(lines)


def run(capture_dir, form, out_path=None, model=None, limit=None,
        dry_run=False, views=VIEWS, seqs=None, model_fn=openai_chat,
        timeout=60.0, retry_errors=True):
    require_form(form)
    scenes = load_scenes(capture_dir, present_ur=False)
    rows, dropped = checks(scenes, views=views, seqs=seqs)
    if dropped:
        print("dropped %d check(s) resting on a face this design no longer "
              "uses: there is no word for it in any form, so asking would "
              "score every one of them wrong by construction." % dropped)
    if seqs is not None:
        asked = {r["seq"] for r in rows}
        missing = [s for s in seqs if s not in asked]
        if missing:
            print("note: %d requested scene(s) are not asked about, either "
                  "absent from the capture or resting on a retired face: %s"
                  % (len(missing), ", ".join(sorted(missing))))
    if limit:
        rows = rows[:limit]

    if dry_run:
        for row in rows:
            print("%-8s %-10s %-11s -> %-9s %s"
                  % (row["seq"], row["view"], row["true_face"],
                     true_answer(row["true_face"], form),
                     os.path.basename(row["image"])))
        print("--- %d checks in form %r, no calls made" % (len(rows), form))
        return []

    seen = MC.done_ids(out_path)          # answers, not lines
    handle = open(out_path, "a") if out_path else None
    produced = []
    try:
        for row in rows:
            cid = check_id(row, model, form)
            if cid in seen:
                continue
            out = ask(row, model, form, model_fn=model_fn, timeout=timeout,
                      retry_errors=retry_errors)
            out["check_id"] = cid
            out["model"] = model
            produced.append(out)
            if handle:
                handle.write(json.dumps(out) + "\n")
                handle.flush()
            print("%-8s %-10s true=%-9s said=%-9s %s"
                  % (out["seq"], out["view"], out["true_answer"],
                     out["answer"] or "?",
                     "ok" if out["correct"] else
                     ("ERROR" if out["error"] else "WRONG")))
    finally:
        if handle:
            handle.close()

    all_rows = produced
    if out_path and os.path.exists(out_path):
        by_id = {}                        # later wins on retry
        for x in open(out_path):
            if x.strip():
                rec = json.loads(x)
                by_id[rec.get("check_id") or len(by_id)] = rec
        all_rows = list(by_id.values())
    # A file holds one form by construction, but a hand-merged one would
    # not, and a single accuracy over two different questions is not a
    # number about anything.
    forms = {r.get("form", "face") for r in all_rows}
    if len(forms) > 1:
        raise SystemExit(
            "%s holds more than one question form (%s). Their accuracies "
            "are comparable but not poolable: one number over two "
            "different questions describes neither."
            % (out_path, ", ".join(sorted(forms))))
    print("---")
    print(format_summary(summarise(all_rows), form=form))
    return all_rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probes", required=True)
    ap.add_argument("--form", required=True, choices=FORMS,
                    help="which question to ask. Never defaulted: a "
                         "posture row recorded as a face row would merge "
                         "two different measurements.")
    ap.add_argument("--out", default=None,
                    help="JSONL to append to; resumed if it exists")
    ap.add_argument("--model", default=None, help="registry alias")
    ap.add_argument("--view", action="append", dest="views", default=None)
    ap.add_argument("--seqs", default=None,
                    help="comma list of scene ids; edge scenes among them "
                         "are reported and skipped")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    views = tuple(a.views) if a.views else VIEWS
    if not a.dry_run and not a.out:
        raise SystemExit("--out is required for a live run: paid calls that "
                         "are not written down cannot be resumed.")
    run(a.probes, a.form, out_path=a.out, model=a.model, limit=a.limit,
        dry_run=a.dry_run, views=views, timeout=a.timeout,
        seqs=(tuple(x.strip() for x in a.seqs.split(",") if x.strip())
              if a.seqs else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
