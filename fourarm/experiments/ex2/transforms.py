"""EX2 step 2: the three state transforms.

One captured scene becomes three different descriptions. The picture never
changes; only what the text claims about it does.

    congruent   the text matches the picture. Both sources agree, so a
                correct answer says nothing about which was used. This is
                the sanity check, not a finding.

    conflict    the text describes the OTHER pose, completely and
                consistently. Only the picture reveals the disagreement.

    dims        resting face and opening are withheld. The object's own
                dimensions remain, so the model must read the face from
                the picture to know which of them the gripper meets.

WHAT THE STATE CARRIES. The conditions differ in one thing only, so the
three pose-related fields are what a condition adds or withholds:

    pose      the RESTING FACE         "small_face" or "large_face"
                                       for the block; the mustard pilot
                                       keeps "upright" and "lying"
    dims_m    height, width, depth     the object's OWN dimensions, stated
                                       as if it were standing on its
                                       smallest face
    grasp_m   one number               the opening the gripper meets, which
                                       follows from the resting face

dims_m is INTRINSIC. It describes the object, not its placement, so it is
identical in both poses and identical in every condition. That is why it
can always be shown without leaking anything.

AND IT IS SHOWN FOR EVERY OBJECT (2026-08-27), not only the flip object.
Withholding is done per FIELD, across the whole state, so in the dims
condition no object states an opening. An object left without dimensions
therefore had no opening and no way to reach one, which made R3
unanswerable for its task and left the flip object as the only one in the
scene carrying a number the rule could act on. That is a pointer to the
answer, and it does not become less of one for arriving through the field
list rather than through the words. See DIMS_M, which now needs a row per
object and raises without one.

What is NOT symmetric, and is disclosed rather than patched: only the flip
object states a "pose". The partner is a clamp, and the two-word
small_face / large_face vocabulary the answer schema enumerates has no
truthful value for it. Inventing one would be a lie the grader would have
to special-case.

WHY THE FALSIFICATION IS COMPLETE. In a conflict cell, pose, grasp_m,
mass_kg and delicate are all swapped together to the other registry row.
The text is then internally consistent and describes a scene that could
exist; it simply is not the scene in the picture. A half-swap would let the
model notice the contradiction without looking, and the experiment would
measure text checking rather than grounding.

WHY dims_m STAYS TRUE IN A CONFLICT CELL. Being intrinsic it is compatible
with either pose, so leaving it alone costs nothing and swapping it would
be a lie the model could catch by arithmetic.

WHY THE RESTING FACE MUST BE ABSENT IN dims. If the text named the face,
the model could pick the right pair of dimensions and never look at the
picture, which is the failure this condition exists to rule out.

The BLOCK, 0.130 x 0.100 x 0.050, authored (see ycb_objects.py):

    small_face   face down 0.100 x 0.050   grasp 0.050   all four arms
    large_face   face down 0.130 x 0.100   grasp 0.100   URs only (0.080)

The block can also rest on 0.130 x 0.050, which the design called "edge"
until 2026-08-27. It is no longer captured and no longer a value here; the
capture script fails a scene that settles on it. labels.py records why.

The MUSTARD pilot, measured by run_ycb_probe, kept for provenance:

    upright   box 0.096 x 0.058 x 0.191   grasp 0.058   all four arms
    lying     box 0.096 x 0.191 x 0.058   grasp 0.096   URs only (0.080)

Usage:
    from experiments.ex2.transforms import transform
    st, meta = transform(probe, "conflict")
"""

import copy

from core.cell import cell_config as C
from experiments.ex2.labels import neutralise, describe

CONDITIONS = ("congruent", "congruent_face", "conflict",
              "conflict_face", "dims")

# The three run.py swept before conflict_face existed. Its default is pinned
# to these so that adding a condition does not silently widen an existing
# driver's sweep by a third; conflict_face is opt-in, via --condition.
CORE_CONDITIONS = ("congruent", "conflict", "dims")

# The object's own dimensions, as if upright. Identical for every pose
# because they describe the OBJECT. Taken from the probe measurements
# (mustard) or the authored cuboid dimensions (block).
#
# EVERY OBJECT IN THE SCENE NEEDS A ROW HERE, not just the flip object.
# Until 2026-08-27 only the flip object carried dims_m, which made it the
# only object in the state with dimensions. In the dims condition, where
# the opening is withheld from every object, that left the partner with no
# opening AND nothing to derive one from: R3 was unanswerable for its task,
# and the one object carrying numbers was the one the model had to reason
# about. A pointer to the answer, arriving through the field list rather
# than through the words.
DIMS_M = {
    "ycb_mustard": {"height": 0.191, "width": 0.096, "depth": 0.058},
    "ycb_block": {"height": 0.130, "width": 0.100, "depth": 0.050},
    # The partner. Not a cuboid, so these are the enclosing box, which is
    # the convention the prompt already states ("the cell judges an object
    # by the box that encloses it"). From ycb_objects.py: footprint_m 0.165
    # is the larger horizontal extent, grasp_m 0.122 the smaller, height
    # 0.036 the vertical. rest_z 0.018 is the CENTRE height, half of
    # height, and is not a third extent.
    #
    # A free internal check: the clamp lies on its 0.165 x 0.122 face, so
    # the same derivation the block requires gives min(0.165, 0.122) =
    # 0.122, which is exactly the grasp_m the registry declares for it.
    "ycb_large_clamp": {"height": 0.165, "width": 0.122, "depth": 0.036},
}

