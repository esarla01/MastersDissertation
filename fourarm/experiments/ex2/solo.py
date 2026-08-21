"""EX2 solo: one queued task, one arm, no round.

WHY THIS REPLACES THE ROUND. The batch version asked the model to serve two
tasks that compete for one UR. That competition is EX3's subject, and it
meant a wrong answer could be a capability misjudgement OR a coordination
failure, with no way to tell which. Solo queues the mustard alone. The
clamp stays in the state as an object and stays visible in the image, so
the picture is unchanged, but it is no longer a task and no longer competes
for an arm.

WHY A SINGLE CHOICE CARRIES INFORMATION HERE. An earlier single-task
attempt failed because the UR was legal under both the true and the
declared pose, so the arm named said nothing about which source the model
believed. The prompt's G6 fixes that by preferring a Franka:

    upright, 0.058   the Franka can take it        correct arm: franka_n
    lying,   0.096   over the Franka's 0.080       correct arm: the UR

So the correct arm differs by pose, and under conflict, following the text
and following the image give OPPOSITE arms on every trial.

Verified across all 22 pair scenes: franka_n is reachable and idle in every
one, and the idle set is always exactly one UR plus franka_n. Note that
franka_s appears in reach_ok_arms for eight scenes but is never idle, so R2
rules it out; the model has to intersect reach with idle.

WHAT THIS GIVES UP. With nothing competing for the UR, naming the UR when a
Franka would do costs nothing, so suboptimal-but-legal choices are
invisible. That is inherent to the redesign.

It is a driver, not a second implementation. The state transforms, the
legality computation, the validator call and the grader all come from the
modules the rest of EX2 uses.

Usage:
    python3 -m experiments.ex2.solo --dry-run
    python3 -m experiments.ex2.solo --out runs/ex2_solo.jsonl
    python3 -m experiments.ex2.solo --out runs/ex2_solo.jsonl --repeats 3
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

from core.decision.vlm_allocator import openai_chat              # noqa: E402
from experiments.ex2 import grade as G                           # noqa: E402
from experiments.ex2 import prompts as P                         # noqa: E402
from experiments.ex2 import transforms as T                      # noqa: E402
from experiments.ex2.labels import pose_prim                     # noqa: E402
from experiments.ex2.run import (flip_task_id, legal_arms,       # noqa: E402
                                 load_scenes, select_scenes)

CONDITIONS = ("congruent", "conflict", "dims")
DEFAULT_MODELS = ("qwen", "gpt")
VIEW = "ex2_cam"
RUNG = "P2"          # default; --rung overrides

# G6 pulls toward one arm type, and a Franka is legal only at 0.058 m. On a
# lying scene 0.058 is the TEXT's number; on an upright one it is the
# IMAGE's. So a model that merely leans Franka scores as follows_state in
# one direction and follows_image in the other, and cannot be told apart
# from one reading the picture. Under the UR preference the pull is toward
# 0.096 and the two accounts predict opposite arms.
PREFERENCES = ("franka", "ur")

# "V" sends the image, "A" does not. The text-only rung is the floor for
# the whole ladder: whatever the model gets right with no picture at all is
# what the structured state alone supports, and every image condition has
# to be read against it.
MODALITIES = ("V", "A")


def queue_flip_only(state, flip_label):
    """Drop every task except the flip object's. Objects are untouched.

    The clamp remains in "objects", so the state still describes the scene
    the camera saw. Removing it from the objects list would leave the text
    denying something plainly visible in the image, which is a mismatch the
    experiment never intended to introduce.
    """
    out = copy.deepcopy(state)
    kept = [t for t in out.get("tasks", []) if t.get("object") == flip_label]
    if len(kept) != 1:
        raise ValueError(
            f"expected exactly one task for {flip_label!r}, found "
            f"{len(kept)}. A solo trial with no task has nothing to ask "
            f"about, and one with two is not solo.")
    out["tasks"] = kept
    return out


def neutralise_baskets(state):
    """Rename the baskets so none is named for a category.

    WHY. basket_food is reachable by ur_w and franka_n. In the eleven west
    scenes the idle UR is ur_w and can deliver directly; in the eleven east
    scenes it is ur_e and cannot reach that basket at all. So a correctly
    assigned lying bottle needed a handover in one half of the sample and
    not the other, putting a delivery cost on the very arm choice under
    test, in exactly the cells where the conflict manipulation works.

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
    baskets = out.get("baskets") or {}
    if not baskets:
        raise ValueError(
            "the state has no baskets. A solo trial still names a "
            "destination, since dest_xy is null in every capture.")
    rename = {}
    for i, name in enumerate(sorted(baskets), start=1):
        rename[name] = "box_%d" % i
    out["baskets"] = {rename[k]: v for k, v in baskets.items()}
    for task in out.get("tasks", []):
        if task.get("dest_basket") in rename:
            task["dest_basket"] = rename[task["dest_basket"]]
    return out


