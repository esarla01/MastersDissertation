"""Mustard pose probe: can the VLM tell a LYING mustard bottle from an UPRIGHT one?

This is a cheap, PNG-only perception test in the spirit of
`analysis/ex2/ex2_perception_floor.py`. It shows the model each captured EX2 frame,
asks the single question "is the mustard bottle lying down or standing
upright?", and scores the answer against ground truth. No simulation, no
allocation, no rules block -- it isolates ONE thing: does the model actually
SEE the pose the rest of EX2 depends on. If it cannot, every downstream
lying-vs-upright result is confounded, and we find that out here for pennies.

The model call path is IMPORTED from the real allocator
(`core.decision.vlm_allocator.openai_chat`), not reimplemented, so this runs
against exactly the endpoint/model an episode would.

GROUND TRUTH -- read this before trusting the filename.
  The naming convention "<seq>_A = lying, <seq>_B = upright" holds ONLY for
  the paired cells (the `e*` and `p*` sequences, kind="pair"). The `m*` and
  `n*` sequences are `null` controls: the mustard is LYING in BOTH members,
  so `m03_B`/`n05_B` are lying, not upright. Scoring those by the filename
  would mislabel every null-pair B frame.

  Therefore the authoritative truth is `consults.jsonl` in the capture dir
  (`ex2.flip_object`: mustard_lying -> lying, mustard_upright -> upright).
  The filename convention is used ONLY as a fallback when no consults file
  is present, and a warning is printed when that happens. Pass --only-pairs
  to restrict the run to the sequences where the A/B convention does apply.

Needs the model key in the environment (same as the allocator -- e.g.
DASHSCOPE_API_KEY for the default qwen alias, or the key for --model gpt).

Usage:
  # default: every ex2_cam frame in out/ex2_capture, scored against consults
  python3 analysis/ex2/ex2_pose_probe.py

  # a different capture dir, the GPT alias, only the true A/B pairs
  python3 analysis/ex2/ex2_pose_probe.py out/ex2_capture --model gpt --only-pairs

  # the overhead table camera instead of the ex2 camera, write a JSONL log
  python3 analysis/ex2/ex2_pose_probe.py --view table_cam --out runs/pose.jsonl

  # see the prompt and the ground-truth labels without spending a token
  python3 analysis/ex2/ex2_pose_probe.py --dry-run

  # score specific frames
  python3 analysis/ex2/ex2_pose_probe.py --images out/ex2_capture/e01_A.png ...
"""

import argparse
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.decision.vlm_allocator import openai_chat   # REAL call path

# Repo-relative default: fourarm/analysis/ -> fourarm/out/ex2_capture
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_CAPTURE = os.path.join(_REPO, "out", "ex2_capture")

POSES = ("lying", "upright")

QUESTION = (
    "This is a photo of a robot workcell table with one or more objects on "
    "it. Find the YELLOW MUSTARD BOTTLE (a tall French's-style squeeze "
    "bottle). Ignore every other object. Decide its pose:\n"
    "  - \"upright\": standing on its base, long axis vertical, cap up.\n"
    "  - \"lying\": tipped over on its side, long axis roughly horizontal "
    "along the table.\n"
    "Judge only from what you see, not from what mustard bottles usually do. "
    "If the mustard bottle is not visible at all, use \"unknown\".\n"
    "Answer with ONLY this JSON and nothing else: "
    '{"pose": "upright|lying|unknown"}'
)


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------

def _pose_from_flip(flip_object):
    """'mustard_upright' -> 'upright', 'mustard_lying' -> 'lying'."""
    if not flip_object:
        return None
    f = flip_object.lower()
    if "upright" in f:
        return "upright"
    if "lying" in f:
        return "lying"
    return None


def load_truth(capture_dir):
    """Map seq (e.g. 'e01_A') -> {'pose', 'kind'} from consults.jsonl.

    Returns {} when there is no consults file; callers then fall back to the
    filename convention.
    """
    path = os.path.join(capture_dir, "consults.jsonl")
    truth = {}
    if not os.path.exists(path):
        return truth
    with open(path) as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            rec = json.loads(raw)
            ex = rec.get("ex2") or {}
            seq = rec.get("seq")
            pose = _pose_from_flip(ex.get("flip_object"))
            if seq and pose:
                truth[seq] = {"pose": pose, "kind": ex.get("kind")}
    return truth


