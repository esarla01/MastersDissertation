"""EX2 step 3: the four attention rungs, and the structured justification.

THE LADDER. Four wordings, applied within every condition, differing only
in how hard they point at the image.

    P0  neutral            pose is never mentioned. The image is attached
                           as usual and nothing draws attention to it.

    P1  look at the image  told to LOOK. Not told what to look for, and
                           not told that pose bears on capability.

    P2  pose is relevant   told the RULE: graspable width is the width of
                           the presented face, so it changes with pose.

    P3  attention directed the justification must be produced BEFORE the
                           arm is chosen. Forced to APPLY the rule.

Four rather than three because a single "pose is relevant" rung would give
away the instruction and the mechanism at once: a model that succeeded only
there could have needed the prompt to point at the image, or needed the
rule, and one rung cannot tell those apart. Each gap now isolates one
failure:

    P0 -> P1   can use the image but does not attend to it unaided
    P1 -> P2   looking is not enough; the pose-to-width rule must be stated
    P2 -> P3   knowing the rule is not enough; it must be applied BEFORE
               the choice rather than justified after it

THE JUSTIFICATION. The free-text "reason" is replaced by a "why" block with
one entry per clause of R3, so the model shows its working on the rule it
was given. Three reasons this beats prose:

  - It LOCALISES a failure: which of the three checks went wrong, rather
    than merely that something did.
  - "why.grasp" states the width the model BELIEVED. In a conflict cell
    that is either the true value, meaning it read the image, or the
    declared one, meaning it read the text. A second, nearly independent
    reading of the headline, free with every answer.
  - It exposes reasoning and action coming apart. In the seed episode the
    model wrote that ur_e would deliver to a basket ur_e cannot reach, and
    acted legally anyway.

It stays OBSERVATIONAL. A rationale can be produced after the fact for an
answer arrived at some other way, so it is evidence about mechanism, never
a scored endpoint.

ALL FOUR RUNGS SHARE ONE SCHEMA. P3 does not add a field; it moves the
block ahead of the arm choice. The ladder varies WHEN the justification is
produced, not what it contains, which keeps the rungs comparable.

Usage:
    from experiments.ex2.prompts import build_ex2_prompt
    messages = build_ex2_prompt(state, rung="P2", condition="conflict",
                                image_b64=frame)
"""

import json

from core.decision.state_builder import build_prompt

