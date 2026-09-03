"""EX2 prompts: the base prompt, the three factors, the six rungs, and
the off-ladder precedence directives.

THE OBJECT. A plain block, 0.130 x 0.100 x 0.050 m, with no recognisable
identity. It rests on one of two faces, and the opening a gripper needs
is the smaller of the two horizontal extents in that orientation:

    resting face   vertical   horizontal pair   opening   Franka (0.080)
    small_face     0.130      0.100, 0.050      0.050     feasible
    large_face     0.050      0.130, 0.100      0.100     infeasible

One of the two is feasible, so the contrast is the whole design: the
opening, and with it the arm, follows from which face is down. Face names
are GEOMETRIC and never describe the outcome. A name such as "upright" for
a feasible orientation would let the model succeed by matching the label.

TWO FACES, NOT THREE (2026-08-27). The block also rests on 0.130 x 0.050,
which the design called "edge" and used as its sharp contrast against
large_face: both flat, differing only in geometry. That contrast is gone
because no model read it. Over 81 answered trials GPT scored 58 percent on
the edge-against-large_face pair, Fisher p = 0.76, while scoring 18 of 18
on a plain-words standing-or-flat question over the same images. The
perception was intact; the three-way face discrimination was not. The
evidence is runs/ex2_q1_cue_*.jsonl, kept on disk.

What that costs is stated where the results are read: a model that
separates standing from flat but not the two flat faces can no longer be
distinguished from one that derives the opening from geometry. The
capture-side settle assertion is what keeps the withdrawn orientation out
of the pictures, so the prompt never has to mention it.

THE SAME COLLAPSE ARRIVES BY A SECOND ROUTE, and it is worth naming
separately because patching the first would not close it. "size_upright_m"
states the frame its three numbers were taken in: measured standing on the
smallest face. With two captured faces the object is either in that frame
or flat, so the field name plus a two-way standing-or-flat judgement fixes
the opening. The model never has to work out which two extents are
horizontal.

This is NOT patched, and the reasoning is on the record so the decision
reads as one. The extents reach the model as an unordered set whatever the
field is called, and with two faces the answer is fixed by a binary posture
read either way, so dropping the frame from the gloss would not restore a
step. It would ADD an ambiguity: a model could read height, width and depth
as the extents AS CURRENTLY PLACED and on large_face derive
min(0.100, 0.050) = 0.050, which is the wrong opening on the correct
condition. That is measurement error, not a harder task.

So the honest statement is that Q1 measures posture-plus-lookup and cannot
separate it from geometric derivation. That belongs in Limitations, and
cells 10 and 14 of the Q1 notebook print it beside every verdict.

Every trial queues one task and offers one idle UR arm and one idle Franka
arm. An arm preference in the guidance block is what makes the arm choice
informative: a UR is legal in every orientation, so without a preference
the arm named carries no information. With a Franka preferred, the correct
arm differs by resting face.

FIELD NAMES. The state is rendered through ALIASES, so the model sees names
that say what each field is and which way each comparison runs. Nothing
underneath changes. EX2 therefore prints different field names from EX1,
and the chapter must say so.

THE CONDITIONS.

    congruent   resting face and opening both stated, both true
    dims        BOTH withheld. The model must read the face from the image
                and derive the opening from size_upright_m
    conflict    a false resting face stated, with the opening that follows
                from it. Each face declares the other, and the pair
                straddles the 0.080 Franka aperture, so every conflict is a
                capability flip

Dims withholds the resting face as well as the opening. Stating the face
would let the opening be derived from text alone and the image would no
longer be needed.

THE FACTORS. Each names a different hypothesis about why a model follows a
supplied opening instead of the scene.

    A  ATTENTION    the model did not consult the image
    C  DERIVATION   the model lacked the relation between resting face and
                    the opening an object needs
    D  ELICITATION  the model held the relation but did not apply it
                    before committing to an arm

THE BOUNDARY RULE, checked mechanically by assert_rungs_isolated:

    A may name the image and the target object. It may NOT name a resting
      face, an orientation or the opening.
    C may name the relation between resting face and opening. It may NOT
      say where to look, and may NOT require anything to be reported.
    D may require a report and fix its position in the answer. It may NOT
      state the relation.
    X may name the image, the stated resting face, and the fact that the
      two can disagree. It may NOT name a face VALUE, an orientation,
      either measured opening, an arm, the face-to-opening relation, or
      require a report.

No LADDER rung names an arm's opening, either measured value, or which
face the object is on. X is the exception and has to be, which is why it
is off the ladder and carries its own rule rather than an exemption.

THE RUNGS.

    N0        base prompt
    N-A       base + A
    N-C       base + C
    N-D       base + D                 (face reported, both before arm)
    N-order   base, no added wording   (opening moved before arm)
    N-CD      base + C + D

N-order is the control for D. D moves the report ahead of the arm choice
AND requires the resting face, and a model generates left to right, so
without N-order an effect of D cannot be attributed to either. N-CD is a
sufficiency cell against N0, never a test of whether C and D interact.

THE DIRECTIVES, off the ladder (2026-08-31).

    X-image   base + A + "where they disagree, go by the image"
    X-state   base + A + "where they disagree, go by the state"

These are NOT a seventh and eighth rung. Every ladder rung scaffolds the
derivation while staying silent about provenance; a directive names the
stated resting face AND announces that the image can contradict it, both
of which the boundary rule forbids A, C and D. So it measures a different
thing: not which source the model privileges when nothing tells it, which
is Q2, but whether it has an arbitration step at all that an instruction
can reach. It is the ceiling on instructed arbitration, and it stands to
Q2 as congruent_face stands to conflict_face.

They live in RUNGS so one code path renders, validates, ids and runs every
variant, and outside LADDER_RUNGS so no default sweep and no table whose
column says "factor" absorbs them. That is the shape CORE_CONDITIONS
already has in transforms.py.

Usage:
    messages = build_ex2_prompt(state, rung="N-C", condition="dims",
                                image_b64=frame, preference="franka")
"""

