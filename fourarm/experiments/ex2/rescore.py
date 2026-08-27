"""Rescore an existing solo run with the self-contradiction detector.

Reads rows already on disk and recomputes the two fields the detector
adds. No model is called and nothing is overwritten: the report goes to
stdout and the original file is left alone.

WHY IT EXISTS. Five qwen conflict replies stated, in effect, "0.096 m,
within franka_n's max_grasp_m of 0.08 m? No, 0.096 > 0.08, so not
acceptable" and then assigned franka_n. They were scored follows_state,
which counts them as evidence the model believed the text. It did not: it
reached the opposite conclusion in writing and assigned against it. Those
trials are evidence of neither source winning, and leaving them inside the
cue-following counts inflates a number the thesis rests on.

Usage:
    python3 -m experiments.ex2.rescore --run runs/ex2_solo.jsonl \\
        --probes out/ex2_capture
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

from experiments.ex2 import grade as G                           # noqa: E402
from experiments.ex2 import labels as L                           # noqa: E402
from experiments.ex2 import solo as SOLO                          # noqa: E402
from experiments.ex2.run import load_scenes                      # noqa: E402


def rescore(run_path, capture_dir):
    scenes = {s["seq"]: s for s in load_scenes(capture_dir)}

    # Keyed on trial_id, LAST write wins. A row that failed to parse is
    # retried on the next run and both end up in the file, so reading every
    # line counts the failure and its replacement as two trials. That put
    # 24 rows in a 22-scene cell and two phantom unparseables in the table.
    # solo.py's own table already deduplicates this way; this did not.
    seen = {}
    order = []
    for line in open(run_path):
        if not line.strip():
            continue
        r = json.loads(line)
        tid = r.get("trial_id")
        if tid not in seen:
            order.append(tid)
        seen[tid] = r

    rows = []
    for tid in order:
        r = seen[tid]
        scene = scenes.get(r.get("seq"))
        limits = G.arm_limits(scene["state"]) if scene else {}
        # Recompute the stated width, do not trust the value on disk.
        # believed_width_m was written at run time by whatever extractor
        # existed then, and the extractor has changed: it used to take the
        # first number in why.grasp, which is an extent the model REJECTED
        # when the reply enumerates before concluding. Rows written before
        # that fix carry 0.191 where the model concluded 0.096, and every
        # downstream verdict inherits it.
        #
        # Both fields are passed. A row from the current schema carries the
        # typed "opening_needed_m" and is read straight off it; a row from
        # a pre-2026-08-26 file carries only prose and falls back to the
        # extractor. Passing the why block alone would have thrown away the
        # typed number on every new row and re-mined prose that is not
        # there.
        _rw = G.believed_width({"opening_needed_m": r.get("opening_needed_m"),
                                "why": r.get("why")})
        if _rw is not None:
            r["believed_width_m"] = _rw
        r["width_belief"] = G.classify_width(r.get("believed_width_m"), r)
        r["self_contradicted"] = G.self_contradicted(
            r.get("believed_width_m"), r.get("arm"), limits)
        r["reasoning"] = G.classify_reasoning(r.get("why"))
        r["resting_face"] = r.get("resting_face")
        r["infeasible"] = SOLO.infeasible(r)
        rows.append(r)

    # A block file written before 2026-08-27 names its resting faces
    # "upright", "lying_large_face" and "lying_small_face". Translate those
    # so the per-face tables group, and SAY SO rather than doing it
    # silently. A mustard file is left alone and reports 0: its "upright"
    # means the bottle standing, and rewriting it would be a lie about
    # which object was run.
    moved = L.modernise_poses(rows)
    if moved:
        print("[rescore] translated %d pre-2026-08-27 block rows to the "
              "resting-face vocabulary" % moved)
    return rows


def report(rows):
    print("%d distinct trials" % len(rows))
    for model in sorted({r["model"] for r in rows}):
        sub = [r for r in rows if r["model"] == model]
        print("=" * 68)
        print(model, len(sub), "trials")
        contra = [r for r in sub if r.get("self_contradicted")]
        print("  self-contradicted: %d" % len(contra))
        for r in sorted(contra, key=lambda x: (x["condition"], x["seq"])):
            print("    %-10s %-8s arm=%-9s stated=%.3f  outcome was %s"
                  % (r["condition"], r["seq"], r["arm"],
                     r["believed_width_m"], r["outcome"]))
        # What the cue-following counts look like once the contradicted
        # trials are set aside. This is the number to report.
        conf = [r for r in sub if r["condition"] == "conflict"]
        if not conf:
            # A baseline file has no conflict trials, and printing an empty
            # table under a heading reads as a result of zero rather than
            # as an absent condition.
            print("  no conflict trials in this file (conditions present: "
                  "%s)" % ", ".join(sorted({r["condition"] for r in sub})))
        else:
            print("  outcomes, conflict only:")
        for label, keep in ((("as scored", conf),
                             ("excluding self-contradicted",
                              [r for r in conf
                               if not r.get("self_contradicted")]))
                            if conf else ()):
            counts = {}
            for r in keep:
                counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
            print("    %-30s n=%-3d %s"
                  % (label, len(keep),
                     "  ".join("%s=%d" % (k, counts[k])
                               for k in sorted(counts))))
        reasoning = {}
        for r in sub:
            reasoning[r["reasoning"]] = reasoning.get(r["reasoning"], 0) + 1
        # Only N-D and N-CD ask for the face, so this is empty everywhere
        # else BY DESIGN and an empty column is not a failure to report.
        faces = {}
        for r in sub:
            if r.get("resting_face"):
                faces[r["resting_face"]] = faces.get(r["resting_face"], 0) + 1
        # Unambiguous regardless of which source was followed: the named
        # arm cannot span the object's TRUE width.
        named = [r for r in sub if r.get("arm")]
        infs = [r for r in named if r.get("infeasible")]
        print("  physically infeasible: %d of %d named arms (%.0f%%)"
              % (len(infs), len(named),
                 100.0 * len(infs) / len(named) if named else float("nan")))
        by = {}
        for r in infs:
            key = (r.get("preference"), r["true_pose"])
            by[key] = by.get(key, 0) + 1
        if by:
            print("    by preference and pose: %s"
                  % "  ".join("%s/%s=%d" % (k[0], k[1], by[k])
                              for k in sorted(by, key=str)))
        print("  reasoning: %s"
              % "  ".join("%s=%d" % (k, reasoning[k])
                          for k in sorted(reasoning, key=str)))
        if faces:
            print("  resting_face reported: %s"
                  % "  ".join("%s=%d" % (k, faces[k]) for k in sorted(faces)))
        print()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--probes", default="out/ex2_capture")
    a = ap.parse_args(argv)
    report(rescore(a.run, a.probes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())