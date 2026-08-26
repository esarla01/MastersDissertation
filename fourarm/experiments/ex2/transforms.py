"""EX2 step 2: the three state transforms.

One captured scene becomes three different descriptions. The picture never
changes; only what the text claims about it does.

    congruent   the text matches the picture. Both sources agree, so a
                correct answer says nothing about which was used. This is
                the sanity check, not a finding.

    conflict    the text describes the OTHER pose, completely and
                consistently. Only the picture reveals the disagreement.

    dims        pose and graspable width are withheld. The object's own
                dimensions remain, so the model must read the pose from
                the picture to know which of them the gripper meets.

WHAT THE STATE CARRIES. Every object gets the same three pose-related
fields in every condition, so the conditions differ in one thing only:

    pose      "upright" or "lying"     which way it is resting
    dims_m    height, width, depth     the object's OWN dimensions, stated
                                       as if it were upright
    grasp_m   one number               the width the gripper meets, which
                                       follows from the pose

dims_m is INTRINSIC. It describes the object, not its placement, so it is
identical in both poses and identical in every condition. That is why it
can always be shown without leaking anything.

WHY THE FALSIFICATION IS COMPLETE. In a conflict cell, pose, grasp_m,
mass_kg and delicate are all swapped together to the other registry row.
The text is then internally consistent and describes a scene that could
exist; it simply is not the scene in the picture. A half-swap would let the
model notice the contradiction without looking, and the experiment would
measure text checking rather than grounding.

WHY dims_m STAYS TRUE IN A CONFLICT CELL. Being intrinsic it is compatible
with either pose, so leaving it alone costs nothing and swapping it would
be a lie the model could catch by arithmetic.

WHY pose MUST BE ABSENT IN dims. If the text named the pose, the model
could pick the right pair of dimensions and never look at the picture,
which is the failure this condition exists to rule out.

Measured values, from run_ycb_probe:

    upright   box 0.096 x 0.058 x 0.191   grasp 0.058   all four arms
    lying     box 0.096 x 0.191 x 0.058   grasp 0.096   URs only (0.080)

Usage:
    from experiments.ex2.transforms import transform
    st, meta = transform(probe, "conflict")
"""

import copy

from core.cell import cell_config as C
from experiments.ex2.labels import neutralise, describe

CONDITIONS = ("congruent", "conflict", "dims")

# The object's own dimensions, as if upright. Identical for every pose
# because they describe the OBJECT. Taken from the probe measurements
# (mustard) or the authored cuboid dimensions (block).
DIMS_M = {
    "ycb_mustard": {"height": 0.191, "width": 0.096, "depth": 0.058},
    "ycb_block": {"height": 0.130, "width": 0.100, "depth": 0.050},
}

# The pose-dependent facts, one row per pose. A conflict swaps the WHOLE
# row, never part of it. POSE_FACTS keeps the mustard's flat two-pose form
# (upright/lying) unchanged; the block, which has three poses across two
# capability classes, lives in POSE_FACTS_BY_LABEL alongside it.
POSE_FACTS = {
    "upright": {"grasp_m": 0.058, "mass_kg": 0.603, "delicate": False},
    "lying": {"grasp_m": 0.096, "mass_kg": 0.603, "delicate": False},
}

OTHER_POSE = {"upright": "lying", "lying": "upright"}

# Per-label facts, so two objects can share a pose name yet differ. The
# block's "upright" (0.050) is not the mustard's (0.058); a flat pose->facts
# map could not hold both.
POSE_FACTS_BY_LABEL = {
    "ycb_mustard": POSE_FACTS,
    "ycb_block": {
        "upright":          {"grasp_m": 0.050, "mass_kg": 0.500,
                             "delicate": False},
        "lying_large_face": {"grasp_m": 0.100, "mass_kg": 0.500,
                             "delicate": False},
        "lying_small_face": {"grasp_m": 0.050, "mass_kg": 0.500,
                             "delicate": False},
    },
}

# The pose a conflict cell DECLARES, given the true one. The block's flip is
# a capability flip, so a conflict always crosses the 0.080 Franka aperture:
# an all-arms pose (upright or small face, 0.050) is declared as the UR-only
# large face (0.100), and the large face is declared upright. Declaring an
# upright block "small face down" would change nothing a model must ground
# (both are all-arms), so that pairing is never used.
OTHER_POSE_BY_LABEL = {
    "ycb_mustard": OTHER_POSE,
    "ycb_block": {
        "upright": "lying_large_face",
        "lying_large_face": "upright",
        "lying_small_face": "lying_large_face",
    },
}

# All-arms below the Franka aperture, UR-only above it. Used to label a
# conflict's direction from geometry rather than from a pose name, so it is
# correct for any object. The aperture itself is fixed in cell_config.
_FRANKA_APERTURE = C.ARM_TYPES["franka"]["max_grasp_m"]


def _flip_entry(state, label):
    for obj in state.get("objects", []):
        if obj["name"] == label:
            return obj
    raise ValueError(f"{label!r} is not in the state")


def transform(probe, condition):
    """Return (state, meta) for one condition.

    The probe is not modified. meta records what was done and what the
    truth is, so a row can always be traced back and the grader never has
    to re-derive ground truth from a state that may be lying.
    """
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}; expected one of "
                         f"{list(CONDITIONS)}. Conditions are never "
                         f"defaulted: a conflict trial recorded as "
                         f"congruent would be invisible in the output.")

    truth = describe(probe)
    label, true_pose = truth["flip_label"], truth["true_pose"]
    state, prim_of = neutralise(probe["state"])
    obj = _flip_entry(state, label)

    if label not in DIMS_M:
        raise ValueError(
            f"no intrinsic dimensions recorded for {label!r}. They come "
            f"from run_ycb_probe (or the authored cuboid) and must be "
            f"measured, not assumed.")
    obj["dims_m"] = dict(DIMS_M[label])

    facts = POSE_FACTS_BY_LABEL[label]

    if condition == "congruent":
        declared = true_pose
        obj["pose"] = declared
        obj.update(facts[declared])

    elif condition == "conflict":
        declared = OTHER_POSE_BY_LABEL[label][true_pose]
        obj["pose"] = declared
        # The WHOLE row, so the text is self-consistent. A partial swap
        # would leave a contradiction the model could catch without ever
        # looking at the picture.
        obj.update(facts[declared])

    else:                                   # dims
        declared = None
        obj.pop("pose", None)
        obj.pop("grasp_m", None)

    # Direction from geometry, not from a pose name: permissive when the
    # true pose is all-arms (the text under-states the arms) and restrictive
    # when it is UR-only (the text over-states them). For the mustard this
    # is exactly the old upright/lying split.
    permissive = facts[true_pose]["grasp_m"] <= _FRANKA_APERTURE

    meta = {
        "condition": condition,
        "flip_label": label,
        "flip_prim": truth["flip_prim"],
        "true_pose": true_pose,
        "declared_pose": declared,
        # Which way a conflict points, since the two directions answer
        # different questions and only one of them separates grounding
        # from blanket caution.
        "direction": (None if condition != "conflict"
                      else ("permissive" if permissive else "restrictive")),
        "true_grasp_m": facts[true_pose]["grasp_m"],
        "declared_grasp_m": (None if declared is None
                             else facts[declared]["grasp_m"]),
        "prim_of": prim_of,
    }
    return state, meta


def sanity(probe):
    """Every condition for one probe, for eyeballing before any spend."""
    return {c: transform(probe, c) for c in CONDITIONS}