import json

from core.cell import cell_config as C

EX2_PROMPT_VERSION = "2026-08-27b"

RESTING_FACES = ("small_face", "large_face")


# ---------------------------------------------------------------------------
# 1. Field aliases
# ---------------------------------------------------------------------------
# Each constraint becomes a visibly matched pair, so the direction of the
# comparison is readable from the names alone:
#
#     object                  arm
#     opening_needed_m        opening_max_m
#     mass_kg                 max_load_kg
#     delicate                handles_delicate
#     position                arms_that_can_reach
#
# size_upright_m carries its frame in its name. resting_face replaces a
# posture label, because posture is not what the opening follows from: the
# name has to be geometric so it cannot be read off as an outcome.

FIELD_ALIASES = {
    "grasp_m": "opening_needed_m",
    "max_grasp_m": "opening_max_m",
    "payload_kg": "max_load_kg",
    "delicate_ok": "handles_delicate",
    "dims_m": "size_upright_m",
    "reach_ok_arms": "arms_that_can_reach",
    "pose": "resting_face",
}

# Dead in every EX2 scene.
DROP_FIELDS = ("at_pad",)

# Withheld in the dims condition. The opening alone is not enough: with the
# face stated, the opening follows from size_upright_m by text alone.
DIMS_WITHHELD = ("opening_needed_m", "resting_face")


# ---------------------------------------------------------------------------
# 2. The base prompt
# ---------------------------------------------------------------------------

SCENE_WITH_IMAGE = """The image shows the four arms at their rest positions, the coloured
boxes, and five white crosses which mark the exchange points and are
not objects to be sorted. Objects to be sorted lie loose on the table.
The image is a side view of this cell, taken now, and a written
description of the same scene follows below. Both describe the cell
you are allocating in.
"""

SCENE_NO_IMAGE = """A written description of the cell state follows below.
"""

VIEW_TEXT = """The image is taken from the south of the table, above it and
looking back at the centre, so north (+y) is away from the camera
and east (+x) is to the right.
"""


def _scene_block(condition, has_image, dims_frame="named"):
    """The object field list, the viewpoint and the scene, blank-line separated.

    Joined here rather than in BASE_PROMPT. Until 2026-08-27 the template
    read "{object_fields}\\n{view}{scene}", and since the field lists carry
    no trailing newline and VIEW_TEXT carries exactly one, two blocks ran
    straight into the next: the field list into the viewpoint sentence, and
    the viewpoint into the scene. Every other block in the prompt is
    separated by a blank line.

    Joining in code also keeps the no-image path right. Writing
    "{view}\\n{scene}" in the template would fix the seam and leave a stray
    blank line wherever `view` is empty.
    """
    blocks = [_object_fields(condition, dims_frame),
              VIEW_TEXT if has_image else "",
              SCENE_WITH_IMAGE if has_image else SCENE_NO_IMAGE]
    return "\n\n".join(b.rstrip("\n") for b in blocks if b.strip()) + "\n"

# The top-down approach and the bounding-box convention are facts about the
# apparatus, so they sit in THE CELL and are present at every rung. Neither
# says which dimension matters or that it changes with the resting face.
# That is factor C.
BASE_PROMPT = """You are the task allocator for a four-arm robotic cell. Each time you are
asked, choose ONE queued task and ONE idle arm, or choose to wait.

THE CELL
A {tx} x {ty} m table, origin at its centre, x east, y north. Two UR10 arms sit
mid-table on the west and east edges, two Franka arms on the south and north
edges, all facing inward. Zones are a centre disc of radius {cr} m plus the
quadrants nw, ne, sw, se. Three coloured boxes stand on the table for
sorting, and five exchange points are marked on it.

Every object is picked from directly above. The gripper turns to whichever
horizontal direction suits before it closes. The cell judges an object by the
box that encloses it, so a shape that tapers or curves counts as its full
extent.

WHAT THE STATE TELLS YOU
Each arm states the widest its gripper opens, "opening_max_m", the heaviest
object it can carry, "max_load_kg", and whether it is cleared for delicate
handling, "handles_delicate".

{scene_block}
HARD RULES. A proposal that breaks any of these is rejected.

R1  Task availability
    Assign only a task whose status is "queued". A task marked
    "in_progress" or "waiting_on_..." is already being handled.

R2  Arm availability
    Assign only an arm from the idle list. A disabled arm is never
    available.

{r3}
R4  Load
    The arm is capable only when its "max_load_kg" is at least the
    object's "mass_kg".

R5  Delicate handling
    An object marked "delicate" may go only to an arm whose
    "handles_delicate" is true.

R6  Reach
    The arm must appear in the object's "arms_that_can_reach" list. That
    list is authoritative, so use it rather than working reach out from
    coordinates. Reaching is not the same as handling: an arm can often
    reach an object it cannot pick up.

R7  Destination
    The task carries no destination, so name a box in "basket". Any box
    the arm you named can reach will do.

GUIDANCE. Not enforced, but this is what a good allocation does.

{preference}
G2  Waiting can be a choice, not only a last resort. If no idle arm is a
    good fit and a better-suited one will free up soon, wait.
{rung}
YOUR ANSWER
{schema}
"""