# The pose-dependent facts, one row per pose. A conflict swaps the WHOLE
# row, never part of it. POSE_FACTS keeps the mustard pilot's flat two-pose
# form (upright/lying) unchanged; the block, which has three resting faces
# across two capability classes, lives in POSE_FACTS_BY_LABEL alongside it.
POSE_FACTS = {
    "upright": {"grasp_m": 0.058, "mass_kg": 0.603, "delicate": False},
    "lying": {"grasp_m": 0.096, "mass_kg": 0.603, "delicate": False},
}

OTHER_POSE = {"upright": "lying", "lying": "upright"}

# Per-label facts, so two objects can never collide on a pose name. The
# block names resting faces and the mustard names postures, and a flat
# pose->facts map could not hold both vocabularies.
# The block is keyed by RESTING FACE, which is what determines the opening.
# Read labels.TRUE_POSE for why "small_face" is the block standing tall and
# The retired third face, "edge", is documented there too.
POSE_FACTS_BY_LABEL = {
    "ycb_mustard": POSE_FACTS,
    "ycb_block": {
        # resting on 0.100 x 0.050, the smallest face; vertical 0.130
        "small_face": {"grasp_m": 0.050, "mass_kg": 0.500,
                       "delicate": False},
        # resting on 0.130 x 0.100, the largest face; vertical 0.050
        "large_face": {"grasp_m": 0.100, "mass_kg": 0.500,
                       "delicate": False},
    },
}

# The resting face a conflict cell DECLARES, given the true one. The block's
# flip is a capability flip, so a conflict always crosses the 0.080 Franka
# aperture: the all-arms small_face (0.050) is declared as the UR-only
# large_face (0.100), and large_face is declared small_face.
#
# With two faces this is a strict involution, which the three-face version
# was not: the retired "edge" declared large_face, but large_face never
# declared edge, because edge and small_face are both all-arms and swapping
# one for the other would change nothing a model must ground.
OTHER_POSE_BY_LABEL = {
    "ycb_mustard": OTHER_POSE,
    "ycb_block": {
        "small_face": "large_face",
        "large_face": "small_face",
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

    # EVERY object, not only the flip object. An object left without
    # dimensions is an object the dims condition cannot ask about, and with
    # the opening withheld from all of them it is also the one object the
    # model can safely ignore. That singles out the flip object without a
    # word of the prompt saying so. Raising rather than skipping, because a
    # new object added to the scene must not reintroduce the asymmetry
    # silently.
    for entry in state.get("objects", []):
        if entry["name"] not in DIMS_M:
            raise ValueError(
                f"no intrinsic dimensions recorded for {entry['name']!r}. "
                f"Every object in the scene needs a DIMS_M row, not just "
                f"the flip object: in the dims condition the opening is "
                f"withheld from all of them, so an object with no "
                f"dimensions has nothing to derive an opening from and "
                f"points at the object that has.")
        entry["dims_m"] = dict(DIMS_M[entry["name"]])

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

    elif condition == "congruent_face":
        # THE TRUE FACE, WITH THE NUMBER WITHHELD. The matched ceiling for
        # conflict_face, and the reason that condition can be read at all.
        #
        # conflict_face differs from congruent in TWO ways at once: the face
        # is false AND the number is gone. Compared against congruent, its
        # contrast would confound "the text lied" with "the model had to
        # derive". congruent_face removes the second: it renders a
        # byte-identical prompt to conflict_face and differs only in whether
        # the stated face is true. The pair isolates precedence exactly.
        #
        # It is also a question in its own right, and Q1's: told the face
        # but not the opening, can the model get from one to the other? That
        # sits between congruent, where the number is handed over, and dims,
        # where neither is.
        declared = true_pose
        obj["pose"] = declared
        obj.update(facts[declared])
        obj.pop("grasp_m", None)

    elif condition == "conflict_face":
        # THE FACE LIES AND THE NUMBER IS WITHHELD.
        #
        # Why this exists, when "conflict" already lies. In conflict the
        # state supplies opening_needed_m, and R3 names that field: "the
        # arm is capable only when its opening_max_m is at least the
        # object's opening_needed_m". So a model that reads the stated
        # number and applies R3 has broken no rule -- it is COMPLYING --
        # and a text-following result there cannot be told apart from
        # rule-following. Worse, no rule mentions resting_face at all, so
        # the false face in conflict is inert: nothing asks the model to
        # consult it, so nothing has to be overcome.
        #
        # Withholding the number puts R3 into its _R3_DIMS form, which
        # names no field and says the opening is not stated. The model
        # then has to derive an opening from a face, and the false face in
        # the text competes with the true face in the image on the one
        # quantity that decides the arm. Neither source is privileged by a
        # rule, so the SIGN of the contrast means what conflict's sign was
        # taken to mean and could not support.
        #
        # declared_grasp_m below is still the declared face's opening, so
        # legal_declared, width_belief and every outcome label are computed
        # exactly as they are in conflict. Nothing downstream changes.
        declared = OTHER_POSE_BY_LABEL[label][true_pose]
        obj["pose"] = declared
        obj.update(facts[declared])
        obj.pop("grasp_m", None)        # dropped here AND withheld at render

    else:                                   # dims
        declared = None
        obj.pop("pose", None)
        obj.pop("grasp_m", None)

    # Direction from geometry, not from a pose name: permissive when the
    # true resting face is all-arms (the text under-states the arms) and
    # restrictive when it is UR-only (the text over-states them). For the
    # mustard pilot this is exactly the old upright/lying split.
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
        # Both conflict conditions, not just the one. conflict_face lies
        # about the same face in the same two directions; only the number
        # is withheld, and the direction is a property of the TRUE opening,
        # which is unaffected by withholding anything.
        "direction": (None if condition not in ("conflict", "conflict_face")
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
