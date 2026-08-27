"""EX2 step 1: pose-neutral object labels.

THE PROBLEM. A captured state names the flip object by its registry entry,
`ycb_mustard_lying` or `ycb_mustard_upright`. That word is the answer,
written into the text the model reads. Three separate ways it would break
the experiment:

  - In a CONFLICT cell the suffix would contradict the declared `pose`
    field, so the falsification would no longer be internally consistent
    and the model could spot the lie without ever looking at the image.
  - It would make "follows the state" ambiguous about WHICH part of the
    state was followed, the name or the declared geometry.
  - In the DIMS condition, where the resting face is deliberately withheld,
    the name would hand it straight back.

THE FIX. The prompt sees `ycb_mustard` in every condition. The true entry
travels alongside as `prim`, is never rendered, and is what the grader
scores against and what physics registration keys on.

The label is NOT anonymised further. R7 needs the category to choose a
basket, and the name's prior is part of what the experiment measures: a
model leaning on what it knows about mustard bottles instead of looking is
exactly the behaviour the conflict cells detect.

This is a pure dict transform over a saved probe. Nothing in the live
pipeline changes, so every episode already recorded stays valid.

Usage:
    from experiments.ex2.labels import neutralise
    state, prim_of = neutralise(probe["state"])
    # state  -> shows ycb_mustard, safe to render
    # prim_of["ycb_mustard"] -> "ycb_mustard_upright", the truth
"""

import copy

# Registry entries that are two poses of ONE object, and the label the model
# should see. Extending EX2 to another object means adding a line here and
# nothing else.
POSE_ENTRIES = {
    "ycb_mustard_lying": "ycb_mustard",
    "ycb_mustard_upright": "ycb_mustard",
    # The synthetic block (2026-08-26), which replaced the mustard bottle.
    # ONE object, TWO poses, so two rows collapse to one neutral label.
    # A third prim, ycb_block_small, resting on the middle face, was retired
    # on 2026-08-27; see the note below TRUE_POSE.
    "ycb_block_upright": "ycb_block",
    "ycb_block_large": "ycb_block",
}

# Which pose each entry actually is. The grader needs this; the prompt sees
# the same word, since 2026-08-27, because there is now ONE vocabulary
# rather than a deployed one and a rendered one.
#
# THE BLOCK IS NAMED BY ITS RESTING FACE, and the names are GEOMETRIC. A
# name such as "upright" would describe posture, and posture does not
# determine the opening. The block is 0.130 x 0.100 x 0.050, and the two
# faces it is captured on are
#
#     prim               face down     vertical  opening  name here
#     ycb_block_upright  0.100 x 0.050   0.130    0.050   small_face
#     ycb_block_large    0.130 x 0.100   0.050    0.100   large_face
#
# READ THE TABLE, NOT THE PRIM NAMES. "ycb_block_upright" is named for a
# posture and rests on the genuinely SMALLEST face; the prim names predate
# the geometric vocabulary and are wrong about it. They are kept because
# they are written into the captures on disk. Anyone extending EX2 must key
# on the geometry.
#
# THE RETIRED THIRD FACE (2026-08-27). A third prim, "ycb_block_small",
# rested on the MIDDLE face, 0.130 x 0.050, standing 0.100 with a 0.050
# opening, and was called "edge". It was removed from the design because no
# model separated it from large_face reliably: over 81 answered trials GPT
# scored 58 percent on that pair, Fisher p = 0.76, which is chance. The
# evidence is runs/ex2_q1_cue_*.jsonl, kept on disk. The prim itself and its
# 34 captures also remain on disk and are simply never loaded; the capture
# plan no longer enumerates it and capture_ex2_scene.py now FAILS a capture
# that settles at its height rather than relabelling it.
#
# Two values rather than one because the two faces are NOT interchangeable:
# large_face needs 0.100 m (URs only) and small_face needs 0.050 m (all
# arms), so a single "block" pose would lose the capability contrast.
#
# The MUSTARD keeps its two posture words. It is the pilot object and a
# bottle has no faces, so "lying" and "upright" are not words the answer
# schema lists. require_face below is what stops a mustard capture being
# scored, or sent, against a vocabulary it can never produce. Its rows stay
# readable and its captures stay on disk.
TRUE_POSE = {
    "ycb_mustard_lying": "lying",
    "ycb_mustard_upright": "upright",
    "ycb_block_upright": "small_face",
    "ycb_block_large": "large_face",
}

# ---------------------------------------------------------------------------
# Reading rows written before 2026-08-27
# ---------------------------------------------------------------------------
# Until that date the block's poses were called "upright",
# "lying_large_face" and "lying_small_face". Every EX2 results file in
# runs/ predates it and is a MUSTARD run, whose "upright" means the bottle
# standing and must not be touched.
#
# So the translation is CONDITIONAL on the file. "lying_large_face" and
# "lying_small_face" only ever named the block, so they translate
# unconditionally. "upright" is ambiguous, and is translated only in a file
# that also carries one of those two words, which makes it a block file.
# A blanket rule would have rewritten every mustard row in the tree.
# "edge" is retired from the design but NOT from this table. These entries
# read files written when it existed, and runs/ex2_q1_cue_*.jsonl are kept
# deliberately as the evidence for retiring it. Translating such a row to
# "edge" and letting require_face reject it downstream is the correct
# outcome: a three-face file must fail loudly rather than be scored against
# a two-face design. Deleting the entry would instead leave the old word
# untranslated and the failure harder to read.
LEGACY_BLOCK_POSES = {
    "lying_large_face": "large_face",
    "lying_small_face": "edge",
}