def render(scene, condition, preference="franka", rung=RUNG,
           modality="V"):
    """(messages, meta) for one solo trial."""
    probe = {"state": scene["state"],
             "positions_exact": scene["positions_exact"]}
    state, meta = T.transform(probe, condition)
    state = queue_flip_only(state, meta["flip_label"])
    state = neutralise_baskets(state)
    b64 = None
    if modality == "V":
        with open(scene["images"][VIEW], "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    return P.build_ex2_prompt(state, rung, condition, image_b64=b64,
                              view=VIEW, solo=True,
                              preference=preference), meta


def one_trial(scene, condition, model, preference="franka", rung=RUNG,
              modality="V", model_fn=openai_chat, timeout=90.0):
    messages, meta = render(scene, condition, preference, rung, modality)

    text, error, usage = "", None, {}
    t0 = time.time()
    for attempt in (1, 2):
        try:
            # Ask for the provider's token accounting where the client
            # supports it. A fake model_fn in the harness will not, so the
            # call falls back rather than failing.
            try:
                text, usage = model_fn(messages, timeout=timeout,
                                       alias=model, return_usage=True)
            except TypeError:
                text, usage = model_fn(messages, timeout=timeout,
                                       alias=model), {}
            error = None
            break
        except Exception as exc:                       # noqa: BLE001
            error = "%s: %s" % (type(exc).__name__, exc)
            if attempt == 2:
                break
            time.sleep(2.0)

    task_id = flip_task_id(scene["state"], meta["flip_prim"])
    legal_true = legal_arms(scene, meta["flip_prim"], task_id)

    # The declared legal set is the same question asked of the pose the
    # TEXT claims. Under congruent and dims the text claims nothing
    # different, so it is the same set: computing it from the other pose
    # would score a correct assignment as wrong.
    declared = meta["declared_pose"]
    if declared is None or declared == meta["true_pose"]:
        legal_decl = legal_true
    else:
        legal_decl = legal_arms(
            scene, pose_prim(meta["flip_label"], declared), task_id)

    row = G.grade(text, meta, legal_true, legal_decl,
                  limits=G.arm_limits(scene["state"]))
    row.update({"seq": scene["seq"], "condition": condition, "model": model,
                "view": VIEW, "rung": rung, "error": error, "solo": True,
                "ex2_prompt_version": P.EX2_PROMPT_VERSION,
                "preference": preference, "modality": modality,
                "latency_ms": round((time.time() - t0) * 1000, 1),
                "prompt_tokens": (usage or {}).get("prompt_tokens"),
                "completion_tokens": (usage or {}).get("completion_tokens"),
                "total_tokens": (usage or {}).get("total_tokens"),
                "true_pose": meta["true_pose"],
                "declared_pose": meta["declared_pose"],
                "true_grasp_m": meta["true_grasp_m"],
                "declared_grasp_m": meta.get("declared_grasp_m"),
                "flip_task": task_id,
                "legal_true": sorted(legal_true),
                "legal_declared": sorted(legal_decl),
                "franka_expected": any(a.startswith("franka")
                                       for a in legal_true)})
    return row


def infeasible(row):
    """Would the named arm physically fail to close on the object.

    The one judgement that is unambiguous in a conflict trial. "Correct"
    there is ambiguous by construction, since the text is deliberately
    false and each source licenses a different arm, so the outcome labels
    say which source was followed rather than right or wrong. But an arm
    whose aperture cannot span the TRUE width fails on the table whatever
    the text claimed, and that is worth counting on its own.

    Read from legal_true, which is computed by the real validator under
    the true pose. Returns None when no arm was named, which is a wait
    rather than an infeasible pick.
    """
    arm = row.get("arm")
    if not arm:
        return None
    return arm not in (row.get("legal_true") or [])


