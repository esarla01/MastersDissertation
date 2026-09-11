"""EX2 runner: turn captured scenes into trials, ask a model, grade, stream.

WHAT A TRIAL IS. One captured scene, one condition, one rung, one view, one
model. The picture never changes within a scene; the text does.

    scenes      44 captures: 11 positions x pair/null x A/B member
    conditions  congruent, conflict, dims
    rungs       N0, N-A, N-C, N-order, N-D, N-CD
    views       ex2_cam (oblique), table_cam (overhead)

ONE TASK, ONE ARM. The prompt module offers a single shape: the model is
asked for one queued task and one idle arm. The batch round it used to ask
for is gone, so a trial queues the flip object ALONE and is graded as a
single assignment. The partner object stays in "objects" and stays visible
in the image, so the picture is unchanged; it is simply no longer a task.

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
                                         chat)
from harvest.frozen_coord import from_record                     # noqa: E402
from experiments.ex2 import grade as G                            # noqa: E402
from experiments.ex2 import prompts as P                          # noqa: E402
from experiments.ex2 import transforms as T                       # noqa: E402
from experiments.ex2.labels import (POSE_ENTRIES,                 # noqa: E402
                                    TRUE_POSE, pose_prim, require_face)

VIEWS = ("ex2_cam", "table_cam")

# Declaration order from the prompt module, so a table reads N0 first and
# the rungs never reorder themselves when the dict is rebuilt. P.RUNGS is a
# dict now, and iterating it directly would put the schema spec where a
# rung name belongs.
#
# THE LADDER, not every rung. P.RUNGS also holds the off-ladder precedence
# directives, and this is trials()' DEFAULT, swept over CORE_CONDITIONS.
# Taking every rung would grow this driver's default cost each time a
# variant was added -- the failure CORE_CONDITIONS is pinned to prevent --
# and worse here: a directive is vacuous in dims, which that sweep
# includes, so the widened default would not merely cost more, it would
# raise mid-run.
RUNGS = tuple(P.LADDER_RUNGS)

# --rung may still ASK for a directive; it just is not swept by default.
ALL_RUNGS = tuple(P.RUNGS)

PREFERENCES = tuple(P.PREFERENCE_TEXT)

_ZM = None


def zonemap():
    global _ZM
    if _ZM is None:
        _ZM = ZoneMap()
    return _ZM


def baskets():
    from ycb_scene import BASKETS
    return BASKETS


def load_scenes(capture_dir, present_ur=True, quiet=False):
    """Every captured scene THIS DESIGN USES, images resolved to real paths.

    The idle UR is normalised here, ONCE, so every consumer -- the prompt,
    the legality computation and the grader -- sees the same idle set. See
    present_reachable_ur. Pass present_ur=False to read the captures exactly
    as they were written.

    SCENES FROM A RETIRED ORIENTATION ARE SKIPPED, AND COUNTED. When the
    design dropped to two resting faces on 2026-08-27 it left 34 captures of
    the third on disk, deliberately: they are evidence, and re-rendering the
    directory to remove them would have discarded 68 good frames with them.
    Their flip object is no longer a registry pose entry, so every consumer
    downstream -- describe(), require_face(), the grader -- would raise on
    them, one at a time and far from the cause.

    They are dropped here instead, once, and the count is PRINTED rather
    than swallowed. A sample that quietly shrinks is the failure this whole
    module is written against; a sample that says "34 captures skipped, they
    rest on a face this design no longer uses" is a fact the reader can
    check. Pass quiet=True in a harness that asserts on the count instead.
    """
    trail = os.path.join(capture_dir, "consults.jsonl")
    if not os.path.exists(trail):
        raise SystemExit(f"no capture trail at {trail}")
    out, retired = [], []
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
        state = rec["state"]
        # The flip object identifies the orientation. A capture whose flip
        # prim is not a current pose entry belongs to a retired design.
        prims = [o["name"] for o in state.get("objects", [])
                 if o["name"] in POSE_ENTRIES]
        if not prims:
            retired.append(rec["seq"])
            continue
        idle_ur = None
        if present_ur:
            state, idle_ur = present_reachable_ur(state)
        out.append({"seq": rec["seq"], "state": state,
                    "positions_exact": rec.get("positions_exact"),
                    "kind": ex2.get("kind", "pair"), "images": images,
                    "frame_path": None, "idle_ur": idle_ur,
                    "provenance": {"seq": rec["seq"], "round": 0}})
    if retired and not quiet:
        print("[ex2] %d capture(s) skipped: they rest on a face this design "
              "no longer uses, and are kept on disk as evidence. %s%s"
              % (len(retired), ", ".join(sorted(retired)[:4]),
                 " ..." if len(retired) > 4 else ""))
    if not out:
        raise SystemExit(
            f"{capture_dir} holds {len(retired)} capture(s) and every one "
            f"rests on a retired face. Nothing in this directory can be run "
            f"against the current design.")
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
            # Per-label facts: the block's resting-face names
            # (small_face, edge, large_face) do not exist in the mustard
            # pilot's flat POSE_FACTS. POSE_ENTRIES maps a prim to its
            # neutral label, which keys POSE_FACTS_BY_LABEL.
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


def queue_flip_only(state, flip_label):
    """Drop every task except the flip object's. Objects are untouched.

    The partner remains in "objects", so the state still describes the
    scene the camera saw. Removing it from the objects list would leave the
    text denying something plainly visible in the image, which is a
    mismatch the experiment never intended to introduce.

    Lives here rather than in solo.py because every driver now needs it:
    the prompt asks for ONE task and one arm, so a scene with two queued
    tasks would let the model answer about the partner and the trial would
    measure nothing.
    """
    out = copy.deepcopy(state)
    kept = [t for t in out.get("tasks", []) if t.get("object") == flip_label]
    if len(kept) != 1:
        raise ValueError(
            f"expected exactly one task for {flip_label!r}, found "
            f"{len(kept)}. A trial with no task has nothing to ask about, "
            f"and one with two is not a single assignment.")
    out["tasks"] = kept
    return out


def present_reachable_ur(state, strict=True):
    """Present the UR that can actually reach the flip object as the idle one.

    WHY THIS IS NEEDED. Two rules gate an assignment: R2 admits only an idle
    arm, R6 only an arm in the object's reach list. Every EX2 block capture
    was made with capture_ex2_scene's default --idle "ur_w,franka_n", so
    ur_w is the idle UR in all 90 scenes. That is right for the 15 west
    positions and wrong for the 15 east ones, where the object is reached
    by ur_e:

        west   idle & reach = {franka_n, ur_w}   two candidates, and which
                                                 one is correct depends on
                                                 the opening. The measurement
        east   idle & reach = {franka_n}         on the two 0.050 faces the
                                                 Franka is the only legal arm
                                                 AND the preferred one, so
                                                 every model names it; on
                                                 large_face nothing is legal
                                                 at all

    So the east half carried no contrast. ycb/ex2_block.txt says the intent
    was "reachable by franka_n AND by the nearer UR (ur_w west / ur_e
    east)"; the default flag simply never varied.

    WHY IT IS LEGITIMATE TO FIX IT HERE. capture_ex2_scene sets ag.state by
    attribute write AFTER the frames are rendered, and never commands an arm
    to move: all four ee_xy are symmetric rest positions. The picture shows
    four parked arms whichever labels the text carries, so this is a
    text-layer choice exactly like the basket names and the queued task, and
    it contradicts nothing in the image.

    CHOSEN FROM GEOMETRY, not from the seq prefix. The UR kept is the one in
    the object's own reach_ok_arms, so this stays correct for a scene list
    that does not name its positions west and east.

    Applied to the CAPTURED state, before anything else, so the prompt and
    the legality computation see one idle set. Presenting one arm and
    grading against another would score every correct answer wrong.
    """
    from experiments.ex2.labels import POSE_ENTRIES, neutral_name

    out = copy.deepcopy(state)
    urs = [n for n, a in C.ARMS.items() if a["type"] == "ur10"]
    flips = [o for o in out.get("objects", [])
             if o["name"] in POSE_ENTRIES
             or neutral_name(o["name"]) != o["name"]]
    if len(flips) != 1:
        raise ValueError(
            f"expected exactly one pose-varying object, found "
            f"{[o['name'] for o in flips]}. The idle UR is chosen from that "
            f"object's reach list, and with two of them the choice would be "
            f"arbitrary.")
    near = [u for u in urs if u in (flips[0].get("reach_ok_arms") or [])]
    if len(near) != 1:
        if not strict:
            return out, None
        raise ValueError(
            f"{len(near)} of the UR arms reach {flips[0]['name']!r} "
            f"({near}). Exactly one must, or there is no 'nearer UR' to "
            f"present and the idle set would be a guess. Every block "
            f"capture satisfies this; a scene set that does not needs its "
            f"positions rechecked rather than a default applied.")

    for arm in out.get("arms", []):
        if arm["name"] in urs:
            arm["state"] = "IDLE" if arm["name"] == near[0] else "TO_PICK"
    return out, near[0]


def neutralise_baskets(state):
    """Rename the baskets so none is named for a category.

    WHY. basket_food is reachable by ur_w and franka_n. In the west scenes
    the idle UR is ur_w and can deliver directly; in the east scenes it is
    ur_e and cannot reach that basket at all. So a correctly assigned
    object needed a handover in one half of the sample and not the other,
    putting a delivery cost on the very arm choice under test, in exactly
    the cells where the conflict manipulation works.

    Renaming rather than moving. Which physical box holds which category is
    arbitrary, so dropping the categories misrepresents nothing, and it
    leaves the captured images untouched. Relabelling one box as food in
    east scenes would instead make the text disagree with whatever the
    colours in the picture imply, which is an unintended text-image
    conflict inside an experiment that measures text-image conflict.

    The object's "category" field is left alone: it is true, and with no
    basket named for a category it now decides nothing.
    """
    out = copy.deepcopy(state)
    baskets_now = out.get("baskets") or {}
    if not baskets_now:
        raise ValueError(
            "the state has no baskets. A trial still names a destination, "
            "since dest_xy is null in every capture.")
    rename = {}
    for i, name in enumerate(sorted(baskets_now), start=1):
        rename[name] = "box_%d" % i
    out["baskets"] = {rename[k]: v for k, v in baskets_now.items()}
    for task in out.get("tasks", []):
        if task.get("dest_basket") in rename:
            task["dest_basket"] = rename[task["dest_basket"]]
    return out


def partner_task_id(state, flip_prim):
    """The other queued task in a CAPTURED EX2 scene.

    A trial queues the flip object alone, so this is not used to build the
    prompt. It is kept because the captured states carry both tasks and
    because grade.grade_round, which scores the historical batch replies,
    needs the partner's id.
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
    # Match on the STEM, and on the numbered variants only when the id
    # carries one of the pilot prefixes. The old rule stripped a leading
    # p/n/e/m and rebuilt four ids, which meant "e00" resolved and "w00"
    # did not: 'w' is not in that set, so the stem was rebuilt as "pw00"
    # and matched nothing. Half the block positions were unselectable.
    stems = {s["seq"].rsplit("_", 1)[0] for s in scenes}
    want = {pair}
    if pair and pair[0] in "pnem" and pair[1:].isdigit():
        want |= {f"{p}{pair[1:]}" for p in "pnem"}
    want &= stems or want
    got = [s for s in scenes if s["seq"].rsplit("_", 1)[0] in want]
    if not got:
        raise SystemExit(
            f"no scenes for pair {pair!r}. Captured pairs: "
            f"{sorted({s['seq'].rsplit('_', 1)[0] for s in scenes})}")
    return got