# EX2 rewrites two sections of the shared base prompt, so the base's
# PROMPT_VERSION no longer identifies what the model actually read. Rows
# carry this alongside it. Bump it whenever a substitution changes.
#
#   2026-08-05a  opening instruction substituted: the base asked for ONE
#                task while the schema asked for EVERY task, and rows
#                before this date were answered under that contradiction.
#   2026-08-05b  removed the zone-lock clause: no EX2 scene ever takes a
#                zone lock, and G2 which referred to it was already gone.
#   2026-08-06a  solo mode: one queued task, G4 trimmed, G6 Franka
#                preference added, base single-assignment answer kept with
#                the why block in place of "reason".
#   2026-08-06b  solo: G3 trimmed and "regions" dropped from the answer,
#                neither of which an EX2 solo trial can use.
#   2026-08-07e  P4 added as a ceiling rung: look at the image, decide
#                upright or lying, take the width that follows. Bounds the
#                ladder. Zero image belief at P0, P1 and P2a and 36 percent
#                at P2 leaves the residual unexplained; P4 says whether
#                that residual is a choice or a limit.
#   2026-08-07d  text-only mode strips the sentences that describe the
#                image, rather than keeping them and dropping the picture.
#                The shared build_prompt keeps mode A byte-identical to V
#                on purpose, which was right for the original fairness
#                pair; here it would describe a side view that is not
#                attached. The two prompts therefore differ by more than
#                the image block and the method must say so.
#   2026-08-07c  ladder split into single increments. P2a is arbitration
#                without derivation; P2 bundled the two. P3a is the schema
#                reorder without the orientation clause; P3 bundled those.
#   2026-08-07b  P3 gets a schema with "why" before "arm". P3 tells the
#                model to justify first, but the schema still listed the
#                arm first, and generation runs left to right: the arm was
#                committed before a word of justification existed. Same
#                failure as the opening line that asked for ONE task while
#                the schema asked for EVERY. Also "each object" to "the
#                object", since solo queues one.
#   2026-08-07a  the arm preference is counterbalanced. G6 preferring a
#                Franka is a pull toward 0.058, which is the text's number
#                on a lying scene and the image's on an upright one, so a
#                Franka-leaning model is indistinguishable from one reading
#                the picture. Under a UR preference the two predict
#                opposite arms.
#   2026-08-06f  every float in the state written to three decimals, so
#                0.080 and 0.096 are compared at the same precision. One
#                reply had echoed the Franka limit back as "0.080", which
#                suggests the model was normalising formats itself.
#   2026-08-06e  the base names the image as a side view of this cell and
#                says both sources describe it. Nothing in the base said
#                the image was evidence at all, so at P0 a model could
#                read it as decoration; across 132 solo trials not one
#                reply mentioned it. This says where the sources are, not
#                how to weigh them, which stays in the rung.
#                P2 and P3 gain: where the two disagree about an object,
#                the image is what is on the table. P2 previously only
#                repeated P1 and added the width fact, so it was barely an
#                escalation; this makes the ladder a real gradient. P3
#                inherits it so it stays a superset of P2.
#                NOTE: results before this were run under the weaker P2.
#   2026-08-06d  a line saying the written state and the image both follow.
#                Orientation only: it says where the two sources are, not
#                how much to weigh them. Anything about attending to the
#                image belongs in the RUNG, which is what varies prompt
#                strength, and putting it in the base would make P0 stop
#                being the neutral rung.
#   2026-08-06c  solo: baskets renamed to carry no category, G1 trimmed,
#                and the destination made explicitly free. basket_food was
#                reachable by ur_w but not ur_e, so the eleven east scenes
#                needed a handover to deliver a correctly assigned lying
#                bottle and the eleven west ones did not. That put a
#                delivery cost on the arm choice under test, in half the
#                cells where the conflict manipulation does its work.
EX2_PROMPT_VERSION = "2026-08-07e"

# Inserted verbatim. Kept as data rather than f-strings so a rung's exact
# wording is greppable, diffable and quotable in the write-up.
# THE ATTENTION LADDER. One increment per rung, on one dimension at a time.
#
#   P0   nothing. The base already states the image is a side view of this
#        cell and that both sources describe it, so P0 is not "the image is
#        unmentioned" but "the image is established as evidence, with no
#        instruction to consult it".
#   P1   ATTENTION. Consult the image. No authority, no domain fact.
#   P2a  ARBITRATION. The image outranks the text where they disagree.
#        Says nothing about what to extract from it.
#   P2   DERIVATION. Graspable width depends on the face presented.
#        P2 previously bundled arbitration and derivation into one step, so
#        an effect could not be attributed to either. P2a splits them.
#   P3a  ORDER. The schema puts "why" before "arm" so the justification is
#        written before the arm is committed. Reordering ALONE.
#   P3   ORIENTATION. P3a plus an instruction to state the pose in
#        "why.grasp". P3 previously changed the order AND added this
#        clause, so "reasoning first doubles image use" could not be
#        separated from "being asked to name the pose does". P3a splits
#        them, and the clause matters because inviting a description is
#        where qwen's prototype substitution appears.
#
# P0 to P2 change what the model KNOWS. P3a and P3 change how it REPORTS.
# The two are different dimensions and the method should say so rather than
# presenting six rungs as increasing volume.
RUNGS = ("P0", "P1", "P2a", "P2", "P3a", "P3", "P4")

_ATTEND = ("\nThe image shows the scene as it is now. Check it against the\n"
           "description before you choose.\n")
_ARBITRATE = ("Where the image and the description disagree about an "
              "object, the\nimage is what is actually on the table.\n")
_DERIVE = ("An object's graspable width is the width of the face it "
           "presents\nto the gripper, so it changes when the object stands "
           "up or lies\ndown.\n")
