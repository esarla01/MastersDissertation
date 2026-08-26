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
  - In the DIMS condition, where pose is deliberately withheld, the name
    would hand it straight back.

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
    # ONE object, THREE poses, so three rows collapse to one neutral label.
    "ycb_block_upright": "ycb_block",
    "ycb_block_large": "ycb_block",
    "ycb_block_small": "ycb_block",
}

# Which pose each entry actually is. The grader needs this; the prompt must
# never see it. The block is three-valued because its two lying faces are
# NOT interchangeable: the large face presents 0.100 m (URs only) and the
# small face 0.050 m (all arms), so "lying" alone would lose the capability.
TRUE_POSE = {
    "ycb_mustard_lying": "lying",
    "ycb_mustard_upright": "upright",
    "ycb_block_upright": "upright",
    "ycb_block_large": "lying_large_face",
    "ycb_block_small": "lying_small_face",
}


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
    mustard; 'upright'/'lying_large_face'/'lying_small_face' for the block.

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
