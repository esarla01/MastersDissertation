"""EX2 step 4: grading.

One reply, one verdict. Graded against MEASURED GEOMETRY, never against the
validator: in a conflict cell the validator is itself operating on a
falsified state, so it would confirm the lie.

FOUR OUTCOMES.

    follows_image   the arm is legal under the TRUE pose and illegal under
                    the declared one
    follows_state   the arm is legal under the DECLARED pose and illegal
                    under the true one
    uninformative   the arm is legal under BOTH. A UR is legal whatever the
                    pose, so a cautious answer lands here
    illegal_both    the arm is legal under neither. Not evidence about
                    which source was used; something else went wrong

WHY "uninformative" IS ITS OWN COLUMN. Without it, every cautious answer
would count as evidence the model ignored the image, and the headline would
be biased toward exactly the conclusion the design exists to test. In a
permissive conflict the picture allows all four arms and the text claims
URs only; naming a UR is consistent with both and says nothing.

FLAGGING is separate from the four outcomes, because a reply can both name
an arm and remark on the disagreement. It has no schema field and can only
appear in free text, so it is scored by a keyword list DECLARED HERE, IN
ADVANCE, and reported as a LOWER BOUND. Keywords were fixed before any
reply was seen and must not be tuned afterwards.

THE REPORTED FIELDS are read but never scored. "opening_needed_m" is
required at every rung and records the opening the model believed, which
in a conflict cell is either the true value, meaning it read the image, or
the declared one, meaning it read the text. That is a second, nearly
independent reading of the headline, and it is also where reasoning and
action can be seen coming apart. "resting_face" is present only under
factor D and records which face the model read off the picture.

Both are TYPED. The prose "why" block they replaced had to be mined by a
regular expression, and three successive extractor rules each produced a
false finding before being caught. Nothing now stands between the reply
and the measurement.

THE LEGACY why BLOCK is still read, as a fallback, for one reason: every
results file collected before 2026-08-26 carries prose and no typed field,
and rescore.py and analyse.py are run over those files. A row that has the
typed field never consults the prose.

Usage:
    from experiments.ex2.grade import grade
    row = grade(reply_text, meta, legal_true, legal_declared)
"""

import json
import re

OUTCOMES = ("follows_image", "follows_state", "uninformative",
            "illegal_both", "noop", "unparseable")

# Fixed 2026-08-04, before any reply existed. Matched case-insensitively
# against the whole reply. Reported as a lower bound: a model can describe
# a disagreement in words none of these cover.
FLAG_KEYWORDS = (
    "does not match", "doesn't match", "do not match", "don't match",
    "contradict", "disagree", "inconsistent", "conflicts with",
    "differs from", "not consistent with",
    "image shows", "picture shows", "appears to be lying",
    "appears to be upright", "actually lying", "actually upright",
)

_NUM = re.compile(r"\d*\.\d+|\d+")


def parse_reply(text):
    """The JSON object in a reply, or None.

    Models wrap JSON in prose or fences however they like, so the first
    balanced object is taken. Returning None rather than raising keeps a
    single malformed reply from ending a paid run.
    """
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    start = s.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except ValueError:
                    return None
    return None


def flagged(text):
    """Did the reply remark on the disagreement. Lower bound, by design."""
    low = (text or "").lower()
    return any(k in low for k in FLAG_KEYWORDS)


# The number the model names as the WIDTH. Three rules have failed here and
# each failure is recorded because the shapes recur.
#
#   first number in the field
#       "extents are 0.191 m and 0.096 m, so graspable width is 0.096 m"
#       returned 0.191, an extent the model had just rejected.
#   number after the last connective
#       most replies name the width first and then compare it, so "so",
#       "means" and "therefore" picked up the arm limit, the payload or the
#       mass: 0.140, 0.603, 6.000.
#   number after the width phrase
#       "0.058 m graspable width (upright bottle depth), covered by ur_e
#       max_grasp_m 0.140 m" puts the number BEFORE the phrase, so this
#       returned the limit.
#
# The rule now handles both orders. A number immediately before the phrase
# wins, where "immediately" means nothing between them but a unit and
# whitespace: that excludes "0.096 m, so graspable width is 0.058", where
# the comma and connective mark the earlier number as working rather than
# as the answer. Otherwise the number after the phrase wins, and the first
# number in the field only when no phrase appears at all.
_WIDTH_PHRASE = re.compile(
    r"(?:graspable|grasp|presented|presenting a)\s+(?:grasp\s+)?width"
    r"\s*(?:is|of|:|=)?\s*", re.IGNORECASE)

