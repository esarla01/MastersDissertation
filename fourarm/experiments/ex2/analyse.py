"""EX2 analysis: the four diagnostic views, from one instrument.

WHY THIS EXISTS. Every number in this project that came from an ad hoc
query written in a chat window has been wrong at least once: six clamp
assignments that were a task-id mistake, a 24-row cell that was two
duplicated retries, an image-following verdict that was a self
contradiction. The summary tables are produced by solo.py and rescore.py;
these four views were not, and they should be.

It reads results files and makes no calls. Rows are deduplicated by
trial_id with the last write winning, the same rule solo.py's own table
uses, so a retried failure does not count twice.

THE FOUR VIEWS

  reason   What the model wrote in why.grasp, grouped so the same scene's
           repeats sit together. The view for reading rather than counting.

           The question it answers: qwen at P3, P3a and P4 reports
           image_referenced on 66 of 66 replies while width_belief is
           state on 66 of 66. It talks about the picture in every reply
           and never takes a number from it. No gpt cell does that, and
           the summary table cannot say what the sentences look like.

  odd      Replies whose stated width is neither candidate value. These
           are the only direct evidence of LOOKING AND MISREADING, as
           opposed to not looking: a width matching the declared value is
           consistent with never having consulted the image, but a third
           value can only have been derived and derived wrongly. Two
           appear in the whole experiment, both at P3 and P4.

  stable   Whether a scene gives the same width_belief on every repeat.
           An aggregate of 38 out of 66 can mean 19 scenes always reading
           the image, or 22 scenes reading it two times in three. Those
           are different claims and only this view separates them.

  noop     Trials where no arm was named. A wait is never correct in this
           design, since a legal arm always exists, so choosing one is a
           signal rather than noise.

Usage:
    python3 -m experiments.ex2.analyse --run runs/A_conflict.jsonl \\
        --probes out/ex2_capture --view reason --model qwen --rung P3
    python3 -m experiments.ex2.analyse --run runs/A_conflict.jsonl --view odd
    python3 -m experiments.ex2.analyse --run runs/A_conflict.jsonl \\
        --view stable
"""

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiments.ex2.rescore import rescore                     # noqa: E402

VIEWS = ("reason", "odd", "stable", "noop", "split", "extract")

# The two values the design can produce. Anything else was derived from
# the picture and derived wrongly.
CANDIDATES = (0.058, 0.096)
TOL = 0.006


def select(rows, model=None, rung=None, preference=None, pose=None,
           condition=None):
    out = rows
    for field, want in (("model", model), ("rung", rung),
                        ("preference", preference), ("true_pose", pose),
                        ("condition", condition)):
        if want:
            out = [r for r in out if r.get(field) == want]
    return out


def view_reason(rows, limit=None):
    """why.grasp, grouped by scene so repeats sit together.

    Printed rather than counted. The keyword classifier already says
    whether the image was mentioned and the arithmetic says which width
    was used; what neither can say is what the sentence actually claims,
    and that is the open question for qwen's talks-about-it-never-uses-it
    cells.
    """
    out = []
    key = lambda r: (r.get("model"), r.get("preference"), r.get("rung"),
                     r["true_pose"], r["seq"], r.get("repeat", 1))
    shown = 0
    last = None
    for r in sorted(rows, key=key):
        group = key(r)[:5]
        if last is not None and group[:4] != last[:4]:
            out.append("")
        last = group
        why = (r.get("why") or {}).get("grasp") or ""
        out.append("%-6s %-6s %-4s %-8s r%s %-8s arm=%-9s %-6s %-16s %s"
                   % (r.get("model"), r.get("preference"), r.get("rung"),
                      r["seq"], r.get("repeat", 1), r["true_pose"],
                      r.get("arm") or "none", r.get("width_belief"),
                      r.get("reasoning"), why[:70]))
        shown += 1
        if limit and shown >= limit:
            out.append("... truncated at %d rows" % limit)
            break
    return "\n".join(out)