# ---------------------------------------------------------------------------
# 3. Conditions
# ---------------------------------------------------------------------------
# Congruent and conflict manipulate the STATE. Dims withholds two fields, and
# two parts of the prompt have to follow, because a prompt that promises a
# field and then retracts it, or a rule that points at a field which is not
# there, makes the model solve a comprehension puzzle rather than the
# derivation under test.
#
#   the glossary   lists only the fields actually present
#   R3             keeps the check and drops the pointer to a supplied number
#
# R3 is substituted rather than deleted, following the discipline Experiment 1
# set with No Rules: the condition must test the value of the SUPPLIED NUMBER,
# not the value of knowing the constraint exists. A model reading a rule that
# names a missing field could reasonably conclude the rule is inapplicable,
# and that would look like a derivation failure while being a rule-reading
# failure.
#
# What neither version says is where the opening comes from, or that its
# absence is an error. Framing the absence as a mistake would steer the model
# toward flagging a fault or abstaining, and abstention is one of the measures
# rather than a behaviour to induce.
#
# THE WITHHOLDING SENTENCE NAMES NO OBJECT. It read "no resting face are given
# for this object" until 2026-08-27, which was wrong twice over: withhold()
# strips per FIELD across the whole state, so it is true of every object, and
# a sentence that says "this object" in a glossary opening "Each object
# states" points at one of them. The same date gave the partner its own
# dimensions in transforms.DIMS_M for the same reason. R3 keeps "this object"
# and is correct to: R3 is a per-object rule, so there the phrase means
# whichever object is being checked.

_OBJECT_FIELDS_FULL = """Each object states the opening it needs from a gripper, "opening_needed_m",
which face it is resting on, "resting_face", its mass, "mass_kg", whether it
is "delicate", its height, width and depth measured standing on its smallest
face, "size_upright_m", and the arms that can reach it,
"arms_that_can_reach"."""

_OBJECT_FIELDS_FACE = """Each object states which face it is resting on,
"resting_face", its mass, "mass_kg", whether it is "delicate", its height,
width and depth measured standing on its smallest face, "size_upright_m", and
the arms that can reach it, "arms_that_can_reach". No opening is given."""

_OBJECT_FIELDS_DIMS = """Each object states its mass, "mass_kg", whether it is "delicate", its height,
width and depth measured standing on its smallest face, "size_upright_m", and
the arms that can reach it, "arms_that_can_reach". No opening and no resting
face are given."""

# ---------------------------------------------------------------------------
# DIMS FRAME. The gloss above names the three extents -- height, width, depth
# -- and the state renders them under those keys. That assigns the axes: a
# model reads height as the vertical one and takes the horizontal pair to be
# width and depth, so on a block lying on its large face it derives
# min(0.100, 0.050) = 0.050 without ever consulting the picture.
#
# The docstring at the top of this module ALREADY argues that keeping the
# frame in the field name is what stops "as currently placed" being read off
# the numbers, and that argument stands. But it rests on the extents
# "reaching the model as an unordered set", and as rendered they do not: they
# arrive as a named dict, which is precisely the axis assignment the argument
# assumes is absent. The frame in the NAME is the mitigation; the names on
# the KEYS are the leak. This variant closes the second without touching the
# first.
#
# Two changes, one decision, so they are one factor:
#   - the extents render as a bare descending list, no axis names
#   - the gloss defines the frame geometrically rather than by naming a
#     face, so the words "smallest face" leave the prompt entirely
#
# That second half also closes the vocabulary collision. "small_face" is an
# answer option, and until now it was also a phrase sitting in the state.
# Defining the frame as "longest extent vertical" says the same thing about
# the measurement and shares no words with the answer schema, so the answer
# vocabulary can stay geometric -- which the FIELD NAMES note above requires,
# because a posture label could be read off as an outcome.
#
# Sorting descending leaks nothing: the three numbers are intrinsic, so the
# order is the same in both poses and carries no information about either.
_OBJECT_FIELDS_DIMS_EXTENTS = """Each object states its mass, "mass_kg", whether it is "delicate", its three
extents largest first, "extents_m", and the arms that can reach it,
"arms_that_can_reach". No opening and no resting face are given."""

_OBJECT_FIELDS_FULL_EXTENTS = """Each object states the opening it needs from a gripper, "opening_needed_m",
which face it is resting on, "resting_face", its mass, "mass_kg", whether it
is "delicate", its three extents largest first, "extents_m", and the arms
that can reach it, "arms_that_can_reach"."""

_OBJECT_FIELDS_FACE_EXTENTS = """Each object states which face it is resting on,
"resting_face", its mass, "mass_kg", whether it is "delicate", its three
extents largest first, "extents_m", and the arms that can reach it,
"arms_that_can_reach". No opening is given."""

DIMS_FRAMES = ("named", "extents")

# KEYED ON THE NAMED GLOSS, not on the condition name. The dispatch here was
# `_OBJECT_FIELDS_DIMS_EXTENTS if condition == "dims" else FULL_EXTENTS`,
# which is right for the two conditions that had ever been rendered under
# extents and wrong for the other three: congruent_face and conflict_face
# withhold the opening and say so ("No opening is given"), and the else
# branch handed them the FULL gloss, which announces an "opening_needed_m"
# the state does not carry. Nothing on disk was rendered that way -- only
# dims and congruent have ever been run under extents -- so no result is
# affected and EX2_PROMPT_VERSION does not move.
#
# Keying on the gloss the condition already uses means a new condition
# reusing an existing gloss is covered without an edit here, and a new gloss
# with no extents twin raises instead of silently receiving the wrong one.
_EXTENTS_BY_NAMED = {
    _OBJECT_FIELDS_FULL: _OBJECT_FIELDS_FULL_EXTENTS,
    _OBJECT_FIELDS_FACE: _OBJECT_FIELDS_FACE_EXTENTS,
    _OBJECT_FIELDS_DIMS: _OBJECT_FIELDS_DIMS_EXTENTS,
}


def _object_fields(condition, dims_frame="named"):
    """The object field gloss for one condition, in the named dims frame."""
    if dims_frame not in DIMS_FRAMES:
        raise ValueError(
            f"unknown dims_frame {dims_frame!r}; expected one of "
            f"{list(DIMS_FRAMES)}. Never defaulted at the call site: an "
            f"extents result recorded as named would be invisible.")
    named = CONDITIONS[condition]["object_fields"]
    if dims_frame == "named":
        return named
    try:
        return _EXTENTS_BY_NAMED[named]
    except KeyError:
        raise ValueError(
            f"condition {condition!r} has an object-field gloss with no "
            f"extents twin. Add one to _EXTENTS_BY_NAMED rather than "
            f"falling back: a gloss that names fields the state withholds "
            f"is a prompt that contradicts itself.") from None