# A number sitting against the phrase, with only a unit, adjectives and an
# opening bracket between: "0.096 m horizontal graspable width" and
# "0.058 m (upright presented width)". A comma or a
# connective in the gap means the earlier number was working rather than
# the answer, as in "0.096 m, so graspable width is 0.058", so the gap is
# letters and spaces only and is checked for connectives separately.
_NUM_BEFORE = re.compile(
    r"(\d*\.?\d+)\s*(?:m|metres|meters)?\b([a-z\s\(\)\-]{0,32})$",
    re.IGNORECASE)
_GAP_CONNECTIVE = re.compile(
    r"\b(?:so|and|but|therefore|thus|hence|means|giving|gives|or)\b",
    re.IGNORECASE)


def reported_opening(decision):
    """The typed "opening_needed_m" from a reply, or None.

    A number, not prose. A wait may legitimately carry null: in dims a
    model may wait BECAUSE it cannot determine the opening, and a null
    there reads as "I cannot tell" rather than as a missing answer.

    A value that is not a number is treated as absent rather than coerced.
    A model that writes "0.05 m" into a field typed as a number has not
    answered in the schema, and silently parsing it would hide that.
    """
    if not isinstance(decision, dict):
        return None
    val = decision.get("opening_needed_m")
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    return None


def reported_face(decision):
    """The typed "resting_face" from a reply, or None.

    Present only under factor D, which is the only rung that asks for it.
    Absent everywhere else by design: naming the face as something to
    report would tell the model that the face matters.

    A word outside the schema's enum is returned as-is rather than dropped,
    so a model answering "flat" is visible as a compliance failure instead
    of vanishing into the same None as a rung that never asked.
    """
    if not isinstance(decision, dict):
        return None
    val = decision.get("resting_face")
    return val if isinstance(val, str) and val.strip() else None


def believed_width(decision):
    """The opening the model believed, in metres, or None.

    Reads the TYPED "opening_needed_m" first. Falls back to mining the
    legacy prose "why.grasp" only when there is no typed field, so that
    rescore.py and analyse.py still work on the pre-2026-08-26 results
    files. The fallback never runs on a reply from the current schema.

    The prose rule below is anchored on the phrase rather than on position,
    because the models wrote the number on either side of it and every
    position-based rule tried here picked up an arm limit or a rejected
    extent instead. It is kept exactly as it was: changing it now would
    silently re-score results already reported.
    """
    typed = reported_opening(decision)
    if typed is not None:
        return typed

    why = (decision or {}).get("why")
    if not isinstance(why, dict):
        return None
    text = str(why.get("grasp", ""))

    m = _WIDTH_PHRASE.search(text)
    if m:
        before = _NUM_BEFORE.search(text[:m.start()])
        if before and not _GAP_CONNECTIVE.search(before.group(2)):
            return float(before.group(1))
        after = _NUM.search(text[m.end():])
        if after:
            return float(after.group())

    m = _NUM.search(text)
    return float(m.group()) if m else None


# Every value classify_width can return. Both summaries count against this
# rather than a literal, so a new verdict cannot be added and then silently
# omitted from the tables.
WIDTH_BELIEFS = ("image", "state", "tie", "other", "none")


def classify_width(believed, meta, tol=0.006):
    """Whether the believed width matches the image, the text, or neither.

    The tolerance covers a model rounding 0.096 to 0.1. The two candidate
    widths are 38 mm apart, so 6 mm cannot confuse them.

    'tie' when the two candidates are the same number, which is every
    congruent trial. Nothing the model says can reveal which source it
    used when both sources say 0.096, and returning 'image' there credited
    the picture for an answer the text supplied just as well. That inflated
    apparent grounding in exactly the cells built to have none.
    """
    if believed is None:
        return "none"
    true_w = meta["true_grasp_m"]
    decl_w = meta.get("declared_grasp_m")
    hits_true = abs(believed - true_w) <= tol
    hits_decl = decl_w is not None and abs(believed - decl_w) <= tol
    if hits_true and hits_decl:
        return "tie"
    if hits_true:
        return "image"
    if hits_decl:
        return "state"
    return "other"


def arm_limits(state):
    """{arm name: max_grasp_m} from a captured state."""
    return {a["name"]: a["max_grasp_m"] for a in state.get("arms", [])
            if "max_grasp_m" in a}


