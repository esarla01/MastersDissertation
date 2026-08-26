"""EX2 runner: turn captured scenes into trials, ask a model, grade, stream.

WHAT A TRIAL IS. One captured scene, one condition, one rung, one view, one
model. The picture never changes within a scene; the text does.

    scenes      44 captures: 11 positions x pair/null x A/B member
    conditions  congruent, conflict, dims
    rungs       P0, P1, P2, P3
    views       ex2_cam (oblique), table_cam (overhead)

Not every combination is a trial. A NULL scene has no conflict to declare,
so nulls run congruent only: their job is to say how much the answer moves
when nothing meaningful does, and a null with a falsified state would be
measuring something else.

GRADING NEEDS GEOMETRY, NOT THE VALIDATOR. For each trial the legal arms
are computed twice, once under the true pose and once under the declared
one, using the real validator over a frozen coordinator built from the
TRUE registry row each time. In a conflict cell the validator run on the
falsified state would confirm the lie, so it is never used for grading.

ROWS STREAM TO DISK as they are produced and the runner resumes: a paid run
of a thousand calls must survive a dropped connection, and re-asking a
question already answered is money for nothing.

Usage:
    python3 -m experiments.ex2.run --probes out/ex2_capture --dry-run
    python3 -m experiments.ex2.run --probes out/ex2_capture \\
        --model qwen --limit 12 --out runs/ex2_smoke.jsonl
"""

import argparse
import base64
import copy
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.cell import cell_config as C                            # noqa: E402
from core.cell.zones import ZoneMap                               # noqa: E402
from core.decision.vlm_allocator import (validate_decision,       # noqa: E402
                                         openai_chat)
from analysis.frozen_coord import from_record                     # noqa: E402
from experiments.ex2 import grade as G                            # noqa: E402
from experiments.ex2 import prompts as P                          # noqa: E402
from experiments.ex2 import transforms as T                       # noqa: E402
from experiments.ex2.labels import (POSE_ENTRIES,                 # noqa: E402
                                    TRUE_POSE, pose_prim)

VIEWS = ("ex2_cam", "table_cam")
_ZM = None


def zonemap():
    global _ZM
    if _ZM is None:
        _ZM = ZoneMap()
    return _ZM


def baskets():
    from ycb_scene import BASKETS
    return BASKETS


def load_scenes(capture_dir):
    """Every captured scene, with its images resolved to real paths."""
    trail = os.path.join(capture_dir, "consults.jsonl")
    if not os.path.exists(trail):
        raise SystemExit(f"no capture trail at {trail}")
    out = []
    for line in open(trail):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        ex2 = rec.get("ex2") or {}
        images = {k: os.path.join(capture_dir, v)
                  for k, v in (ex2.get("images") or {}).items()}
        missing = [k for k, v in images.items() if not os.path.exists(v)]
        if missing:
            raise SystemExit(
                f"{rec['seq']} names images {missing} that do not exist. A "
                f"missing frame must fail loudly: sending the trial without "
                f"it would silently turn a vision condition into a text one.")
        out.append({"seq": rec["seq"], "state": rec["state"],
                    "positions_exact": rec.get("positions_exact"),
                    "kind": ex2.get("kind", "pair"), "images": images,
                    "frame_path": None,
                    "provenance": {"seq": rec["seq"], "round": 0}})
    return out


def legal_arms(scene, pose_prim, task_id):
    """Arms the REAL validator accepts for the flip task under one pose.

    Called twice per conflict trial, once per pose, which is how
    follows_image and follows_state are told apart without ever asking the
    validator about the falsified state.

    The object is RENAMED to the prim of the pose being tested rather than
    having that pose's numbers written onto the other prim. Both poses are
    genuine registry entries, so this asks a real question about a real
    object instead of falsifying one. It also keeps frozen_coord's guard
    intact: that guard refuses a prim appearing with two different widths,
    on the grounds that it means two episodes are being mixed, and it is
    right to refuse.
    """
    probe = {"state": copy.deepcopy(scene["state"]),
             "positions_exact": dict(scene["positions_exact"])}
    for obj in probe["state"]["objects"]:
        old_name = obj["name"]
        if old_name in POSE_ENTRIES and old_name != pose_prim:
            obj["name"] = pose_prim
            # Per-label facts: the block's pose names (lying_large_face, ...)
            # do not exist in the mustard's flat POSE_FACTS. POSE_ENTRIES maps
            # a prim to its neutral label, which keys POSE_FACTS_BY_LABEL.
            obj.update(
                T.POSE_FACTS_BY_LABEL[POSE_ENTRIES[pose_prim]][
                    TRUE_POSE[pose_prim]])
            for t in probe["state"]["tasks"]:
                if t["object"] == old_name:
                    t["object"] = pose_prim
            if old_name in probe["positions_exact"]:
                probe["positions_exact"][pose_prim] = \
                    probe["positions_exact"].pop(old_name)

    out = set()
    bs = baskets()
    for arm in C.ARMS:
        for basket in list(bs) + [None]:
            coord = from_record(probe)
            ok, _, _, _ = validate_decision(
                {"task_id": task_id, "arm": arm, "basket": basket},
                coord, zonemap(), bs)
            if ok:
                out.add(arm)
                break
    return out