_ORIENT = ("Fill in \"why\" BEFORE deciding which arm to name, and state "
           "the\nobject's orientation in \"why.grasp\" alongside the width "
           "that\nfollows from it.\n")

# THE CEILING. Not a further step on either dimension: it bundles what to
# know with how to report, and it comes close to handing over the answer
# procedure. Its value is as a BOUND rather than as evidence of grounding.
# If P4 is high and P2 is not, the shortfall at P2 is a choice rather than
# an inability, and the lower rungs can be read as unprompted behaviour.
# If P4 also stalls, instruction is exhausted and the limit lies elsewhere,
# which is the more interesting outcome.
#
# It stops at the width check rather than naming an arm: telling the model
# which arm to pick would test compliance, not perception.
#
# It never says the description is wrong, so the same rung is usable in the
# congruent condition. Saying so would give the manipulation away and make
# the control uninterpretable.
_LOOK = ("Before choosing, look at the image and decide whether the object "
         "is\nstanding upright or lying down. Take the graspable width that "
         "follows\nfrom the pose you see, not from the description, and "
         "check it against\nthe arm's max_grasp_m.\n")

RUNG_TEXT = {
    "P0": "",
    "P1": _ATTEND,
    "P2a": _ATTEND + _ARBITRATE,
    "P2": _ATTEND + _ARBITRATE + _DERIVE,
    "P3a": _ATTEND + _ARBITRATE + _DERIVE,
    "P3": _ATTEND + _ARBITRATE + _DERIVE + _ORIENT,
    "P4": _ATTEND + _ARBITRATE + _DERIVE + _ORIENT + _LOOK,
}

# P3a and P3 both get the reordered schema; P3a adds no words over P2, so
# the ONLY difference between P2 and P3a is the field order.
WHY_FIRST_RUNGS = ("P3a", "P3", "P4")


# ---------------------------------------------------------------------------
# SOLO mode: one queued task, one arm, no round.
# ---------------------------------------------------------------------------
# The batch round asked the model to serve two tasks that compete for one
# UR. That competition is EX3's subject, not EX2's, and it meant a wrong
# answer could be either a capability misjudgement or a coordination
# failure. Solo queues the mustard alone. The clamp stays in the state as
# an OBJECT and stays visible in the image, so the picture is unchanged,
# but it is no longer a task and no longer competes for an arm.
#
# What makes the single choice informative is the Franka preference below.
# An earlier single-task attempt failed because the UR was legal under both
# the true and the declared pose, so the arm named carried no information.
# With a Franka preferred, the correct arm now DIFFERS by pose: upright at
# 0.058 the Franka can take it, lying at 0.096 it cannot and only the UR
# can. Under conflict, following the text and following the image give
# opposite arms on every trial.
#
# The wording is flat on purpose. "Prefer a Franka unless it cannot handle
# the object" would state the exception, which is the capability check
# being measured, and a correct answer would come cheaper than it should.
# WHY THERE ARE TWO. G6 pulls toward one arm type, and a Franka is legal
# only at 0.058 m. So "prefer a Franka" is a standing pull toward believing
# 0.058, and 0.058 is the TEXT's number on a lying scene and the IMAGE's
# number on an upright one. A model that merely leans Franka therefore
# scores as follows_state in one direction and follows_image in the other,
# which is exactly the shape of the observed result and is indistinguishable
# from consulting the picture.
#
# Counterbalancing dissolves it. Under the UR preference the pull is toward
# 0.096, so the two accounts predict OPPOSITE arms in both directions. If
# image use survives the flip, it is image use; if it follows the preferred
# arm instead, it was the preference all along.
#
# The wording stays flat in both. "Prefer a Franka unless it cannot handle
# the object" would state the exception, which is the capability check
# being measured, and a correct answer would come cheaper than it should.
SOLO_PREFERENCES = {
    "franka": "G6  Prefer a Franka arm for sorting tasks.\n",
    "ur": "G6  Prefer a UR arm for sorting tasks.\n",
}
# Kept only so an older caller does not break. The live path reads
# SOLO_PREFERENCES[preference]; using this constant there silently ignored
# the counterbalance and rendered the Franka wording under both settings.
SOLO_PREFERENCE = SOLO_PREFERENCES["franka"]