EXTENTS_FIELD = "extents_m"


def as_extents(value):
    """Render every size_upright_m as a descending list under a frame-free
    name. Applied AFTER aliasing, so the field is already renamed once.

    THE NAME GOES WITH THE KEYS. "size_upright_m" states the frame its three
    numbers were taken in, and that frame is what stops the named axes being
    read as the extents AS CURRENTLY PLACED. With the axis names gone there
    is nothing left for it to anchor: the three extents of a rigid box are
    the same multiset in every orientation, so a frame adds no information
    to a sorted list. All "upright" would still do is put a pose word in
    front of the model for no return, which is the leak this variant exists
    to close.

    What is NOT added is a sentence saying the extents do not indicate the
    resting pose. Removing a false claim is not scaffolding; adding a denial
    would be, and it is A_ATTEND's job at the N-A rung. Silence about pose
    is the correct neutral state at N0.
    """
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == "size_upright_m" and isinstance(v, dict):
                out[EXTENTS_FIELD] = sorted(v.values(), reverse=True)
            else:
                out[k] = as_extents(v)
        return out
    if isinstance(value, (list, tuple)):
        return [as_extents(v) for v in value]
    return value

_R3_FULL = """R3  Gripper opening
    The gripper must open wide enough for the object. The arm is capable
    only when its "opening_max_m" is at least the object's
    "opening_needed_m".
"""

_R3_DIMS = """R3  Gripper opening
    The gripper must open wide enough for the object. The arm is capable
    only when its "opening_max_m" is at least the opening the object needs.
    That opening is not stated for this object.
"""

# "withheld" is per condition rather than a single DIMS_WITHHELD constant,
# because there are now three withholding patterns, not two: nothing,
# the opening alone, and both fields. render_state, the glossary assertion
# and the R3 assertion all read it from here, so a new condition cannot be
# added that renders a field the prompt does not gloss.
CONDITIONS = {
    "congruent":     {"object_fields": _OBJECT_FIELDS_FULL, "r3": _R3_FULL,
                      "withheld": ()},
    "conflict":      {"object_fields": _OBJECT_FIELDS_FULL, "r3": _R3_FULL,
                      "withheld": ()},
    "congruent_face": {"object_fields": _OBJECT_FIELDS_FACE, "r3": _R3_DIMS,
                       "withheld": ("opening_needed_m",)},
    "conflict_face": {"object_fields": _OBJECT_FIELDS_FACE, "r3": _R3_DIMS,
                      "withheld": ("opening_needed_m",)},
    "dims":          {"object_fields": _OBJECT_FIELDS_DIMS, "r3": _R3_DIMS,
                      "withheld": DIMS_WITHHELD},
}

# The wording stays flat. "Prefer a Franka unless it cannot handle the
# object" would state the capability check being measured.
#
# The UR setting is the counterbalance, run at N0 only. Under it a UR is
# legal in every orientation, so every model should land near zero on the
# paired difference. A model that does not is not choosing on capability.
PREFERENCE_TEXT = {
    "franka": "G1  Prefer a Franka arm for sorting tasks.\n",
    "ur": "G1  Prefer a UR arm for sorting tasks.\n",
}


# ---------------------------------------------------------------------------
# 4. Factors and rungs
# ---------------------------------------------------------------------------

A_ATTEND = """
The image shows the table as it is now. Look at the object in the image
before you choose.
"""

# Names the relation and nothing else. It does not say which faces exist,
# which one the object is on, or where to look.
C_DERIVE = """
The opening an object needs is the smaller of its two horizontal extents,
so it depends on which face the object is resting on.
"""

# Requires the report and fixes its position. It does not give the relation,
# so a model without C must supply the relation itself.
D_ELICIT = """
Give "resting_face" and "opening_needed_m" BEFORE naming an arm, and choose
the arm to fit the opening you gave.
"""

# THE PRECEDENCE DIRECTIVE. Off the ladder, and it has to be, because it
# breaks the boundary rule on purpose: it names the stated resting face AND
# it says the image can contradict it. A, C and D are forbidden both.
#
# THE WORDING IS CONDITIONAL, "where they disagree", never assertive. "The
# image disagrees with the text" would be a FALSE sentence in
# congruent_face, and congruent_face is the control that makes the cell
# readable: the same prompt, the same sentence, an antecedent that is never
# satisfied. An assertive form could only run in conflict_face, and there
# would then be no way to tell obedience from the extra sentence simply
# making the model look harder.
#
# IT NAMES NO OPENING. Saying which source to believe about the resting FACE
# is precedence. Saying which to believe about the opening would hand over
# the measured quantity.
X_PREFER_IMAGE = """
Where the image and the stated resting face disagree, go by the image.
"""

# The symmetry control, and the reason X-image's number means anything. The
# two sentences differ in ONE word, and BOTH name the image. So if X-image
# moves the model toward the picture and X-state does too, the model is
# responding to image-talk rather than to which source was named, and
# neither number is about precedence.
X_PREFER_STATE = """
Where the image and the stated resting face disagree, go by the state.
"""