def partner_task_id(state, flip_prim):
    """The other queued task in an EX2 scene.

    Batch grading needs both: the round is what reveals the belief, and a
    round with one task missing is a schema failure rather than a belief.
    """
    others = [t["id"] for t in state.get("tasks", [])
              if t["object"] != flip_prim]
    if len(others) != 1:
        raise ValueError(
            f"expected exactly one partner task, found {others}. An EX2 "
            f"scene is one flip object plus a fixed partner.")
    return others[0]


def flip_task_id(state, name):
    """Task id for an object, by PRIM name or by neutral label.

    The captured state carries prim names; the rendered state carries the
    neutral label. Grading works on the captured state, so callers must
    pass the prim, but accepting either stops a mismatch becoming a silent
    lookup failure.
    """
    from experiments.ex2.labels import neutral_name
    for t in state.get("tasks", []):
        if t["object"] == name or neutral_name(t["object"]) == name:
            return t["id"]
    raise ValueError(
        f"no task for {name!r}; the state has "
        f"{[t['object'] for t in state.get('tasks', [])]}")


def select_scenes(scenes, pair=None):
    """Every scene belonging to one pair id, or all of them.

    "p02" selects p02_A and p02_B and, if it was captured, the matching
    null n02_A and n02_B. The null shares the pair's positions, so a pair
    and its noise floor are always run together: a flip rate without its
    null is uninterpretable, and running them separately invites forgetting
    one.
    """
    if not pair:
        return scenes
    num = pair[1:] if pair[0] in "pnem" else pair
    want = {f"p{num}", f"n{num}", f"e{num}", f"m{num}"}
    got = [s for s in scenes if s["seq"].rsplit("_", 1)[0] in want]
    if not got:
        raise SystemExit(
            f"no scenes for pair {pair!r}. Captured pairs: "
            f"{sorted({s['seq'].rsplit('_', 1)[0] for s in scenes})}")
    return got


def trials(scenes, views=VIEWS, rungs=P.RUNGS, conditions=T.CONDITIONS):
    """Every trial the design calls for, as plain dicts."""
    out = []
    for scene in scenes:
        for view in views:
            if view not in scene["images"]:
                continue
            # A null has no conflict to declare: its job is to show how much
            # the answer moves when nothing meaningful does.
            conds = ("congruent",) if scene["kind"] == "null" else conditions
            for condition in conds:
                for rung in rungs:
                    out.append({"seq": scene["seq"], "kind": scene["kind"],
                                "view": view, "condition": condition,
                                "rung": rung})
    return out


def trial_id(t, model):
    return f"{t['seq']}|{t['view']}|{t['condition']}|{t['rung']}|{model}"


def render(scene, condition, rung, view):
    """(messages, meta) for one trial."""
    probe = {"state": scene["state"],
             "positions_exact": scene["positions_exact"]}
    state, meta = T.transform(probe, condition)
    with open(scene["images"][view], "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return P.build_ex2_prompt(state, rung, condition, image_b64=b64,
                              view=view), meta