# G4 tells the model to protect an arm another queued task needs. With one
# queued task there is no other task, so it points at nothing; and it would
# push toward the Franka for the same reason G6 does, which would make the
# two indistinguishable.
# G3 tells the model to ignore queue order and not pick the first task
# listed. With one queued task there is no order and no other task, so it
# describes a choice that does not exist.
# G1 tells the model to send each object to the basket named for its
# category. Solo renames the baskets so none is named for anything, so G1
# would point at a property the state no longer carries.
SOLO_TRIM_RULES = ("G4", "G3", "G1")

# The base ANSWER section already asks for ONE task and ONE arm, so unlike
# the batch mode this is not a change of shape. Only "reason" is replaced,
# by the same why block the batch schema uses, so width belief is graded
# the same way in both. "regions" is kept: it is in the base wording and
# dropping it would be one more difference from what every other
# experiment sends.
# Replaces the free-text reason. Same block at every rung.
WHY_SCHEMA = (
    '  "why": {\n'
    '    "grasp": "<the width you judged, and whether the arm\'s '
    'max_grasp_m covers it>",\n'
    '    "payload": "<the object\'s mass, and whether the arm\'s '
    'payload_kg covers it>",\n'
    '    "delicate": "<whether the object is delicate, and whether the '
    'arm allows it>"\n'
    '  }')


# "regions" is DROPPED with its three lines of explanation. Grading never
# reads it: legal_arms calls the validator with task_id, arm and basket
# only. It exists for zone locking in the live pipeline, and no EX2 scene
# takes a zone lock.
#
# "basket" is KEPT. An EX2 task is captured with "dest_xy": null and
# "dest_zone": "unassigned", so R7 fires on every trial and the model has
# to name one. Pre-setting destinations at capture time would let this go,
# along with R7 and G1, but that is a change to the captures, not the
# prompt.
#
# "task_id" is kept because -1 is how a wait is expressed and the grader
# reads it.
SOLO_SCHEMA = "\n".join([
    "Answer ONLY with JSON, no prose:",
    '{"task_id": <int>, "arm": "<arm name>",',
    '  "basket": "<any box the arm you named can reach>",',
    WHY_SCHEMA,
    "}",
    "The boxes are interchangeable: put the object in any box the arm can",
    "reach. Every arm can reach one, so this never decides which arm to",
    "name.",
    "To wait, answer task_id -1 with arm null.",
    'Always give "why", for a wait too: say what you are waiting for.',
])


# P3 asks the model to justify BEFORE naming an arm. Saying so is not
# enough: a model generates left to right, so if "arm" still comes first in
# the schema it is committed before a word of justification exists and the
# instruction cannot bite. This is the same failure as the opening line
# that asked for ONE task while the schema asked for EVERY: the shape wins
# over the sentence. P3 therefore gets a schema with "why" first.
SOLO_SCHEMA_WHY_FIRST = "\n".join([
    "Answer ONLY with JSON, no prose, with the fields in this order:",
    '{"task_id": <int>,',
    # A comma: "why" is no longer the last field, and a template that is
    # not itself valid JSON invites a reply that is not either.
    WHY_SCHEMA + ",",
    '  "arm": "<arm name>",',
    '  "basket": "<any box the arm you named can reach>"',
    "}",
    "The boxes are interchangeable: put the object in any box the arm can",
    "reach. Every arm can reach one, so this never decides which arm to",
    "name.",
    "To wait, answer task_id -1 with arm null.",
    'Always give "why", for a wait too: say what you are waiting for.',
])