def self_contradicted(believed, arm, limits, tol=0.006):
    """Did the reply state a width its own named arm cannot take.

    ARITHMETIC, not keyword matching. The reply says a width, names an arm,
    and the two are compared against the arm's real limit. No judgement
    about phrasing enters into it.

    This exists because of a specific observed failure. Five qwen conflict
    replies read, in effect, "0.096 m, within franka_n's max_grasp_m of
    0.08 m? No, 0.096 > 0.08, so not acceptable", and then assigned
    franka_n. The model reached the right conclusion and did not act on it.

    Those five were scored follows_state, which is wrong twice over: the
    model did not follow the state's implication, it contradicted it, and
    counting them as cue-following inflates a number that is meant to mean
    the model believed the text. A reply at war with itself is evidence of
    neither source winning.

    The likely mechanism is generation order. "arm" precedes
    "opening_needed_m" in the base schema, at N0, N-A and N-C, so the arm
    is committed before the opening is written and the reasoning arrives
    too late to change it. N-order reorders the schema and adds no wording,
    and N-D and N-CD put the resting face and the opening ahead of the arm,
    which is what makes this measurable rather than assumed.

    Returns None when there is nothing to compare: no width stated, no arm
    named, or an arm whose limit is not in the state.
    """
    if believed is None or not arm:
        return None
    limit = (limits or {}).get(arm)
    if limit is None:
        return None
    return believed > limit + tol


# Weaker than the arithmetic above and reported as secondary. A model that
# looked at the image and did not say so is indistinguishable here from one
# that never looked, so absence of a mention is not evidence of absence.
_IMAGE_WORDS = ("image", "picture", "photo", "shown", "visible", "appears",
                "looks", "seen", "view")

# A reply can read the picture and never say so. Three gpt replies wrote
# "0.096 m for the mustard bottle lying down" and were filed as text-only
# because the word "image" did not appear, when the stated pose could only
# have come from looking. Pose words are therefore a second route into
# image_referenced.
#
# This still only sharpens a keyword test. width_belief remains the primary
# reading: when the text declares one pose and the reply states the width
# of the other, the picture is the only place that number can come from,
# and that is arithmetic rather than vocabulary.
_POSE_WORDS = ("lying", "lies", "on its side", "standing", "stands",
               "upright", "vertical", "horizontal", "presented width",
               "presents")
_CONFLICT_WORDS = ("disagree", "contradic", "inconsistent", "mismatch",
                   "conflict", "does not match", "doesn't match",
                   "differs from")


def classify_reasoning(why):
    """What the stated justification appeals to. LEGACY ONLY.

    The current schema asks for typed fields and no prose, so a reply from
    it has no "why" block and this returns "none" for every such row. It is
    kept because rescore.py and analyse.py are run over the pre-2026-08-26
    results files, where the prose is the only record of what was said.

    Do not read a "none" column on a current run as a finding. It says the
    schema carries no prose, which was the point of changing it: three
    successive keyword and extractor rules each produced a false finding
    here before being caught.

    'image_referenced' and 'conflict_flagged' are keyword matches over the
    model's own prose, so they are indicative rather than exact, and a
    reply can be both. 'state_only' is the default and means no image,
    pose or conflict language appeared.

    Report width_belief as the primary reading, not this. A reply that
    states the width of the pose the text DENIES can only have got that
    number from the picture, which is arithmetic; a reply that happens not
    to use the word "image" is a fact about its vocabulary.
    """
    if not isinstance(why, dict):
        return "none"
    text = " ".join(str(v) for v in why.values()).lower()
    if not text.strip():
        return "none"
    if any(w in text for w in _CONFLICT_WORDS):
        return "conflict_flagged"
    if any(w in text for w in _IMAGE_WORDS + _POSE_WORDS):
        return "image_referenced"
    return "state_only"