def run(capture_dir, out_path, model=None, limit=None, dry_run=False,
        views=VIEWS, rungs=P.RUNGS, conditions=T.CONDITIONS,
        model_fn=openai_chat, timeout=90.0, pair=None, retry_errors=True):
    all_scenes = load_scenes(capture_dir)
    chosen = select_scenes(all_scenes, pair)
    scenes = {s["seq"]: s for s in all_scenes}
    plan = trials(chosen, views, rungs, conditions)
    if limit:
        plan = plan[:limit]

    done, failed = set(), set()
    if out_path and os.path.exists(out_path):
        for line in open(out_path):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            # A row that errored, or that never parsed, is not an answer.
            # Skipping it on resume is how twelve empty rows survived three
            # reruns of the smoke test.
            if r.get("error") or (retry_errors
                                  and r.get("outcome") == "unparseable"):
                failed.add(r["trial_id"])
            else:
                done.add(r["trial_id"])
        print(f"[ex2] resuming: {len(done)} answered"
              + (f", {len(failed)} to retry" if failed else ""))

    fh = open(out_path, "a") if out_path and not dry_run else None
    n_done = n_skip = 0
    try:
        for i, t in enumerate(plan, 1):
            tid = trial_id(t, model)
            if tid in done:
                n_skip += 1
                continue
            scene = scenes[t["seq"]]
            messages, meta = render(scene, t["condition"], t["rung"],
                                    t["view"])
            if dry_run:
                print(f"{tid}  prompt {len(messages[0]['content'])} chars, "
                      f"declared {meta['declared_pose']}, "
                      f"true {meta['true_pose']}")
                n_done += 1
                continue

            t0 = time.time()
            try:
                try:
                    text = model_fn(messages, timeout=timeout, alias=model)
                except TypeError:
                    text = model_fn(messages, timeout=timeout)
                err = None
            except Exception as e:                 # never end a paid run
                text, err = "", f"{type(e).__name__}: {e}"

            # The captured state uses PRIM names, so the lookup and the
            # legality computation both key on the prim, not the label the
            # model was shown.
            task_id = flip_task_id(scene["state"], meta["flip_prim"])
            legal_true = legal_arms(scene, meta["flip_prim"], task_id)
            # legal_declared is the SAME question asked of the pose the text
            # declares. Under congruent the text declares the true pose, so
            # the two sets must be identical: computing this from the other
            # pose scored correct assignments as wrong, because the legal
            # set described a bottle in an orientation nobody claimed.
            #
            # The declared prim is derived from the DECLARED pose, not from
            # the true one. In a conflict cell the two give the same answer,
            # since declared is the opposite of true by construction, but
            # only by coincidence, and the coincidence ends as soon as a
            # second flip object exists.
            declared_pose = meta["declared_pose"]
            if declared_pose is None or declared_pose == meta["true_pose"]:
                legal_decl = legal_true
            else:
                declared_prim = pose_prim(meta["flip_label"], declared_pose)
                if declared_prim is None:
                    raise SystemExit(
                        f"no registry entry for {meta['flip_label']!r} in "
                        f"pose {declared_pose!r}. A conflict trial whose "
                        f"declared pose has no real entry cannot be graded, "
                        f"and guessing one would fabricate the comparison.")
                legal_decl = legal_arms(scene, declared_prim, task_id)

            partner_id = partner_task_id(scene["state"], meta["flip_prim"])
            partner_legal = legal_arms(scene, meta["flip_prim"], partner_id)
            row = G.grade_round(text, meta, task_id, partner_id,
                                legal_true, legal_decl, partner_legal)
            row["partner_legal"] = sorted(partner_legal)
            row["partner_task"] = partner_id
            row.update({"trial_id": tid, "model": model, "error": err,
                        "latency_ms": round((time.time() - t0) * 1000, 1),
                        "legal_true": sorted(legal_true),
                        "legal_declared": sorted(legal_decl),
                        "raw": text})
            row.update({k: t[k] for k in ("seq", "kind", "view", "condition",
                                          "rung")})
            row.update({k: meta[k] for k in ("true_pose", "declared_pose",
                                             "direction", "true_grasp_m",
                                             "declared_grasp_m")})
            if fh:
                fh.write(json.dumps(row) + "\n")
                fh.flush()
            n_done += 1
            if n_done % 20 == 0:
                print(f"[ex2] {n_done}/{len(plan) - n_skip}", file=sys.stderr)
    finally:
        if fh:
            fh.close()
    print(f"[ex2] {n_done} trials, {n_skip} already done, "
          f"{len(plan)} planned")
    return n_done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", default="out/ex2_capture")
    ap.add_argument("--out", default=None)
    ap.add_argument("--model", default=None, help="registry alias")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--pair", default=None,
                    help="run one pair and its null, e.g. p02 or e01. "
                         "Everything else is left alone, and rows append to "
                         "the same file, so pairs can be run one at a time.")
    ap.add_argument("--keep-errors", action="store_true",
                    help="do not retry rows that errored or failed to parse")
    ap.add_argument("--dry-run", action="store_true",
                    help="render prompts, send nothing, spend nothing")
    ap.add_argument("--view", default=None, choices=VIEWS)
    ap.add_argument("--rung", default=None, choices=P.RUNGS)
    ap.add_argument("--condition", default=None, choices=T.CONDITIONS)
    ap.add_argument("--show", default=None,
                    help="print the full rendered prompt for one trial id "
                         "and exit, e.g. p02_A|ex2_cam|conflict|P2")
    a = ap.parse_args(argv)

    if a.show:
        seq, view, condition, rung = a.show.split("|")
        scenes = {s["seq"]: s for s in load_scenes(a.probes)}
        messages, meta = render(scenes[seq], condition, rung, view)
        print("=" * 70)
        print("SYSTEM")
        print("=" * 70)
        print(messages[0]["content"])
        print("=" * 70)
        print("USER  (the state the model reads; image block omitted)")
        print("=" * 70)
        for block in messages[1]["content"]:
            if block.get("type") == "text":
                print(block["text"])
            else:
                print(f"[{block.get('type')} block, not shown]")
        print("\n--- meta ---")
        print(json.dumps({k: v for k, v in meta.items() if k != "prim_of"},
                         indent=1))
        return 0

    if not a.dry_run and not a.out:
        ap.error("--out is required unless --dry-run is given")
    run(a.probes, a.out, model=a.model, limit=a.limit, dry_run=a.dry_run,
        views=(a.view,) if a.view else VIEWS,
        rungs=(a.rung,) if a.rung else P.RUNGS,
        conditions=(a.condition,) if a.condition else T.CONDITIONS,
        pair=a.pair, retry_errors=not a.keep_errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