RUNGS = {
    "N0":      {"text": "", "schema": "base", "factors": ()},
    "N-A":     {"text": A_ATTEND, "schema": "base",
                "factors": ("attention",)},
    "N-C":     {"text": C_DERIVE, "schema": "base",
                "factors": ("derivation",)},
    "N-order": {"text": "", "schema": "report_first",
                "factors": ("order",)},
    "N-D":     {"text": D_ELICIT, "schema": "face_first",
                "factors": ("elicitation", "order")},
    "N-CD":    {"text": C_DERIVE + D_ELICIT, "schema": "face_first",
                "factors": ("derivation", "elicitation", "order")},

    # THE CEILING CELL, and NOT part of the pre-registration. Added
    # 2026-09-01, after the ladder had been run, because the ladder tests
    # each factor alone and one pair and never the complete procedure.
    # Without it a model that stops short at N-CD cannot be told apart from
    # one that was never asked for every step: "cannot derive" and "was not
    # instructed to derive" predict the same number. It is the analogue of
    # EX1's givenset, which bounds obedience above that experiment's spine.
    #
    # A_ATTEND is used UNCHANGED. A stronger sentence naming the resting
    # face as visible would be a new factor with no single-factor cell of
    # its own, and it would cross into telling the model where the answer
    # is, which is the directives' job and not the ladder's.
    "N-ACD":   {"text": A_ATTEND + C_DERIVE + D_ELICIT,
                "schema": "face_first",
                "factors": ("attention", "derivation", "elicitation",
                            "order")},

    # OFF THE LADDER. See LADDER_RUNGS below and the module docstring.
    #
    # The text is A_ATTEND plus one sentence, exactly as N-CD is C plus D.
    # That is what makes the reading cheap: N-A is already on disk in
    # conflict_face at three repeats, so X-image minus N-A is the precedence
    # sentence and nothing else, bought for nothing.
    #
    # The schema stays "base". A directive that also reordered the answer
    # would confound precedence with the report order, which is exactly what
    # N-order exists to separate, and "base" is what N-A uses, so the
    # headline comparison is like for like.
    "X-image": {"text": A_ATTEND + X_PREFER_IMAGE, "schema": "base",
                "factors": ("attention", "precedence_image")},
    "X-state": {"text": A_ATTEND + X_PREFER_STATE, "schema": "base",
                "factors": ("attention", "precedence_state")},
}

# THE LADDER, pinned. RUNGS holds every variant that exists; this holds the
# six the pre-registered ladder IS, and it is what every default sweep and
# every table with a "factor" column reads. Pinned for the reason
# CORE_CONDITIONS is pinned in transforms.py: adding a variant must not
# silently widen an existing driver's cost, and a directive must never
# appear in a table that presents it as one of the four factors.
# N-ACD is LAST and is marked here rather than in a comment elsewhere: the
# first six are the pre-registered ladder, and N-ACD was added on
# 2026-09-01 after they had been run. Any table that presents the ladder as
# a pre-registered design must say so, and PRE_REGISTERED_LADDER below is
# what such a table reads.
PRE_REGISTERED_LADDER = ("N0", "N-A", "N-C", "N-order", "N-D", "N-CD")
LADDER_RUNGS = PRE_REGISTERED_LADDER + ("N-ACD",)

# Derived, never typed twice.
DIRECTIVE_RUNGS = tuple(r for r in RUNGS if r not in LADDER_RUNGS)

# WHERE A DIRECTIVE IS VACUOUS. dims pops resting_face from the state and
# the glossary says "No opening and no resting face are given", so a
# sentence about "the stated resting face" would name a field the prompt
# has just withdrawn. That is the comprehension puzzle _R3_DIMS exists to
# avoid. REFUSED rather than left to discipline: the cell cannot be
# rendered, so it cannot be bought.
RUNG_VACUOUS_IN = {"X-image": ("dims",), "X-state": ("dims",)}

# Recorded before the first call so the factor structure cannot be fitted to
# the outcome, following experiments/ex1/mislabel.py.
PREDICTIONS = {
    "attention": "inert",
    "derivation": "moves in conflict",
    "elicitation": "moves in both, more than derivation alone",
    "order": "inert",
    "precedence_image": "moves in conflict_face toward the image, short of "
                        "the congruent_face ceiling; inert in congruent_face",
    # Predicted inert BECAUSE of a floor effect, and saying so in advance is
    # what stops a null here being read as "the model ignores instructions".
    "precedence_state": "inert in conflict_face: text-following is already "
                        "at floor there, so there is nothing for it to add",
}