def truth_from_name(seq):
    """Filename fallback: <seq>_A -> lying, <seq>_B -> upright.

    Correct ONLY for the paired cells; see the module docstring. Used only
    when consults.jsonl is absent.
    """
    if seq.endswith("_A"):
        return "lying"
    if seq.endswith("_B"):
        return "upright"
    return None


# ---------------------------------------------------------------------------
# Frame discovery
# ---------------------------------------------------------------------------

def seq_and_view(filename):
    """('p02_A_table_cam.png') -> ('p02_A', 'table_cam');
    ('p02_A.png') -> ('p02_A', 'ex2_cam'). None for non-frames."""
    if not filename.endswith(".png"):
        return None
    stem = filename[:-len(".png")]
    if stem.endswith("_table_cam"):
        return stem[:-len("_table_cam")], "table_cam"
    return stem, "ex2_cam"


def discover(capture_dir, view):
    """List (path, seq, view) for frames of the requested view(s)."""
    want = {"ex2_cam", "table_cam"} if view == "both" else {view}
    out = []
    for name in sorted(os.listdir(capture_dir)):
        sv = seq_and_view(name)
        if not sv:
            continue
        seq, v = sv
        if v in want:
            out.append((os.path.join(capture_dir, name), seq, v))
    return out


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def extract_pose(text):
    """Pull a pose out of the reply. Prefers the JSON object; falls back to
    a bare word so a chatty model is not scored as unparseable."""
    if text is None:
        return None, None
    raw = text.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if 0 <= start < end:
        try:
            d = json.loads(raw[start:end + 1])
            p = str(d.get("pose", "")).lower()
            if p in POSES or p == "unknown":
                return p, raw
        except json.JSONDecodeError:
            pass
    low = raw.lower()
    hits = [p for p in POSES if p in low]
    if len(hits) == 1:
        return hits[0], raw
    if "unknown" in low and not hits:
        return "unknown", raw
    return None, raw