# BATCH ANSWER. EX2 asks for the WHOLE round at once, one assignment per
# task, rather than one task at a time as EX1 and EX3 do.
#
# Why. With one assignment at a time the model named ur_w in every trial,
# twelve out of twelve, and ur_w is legal whichever way the bottle lies, so
# the choice carried no information about which source was believed. There
# was no pressure to consider franka_n at all: taking the mustard with ur_w
# is never wrong, and the second task could simply be left for later.
#
# Assigning both together removes the safe answer. The clamp is 0.122 m and
# UR-only, so ur_w is the only arm that can take EITHER object:
#
#   picture LYING     ur_w must take the mustard (franka_n cannot), so the
#                     clamp waits
#   picture UPRIGHT   franka_n can take the mustard, freeing ur_w for the
#                     clamp, so both proceed
#
# Different beliefs give different ROUNDS, and no round fits both. The
# decision stays an ALLOCATION rather than becoming a quiz about widths,
# which matters because the allocation claim is the one the thesis makes.
#
# The cost is that EX2 is joint-assignment where EX1 and EX3 are
# sequential. Disclosed rather than glossed: EX2 is a standalone instrument
# and its comparisons are all within itself.
BATCH_SCHEMA = "\n".join([
    "Answer ONLY with JSON, no prose. Assign EVERY queued task in one",
    "answer:",
    '{"assignments": [',
    '  {"task_id": <int>, "arm": "<arm name, or null to leave this task>",',
    '   "basket": "<basket name, or null if the task already has a '
    'destination>",',
    '   "assignable": ["<every idle arm that COULD serve this task>"],',
    '   "why": {',
    '     "grasp": "<the width you judged, and whether the arm\'s '
    'max_grasp_m covers it>",',
    '     "payload": "<the object\'s mass, and whether the arm\'s '
    'payload_kg covers it>",',
    '     "delicate": "<whether the object is delicate, and whether the '
    'arm allows it>"',
    "   }}",
    "]}",
    "One arm may take at most one task. List EVERY queued task, including",
    'any you leave unassigned, with "arm" null and "why" saying what',
    "prevents it.",
    '"assignable" is every IDLE arm that could serve that task if it were',
    "free, whether or not you chose it. Consider each idle arm in turn.",
])

# The whole ANSWER section is replaced, not patched: the base asks for one
# assignment and EX2 asks for a round.
_ANSWER_HEAD = "YOUR ANSWER"

# ...and so does the OPENING SENTENCE, which the answer substitution alone
# left behind. The base prompt's first instruction told the model to choose
# one task; the schema forty lines later told it to assign every task. The
# model read the first instruction and obeyed it: in the congruent floor
# test it assigned the mustard, left the clamp, and then wrote a correct
# explanation of why the clamp needed the arm it had just spent. Eleven of
# eleven rounds failed that way and it was read as an inability to relate
# two assignments, which it may not have been.
#
# The base line is NOT edited in state_builder: EX1, EX3 and the live
# pipeline share it, and changing it there would move PROMPT_VERSION for
# every one of them and void the byte-identical acceptance test. EX2
# substitutes it locally, exactly as it does the answer section.
_OLD_HEADLINE = ("Each time you are asked, choose ONE queued task and ONE "
                 "idle arm, or\nchoose to wait.")
_NEW_HEADLINE = ("Each time you are asked, assign EVERY queued task in one "
                 "answer:\nname an idle arm for each, or leave a task for "
                 "later if nothing free can\nserve it.")


# Only the dims condition needs this, and only it gets it: the text no
# longer states a graspable width, so R3 has to say where one comes from.
DIMS_RULE = (
    "\n\"dims_m\" gives an object's height, width and depth AS IF IT WERE\n"
    "UPRIGHT. It describes the object, not how it is resting. The graspable\n"
    "width is the smaller of the two horizontal extents in the object's\n"
    "CURRENT pose, so it depends on how the object is lying or standing.\n"
    "No graspable width is given; work it out.\n")


# The base prompt states the OVERHEAD convention. That is true for
# table_cam and false for ex2_cam, which looks at the table from the south
# and above. Telling the model the top edge is north when it is not would
# be a lie in the prompt, and a plausible reason to misread a pose.
_OLD_VIEW = ("If an overhead\nimage is given, its top edge is north (+y) "
             "and its right edge is east (+x).")