def rungs_for(condition):
    """The rungs that render a coherent prompt in this condition."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}; expected one of "
                         f"{sorted(CONDITIONS)}")
    return tuple(r for r in RUNGS
                 if condition not in RUNG_VACUOUS_IN.get(r, ()))


# ---------------------------------------------------------------------------
# 5. The answer schema
# ---------------------------------------------------------------------------
# Typed fields rather than prose. Every number the analysis reads is parsed
# as a number and every category as an enum, so no extractor stands between
# the reply and the measurement.
#
# "opening_needed_m" is required at EVERY rung. R3 already names it, so
# reporting it is a reporting requirement rather than a hint, and it gives
# the diagnostic at N0 where Q1 and Q2 are read. "resting_face" is required
# only under factor D, because naming the face as something to report would
# otherwise tell the model that the face matters.
#
# The base schema puts the opening AFTER the arm, so the arm is committed
# first. N-order moves it before. D moves it before and adds the face.
#
# Whether the reported opening is consistent with the chosen arm's aperture
# is computed in analysis, not asked of the model. Asking invites a
# rationalisation.
#
# A wait may carry a null opening. In dims a model may wait BECAUSE it
# cannot determine the opening, and demanding a number from a model that has
# just said it cannot produce one corrupts the reported-opening measure
# exactly where it is most informative. A wait with null reads as "I cannot
# tell", a wait with a value as "I can tell and no arm fits".
#
# OPEN: "basket" is required on every reply and decides nothing, since the
# boxes are interchangeable and every arm reaches one. It exists only
# because R7 fires on every capture. Pre-assigning destinations at capture
# time would let R7, the field and two lines of the tail go together, which
# is worth doing while the captures are being rebuilt.

_SCHEMA_TAIL = """The boxes are interchangeable, so this never decides which arm to name.
"opening_needed_m" is the opening you judge the object needs, in metres, as a
number with three decimals.
To wait, answer task_id -1 with arm null. Give "opening_needed_m" if you can,
or null if you cannot."""

# FACE OPTION ORDER. The answer vocabulary is two words and a model that
# is not reading the picture will tend to the one it saw first, so the
# order is itself a factor and not a formatting choice. It is also
# confounded with the state, which describes the object "standing on its
# smallest face": small_face is both the first option AND a word already
# on the page, and until the order can be flipped the two pulls cannot be
# told apart.
#
# small_first is the DEFAULT because it is what every run before
# 2026-08-27 used. Changing the default would silently re-ask a different
# question of every file already on disk.
FACE_ORDERS = {
    "small_first": ("small_face", "large_face"),
    "large_first": ("large_face", "small_face"),
}


def _face_field(face_order="small_first"):
    """The resting_face line of the schema, options in the named order."""
    if face_order not in FACE_ORDERS:
        raise ValueError(
            f"unknown face_order {face_order!r}; expected one of "
            f"{sorted(FACE_ORDERS)}. The order is never defaulted at the "
            f"call site: a large_first result recorded as small_first "
            f"would be invisible in the output.")
    first, second = FACE_ORDERS[face_order]
    return '  "resting_face": "<%s | %s>",' % (first, second)


_FACE_FIELD = _face_field("small_first")
_OPEN_FIELD = ('  "opening_needed_m": <number>')
_OPEN_FIELD_C = ('  "opening_needed_m": <number>,')

SCHEMAS = {
    # N0, N-A, N-C. Arm first, report last.
    "base": "\n".join([
        "Answer ONLY with JSON, no prose:",
        '{"task_id": <int>,',
        '  "arm": "<arm name>",',
        '  "basket": "<any box the arm you named can reach>",',
        _OPEN_FIELD,
        "}",
        _SCHEMA_TAIL,
    ]),
    # N-order. Same fields, opening moved ahead of the arm. No added wording.
    "report_first": "\n".join([
        "Answer ONLY with JSON, no prose, with the fields in this order:",
        '{"task_id": <int>,',
        _OPEN_FIELD_C,
        '  "arm": "<arm name>",',
        '  "basket": "<any box the arm you named can reach>"',
        "}",
        _SCHEMA_TAIL,
    ]),
    # N-D, N-CD. Face and opening, both ahead of the arm.
    "face_first": "\n".join([
        "Answer ONLY with JSON, no prose, with the fields in this order:",
        '{"task_id": <int>,',
        _FACE_FIELD,
        _OPEN_FIELD_C,
        '  "arm": "<arm name>",',
        '  "basket": "<any box the arm you named can reach>"',
        "}",
        _SCHEMA_TAIL,
    ]),
}


# ---------------------------------------------------------------------------
# 6. State rendering
# ---------------------------------------------------------------------------

TRIM_STATE_KEYS = ("exchange_pads", "zone_locks", "zone_inbound",
                   "recent_events", "metrics", "tasks_completed",
                   "tasks_failed")

# json.dumps prints 0.05 as "0.05" and 0.100 as "0.1", so the openings the
# experiment turns on would reach the model at different precisions. Each
# float is marked, the state is serialised, and the marks and their quotes
# are stripped, leaving a bare fixed-width number.
_MARK = "@F@"
_DECIMALS = 3


def apply_aliases(value):
    """Rename fields for display and drop the ones no EX2 scene uses."""
    if isinstance(value, dict):
        return {FIELD_ALIASES.get(k, k): apply_aliases(v)
                for k, v in value.items() if k not in DROP_FIELDS}
    if isinstance(value, (list, tuple)):
        return [apply_aliases(v) for v in value]
    return value


def withhold(value, fields):
    """Drop named fields, after aliasing, wherever they appear."""
    if isinstance(value, dict):
        return {k: withhold(v, fields) for k, v in value.items()
                if k not in fields}
    if isinstance(value, (list, tuple)):
        return [withhold(v, fields) for v in value]
    return value


def trim_state(state):
    """A copy with the blocks no EX2 scene can use removed."""
    import copy as _copy
    out = _copy.deepcopy(state)
    for key in TRIM_STATE_KEYS:
        out.pop(key, None)
    return out


def mark_decimals(value):
    """Replace every float with a marked, fixed-width string."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return "%s%.*f%s" % (_MARK, _DECIMALS, value, _MARK)
    if isinstance(value, dict):
        return {k: mark_decimals(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mark_decimals(v) for v in value]
    return value


def unmark_decimals(text):
    """Strip the marks and the quotes json put around them."""
    import re as _re
    out = _re.sub(r'"%s([-0-9.]+)%s"' % (_MARK, _MARK), r"\1", text)
    if _MARK in out:
        raise ValueError(
            "a marked number survived into the prompt text. Sending the "
            "marker to the model would corrupt a measurement it has to "
            "compare, so this fails rather than passing it on.")
    return out


def render_state(state, condition, dims_frame="named"):
    """The user-message text: trimmed, aliased, withheld, fixed-width."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    body = apply_aliases(trim_state(state))
    body = withhold(body, CONDITIONS[condition]["withheld"])
    if dims_frame == "extents":
        body = as_extents(body)
    elif dims_frame not in DIMS_FRAMES:
        raise ValueError(f"unknown dims_frame {dims_frame!r}")
    idle = [a["name"] for a in state["arms"]
            if a["state"] == "IDLE" and not a["disabled"]]
    return unmark_decimals(
        "Cell state:\n" + json.dumps(mark_decimals(body), indent=1)
        + "\nIdle arms right now: " + (", ".join(idle) or "none")
        + ".\nAssign the queued task to ONE of these idle arms, or answer "
          "task_id -1 if none can take it now.")


# ---------------------------------------------------------------------------
# 7. Build
# ---------------------------------------------------------------------------

def schema_text(name, face_order="small_first"):
    """The answer schema, with the face options in the named order.

    SCHEMAS itself stays the default-order rendering so that anything
    reading it directly keeps seeing what it always saw; only the face
    line is rebuilt, and only when the order is not the default.
    """
    text = SCHEMAS[name]
    if face_order == "small_first":
        return text
    return text.replace(_FACE_FIELD, _face_field(face_order))


def system_prompt(rung, condition, has_image=True, preference="franka",
                  face_order="small_first", dims_frame="named"):
    """The system prompt for one cell of the design."""
    if rung not in RUNGS:
        raise ValueError(
            f"unknown rung {rung!r}; expected one of {sorted(RUNGS)}. Rungs "
            f"are never defaulted: an N0 result recorded as N-C would be "
            f"invisible in the output.")
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}; expected one of "
                         f"{sorted(CONDITIONS)}")
    if preference not in PREFERENCE_TEXT:
        raise ValueError(f"unknown preference {preference!r}; expected one "
                         f"of {sorted(PREFERENCE_TEXT)}")
    if condition in RUNG_VACUOUS_IN.get(rung, ()):
        raise ValueError(
            f"{rung!r} is vacuous in {condition!r}: it speaks about the "
            f"stated resting face and this condition states none. A prompt "
            f"naming a withdrawn field makes the model solve a comprehension "
            f"puzzle rather than the question under test, so the cell is "
            f"refused rather than rendered.")

    spec = RUNGS[rung]
    return BASE_PROMPT.format(
        tx=C.TABLE_TOP[0], ty=C.TABLE_TOP[1], cr=C.CENTER_RADIUS,
        scene_block=_scene_block(condition, has_image, dims_frame),
        r3=CONDITIONS[condition]["r3"],
        preference=PREFERENCE_TEXT[preference],
        rung=spec["text"],
        schema=schema_text(spec["schema"], face_order),
    )


def build_ex2_prompt(state, rung, condition, image_b64=None,
                     preference="franka", face_order="small_first",
                     dims_frame="named"):
    """Messages for one EX2 trial."""
    content = [{"type": "text",
                "text": render_state(state, condition, dims_frame)}]
    if image_b64 is not None:
        content = [{"type": "image_url",
                    "image_url":
                        {"url": f"data:image/png;base64,{image_b64}"}}
                   ] + content
    return [
        {"role": "system",
         "content": system_prompt(rung, condition,
                                  has_image=image_b64 is not None,
                                  preference=preference,
                                  face_order=face_order,
                                  dims_frame=dims_frame)},
        {"role": "user", "content": content},
    ]


def manipulation_check(image_b64):
    """The control, asked once per scene per view and per blur level.

    Two-way since 2026-08-27. It was three-way, and the extra option was
    the middle face, which no model separated from large_face: 58 percent
    over 81 trials, Fisher p = 0.76. Chance is now one in two.

    THE THIRD FACE IS NOT NAMED, not even to exclude it. Mentioning it
    would make this a three-way question with one option discouraged,
    which is a different measurement from the one the captures support.
    The capture script guarantees no scene shows it.
    """
    return [
        {"role": "system",
         "content": "Answer with one word and nothing else."},
        {"role": "user", "content": [
            {"type": "text",
             "text": "The block on the table is resting on one of two "
                     "faces. They measure 0.130 x 0.100 m (the larger) and "
                     "0.100 x 0.050 m (the smaller). Which one is it "
                     "resting on? Answer 'large_face' or 'small_face'."},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]},
    ]


# ---------------------------------------------------------------------------
# 8. Verification
# ---------------------------------------------------------------------------

_ANCHOR = "\nYOUR ANSWER"


def rung_diff(condition="congruent", **kw):
    """Each rung's system prompt, for eyeballing before any spend.

    Only the rungs coherent in this condition: a directive is vacuous where
    no resting face is stated, and system_prompt refuses to render it.
    """
    return {r: system_prompt(r, condition, **kw)
            for r in rungs_for(condition)}


def assert_glossary_matches_state(condition):
    """The glossary names exactly the fields the state carries.

    Per condition, because dims withholds two of them. A promise the state
    does not keep, or a field present but unglossed, both make the model
    solve a comprehension puzzle rather than the derivation under test.
    """
    text = system_prompt("N0", condition)
    # The head only. The answer schema legitimately asks the model to REPORT
    # the opening in every condition, including dims where the state does not
    # supply it, and the schema tail defines it there.
    text = text[:text.index("\nYOUR ANSWER")]
    absent = CONDITIONS[condition]["withheld"]
    for name in FIELD_ALIASES.values():
        named = ('"%s"' % name) in text
        if name in absent and named:
            raise ValueError(
                f"{name} is withheld from the state in {condition} but the "
                f"prompt still names it.")
        if name not in absent and not named:
            raise ValueError(
                f"{name} is rendered into the state but not glossed.")
    for dead in DROP_FIELDS:
        if '"%s"' % dead in text:
            raise ValueError(f"{dead} is dropped from the state but still "
                             f"named in the prompt.")
    return True


def assert_r3_matches_state(condition):
    """R3 never points at a field the state does not carry.

    R3 is substituted rather than deleted in dims. Deleting it would test
    the value of knowing the constraint exists, which is not the question.
    """
    text = system_prompt("N0", condition)
    r3 = text[text.index("R3  Gripper opening"):text.index("R4  Load")]
    names_field = '"opening_needed_m"' in r3
    withheld = "opening_needed_m" in CONDITIONS[condition]["withheld"]
    if withheld and names_field:
        raise ValueError(
            f"R3 names opening_needed_m in {condition}, where the field is "
            f"withheld. A model could read the rule as inapplicable, and "
            f"that would score as a derivation failure while being a "
            f"rule-reading failure.")
    if not withheld and not names_field:
        raise ValueError(f"R3 does not name opening_needed_m in {condition}.")
    return True


def assert_base_states_no_relation():
    """The base prompt states the conventions and never the relation.

    The bounding-box and top-down sentences are deliberately close to
    factor C, so the boundary is enforced on the base as well as on the
    rungs.
    """
    head = BASE_PROMPT[:BASE_PROMPT.index("{rung}")].lower()
    for phrase in ("smaller of", "horizontal extent", "depends on which face",
                   "changes when"):
        if phrase in head:
            raise ValueError(
                f"the base prompt contains {phrase!r}, which states the "
                f"pose-to-opening relation. That is factor C, and putting "
                f"it in the base gives every rung the derivation fact.")
    return True


def assert_rungs_isolated(condition="congruent", **kw):
    """Every rung differs from N0 by its own factor and nothing else.

    A wording factor inserts one block at the anchor. The order factor
    changes the schema and adds no words. Factor D does both, so it is
    checked against N0's head plus its block, and separately on its schema.
    A directive is structurally a wording factor and is held to its own
    content rule.

    Every rendered rung must fall to one of the branches: the `unchecked`
    tally is what stops a new variant being isolated by nothing while this
    assertion still reports a pass.
    """
    p = rung_diff(condition, **kw)
    base = p["N0"]
    if base.count(_ANCHOR) != 1:
        raise ValueError("the answer anchor is not unique, so a factor "
                         "block cannot be located unambiguously.")

    head = lambda t: t[:t.index(_ANCHOR)]

    # Every rendered rung must be accounted for by one of the branches
    # below, and the tally is asserted rather than trusted.
    checked = {"N0"}

    for rung in ("N-A", "N-C"):
        if p[rung] != base.replace(_ANCHOR, RUNGS[rung]["text"] + _ANCHOR, 1):
            raise ValueError(
                f"{rung} does not equal N0 with its factor block inserted, "
                f"so its contrast against N0 carries more than one change.")
        checked.add(rung)

    if head(p["N-order"]) != head(base):
        raise ValueError(
            "N-order differs from N0 before the answer section. It is the "
            "control for the report order and must add no wording.")
    if p["N-order"] == base:
        raise ValueError(
            "N-order is identical to N0. The reordered schema was not "
            "applied, so the control measures nothing.")
    checked.add("N-order")

    for rung in ("N-D", "N-CD", "N-ACD"):
        if head(p[rung]) != head(base) + RUNGS[rung]["text"]:
            raise ValueError(
                f"{rung}'s wording is not N0's plus its blocks, so its "
                f"effect cannot be separated from the report order.")
        if RUNGS[rung]["schema"] != "face_first":
            raise ValueError(f"{rung} must use the face-first schema.")
        checked.add(rung)

    # THE DIRECTIVES. Structurally N0 plus a block at the anchor, like N-A
    # and N-C, and they keep the base schema so the arm is still committed
    # before the opening and the comparison against N-A is like for like.
    # What differs is the CONTENT rule, below.
    for rung in DIRECTIVE_RUNGS:
        if rung not in p:
            continue                      # vacuous here, and refused
        if RUNGS[rung]["schema"] != "base":
            raise ValueError(
                f"{rung} does not use the base schema. A directive that also "
                f"reordered the answer would confound precedence with the "
                f"report order, which is what N-order exists to separate.")
        if p[rung] != base.replace(_ANCHOR, RUNGS[rung]["text"] + _ANCHOR, 1):
            raise ValueError(
                f"{rung} does not equal N0 with its block inserted, so its "
                f"contrast against N0 carries more than one change.")
        if not RUNGS[rung]["text"].startswith(A_ATTEND):
            raise ValueError(
                f"{rung} does not open with A_ATTEND. Its whole attribution "
                f"is that it is N-A plus one sentence, so that {rung} minus "
                f"N-A is the precedence sentence and nothing else.")
        checked.add(rung)

    unchecked = set(p) - checked
    if unchecked:
        raise ValueError(
            f"{sorted(unchecked)} rendered but was checked by no rule. Until "
            f"2026-08-31 this function walked literal rung names, so a rung "
            f"added to RUNGS was isolated by nothing while the assertion "
            f"passed. A silent gap in an auditable structure is worse than "
            f"no assertion.")

    # The boundary rule, mechanically. Per rung, never blanket: "face" is
    # forbidden to A and REQUIRED of X, so a shared list could not express
    # both and the new variant would have to be exempted instead of checked.
    forbidden = {
        "N-A": ("resting_face", "face", "orientation", "opening", "extent"),
        "N-C": ("look", "image", "give", "report"),
        "N-D": ("smaller of", "horizontal extent", "depends on"),
        "X-image": ("small_face", "large_face", "orientation", "opening",
                    "extent", "smaller of", "depends on", "franka", "ur_",
                    "report"),
        "X-state": ("small_face", "large_face", "orientation", "opening",
                    "extent", "smaller of", "depends on", "franka", "ur_",
                    "report"),
    }
    # Exempting a rung is a DECISION and must be written where it can be
    # read, not reached by falling off the end of a dict. N0 and N-order add
    # no wording; N-CD is a declared combination rather than one factor.
    exempt = {"N0", "N-order", "N-CD", "N-ACD"}
    unruled = set(RUNGS) - set(forbidden) - exempt
    if unruled:
        raise ValueError(
            f"{sorted(unruled)} has no boundary rule and is not declared "
            f"exempt. Add a rule or add it to `exempt` with a reason; "
            f"silence is not a third option.")

    for rung, words in forbidden.items():
        block = RUNGS[rung]["text"].lower()
        for w in words:
            if w in block:
                raise ValueError(
                    f"{rung} names {w!r}, which belongs to another factor. "
                    f"The boundary rule in the module docstring is what "
                    f"makes the factor structure auditable.")

    # POSITIVE rules, for the directives only. A directive that lost its
    # "disagree" clause passes every negative test above and quietly stops
    # being a directive, which is the one failure the forbidden map cannot
    # see.
    required = {
        "X-image": ("image", "resting face", "disagree", "go by the image"),
        "X-state": ("image", "resting face", "disagree", "go by the state"),
    }
    for rung, words in required.items():
        block = " ".join(RUNGS[rung]["text"].split()).lower()
        for w in words:
            if w not in block:
                raise ValueError(
                    f"{rung} does not say {w!r}. A directive is defined by "
                    f"naming both sources and which one wins; without that "
                    f"it is not the thing the cell is buying.")
    return True