def table(rows):
    """Outcomes per model per condition, plus the arm actually named.

    Congruent and dims are scored against the truth: nothing disagrees with
    the picture, so there is no source to prefer. Only conflict gets the
    image and state labels, and width belief is reported there alone,
    because elsewhere both sources state the same number and any verdict is
    an artefact rather than a signal.
    """
    out = []
    head = ("%-6s %-10s %-10s %-5s %-4s %-34s | %-12s | %s"
            % ("model", "pref/rung", "condition", "pose", "n", "outcomes",
               "infeasible", "arms"))
    out += [head, "-" * max(len(head), 70)]
    prefs = sorted({(r.get("preference", "franka"), r.get("rung", RUNG))
                    for r in rows})
    for model in sorted({r["model"] for r in rows}):
      for pref, rung in prefs:
        for cond in CONDITIONS:
            for pose in ("lying", "upright"):
                sub = [r for r in rows if r["model"] == model
                       and r.get("preference", "franka") == pref
                       and r.get("rung", RUNG) == rung
                       and r["condition"] == cond and r["true_pose"] == pose]
                if not sub:
                    continue
                counts = {}
                for r in sub:
                    counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
                arms = {}
                for r in sub:
                    key = r.get("arm") or "none"
                    arms[key] = arms.get(key, 0) + 1
                infs = sum(1 for r in sub if infeasible(r))
                out.append("%-6s %-10s %-10s %-5s %-4d %-34s | infeas %2d/%-3d"
                           " | arms: %s"
                           % (model, "%s/%s" % (pref, rung), cond, pose,
                              len(sub),
                              "  ".join("%s=%d" % (k, counts[k])
                                        for k in sorted(counts)),
                              infs, len(sub),
                              "  ".join("%s=%d" % (k, arms[k])
                                        for k in sorted(arms))))
        sub = [r for r in rows if r["model"] == model
               and r.get("preference", "franka") == pref
               and r.get("rung", RUNG) == rung
               and r["condition"] == "conflict"]
        if sub:
            wb = {}
            for r in sub:
                wb[r["width_belief"]] = wb.get(r["width_belief"], 0) + 1
            out.append("%-6s %-10s %-10s %-5s %s"
                       % (model, "%s/%s" % (pref, rung), "  width", "",
                          "  ".join("%s=%d" % (k, wb[k])
                                    for k in sorted(wb))))
        # A reply that states a width its own named arm cannot take is not
        # evidence that either source won, so it is counted apart from the
        # cue-following outcomes rather than inside them.
        allr = [r for r in rows if r["model"] == model
                and r.get("preference", "franka") == pref
                and r.get("rung", RUNG) == rung]
        contra = sum(1 for r in allr if r.get("self_contradicted"))
        if contra:
            by_cond = {}
            for r in allr:
                if r.get("self_contradicted"):
                    by_cond[r["condition"]] = by_cond.get(r["condition"],
                                                          0) + 1
            out.append("%-6s %-10s %-10s %-4d %s"
                       % (model, "%s/%s" % (pref, rung), "  self-contradicted", contra,
                          "  ".join("%s=%d" % (k, by_cond[k])
                                    for k in sorted(by_cond))))
        reasoning = {}
        for r in allr:
            reasoning[r.get("reasoning")] = reasoning.get(
                r.get("reasoning"), 0) + 1
        out.append("%-6s %-10s %-10s %-5s %s"
                   % (model, "%s/%s" % (pref, rung), "  reasoning", "",
                      "  ".join("%s=%d" % (k, reasoning[k])
                                for k in sorted(reasoning, key=str))))
        out.append("")
    return "\n".join(out).rstrip()