def ask(frame_path, model_fn=openai_chat, alias=None, timeout=60.0):
    with open(frame_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    messages = [
        {"role": "system",
         "content": "You answer questions about images, ONLY in the JSON "
                    "format the question specifies. No prose."},
        {"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": QUESTION},
        ]},
    ]
    # Match perception_floor: pass alias only when set, so model_fn stubs
    # that take no alias keep working.
    if alias is None:
        return model_fn(messages, timeout=timeout)
    return model_fn(messages, timeout=timeout, alias=alias)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary(rows):
    graded = [r for r in rows if r["truth"] in POSES]
    correct = [r for r in graded if r["pred"] == r["truth"]]
    unknown = [r for r in graded if r["pred"] == "unknown"]
    unparsed = [r for r in graded if r["pred"] is None]
    errors = [r for r in rows if r.get("error")]

    print("\n" + "=" * 60)
    n = len(graded)
    acc = (len(correct) / n) if n else 0.0
    print(f"SCORED {n} frame(s): {len(correct)} correct  "
          f"accuracy {acc:.1%}")
    if unknown:
        print(f"  model said 'unknown' (mustard not seen): {len(unknown)}")
    if unparsed:
        print(f"  unparseable replies: {len(unparsed)}")
    if errors:
        print(f"  call errors: {len(errors)}")

    # Confusion matrix over the two real poses.
    print("\n  confusion (rows = truth, cols = predicted)")
    preds = list(POSES) + ["unknown", "unparsed"]
    header = "    truth\\pred |" + "".join(f"{p:>10}" for p in preds)
    print(header)
    for t in POSES:
        cells = []
        for p in preds:
            if p == "unparsed":
                c = sum(1 for r in graded if r["truth"] == t and r["pred"] is None)
            else:
                c = sum(1 for r in graded if r["truth"] == t and r["pred"] == p)
            cells.append(f"{c:>10}")
        print(f"    {t:>10} |" + "".join(cells))

    # Per-pose recall, the number that actually answers the user's question.
    print("\n  per-pose accuracy")
    for t in POSES:
        sub = [r for r in graded if r["truth"] == t]
        hit = sum(1 for r in sub if r["pred"] == t)
        rate = (hit / len(sub)) if sub else 0.0
        print(f"    {t:>10}: {hit}/{len(sub)}  ({rate:.1%})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(model_fn=openai_chat):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture_dir", nargs="?", default=DEFAULT_CAPTURE,
                    help=f"folder of captured frames (default: {DEFAULT_CAPTURE})")
    ap.add_argument("--images", nargs="+", default=None,
                    help="score these PNG paths instead of scanning a dir")
    ap.add_argument("--view", default="ex2_cam",
                    choices=["ex2_cam", "table_cam", "both"],
                    help="which camera's frames to score (default ex2_cam)")
    ap.add_argument("--model", default=None,
                    help="model registry alias (default: FOURARM_MODEL, e.g. qwen)")
    ap.add_argument("--only-pairs", action="store_true",
                    help="only the kind='pair' sequences where the "
                         "_A=lying/_B=upright convention actually holds")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N frames (a quick smoke test)")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--dry-run", action="store_true",
                    help="list frames + ground truth and print the prompt; "
                         "no model call")
    ap.add_argument("--out", default=None, help="write per-frame JSONL here")
    a = ap.parse_args()

    # Resolve the frame list and the capture dir that owns their truth.
    if a.images:
        frames = []
        for p in a.images:
            sv = seq_and_view(os.path.basename(p))
            seq, v = sv if sv else (os.path.basename(p), "ex2_cam")
            frames.append((p, seq, v))
        capture_dir = os.path.dirname(os.path.abspath(a.images[0]))
    else:
        capture_dir = a.capture_dir
        if not os.path.isdir(capture_dir):
            ap.error(f"not a directory: {capture_dir}")
        frames = discover(capture_dir, a.view)

    truth = load_truth(capture_dir)
    used_fallback = not truth
    if used_fallback:
        print("WARNING: no consults.jsonl in the capture dir; falling back "
              "to the filename convention (_A=lying, _B=upright). This is "
              "WRONG for null-control pairs (m*, n*) if any are present.\n")

    def truth_for(seq):
        if seq in truth:
            return truth[seq]["pose"]
        return truth_from_name(seq)

    def kind_for(seq):
        return truth[seq]["kind"] if seq in truth else None

    if a.only_pairs:
        frames = [f for f in frames if kind_for(f[1]) == "pair"
                  or (used_fallback and f[1].endswith(("_A", "_B")))]

    if a.limit is not None:
        frames = frames[:a.limit]

    if not frames:
        print("No frames matched. Check --view / --capture_dir / --only-pairs.")
        return 1

    print(f"{len(frames)} frame(s) from {capture_dir}")
    print(f"view={a.view}  model={a.model or os.environ.get('FOURARM_MODEL', 'qwen')}"
          f"  truth={'filename-fallback' if used_fallback else 'consults.jsonl'}")

    if a.dry_run:
        print("\n--- PROMPT ---\n" + QUESTION)
        print("\n--- FRAMES + GROUND TRUTH ---")
        for path, seq, v in frames:
            print(f"  {seq:<12} view={v:<9} truth={truth_for(seq)!s:<8} "
                  f"kind={kind_for(seq)}  {os.path.basename(path)}")
        return 0

    rows = []
    out_fh = open(a.out, "w") if a.out else None
    try:
        for path, seq, v in frames:
            t = truth_for(seq)
            row = {"seq": seq, "view": v, "path": path, "truth": t,
                   "pred": None, "raw": None, "error": None}
            try:
                pred, raw = extract_pose(
                    ask(path, model_fn=model_fn, alias=a.model, timeout=a.timeout))
                row["pred"], row["raw"] = pred, raw
            except Exception as e:      # network / protocol / decode
                row["error"] = f"{type(e).__name__}: {e}"

            if row["error"]:
                mark = "ERROR"
            elif t not in POSES:
                mark = "INFO "        # no ground truth to grade against
            elif row["pred"] == t:
                mark = "PASS "
            elif row["pred"] in (None, "unknown"):
                mark = "?    "
            else:
                mark = "FAIL "
            print(f"  [{mark}] {seq:<12} {v:<9} "
                  f"pred={str(row['pred']):<8} truth={str(t):<8}"
                  + (f"  ! {row['error']}" if row["error"] else ""))

            rows.append(row)
            if out_fh:
                out_fh.write(json.dumps(row) + "\n")
                out_fh.flush()
    finally:
        if out_fh:
            out_fh.close()

    print_summary(rows)
    if a.out:
        print(f"\nwrote {len(rows)} rows to {a.out}")

    graded = [r for r in rows if r["truth"] in POSES and not r["error"]]
    wrong = [r for r in graded if r["pred"] != r["truth"]]
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