def trials(scenes, views=VIEWS, rungs=RUNGS, conditions=T.CORE_CONDITIONS):
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


def trial_id(t, model, preference="franka"):
    """Stable identity for one trial.

    The PREFERENCE is part of it. G1 names an arm type on every prompt, so
    the two settings are different questions; sharing an id would let a UR
    run resume onto a Franka file, find every trial present and report
    itself complete having spent nothing.
    """
    return (f"{t['seq']}|{t['view']}|{t['condition']}|{t['rung']}"
            f"|{preference}|{model}")


def render(scene, condition, rung, view, preference="franka"):
    """(messages, meta) for one trial.

    `view` names which CAPTURED IMAGE to attach. It is no longer passed to
    the prompt module: the camera convention is fixed there, so a prompt
    built for one camera and sent with another's frame would describe a
    viewpoint that is not attached.
    """
    probe = {"state": scene["state"],
             "positions_exact": scene["positions_exact"]}
    state, meta = T.transform(probe, condition)
    # The prompt module renders the pose value as it finds it, so a capture
    # whose poses are not resting faces would show the model a word the
    # answer schema does not list -- and be scored against it. Checked here,
    # before the image is read and long before a call is paid for.
    require_face(meta["true_pose"], P.RESTING_FACES)
    state = queue_flip_only(state, meta["flip_label"])
    state = neutralise_baskets(state)
    with open(scene["images"][view], "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return P.build_ex2_prompt(state, rung, condition, image_b64=b64,
                              preference=preference), meta