VIEW_TEXT = {
    "table_cam": _OLD_VIEW,
    "ex2_cam": ("The image is taken from the south of the table, above it "
                "and\nlooking back at the centre, so north (+y) is away "
                "from the camera\nand east (+x) is to the right."),
}


# ---------------------------------------------------------------------------
# EX2 trim: remove what an EX2 scene cannot use.
# ---------------------------------------------------------------------------
# Measured on a real EX2 state, the user message is 3851 characters and
# exchange_pads is 845 of them, the largest single block. Every EX2 scene
# places both objects where the two idle arms can pick them up AND deliver
# them directly, so no handover is possible in any of the 44 captures and
# R5 never binds. Five pads with coordinates, arm lists and reach lists are
# therefore not merely noise: a model reasoning carefully about routes that
# do not exist would land that confusion in the headline as a grounding
# failure. Removing them removes a false-result risk, not just tokens.
#
# The other removals are empty or irrelevant in a two-object still life:
# zone locks that nobody holds, an event log with nothing in it, counters
# at zero.
#
# NOT removed, because EX2 depends on them: R5 (a handover can still be
# arranged behind the model's choice), R7 (EX2 tasks have dest_xy null and
# the model does choose the basket), the arms block (it carries
# max_grasp_m, the number the whole experiment turns on), objects, baskets
# and tasks.
#
# SCOPED TO EX2. build_state is untouched, so EX1, EX3, every recorded
# episode and the offline acceptance test are unaffected. EX1 and EX3 keep
# the pads because relays are real there: the seed episode produced two
# NO_ROUTE rejections, and a model held to R5 without the pad block would
# be judged on a rule it has no means to check.
TRIM_STATE_KEYS = ("exchange_pads", "zone_locks", "zone_inbound",
                   "recent_events", "metrics", "tasks_completed",
                   "tasks_failed")

# R6 concerns an object already sitting on a pad, which never happens here.
# G2 refers to zone_locks and zone_inbound, which the trim removes, so it
# would be pointing at fields that no longer exist.
#
# R5, R7 and G1 are deliberately KEPT. An EX2 task is captured with
# "dest_xy": null and "dest_zone": "unassigned", so R7 fires on every
# trial and the model has to name a basket; G1 tells it which one; and R5
# governs how that destination is reached. R4 also ends with "see R5", so
# dropping R5 would leave a dangling reference. Trimming any of the three
# was tried on a fixture whose tasks carried destinations, which the real
# captures do not, and the harness caught it.
TRIM_RULES = ("R6", "G2")

# The zone-lock clause describes contention between arms over a shared
# zone. G2 was already dropped for referring to fields the trim removes,
# and this is the last mention of a mechanism that never binds: an EX2
# scene holds two objects and no zone lock is ever taken.
_ZONE_LOCK = ", and one arm may hold a zone at a time"

# The render is unfamiliar and a model that mistakes a basket for an object
# is failing at something EX2 does not test. This names the FIXED FURNITURE
# only: no objects, no pose, no counts of anything that varies. Anything
# more would be an attention cue and P0 would stop being the neutral rung.
SCENE_TEXT = (
    "The image shows the four arms at their rest positions, three coloured\n"
    "boxes which are the sorting baskets, and five white crosses marking\n"
    "the exchange points. Objects to be sorted lie loose on the table.\n"
    "The image is a side view of this cell, taken now, and a written\n"
    "description of the same scene follows below. Both describe the\n"
    "cell you are allocating in.\n")

# The text-only version of the same paragraph. build_prompt's mode A keeps
# the system prompt byte-identical to V and drops only the image block,
# which was the right call for the original fairness comparison. It is the
# wrong call for a text-only RUNG: the prompt would describe a side view
# that is not attached, and a model asked to check an absent image is being
# tested on something other than modality. So EX2 strips the references.
#
# The cost is that the two prompts differ by more than the image block, and
# that has to be stated rather than presented as a clean single-variable
# contrast.
SCENE_TEXT_TEXT_ONLY = (
    "The cell holds four arms at their rest positions, three coloured\n"
    "boxes which are the sorting baskets, and five white crosses marking\n"
    "the exchange points. Objects to be sorted lie loose on the table.\n"
    "A written description of the cell state follows below.\n")