def grade(text, meta, legal_true, legal_declared, limits=None):
    """One reply into one row.

    legal_true and legal_declared are the arms the REAL validator accepts
    for the flip task under each pose, computed by the caller from
    geometry. They are passed in rather than derived here so that grading
    stays a pure function of what was measured.
    """
    row = {"outcome": None, "arm": None, "task_id": None,
           "flagged": flagged(text), "width_belief": None,
           "believed_width_m": None, "why": None, "raw_len": len(text or ""),
           "self_contradicted": None, "reasoning": None,
           # The two typed fields, stored exactly as the model gave them.
           # believed_width_m is the derived reading and may come from the
           # legacy prose on an old row; opening_needed_m is only ever the
           # schema field, so the two can be told apart afterwards.
           "opening_needed_m": None, "resting_face": None}

    decision = parse_reply(text)
    if decision is None:
        row["outcome"] = "unparseable"
        return row

    row["task_id"] = decision.get("task_id")
    row["arm"] = decision.get("arm")
    row["why"] = decision.get("why")
    row["opening_needed_m"] = reported_opening(decision)
    row["resting_face"] = reported_face(decision)
    row["believed_width_m"] = believed_width(decision)
    row["width_belief"] = classify_width(row["believed_width_m"], meta)
    row["reasoning"] = classify_reasoning(row["why"])
    row["self_contradicted"] = self_contradicted(
        row["believed_width_m"], row["arm"], limits)

    if decision.get("task_id") in (-1, None) or decision.get("arm") is None:
        row["outcome"] = "noop"
        return row

    arm = decision["arm"]
    in_true = arm in legal_true
    in_decl = arm in legal_declared

    if in_true and in_decl:
        row["outcome"] = "uninformative"
    elif in_true:
        row["outcome"] = "follows_image"
    elif in_decl:
        row["outcome"] = "follows_state"
    else:
        row["outcome"] = "illegal_both"
    return row


def summarise(rows):
    """Counts per outcome, plus the two observational columns."""
    out = {o: 0 for o in OUTCOMES}
    for r in rows:
        out[r["outcome"]] = out.get(r["outcome"], 0) + 1
    return {
        "n": len(rows),
        "outcomes": out,
        "flagged": sum(1 for r in rows if r["flagged"]),
        "width_belief": {k: sum(1 for r in rows if r["width_belief"] == k)
                         for k in WIDTH_BELIEFS},
        # Reasoning and action coming apart: the stated width matches one
        # source while the arm chosen follows the other.
        "belief_action_mismatch": sum(
            1 for r in rows
            if (r["width_belief"] == "image"
                and r["outcome"] == "follows_state")
            or (r["width_belief"] == "state"
                and r["outcome"] == "follows_image")),
    }


# ---------------------------------------------------------------------------
# Batch grading: one ROUND, not one assignment. LEGACY.
# ---------------------------------------------------------------------------
# No driver calls this any more. The prompt module offers a single shape,
# one task and one arm, so run.py and cue.py grade with grade() above.
# It is kept, and kept harnessed, because it is what scored the batch
# results files and rescoring those has to stay possible.
#
# With a single assignment the model named ur_w in twelve trials out of
# twelve, and ur_w is legal whichever way the bottle lies, so the choice
# said nothing about which source was believed. A round removes the safe
# answer, because ur_w is the only arm that can take EITHER object and it
# cannot take both.
#
# The flip object is the mustard; the partner is the clamp, 0.122 m and
# UR-only in every scene. With ur_w and franka_n idle:
#
#   true LYING     mustard needs ur_w (franka_n cannot at 0.096 m), so the
#                  clamp cannot be served this round
#   true UPRIGHT   franka_n can take the mustard at 0.058 m, freeing ur_w
#                  for the clamp, so both are served
#
# So the ROUND reveals the belief even though either individual choice
# might not.
# image/state only mean something when the text and the picture DISAGREE.
# In a congruent or dims trial there is nothing to disagree with, so those
# are scored for correctness against the one true reading instead. Scoring
# them as image-versus-state, as the first version did, produced labels
# that looked like findings and meant nothing.
ROUND_OUTCOMES = ("round_image", "round_state", "round_partial",
                  "round_illegal", "round_incomplete", "unparseable",
                  "round_correct", "round_wrong")

# The ASSIGNABLE set is the primary reading. A single choice can be
# satisficing: the model picks a sufficient arm and stops. Asked which arms
# COULD serve the task, it has to enumerate, and the true and declared
# poses give different sets, so no answer fits both.
ASSIGNABLE_BELIEFS = ("image", "state", "both", "neither", "missing")


def classify_assignable(listed, legal_true, legal_declared):
    """Which pose the model's assignable set matches."""
    if listed is None:
        return "missing"
    got = {a for a in listed if isinstance(a, str)}
    hit_true = got == set(legal_true)
    hit_decl = got == set(legal_declared)
    if hit_true and hit_decl:
        return "both"
    if hit_true:
        return "image"
    if hit_decl:
        return "state"
    return "neither"


def parse_round(text):
    """The assignments list from a batch reply, or None.

    Accepts a bare object too: a model that answers with one assignment
    instead of a list has not followed the schema, but the reply is not
    malformed and the run should record what it did rather than discard it.
    """
    obj = parse_reply(text)
    if obj is None:
        return None
    if isinstance(obj.get("assignments"), list):
        return obj["assignments"]
    if "task_id" in obj:
        return [obj]
    return None