# Only meaningful once the file is known to be a block file.
_LEGACY_AMBIGUOUS = {"upright": "small_face"}


def modernise_poses(rows, field="true_pose"):
    """Rewrite a pre-2026-08-27 block file's pose words, in place.

    Returns the number of rows changed, so a caller can say so rather than
    translating silently. A mustard file is left completely alone and
    returns 0.

    Also rewrites "declared_pose" wherever it appears, since a conflict row
    carries both and translating one would leave the pair disagreeing.
    """
    rows = list(rows)
    is_block = any(r.get(f) in LEGACY_BLOCK_POSES
                   for r in rows for f in (field, "declared_pose"))
    table = dict(LEGACY_BLOCK_POSES)
    if is_block:
        table.update(_LEGACY_AMBIGUOUS)
    changed = 0
    for r in rows:
        hit = False
        for f in (field, "declared_pose"):
            if r.get(f) in table:
                r[f] = table[r[f]]
                hit = True
        changed += hit
    return changed


def block_faces():
    """The resting faces the block actually has, from the registry."""
    return frozenset(TRUE_POSE[p] for p, lab in POSE_ENTRIES.items()
                     if lab == "ycb_block")


def require_face(pose, allowed=None):
    """Return `pose` if it is a resting face, else raise.

    The block's poses ARE the words the answer schema accepts, so this is a
    guard rather than a translation. What it catches is an object whose
    poses are not faces at all -- the mustard pilot above all, whose
    "upright" and "lying" would otherwise be compared against, or shown
    beside, a three-way face enum they can never match.

    `allowed` is passed by callers that know the schema, so the check is
    against the vocabulary the MODEL replies in rather than against this
    module's own idea of it. If the two ever diverge, this is where it
    surfaces.
    """
    allowed = frozenset(allowed) if allowed is not None else block_faces()
    if pose not in allowed:
        raise ValueError(
            f"{pose!r} is not a resting face; expected one of "
            f"{sorted(allowed)}. The answer schema lists exactly those, so "
            f"using this would compare the model against a word it cannot "
            f"produce. The mustard pilot's poses reach here if a mustard "
            f"capture is run through the block design.")
    return pose


def neutral_name(prim):
    """The label for a prim. Objects with only one pose keep their name."""
    return POSE_ENTRIES.get(prim, prim)


def pose_prim(label, pose):
    """The registry entry for one label in one pose, or None.

    The inverse of TRUE_POSE, and it lives here because this module owns
    the prim-to-pose relationship. A caller that spells the two mustard
    entries out by hand is correct only until a second flip object exists,
    which is exactly the extension POSE_ENTRIES promises to make cheap.

    Keyed on LABEL AND POSE, not on pose alone. With one flip object the
    pose is enough; with two, 'upright' names more than one entry, and a
    lookup that ignored the label would silently return the wrong object's
    row.
    """
    for prim, prim_label in POSE_ENTRIES.items():
        if prim_label == label and TRUE_POSE.get(prim) == pose:
            return prim
    return None


def neutralise(state):
    """Return (renamed_state, prim_of) with pose suffixes removed.

    The input is not modified: a probe set is frozen and a transform that
    edited it would change the thing every other condition is compared
    against.

    Raises if two poses of the same object appear in one state. That cannot
    happen in a captured EX2 scene, and if it ever did the rename would
    collapse two distinct objects onto one label and silently corrupt both.
    """
    out = copy.deepcopy(state)
    prim_of = {}

    for obj in out.get("objects", []):
        prim = obj["name"]
        label = neutral_name(prim)
        if label in prim_of and prim_of[label] != prim:
            raise ValueError(
                f"both {prim_of[label]!r} and {prim!r} are present in one "
                f"state and both map to {label!r}. Renaming would merge two "
                f"different objects into one label.")
        prim_of[label] = prim
        obj["name"] = label

    for task in out.get("tasks", []):
        if task.get("object") in prim_of.values():
            task["object"] = neutral_name(task["object"])

    return out, prim_of


def true_pose(prim):
    """The pose of a pose entry, else None. 'upright'/'lying' for the
    mustard pilot; 'small_face'/'large_face' for the block.

    Ground truth for grading. Derived from the registry entry rather than
    from anything in the state, because in a conflict cell the state is
    deliberately wrong about exactly this.
    """
    return TRUE_POSE.get(prim)


def describe(probe):
    """What this probe really contains, for the record and the grader.

    Returns the flip object's prim, its label and its true pose, plus every
    other object present. Kept separate from the rendered state so the two
    can never be confused.
    """
    prims = [o["name"] for o in probe["state"].get("objects", [])]
    flips = [p for p in prims if p in POSE_ENTRIES]
    if len(flips) != 1:
        raise ValueError(
            f"expected exactly one pose-varying object, found {flips}. An "
            f"EX2 scene is one flip object plus a fixed partner.")
    return {"flip_prim": flips[0],
            "flip_label": neutral_name(flips[0]),
            "true_pose": true_pose(flips[0]),
            "others": [p for p in prims if p not in POSE_ENTRIES]}