def run(capture_dir, out_path, model=None, limit=None, dry_run=False,
        views=VIEWS, rungs=RUNGS, conditions=T.CORE_CONDITIONS,
        preference="franka", model_fn=chat, timeout=90.0, pair=None,
        retry_errors=True):
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
            tid = trial_id(t, model, preference)
            if tid in done:
                n_skip += 1
                continue
            scene = scenes[t["seq"]]
            messages, meta = render(scene, t["condition"], t["rung"],
                                    t["view"], preference)
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

            # One task, one arm. grade_round scored a whole round, which
            # the prompt no longer asks for; scoring a single-assignment
            # reply as an incomplete round would file every trial as a
            # schema failure.
            row = G.grade(text, meta, legal_true, legal_decl,
                          limits=G.arm_limits(scene["state"]))
            row["flip_task"] = task_id
            row.update({"trial_id": tid, "model": model, "error": err,
                        "ex2_prompt_version": P.EX2_PROMPT_VERSION,
                        "latency_ms": round((time.time() - t0) * 1000, 1),
                        "preference": preference,
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
    ap.add_argument("--rung", default=None, choices=ALL_RUNGS)
    ap.add_argument("--condition", default=None, choices=T.CONDITIONS)
    ap.add_argument("--preference", default="franka", choices=PREFERENCES,
                    help="arm type G1 prefers. A UR is legal on every "
                         "resting face, so under the UR setting the arm "
                         "named carries no information and the cell is the "
                         "counterbalance rather than a result.")
    ap.add_argument("--show", default=None,
                    help="print the full rendered prompt for one trial id "
                         "and exit, e.g. p02_A|ex2_cam|conflict|N0")
    a = ap.parse_args(argv)

    if a.show:
        seq, view, condition, rung = a.show.split("|")
        scenes = {s["seq"]: s for s in load_scenes(a.probes)}
        messages, meta = render(scenes[seq], condition, rung, view,
                                a.preference)
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
        rungs=(a.rung,) if a.rung else RUNGS,
        conditions=(a.condition,) if a.condition else T.CONDITIONS,
        preference=a.preference,
        pair=a.pair, retry_errors=not a.keep_errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