def view_odd(rows):
    """Stated widths that are neither candidate value.

    The only direct evidence of looking and misreading. A declared-value
    match is consistent with never having consulted the image; a third
    value is not.
    """
    odd = []
    for r in rows:
        w = r.get("believed_width_m")
        if w is None:
            continue
        if not any(abs(w - c) <= TOL for c in CANDIDATES):
            odd.append(r)
    out = ["%d replies stated a width that is neither %.3f nor %.3f"
           % (len(odd), CANDIDATES[0], CANDIDATES[1])]
    if not odd:
        out.append("  none. Every stated width in this file is one of the "
                   "two values already present, so the model is SELECTING "
                   "between given numbers rather than measuring anything.")
        return "\n".join(out)
    for r in sorted(odd, key=lambda x: (x.get("model"), x.get("rung"),
                                        x["seq"])):
        why = (r.get("why") or {}).get("grasp") or ""
        out.append("  %-6s %-6s %-4s %-8s %-8s stated=%.3f arm=%-9s %s"
                   % (r.get("model"), r.get("preference"), r.get("rung"),
                      r["seq"], r["true_pose"], r["believed_width_m"],
                      r.get("arm") or "none", why[:60]))
    return "\n".join(out)


def view_stable(rows):
    """Per-scene consistency of width_belief across repeats.

    An aggregate of 38 of 66 can mean 19 scenes that always read the image
    or 22 that read it twice in three. Those are different claims about
    whether source selection is a property of the scene or of the sample,
    and the aggregate cannot tell them apart.
    """
    cells = {}
    for r in rows:
        key = (r.get("model"), r.get("preference"), r.get("rung"))
        cells.setdefault(key, {}).setdefault(r["seq"], []).append(
            r.get("width_belief"))
    head = ("%-6s %-6s %-4s %-7s %-9s %-9s %s"
            % ("model", "pref", "rung", "scenes", "always-im", "always-st",
               "flips"))
    out = [head, "-" * len(head)]
    for key in sorted(cells, key=str):
        scenes = cells[key]
        always_im = [s for s, v in scenes.items() if set(v) == {"image"}]
        always_st = [s for s, v in scenes.items() if set(v) == {"state"}]
        flips = [s for s, v in scenes.items() if len(set(v)) > 1]
        out.append("%-6s %-6s %-4s %-7d %-9d %-9d %d  %s"
                   % (key[0], key[1], key[2], len(scenes), len(always_im),
                      len(always_st), len(flips),
                      " ".join(sorted(flips))))
    return "\n".join(out)


def view_extract(rows):
    """Every reply whose extracted width is not a candidate value.

    A VALIDATION view, not a result. The models state 0.058 or 0.096 in
    almost every reply, so an extracted value that is neither is far more
    likely to be an extraction fault than a model one. Three extractor
    rules have failed here, each on a sentence shape the previous test
    cases did not contain, and each time the faults were reported as
    findings before being caught.

    Run this on every results file before quoting any width-derived number.
    It prints the FULL prose, untruncated, so a fault is visible rather
    than inferred.
    """
    odd = []
    for r in rows:
        w = r.get("believed_width_m")
        if w is None:
            continue
        if not any(abs(w - c) <= TOL for c in CANDIDATES):
            odd.append(r)
    out = ["%d of %d replies extracted a width that is neither %.3f nor "
           "%.3f" % (len(odd), len(rows), CANDIDATES[0], CANDIDATES[1])]
    if not odd:
        out.append("  none. Every extracted width is a candidate value, so "
                   "the extractor is consistent with the data and the "
                   "model is selecting between the two supplied numbers "
                   "rather than measuring anything.")
        return "\n".join(out)
    out.append("  CHECK EACH ONE against its prose before treating it as a "
               "model failure.")
    for r in odd:
        out.append("")
        out.append("  %-5s %-6s %-4s %-9s %-8s true=%-8s arm=%-9s "
                   "extracted=%s"
                   % (r.get("model"), r.get("preference"), r.get("rung"),
                      r.get("condition"), r.get("seq"), r.get("true_pose"),
                      r.get("arm"), r.get("believed_width_m")))
        out.append("      %s" % ((r.get("why") or {}).get("grasp") or ""))
    return "\n".join(out)