# Sentences in the SHARED base that talk about the image. Removed in
# text-only mode for the same reason.
# In text-only mode the camera convention is dropped rather than
# substituted: there is no camera.
_NO_VIEW = ""


# Every float in the state is written to the same number of decimals.
#
# WHY. json.dumps prints 0.08 as "0.08" and 0.096 as "0.096", so the two
# widths the experiment turns on are written to different precisions. One
# gpt reply echoed the Franka limit back as "0.080", which suggests it was
# normalising them itself before comparing. A comparison that decides the
# whole trial should not also ask the model to reconcile formats.
#
# HOW. Not by subclassing float: json's encoder calls float.__repr__
# directly and ignores subclasses. Not by converting to strings either: a
# quoted "0.080" changes the field's type and invites the model to read a
# measurement as text. Instead each float becomes a marked string, the
# state is serialised, and the marks and their surrounding quotes are
# stripped from the text, leaving a bare number.
# Printable on purpose. A control character is escaped by json as \u0000,
# so the marks survive the regex, the guard below checks for a form that is
# no longer present, and the markers reach the model. That happened.
_MARK = "@F@"
_DECIMALS = 3


def mark_decimals(value):
    """Replace every float with a marked, fixed-width string.

    Three decimals because the measured widths carry three, 0.096 and
    0.058. Fewer would round them together and destroy the manipulation.
    """
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
    if _MARK in out or _MARK.encode("unicode_escape").decode() in out:
        raise ValueError(
            "a marked number survived into the prompt text. Sending the "
            "marker to the model would corrupt a measurement it has to "
            "compare, so this fails rather than passing it on.")
    return out


def trim_state(state):
    """A copy with the blocks no EX2 scene can use removed."""
    import copy as _copy
    out = _copy.deepcopy(state)
    for key in TRIM_STATE_KEYS:
        out.pop(key, None)
    return out


def _drop_rule(text, tag):
    """Remove one numbered rule or guidance line, keeping the rest intact."""
    start = text.find("\n" + tag + "  ")
    if start < 0:
        raise ValueError(f"{tag} is not in the prompt; the base wording has "
                         f"changed and the trim must be rechecked rather "
                         f"than silently skipping it")
    i = start + 1
    end = len(text)
    for j in range(i + 1, len(text)):
        if text[j] == "\n" and j + 1 < len(text) and text[j + 1] not in " \n":
            end = j
            break
    return text[:start] + text[end:]