def grade_round(text, meta, flip_task, partner_task,
                flip_legal_true, flip_legal_declared, partner_legal):
    """Score a whole round.

    flip_legal_true and flip_legal_declared are the arms the REAL validator
    accepts for the FLIP task under each pose. partner_legal is the same for
    the partner, which does not depend on the pose.

    Outcomes:

      round_image      the round is coherent under the TRUE pose and not
                       under the declared one
      round_state      the reverse
      round_partial    coherent under both, so uninformative
      round_illegal    coherent under neither
      round_incomplete a task was omitted entirely, which is a failure to
                       follow the schema rather than a belief
    """
    row = {"outcome": None, "assignments": None, "flagged": flagged(text),
           "width_belief": None, "believed_width_m": None,
           "assignable": None, "assignable_belief": "missing",
           "opening_needed_m": None, "resting_face": None,
           "why": None, "raw_len": len(text or "")}

    items = parse_round(text)
    if items is None:
        row["outcome"] = "unparseable"
        return row

    by_task = {}
    for a in items:
        if isinstance(a, dict) and a.get("task_id") is not None:
            by_task[a["task_id"]] = a
    row["assignments"] = {k: v.get("arm") for k, v in by_task.items()}

    flip = by_task.get(flip_task)
    if flip is not None:
        row["why"] = flip.get("why")
        row["opening_needed_m"] = reported_opening(flip)
        row["resting_face"] = reported_face(flip)
        row["believed_width_m"] = believed_width(flip)
        row["width_belief"] = classify_width(row["believed_width_m"], meta)
        row["reasoning"] = classify_reasoning(row["why"])
        row["assignable"] = flip.get("assignable")
        row["assignable_belief"] = classify_assignable(
            row["assignable"], flip_legal_true, flip_legal_declared)

    # Every queued task must appear, assigned or explicitly left.
    if flip_task not in by_task or partner_task not in by_task:
        row["outcome"] = "round_incomplete"
        return row

    flip_arm = flip.get("arm")
    part_arm = by_task[partner_task].get("arm")

    if flip_arm is not None and flip_arm == part_arm:
        row["outcome"] = "round_illegal"     # one arm, two tasks
        return row

    def both_servable(flip_legal):
        """Could a round serve BOTH tasks under this pose, one arm each."""
        return any(f != p for f in flip_legal for p in partner_legal)

    def coherent(flip_legal):
        """Is this round what a model holding this belief would produce.

        Legality is necessary but not sufficient. If the belief allows both
        tasks to be served, a round that serves only one is evidence
        AGAINST that belief: a model that thinks the bottle is upright can
        give it to franka_n and free ur_w for the clamp, so declining to do
        so says it does not think that. Without this, giving the mustard to
        ur_w and leaving the clamp scored as consistent with both beliefs
        and the round carried no more information than the single choice
        it replaced.
        """
        if flip_arm is not None and flip_arm not in flip_legal:
            return False
        if part_arm is not None and part_arm not in partner_legal:
            return False
        served = (flip_arm is not None) + (part_arm is not None)
        if both_servable(flip_legal) and served < 2:
            return False
        # Leaving a task unassigned is only coherent if nothing free could
        # have taken it once the other assignment is made.
        if flip_arm is None and (flip_legal - {part_arm}):
            return False
        if part_arm is None and (partner_legal - {flip_arm}):
            return False
        return True

    ok_true = coherent(flip_legal_true)
    ok_decl = coherent(flip_legal_declared)

    if meta.get("condition") != "conflict":
        # Nothing to disagree with: score correctness, not allegiance.
        row["outcome"] = "round_correct" if ok_true else "round_wrong"
        return row

    if ok_true and ok_decl:
        row["outcome"] = "round_partial"
    elif ok_true:
        row["outcome"] = "round_image"
    elif ok_decl:
        row["outcome"] = "round_state"
    else:
        row["outcome"] = "round_illegal"
    return row


def summarise_rounds(rows):
    out = {o: 0 for o in ROUND_OUTCOMES}
    for r in rows:
        out[r["outcome"]] = out.get(r["outcome"], 0) + 1
    return {
        "n": len(rows),
        "outcomes": out,
        "flagged": sum(1 for r in rows if r["flagged"]),
        "width_belief": {k: sum(1 for r in rows if r["width_belief"] == k)
                         for k in WIDTH_BELIEFS},
        "assignable_belief": {
            k: sum(1 for r in rows if r.get("assignable_belief") == k)
            for k in ASSIGNABLE_BELIEFS},
    }