def view_split(rows):
    """Arm family crossed with stated width. Splits "uninformative".

    A UR is legal under BOTH poses, so naming one cannot be scored on the
    arm axis and the grader calls it uninformative. That is a fact about
    the arm, not about the trial: crossed with the width the model stated,
    the same rows separate cleanly.

    Take a LYING conflict trial under the Franka preference. The text
    claims upright at 0.058 and the guidance pulls toward franka_n, so
    naming a UR goes against both. Why it did so is in the width:

      0.096 + UR      read the picture, found the Franka too small, and
                      overrode the preference. Image use that the arm
                      column cannot show.
      0.058 + UR      believed the text, which says the Franka fits, and
                      declined it anyway. Not perception: the guidance was
                      simply not followed.
      0.058 + Franka  followed the text and the preference together.
      0.096 + Franka  states a width its own arm cannot span.

    On an UPRIGHT trial the text claims lying at 0.096, so the readings
    invert: a Franka choice needs the image, and a UR choice is what the
    text implies.
    """
    notes_lying = {
        ("image", "UR"): "read the image, overrode the preference",
        ("state", "UR"): "believed the text, declined the Franka anyway",
        ("state", "franka"): "followed the text and the preference",
        ("image", "franka"): "states a width that arm cannot span",
    }
    notes_upright = {
        ("image", "franka"): "read the image, used the wider arm set",
        ("state", "UR"): "followed the text, which claims lying",
        ("image", "UR"): "read the image but took the safer arm",
        ("state", "franka"): "states a width that arm cannot span",
    }
    out = []
    cells = {}
    for r in rows:
        cells.setdefault((r.get("model"), r.get("preference"),
                          r.get("rung")), []).append(r)
    for key in sorted(cells, key=str):
        out.append("=" * 74)
        out.append("%s / %s / %s" % key)
        for pose in ("lying", "upright"):
            pr = [r for r in cells[key] if r.get("true_pose") == pose]
            if not pr:
                continue
            tally = {}
            for r in pr:
                arm = r.get("arm")
                fam = ("none" if not arm else
                       "franka" if arm.startswith("franka") else "UR")
                k = (r.get("width_belief"), fam)
                tally[k] = tally.get(k, 0) + 1
            notes = notes_lying if pose == "lying" else notes_upright
            out.append("  %-8s n=%d" % (pose, len(pr)))
            for k in sorted(tally, key=str):
                out.append("    width=%-6s arm=%-7s %3d   %s"
                           % (k[0], k[1], tally[k], notes.get(k, "")))
    return "\n".join(out)


def view_noop(rows):
    """Trials where no arm was named.

    A legal arm exists in every scene, so a wait is never correct here and
    choosing one is a signal rather than noise.
    """
    noops = [r for r in rows if not r.get("arm")]
    out = ["%d trials named no arm" % len(noops)]
    for r in sorted(noops, key=lambda x: (x.get("model"), x.get("rung"),
                                          x["seq"])):
        why = json.dumps(r.get("why"))
        out.append("  %-6s %-6s %-4s %-8s %-8s outcome=%-14s %s"
                   % (r.get("model"), r.get("preference"), r.get("rung"),
                      r["seq"], r["true_pose"], r.get("outcome"), why[:110]))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--probes", default="out/ex2_capture")
    ap.add_argument("--view", default="stable", choices=VIEWS)
    ap.add_argument("--model", default=None)
    ap.add_argument("--rung", default=None)
    ap.add_argument("--preference", default=None)
    ap.add_argument("--pose", default=None, choices=("lying", "upright"))
    ap.add_argument("--condition", default=None)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)

    rows = rescore(a.run, a.probes)
    rows = select(rows, a.model, a.rung, a.preference, a.pose, a.condition)
    print("%d trials after filtering" % len(rows))
    print()
    if a.view == "reason":
        print(view_reason(rows, a.limit))
    elif a.view == "odd":
        print(view_odd(rows))
    elif a.view == "stable":
        print(view_stable(rows))
    elif a.view == "split":
        print(view_split(rows))
    elif a.view == "extract":
        print(view_extract(rows))
    else:
        print(view_noop(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())