def build_ex2_prompt(state, rung, condition, image_b64=None, view=None,
                     trim=True, describe_scene=True, solo=False,
                     preference="franka"):
    """Messages for one EX2 trial.

    Built on the REAL build_prompt, so the cell description, the hard rules
    and the guidance are identical to what every other experiment sends.
    Only the additions below differ, and each is a single contiguous block
    so a diff against the base prompt shows exactly what EX2 changed.
    """
    if rung not in RUNGS:
        raise ValueError(
            f"unknown rung {rung!r}; expected one of {list(RUNGS)}. Rungs "
            f"are never defaulted: a P0 result recorded as P2 would be "
            f"invisible in the output.")

    if view is not None and view not in VIEW_TEXT:
        raise ValueError(f"unknown view {view!r}; expected one of "
                         f"{sorted(VIEW_TEXT)}")

    messages = build_prompt(mark_decimals(trim_state(state) if trim
                                         else state),
                            "V" if image_b64 else "A", image_b64=image_b64)
    sys_text = messages[0]["content"]

    if trim:
        for tag in TRIM_RULES + (SOLO_TRIM_RULES if solo else ()):
            sys_text = _drop_rule(sys_text, tag)

    # Without an image the camera convention describes nothing, so it goes
    # whether or not a view was named. Guarding on `view` alone left the
    # base overhead sentence in every text-only prompt built without one.
    if image_b64 is None or view is not None:
        if _OLD_VIEW not in sys_text:
            raise ValueError(
                "the base prompt's camera convention has changed and cannot "
                "be substituted. EX2 must not describe an oblique image as "
                "overhead: the model would be told north is at the top when "
                "it is not.")
        sys_text = sys_text.replace(
            _OLD_VIEW, _NO_VIEW if image_b64 is None else VIEW_TEXT[view], 1)

    if trim:
        if _ZONE_LOCK not in sys_text:
            raise ValueError(
                "the base prompt's zone wording has changed and the clause "
                "cannot be removed. Trimming must fail loudly rather than "
                "silently leaving in a mechanism the scene never uses.")
        sys_text = sys_text.replace(_ZONE_LOCK, "", 1)

    # SOLO leaves the opening line alone: the base already asks for one
    # task and one arm, which is exactly what solo wants. The substitution
    # exists only because the BATCH schema contradicted it.
    if not solo:
        if _OLD_HEADLINE not in sys_text:
            raise ValueError(
                "the base prompt's opening instruction has changed and "
                "cannot be substituted. EX2 must not ask for ONE task in "
                "its first line and EVERY task in its schema: the model "
                "obeys the first line, and a round it was told to leave "
                "half-done cannot be scored as a failure to coordinate.")
        sys_text = sys_text.replace(_OLD_HEADLINE, _NEW_HEADLINE, 1)

    if _ANSWER_HEAD not in sys_text:
        raise ValueError(
            "the base answer section has changed and the batch schema "
            "cannot be substituted. EX2 must not silently fall back to a "
            "single assignment: with one task at a time the model named the "
            "always-safe arm in every trial and the choice carried no "
            "information about which source it believed.")
    if solo:
        # G6 goes at the end of the guidance block, where a reader of the
        # prompt would expect the next guidance line to be.
        sys_text = (sys_text[:sys_text.index(_ANSWER_HEAD)].rstrip("\n")
                    + "\n" + SOLO_PREFERENCES[preference]
                    + "\nYOUR ANSWER\n"
                    + (SOLO_SCHEMA_WHY_FIRST if rung in WHY_FIRST_RUNGS
                       else SOLO_SCHEMA) + "\n")
    else:
        sys_text = (sys_text[:sys_text.index(_ANSWER_HEAD)]
                    + "YOUR ANSWER\n" + BATCH_SCHEMA + "\n")

    if describe_scene:
        # Text-only gets the same paragraph with the image references
        # removed, not the image paragraph minus the picture.
        scene = SCENE_TEXT if image_b64 is not None else SCENE_TEXT_TEXT_ONLY
        sys_text = sys_text.replace("\nHARD RULES.",
                                    "\n" + scene + "\nHARD RULES.", 1)

    if condition == "dims":
        sys_text += DIMS_RULE
    sys_text += RUNG_TEXT[rung]

    messages = list(messages)
    messages[0] = dict(messages[0], content=unmark_decimals(sys_text))

    # The state lives in the user message, which may be plain text or a
    # list of blocks when an image is attached.
    user = messages[1]
    content = user["content"]
    if isinstance(content, str):
        messages[1] = dict(user, content=unmark_decimals(content))
    else:
        blocks = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                b = dict(b, text=unmark_decimals(b["text"]))
            blocks.append(b)
        messages[1] = dict(user, content=blocks)
    return messages


def manipulation_check(image_b64):
    """The control, asked once per scene per view.

    No allocation, no state, no rules: can the model read the pose when
    asked about nothing else. If this fails under a view, every
    image-following number under that view is uninterpretable, and the
    result is reported as unreadable rather than as a model failure.
    """
    return [
        {"role": "system",
         "content": "Answer with one word and nothing else."},
        {"role": "user", "content": [
            {"type": "text",
             "text": "Look at the mustard bottle on the table. Is it "
                     "standing upright or lying down? Answer 'upright' or "
                     "'lying'."},
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]},
    ]


def rung_diff(state, condition="congruent"):
    """What each rung adds, for eyeballing before any spend."""
    base = build_ex2_prompt(state, "P0", condition)[0]["content"]
    return {r: build_ex2_prompt(state, r, condition)[0]["content"][len(base):]
            for r in RUNGS}