def cost_table(rows):
    """Tokens and wall time per call, by model and modality.

    Token counts are the provider's own. Image tokens depend on resolution
    and on how the provider tiles the picture, so a local estimate would be
    wrong by an unknown factor; anything reported has to come from the
    response.
    """
    out = []
    head = ("%-6s %-3s %-5s %-6s %-9s %-9s %-9s %s"
            % ("model", "mod", "rung", "n", "prompt", "reply", "total",
               "median s"))
    out += [head, "-" * len(head)]
    groups = {}
    for r in rows:
        if r.get("error"):
            continue
        key = (r["model"], r.get("modality", "V"), r.get("rung", RUNG))
        groups.setdefault(key, []).append(r)
    for key in sorted(groups, key=str):
        sub = groups[key]

        def _mean(field):
            vals = [r[field] for r in sub if r.get(field) is not None]
            return sum(vals) / len(vals) if vals else float("nan")

        lat = sorted(r["latency_ms"] / 1000.0 for r in sub
                     if r.get("latency_ms"))
        med = lat[len(lat) // 2] if lat else float("nan")
        out.append("%-6s %-3s %-5s %-6d %-9.0f %-9.0f %-9.0f %.1f"
                   % (key[0], key[1], key[2], len(sub),
                      _mean("prompt_tokens"), _mean("completion_tokens"),
                      _mean("total_tokens"), med))
    tot = sum(r.get("total_tokens") or 0 for r in rows)
    secs = sum((r.get("latency_ms") or 0) / 1000.0 for r in rows)
    out.append("")
    out.append("totals: %d tokens, %.0f s of model time over %d calls"
               % (tot, secs, len(rows)))
    return "\n".join(out)


def run(capture_dir, out_path=None, models=DEFAULT_MODELS,
        conditions=CONDITIONS, preferences=("franka",), rungs=(RUNG,),
        modalities=("V",), kind="pair", repeats=1, pair=None, limit=None,
        dry_run=False,
        model_fn=openai_chat, timeout=90.0):
    scenes = [s for s in load_scenes(capture_dir)
              if kind is None or s["kind"] == kind]
    scenes = select_scenes(scenes, pair)
    if not scenes:
        raise SystemExit(f"no {kind!r} scenes in {capture_dir}")
    plan = [(s, c) for s in scenes for c in conditions]
    if limit:
        plan = plan[:limit]

    if dry_run:
        for scene, cond in plan:
            _, meta = render(scene, cond)
            print("%-8s %-10s true=%-8s declared=%-8s"
                  % (scene["seq"], cond, meta["true_pose"],
                     meta["declared_pose"]))
        print("--- %d scene-conditions x %d model(s) x %d preference(s) "
              "x %d rung(s) x %d repeat(s) = %d calls, none made"
              % (len(plan), len(models), len(preferences), len(rungs),
                 repeats, len(plan) * len(models) * len(preferences)
                 * len(rungs) * repeats))
        return []

    # A row that ERRORED is not an answer. Skipping it on resume is how a
    # run of missing-key rows once re-reported itself as complete having
    # made no calls at all.
    done = set()
    if out_path and os.path.exists(out_path):
        for line in open(out_path):
            if line.strip():
                r = json.loads(line)
                if (r.get("error") is None
                        and r.get("outcome") != "unparseable"):
                    done.add(r.get("trial_id"))

    handle = open(out_path, "a") if out_path else None
    try:
        for model in models:
            for pref in preferences:
              for rung in rungs:
               for modality in modalities:
                for rep in range(1, repeats + 1):
                    for scene, cond in plan:
                        # The rung is part of the id. Without it a P3 run
                        # pointed at a P2 file would find every trial
                        # present, skip the lot and report itself complete
                        # having spent nothing.
                        tid = "%s|%s|%s|%s|%s|%s|r%d" % (
                            scene["seq"], cond, model, pref, rung, modality,
                            rep)
                        if tid in done:
                            continue
                        row = one_trial(scene, cond, model, pref, rung,
                                        modality, model_fn=model_fn,
                                        timeout=timeout)
                        row["trial_id"] = tid
                        row["repeat"] = rep
                        if handle:
                            handle.write(json.dumps(row) + "\n")
                            handle.flush()
                        print("%-5s %-6s %-3s %s r%d %-8s %-10s true=%-8s "
                              "-> arm=%-10s %s"
                              % (model, pref, rung, modality, rep,
                                 scene["seq"], cond,
                                 row["true_pose"], row.get("arm") or "none",
                                 row["outcome"]))
    finally:
        if handle:
            handle.close()

    all_rows = []
    if out_path and os.path.exists(out_path):
        seen = {}
        for line in open(out_path):
            if line.strip():
                r = json.loads(line)
                seen[r.get("trial_id")] = r      # later wins on retry
        all_rows = list(seen.values())
    print()
    print(table(all_rows))
    print()
    print(cost_table(all_rows))
    return all_rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probes", default="out/ex2_capture")
    ap.add_argument("--out", default=None)
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--condition", action="append", dest="conditions",
                    default=None, choices=CONDITIONS)
    ap.add_argument("--kind", default="pair", choices=("pair", "null", "all"))
    ap.add_argument("--pair", default=None, help="one pair id, e.g. p03")
    ap.add_argument("--preference", action="append", dest="preferences",
                    default=None, choices=PREFERENCES,
                    help="arm type G6 prefers; repeatable. Give both to "
                         "counterbalance, which is what tells an "
                         "image-reading model apart from one that just "
                         "leans toward the preferred arm.")
    ap.add_argument("--rung", action="append", dest="rungs", default=None,
                    choices=P.RUNGS,
                    help="prompt rung; repeatable. P3 asks the model to "
                         "justify before naming an arm, and gets a schema "
                         "with \"why\" first so the instruction can bite.")
    ap.add_argument("--modality", action="append", dest="modalities",
                    default=None, choices=MODALITIES,
                    help="V sends the image, A does not. A is the text-only "
                         "floor the image conditions are read against.")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    if not a.dry_run and not a.out:
        raise SystemExit("--out is required for a live run: paid calls that "
                         "are not written down cannot be resumed.")
    run(a.probes, out_path=a.out,
        models=tuple(x.strip() for x in a.models.split(",") if x.strip()),
        conditions=tuple(a.conditions) if a.conditions else CONDITIONS,
        preferences=tuple(a.preferences) if a.preferences else ("franka",),
        rungs=tuple(a.rungs) if a.rungs else (RUNG,),
        modalities=tuple(a.modalities) if a.modalities else ("V",),
        kind=None if a.kind == "all" else a.kind,
        repeats=a.repeats, pair=a.pair, limit=a.limit, dry_run=a.dry_run,
        timeout=a.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())