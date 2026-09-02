"""EX1 v2: the information ladder, rebuilt on Experiment 2's base.

WHY A SECOND MODULE RATHER THAN AN EDIT.

experiments/ex1/prompts.py renders the prompts every published Experiment 1
number was measured under. Editing it would move those numbers without
moving the files they were computed from, so the v1 module is left exactly
as it is and this one sits beside it. Nothing imports both: a run declares
its design once, at the call site, and the design is recorded on every row.

WHAT CHANGED, AND WHAT EACH CHANGE BUYS.

  ONE TASK AT A TIME. The states are harvested from a SERIALISED cell (see
        Coordinator(serialised=True)), so every arm is idle at every
        decision and the allocator is offered one named task. Both arm
        types are therefore available at almost every state, so the
        gripper opening can bind far more often than the 96 of 162 states
        it bound on the v1 set, and a rejection can only ever be about the
        arm. This module does not create that property; it assumes it, and
        assert_states_are_serialised below refuses a set that does not have
        it.

  RULES SEPARATED PER CONSTRAINT. The v1 base cross-referenced its own
        rules, which is why its No Rules cell had to withhold R3 and R4 as
        a pair. Here each constraint is its own numbered rule with its own
        text and no cross-reference, so the ablation can withhold one at a
        time: the gripper opening alone, the load alone, delicate handling
        alone, reach alone.

  FIELD NAMES ALIGNED WITH EXPERIMENT 2. The two chapters described the
        same physical quantity with two different words, which hid the
        fact that they are one experiment on one constraint. The aliases
        are IMPORTED from experiments/ex2/prompts.py rather than copied, so
        the two cannot drift; see FIELD_ALIASES below for the one entry
        that is deliberately dropped and why.

  THE WAITING RULE RE-SCOPED, NOT REMOVED. Correct refusal is an endpoint:
        it is measured on the states where no arm can take the queued task,
        and if the prompt never says declining is permitted then a refusal
        is disobedience rather than a judgement. What no longer applies is
        the CONGESTION clause. With one task at a time and every arm idle,
        "a better-suited arm will free up soon" is never true, so the
        sentence becomes vacuous and would invite waiting on nothing. G2
        keeps the licence and drops the clause.

  CONGESTION LANGUAGE REMOVED. Zone locks, zone occupancy and the declared
        "regions" all describe a cell where two arms compete, and no two
        arms ever work at once here. They are dropped from the cell
        description, trimmed from the rendered state and dropped from the
        answer schema. This also retires the failure mode measured on
        2026-08-16: with the zone machinery present but demoted to a
        preference, removing that demotion made GPT wait on zone locks in
        19 percent of picking states. Nothing is demoted here because
        nothing is stated.

WHAT DID NOT CHANGE, AND MUST NOT.

  NO DIMENSIONS FIELD. Experiment 2 states object size as
        "size_upright_m" and that field opens a derivation route: the
        opening follows from the extents by text alone. Experiment 1 has
        no dimensions field, so it inherits no such problem, and it must
        not acquire one. If a dimensions field were added here, Experiment
        1 would stop being a study of retrieval and become a second study
        of derivation. FIELD_ALIASES drops the dims entry for that reason
        and assert_no_dimensions_route checks the rendered prompt.

  BINDING CAUSE IS FIXED BEFORE ANY MODEL CALL. Unchanged. It is what
        makes restricting the endpoint to grasp-binding states a
        restriction on the state rather than a selection on the outcome.

  THE NEGATIVE CONTROL. States where the opening binds nothing, at 100
        percent legality, are what localise the width effect to the
        opening. Five of the eleven objects are 0.080 m or narrower, so
        the opening can never bind on them. Selection must hold a declared
        floor of such states rather than filter them out; that floor lives
        in analysis/build_ex1_set_v2.py, not here.

THE TWO AXES.

  CONDITIONS say what the STATE carries and which rules are stated. They
        are the redesign's condition set: full, nowidth, anon,
        nowidth-anon, swap, nowidth-swap, givenset, and one norules cell
        per constraint.

  DIRECTIVES are prompt-only sentences added at one anchor, in Experiment
        2's sense: none, recall, report, elicit. They are the treatments.
        A directive is orthogonal to a condition, so the pair names the
        cell, and the two are recorded separately on every row.

READ report AND elicit AS A PAIR. The reported opening is what makes the
null at nowidth a measurement rather than an absence, and the two rungs
separate two different things: report asks the model to STATE the opening
before naming an arm, and elicit additionally asks it to CHOOSE the arm to
fit the opening it gave. So elicit minus report is the instruction to use
the number, and report minus the plain cell is the cost of being asked for
it at all. Experiment 2 keeps the opening in its schema at every rung and
buys the same separation with N-order; Experiment 1 cannot, because naming
the opening in the schema of every cell would put a quantity into the
prompt of the very cells that withhold it.

WHAT THIS MODULE DOES NOT DO.

The state edits. Withholding the opening, anonymising names and swapping
them are STATE edits and live in analysis/probe_replay.py's state_at_rung,
which reads the condition table here. This module owns the condition
table, the rule text, the directives and the rendering, so there is one
place that answers "what is nowidth-anon".

The knowledge probe is not a condition and is not here. It asks each model
the opening each object needs, outside the allocation task, and lives in
experiments/ex1/knowledge_probe.py.

VERSION HISTORY.

  2026-09-02a  first build of the v2 design. Serialised cell, Experiment 2
               aliases, seven separated rules, per-constraint norules
               cells, the re-scoped waiting rule, and the recall, report
               and elicit directives.
"""

import json

from core.cell import cell_config as C
from experiments.ex2 import prompts as EX2P

# Bumped on ANY change to the text below. Recorded on every row, because
# the base PROMPT_VERSION does not identify a prompt this module builds
# from scratch rather than substitutes into.
EX1_V2_PROMPT_VERSION = "2026-09-02a"

DESIGN = "v2"


# ---------------------------------------------------------------------------
# 1. Field aliases
# ---------------------------------------------------------------------------
# Imported, not copied. Experiment 2 already renamed these so that each
# field says what it is and which way its comparison runs:
#
#     object                  arm
#     opening_needed_m        opening_max_m
#     mass_kg                 max_load_kg
#     delicate                handles_delicate
#     position                arms_that_can_reach
#
# dims_m -> size_upright_m is DROPPED, and this is the one rename that
# carries a hidden decision. In Experiment 2 that field, glossed "measured
# standing on its smallest face", turned out to name one of its two
# conditions. Experiment 1 has no dimensions in its state, so it inherits
# no such problem. Keeping the alias would invite one to be added.
#
# pose -> resting_face is dropped for the same reason: no Experiment 1
# object states a pose, and an alias for a field that is never present can
# only ever be used by adding the field.
_EX1_DROPPED_ALIASES = ("dims_m", "pose")

FIELD_ALIASES = {k: v for k, v in EX2P.FIELD_ALIASES.items()
                 if k not in _EX1_DROPPED_ALIASES}

# The display names of the fields the ladder manipulates, so nothing has to
# spell them again.
OPENING_FIELD = FIELD_ALIASES["grasp_m"]            # opening_needed_m
OPENING_MAX_FIELD = FIELD_ALIASES["max_grasp_m"]    # opening_max_m
LOAD_FIELD = FIELD_ALIASES["payload_kg"]            # max_load_kg
DELICATE_FIELD = FIELD_ALIASES["delicate_ok"]       # handles_delicate
REACH_FIELD = FIELD_ALIASES["reach_ok_arms"]        # arms_that_can_reach

# Blocks the serialised cell cannot produce or the model cannot use. The
# list is Experiment 2's, unchanged, and each entry earns its place here for
# its own reason.
#
#   zone_locks, zone_inbound   THE CONGESTION LANGUAGE. With one task at a
#         time no arm ever holds a zone against another, so a lock is
#         either empty or names the arm about to be chosen. Leaving them in
#         would invite waiting on a constraint that cannot bind, which is
#         the failure measured on 2026-08-16 and recorded in the v1 module.
#
#   exchange_pads   The model does not choose pads: R7 says the cell
#         arranges any handover itself. A table of pad coordinates it
#         cannot act on is a thousand characters of noise, and the "at_pad"
#         field plus R7 carry everything a state with a parked object
#         needs.
#
#   recent_events, metrics, tasks_completed, tasks_failed   History of a
#         run that, serialised, contains one finished task per decision.
#         Nothing in the rules reads them.
#
# The per-object "zone" label STAYS. It is a position descriptor rather
# than a congestion signal, and dropping it would be one more edit to the
# state than the redesign calls for.
TRIM_STATE_KEYS = ("exchange_pads", "zone_locks", "zone_inbound",
                   "recent_events", "metrics", "tasks_completed",
                   "tasks_failed")


# ---------------------------------------------------------------------------
# 2. The base prompt
# ---------------------------------------------------------------------------
# THE CELL is the deployed description minus the congestion sentence and
# minus the zone vocabulary. Nothing was added: no bounding-box convention
# and no grasp-direction sentence, because both are steps on the road to
# deriving an opening from a shape, and Experiment 1 asks whether the
# opening is RETRIEVED. A sentence that helps a model derive one would
# answer the question in the prompt.

IMAGE_LINE = ("\nAn overhead image of the cell is given: its top edge is "
              "north (+y)\nand its right edge is east (+x).")

BASE_PROMPT = """You are the task allocator for a four-arm robotic cell. Each time you are
asked, choose ONE queued task and ONE idle arm, or choose to wait.

THE CELL
A {tx} x {ty} m table, origin at its centre, x east, y north. Two UR10 arms sit
mid-table on the west and east edges, two Franka arms on the south and north
edges, all facing inward. The cell runs one task at a time, so every arm that
is not disabled is idle when you are asked.{image_line}

WHAT THE STATE TELLS YOU
Each arm states the widest its gripper opens, "{opening_max}", the heaviest
object it can carry, "{load}", and whether it is cleared for delicate
handling, "{delicate}".

{object_fields}

HARD RULES. A proposal that breaks any of these is rejected.

{r1}
{r2}
{r3}
{r4}
{r5}
{r6}
{r7}
GUIDANCE. Not enforced, but this is what a good allocation does.

G1  Prefer a Franka arm for sorting tasks.
G2  Declining is a choice. If no arm can handle this object, decline rather
    than naming one that cannot.
G3  Sort correctly: send each object to the basket named for its "category",
    so that objects of the same kind end up together.
{directive}
YOUR ANSWER
{schema}
"""

# G1 IS EXPERIMENT 2's, VERBATIM, AND IT IS WHAT MAKES A SINGLE CHOICE
# INFORMATIVE. With every arm idle and no competition, naming a UR is
# always safe, so a model that never reasons about the opening would score
# full marks by always naming a UR and the endpoint would measure nothing.
# The preference pulls toward the narrow gripper, so the opening has to be
# checked to overrule it. It states a preference and never a capability
# check: "prefer a Franka unless it cannot handle the object" would state
# the rule under measurement.
#
# G3 IS AN ADDITION to the redesign's two-line guidance block, and it is
# not decoration. The basket choice is a scored endpoint (basket_correct),
# the validator deliberately does not check it, and with no instruction to
# sort by category the measure would become a preference test. It is kept
# in GUIDANCE and not in a rule because naming a wrong-category basket is
# not rejected, and listing it under "a proposal that breaks any of these
# is rejected" would be false.


# ---------------------------------------------------------------------------
# 3. The rules, one per constraint
# ---------------------------------------------------------------------------
# Each rule is a complete statement that names its own fields and refers to
# no other rule, with one exception noted at R6. That is the whole point of
# the rewrite: a rule that cited another could not be withheld alone,
# because withholding it would leave the citation dangling, and that was
# the defect that forced v1 to withhold two rules as a pair.

R1 = """R1  Task availability
    Assign only a task whose status is "queued". A task marked
    "in_progress" or "waiting_on_..." is already being handled.
"""

R2 = """R2  Arm availability
    Assign only an arm from the idle list. A disabled arm is never
    available, and its body still blocks the space where it froze.
"""

R3 = """R3  Gripper opening
    The gripper must open wide enough for the object. The arm is capable
    only when its "{opening_max}" is at least the object's "{opening}".
"""

R4 = """R4  Load
    The arm is capable only when its "{load}" is at least the object's
    "mass_kg".
"""

R5 = """R5  Delicate handling
    An object marked "delicate" may go only to an arm whose
    "{delicate}" is true.
"""

# THE ONE CROSS-REFERENCE, AND WHY IT STAYS. The final sentence is R4's
# scope statement from the v1 base, carried over unchanged in substance.
# It is not a capability instruction: it tells the model what lies OUTSIDE
# its job. Dropping it would make the reach ablation differ from the full
# cell in two ways at once, no reach rule AND no assurance about
# destinations, and a model that then started weighing destination reach
# would look like a model that had stopped checking reach. It points at R7,
# which is never withheld, so the reference always resolves.
R6 = """R6  Reach
    The arm must appear in the object's "{reach}" list. That
    list is authoritative, so use it rather than working reach out from
    coordinates. Reaching is not the same as handling: an arm can often
    reach an object it cannot pick up. Reaching the destination is not
    required of you; see R7.
"""

# R7 CARRIES THE DELIVERY MATERIAL. In the v1 base this was spread over two
# rules, one saying the cell arranges handovers and one saying an object
# already on an exchange point goes straight to its basket. Neither is a
# capability check and neither is ever withheld, so they belong together
# under the rule that owns the destination. Folding them in is what lets
# the seven rules be seven constraints.
R7 = """R7  Destination
    A task whose "dest_xy" is null has no destination yet: name one in
    "basket". You do not arrange delivery. If the arm you name cannot reach
    the destination, the cell hands the object over to a second arm itself,
    and your proposal is legal only when such a route exists; if none does,
    name a different arm or decline. An object whose "at_pad" names an
    exchange point has already been handed over and goes straight to its
    destination now.
"""

# --- the withheld forms ----------------------------------------------------
#
# NEUTRALISED, NOT DELETED. The rule count, the numbering and the section
# structure stay identical to the full cell, so the rule CONTENT is the
# only difference and a behaviour change is attributable to it. Deleting a
# rule would renumber the rest and change the shape of the page.
#
# Each withheld text says a check EXISTS and does not say what it is.
# Saying nothing would let the model conclude no check applies, which is a
# different manipulation. Saying "work it out from the numbers" would
# reinstate the instruction the cell exists to remove. And none of them
# names a state field: naming one would leave the instruction standing
# under a withheld label.
#
# THE HEADERS STAY. "R5  Delicate handling" names the constraint while its
# body withholds the check, and that is the intended manipulation: a
# per-constraint ablation is only readable if the model knows WHICH check
# it was not given. The v1 withheld text said as much in its body already
# ("the cell checks that the arm you name can handle the object"), so the
# header adds nothing the body did not.

R3_WITHHELD = """R3  Gripper opening
    The cell checks that the arm you name can open wide enough for the
    object. That check is not stated here.
"""

R4_WITHHELD = """R4  Load
    The cell checks that the arm you name can carry the object. That check
    is not stated here.
"""

R5_WITHHELD = """R5  Delicate handling
    The cell checks that the arm you name may handle this object. That
    check is not stated here.
"""

R6_WITHHELD = """R6  Reach
    The cell checks that the arm you name can reach the object. That check
    is not stated here. Reaching the destination is not required of you;
    see R7.
"""

# --- the withheld-DATA form of R3 ------------------------------------------
#
# A DELIBERATE DEPARTURE FROM v1, AND THE ONE PLACE THE TWO DESIGNS ASK A
# DIFFERENT QUESTION. In v1 the nowidth cells left R3 naming "grasp_m", a
# field the state no longer carried, and its note called that the
# manipulation itself: the model is told which quantity it must supply and
# is not given it.
#
# Experiment 2 does the opposite in the same situation. Its R3 is
# substituted so the rule never points at a field the state does not carry,
# on the argument that a model reading a rule which names a missing field
# could reasonably conclude the rule is inapplicable, and that a
# rule-reading failure would then be scored as a retrieval failure.
#
# v2 follows Experiment 2, because the two chapters are meant to be read as
# one argument and this is the exact sentence the comparison runs through.
# The v1 form is kept below as data so the choice is a call-site change and
# not a rewrite, and so that anyone who prefers it can run the other cell
# and report both.
R3_NO_OPENING = """R3  Gripper opening
    The gripper must open wide enough for the object. The arm is capable
    only when its "{opening_max}" is at least the opening the object needs.
    That opening is not stated.
"""

R3_NO_OPENING_V1_STYLE = R3      # names the withdrawn field, as v1 did

# --- the resolved-set form -------------------------------------------------
#
# givenset hands the legal set over instead of asking for it. Every header
# stays and R4 to R6 point at R3, which is the one place the resolved list
# is described. The alternative, four repetitions of the same paragraph,
# would change how much of the page each constraint occupies and make the
# cell differ from the full one in layout as well as in content.

R3_ELIGIBLE = """R3  Gripper opening
    The task's "eligible_arms" list is authoritative and final. It already
    applies this check, R4, R5 and R6, and the existence of a delivery
    route. Do not re-derive it from the numbers. An EMPTY list means no arm
    can take this task now, so decline.
"""

R4_ELIGIBLE = """R4  Load
    Settled by "eligible_arms"; see R3.
"""

R5_ELIGIBLE = """R5  Delicate handling
    Settled by "eligible_arms"; see R3.
"""

R6_ELIGIBLE = """R6  Reach
    Settled by "eligible_arms"; see R3. Reaching the destination is not
    required of you; see R7.
"""


# ---------------------------------------------------------------------------
# 4. The glossary
# ---------------------------------------------------------------------------
# The object field list names exactly the fields the state carries, per
# condition. A prompt that promises a field and then retracts it, or that
# leaves a rendered field unglossed, makes the model solve a comprehension
# puzzle rather than the question under test. assert_glossary_matches_state
# checks both directions on every condition.

_OBJECT_FIELDS_FULL = """Each object states the opening it needs from a gripper,
"{opening}", its mass, "mass_kg", whether it is "delicate", and the arms
that can reach it, "{reach}"."""

_OBJECT_FIELDS_NO_OPENING = """Each object states its mass, "mass_kg", whether it is "delicate", and the
arms that can reach it, "{reach}". No opening is given."""

# givenset adds one field, on the TASK rather than on the object, so the
# glossary gains a sentence rather than losing one.
_ELIGIBLE_SENTENCE = """
Each queued task also states "eligible_arms", the arms that may take it."""


# ---------------------------------------------------------------------------
# 5. Conditions
# ---------------------------------------------------------------------------
# Each flag means the information is PRESENT, matching the v1 table so that
# analysis code reading one can read the other.
#
#   declared_width  the object's opening is rendered into the state
#   names           object names are real rather than aliased
#   eligible        each task carries a resolved eligible_arms list
#   mislabel        names are present but swapped across the Franka aperture
#   withhold_rule   which single rule is neutralised, or None
#
# THE v1 NAMES ARE KEPT AS ALIASES. Run files, tables and the thesis all
# name the v1 rungs, and a rename would break the trail from a published
# number to the data behind it. CONDITION_ALIASES below maps them, so
# --rung L3 resolves to full and records "full".

CONDITIONS = {
    # The baseline. Everything supplied.
    "full": {"declared_width": True, "names": True, "eligible": False,
             "mislabel": False, "withhold_rule": None},

    # The declared opening withheld. The primary manipulation: the model
    # must supply an opening it was not given, and the routes left are the
    # object's name and, under condition V, the image.
    "nowidth": {"declared_width": False, "names": True, "eligible": False,
                "mislabel": False, "withhold_rule": None},

    # Identity removed, opening present. The control for anonymisation
    # itself: if this matches full, anonymisation is inert and the reading
    # that it costs a few points on its own is closed.
    "anon": {"declared_width": True, "names": False, "eligible": False,
             "mislabel": False, "withhold_rule": None},

    # Both routes closed. The memorisation probe the chapter rests on.
    "nowidth-anon": {"declared_width": False, "names": False,
                     "eligible": False, "mislabel": False,
                     "withhold_rule": None},

    # Identity falsified, opening present. Anonymisation can only produce a
    # null, which is consistent both with the name being unused and with it
    # being used and the loss absorbed elsewhere. A swap asks the question
    # directionally: following the number is evidence the name is inert,
    # following the name is identity retrieval.
    "swap": {"declared_width": True, "names": True, "eligible": False,
             "mislabel": True, "withhold_rule": None},

    # Identity falsified, opening absent.
    "nowidth-swap": {"declared_width": False, "names": True,
                     "eligible": False, "mislabel": True,
                     "withhold_rule": None},

    # The eligible set supplied. Reported as a TREATMENT and not only as an
    # obedience bound: it is the cell that says what the model does when
    # the answer is handed to it, which is what makes a shortfall anywhere
    # else attributable to the reasoning rather than to the format.
    "givenset": {"declared_width": True, "names": True, "eligible": True,
                 "mislabel": False, "withhold_rule": None},

    # THE RULE ABLATION, ONE CONSTRAINT AT A TIME. v1 could only withhold
    # the capability rule and the reach rule together, because the base
    # cross-referenced them. All data is present in every one of these:
    # what is removed is the instruction, never the number.
    "norules-opening": {"declared_width": True, "names": True,
                        "eligible": False, "mislabel": False,
                        "withhold_rule": "R3"},
    "norules-load": {"declared_width": True, "names": True,
                     "eligible": False, "mislabel": False,
                     "withhold_rule": "R4"},
    "norules-delicate": {"declared_width": True, "names": True,
                         "eligible": False, "mislabel": False,
                         "withhold_rule": "R5"},
    "norules-reach": {"declared_width": True, "names": True,
                      "eligible": False, "mislabel": False,
                      "withhold_rule": "R6"},
}

# v1 rung name -> v2 condition name. One-way: a v2 run records the v2 name.
# "L2" maps to the opening ablation because that is the constraint the
# chapter reads, and because a v1 L2 result is NOT comparable to any single
# v2 cell: it withheld two rules at once. The alias exists so a command
# line typed from memory resolves, not so the two can be pooled.
CONDITION_ALIASES = {
    "L3": "full",
    "L3-nowidth": "nowidth",
    "L3-anon": "anon",
    "L1-nowidth": "nowidth-anon",
    "L3-swap": "swap",
    "L1-swap": "nowidth-swap",
    "L4": "givenset",
    "L2": "norules-opening",
}

# The data spine, in order. Each step removes exactly one kind of
# information; assert_spine_is_one_removal pins that.
SPINE = ("full", "nowidth", "nowidth-anon")

# The two removals crossed.
FACTORIAL = {(True, True): "full", (False, True): "nowidth",
             (True, False): "anon", (False, False): "nowidth-anon"}

# The rule ablation, one cell per constraint.
RULE_CELLS = ("norules-opening", "norules-load", "norules-delicate",
              "norules-reach")


def condition_spec(condition):
    """What this condition supplies. Raises on an unknown name.

    Never defaults. A condition that quietly fell back to full would report
    a full result under another label and nothing in the output would show
    it.
    """
    name = CONDITION_ALIASES.get(condition, condition)
    if name not in CONDITIONS:
        raise ValueError(
            f"unknown EX1 v2 condition {condition!r}; expected one of "
            f"{sorted(CONDITIONS)} (or a v1 alias: "
            f"{sorted(CONDITION_ALIASES)}). Conditions are never defaulted: "
            f"a result recorded under the wrong label would be invisible in "
            f"the output.")
    return dict(CONDITIONS[name])


def canonical(condition):
    """The v2 name for a condition given by either name."""
    name = CONDITION_ALIASES.get(condition, condition)
    if name not in CONDITIONS:
        condition_spec(condition)        # raises with the full message
    return name


# ---------------------------------------------------------------------------
# 6. Directives
# ---------------------------------------------------------------------------
# One block, inserted at one anchor, exactly as Experiment 2 inserts its
# factors. A directive names a source or fixes an order; none of them
# supplies a number, and none names an object.

# THE TREATMENT FOR THE RECALL ROUTE, and the analogue of Experiment 2's
# X-image. It names the source to use and says nothing about which opening
# any object needs. Without it "no instruction repairs a retrieval failure"
# is an assertion: one instruction has to have been tried and failed.
RECALL_DIRECTIVE = """
You may use what you already know about an object of this kind to judge the
opening it needs.
"""

# Requires the report and fixes its position, and says nothing about where
# the number should come from. Paired with the elicitation below, it is what
# makes the elicitation attributable: the two differ by the instruction to
# CHOOSE the arm to fit the reported number.
REPORT_DIRECTIVE = """
Give "{opening}" BEFORE naming an arm.
"""

ELICIT_DIRECTIVE = """
Give "{opening}" BEFORE naming an arm, and choose the arm
to fit the opening you gave.
"""

DIRECTIVES = {
    "none":   {"text": "", "schema": "base", "factors": ()},
    "recall": {"text": RECALL_DIRECTIVE, "schema": "base",
               "factors": ("recall",)},
    "report": {"text": REPORT_DIRECTIVE, "schema": "opening_first",
               "factors": ("report",)},
    "elicit": {"text": ELICIT_DIRECTIVE, "schema": "opening_first",
               "factors": ("report", "elicitation")},
}

# A directive that asks for the opening is INCOHERENT where the state
# supplies it: "give the opening before naming an arm" is a copy
# instruction there, not an elicitation, and the number it produces would
# not be a judgement. The treatments therefore run on the cells where the
# opening is withheld, and system_prompt refuses the rest rather than
# rendering a cell that cannot be read.
_OPENING_ASKED = ("report", "elicit")


def directive_spec(directive):
    """What this directive adds. Raises on an unknown name."""
    if directive not in DIRECTIVES:
        raise ValueError(
            f"unknown directive {directive!r}; expected one of "
            f"{sorted(DIRECTIVES)}. Never defaulted: a recall result "
            f"recorded as a plain one would be invisible in the output.")
    return dict(DIRECTIVES[directive])


# ---------------------------------------------------------------------------
# 7. The answer schema
# ---------------------------------------------------------------------------
# "regions" is GONE. It declared the zones an assignment would occupy, and
# with one task at a time no zone is ever contended, so the field asked the
# model to restate two values it had just been shown. "via_pad" went in the
# 2026-08-01 base already: the cell routes handovers itself.
#
# The reason is KEPT and required on a decline. Correct refusal is an
# endpoint, and a decline with no reason cannot be told from a decline the
# model could not justify.

_SCHEMA_TAIL = """To wait, answer task_id -1 with arm null.
Always give a reason, for a wait too: say what you are waiting for."""

_OPENING_TAIL = """"{opening}" is the opening you judge the object needs, in metres, as a
number with three decimals. If you wait because you cannot judge it, give
null."""

SCHEMAS = {
    # Every cell with no reporting directive. Arm first, nothing else asked.
    "base": "\n".join([
        "Answer ONLY with JSON, no prose:",
        '{{"task_id": <int>,',
        '  "arm": "<arm name>",',
        '  "basket": "<basket name>",',
        '  "reason": "<one short sentence>"',
        "}}",
        _SCHEMA_TAIL,
    ]),
    # report and elicit. The opening is committed before the arm is named.
    "opening_first": "\n".join([
        "Answer ONLY with JSON, no prose, with the fields in this order:",
        '{{"task_id": <int>,',
        '  "{opening}": <number>,',
        '  "arm": "<arm name>",',
        '  "basket": "<basket name>",',
        '  "reason": "<one short sentence>"',
        "}}",
        _SCHEMA_TAIL,
        _OPENING_TAIL,
    ]),
}


# ---------------------------------------------------------------------------
# 8. Assembly
# ---------------------------------------------------------------------------

def _fields():
    """The field names every template interpolates."""
    return {"opening": OPENING_FIELD, "opening_max": OPENING_MAX_FIELD,
            "load": LOAD_FIELD, "delicate": DELICATE_FIELD,
            "reach": REACH_FIELD}


def _rules(spec):
    """The seven rule blocks for one condition, in order.

    Selection is table-driven rather than a chain of branches, so a new
    condition cannot add a rule variant without adding it here, and the
    number of blocks is seven whatever the condition.
    """
    f = _fields()
    withheld = spec["withhold_rule"]
    if spec["eligible"]:
        r3, r4, r5, r6 = (R3_ELIGIBLE, R4_ELIGIBLE, R5_ELIGIBLE, R6_ELIGIBLE)
    else:
        r3 = R3 if spec["declared_width"] else R3_NO_OPENING
        r4, r5, r6 = R4, R5, R6
    blocks = {"R1": R1, "R2": R2, "R3": r3, "R4": r4, "R5": r5, "R6": r6,
              "R7": R7}
    if withheld is not None:
        blocks[withheld] = {"R3": R3_WITHHELD, "R4": R4_WITHHELD,
                            "R5": R5_WITHHELD,
                            "R6": R6_WITHHELD}[withheld]
    return {k.lower(): v.format(**f) for k, v in blocks.items()}


def _object_fields(spec):
    """The glossary for one condition."""
    text = (_OBJECT_FIELDS_FULL if spec["declared_width"]
            else _OBJECT_FIELDS_NO_OPENING)
    text = text.format(**_fields())
    if spec["eligible"]:
        text += _ELIGIBLE_SENTENCE
    return text


def schema_text(name):
    return SCHEMAS[name].format(**_fields())


def system_prompt(condition, directive="none", has_image=False):
    """The system prompt for one cell of the design."""
    spec = condition_spec(condition)
    dspec = directive_spec(directive)
    if directive in _OPENING_ASKED and spec["declared_width"]:
        raise ValueError(
            f"directive {directive!r} asks for the opening and condition "
            f"{condition!r} states it. Reporting a number the state just "
            f"supplied is a copy instruction, not an elicitation, so the "
            f"cell is refused rather than rendered under a label that "
            f"claims otherwise.")
    return BASE_PROMPT.format(
        tx=C.TABLE_TOP[0], ty=C.TABLE_TOP[1],
        image_line=IMAGE_LINE if has_image else "",
        object_fields=_object_fields(spec),
        directive=dspec["text"].format(**_fields()),
        schema=schema_text(dspec["schema"]),
        **_fields(), **_rules(spec))


# ---------------------------------------------------------------------------
# 9. State rendering
# ---------------------------------------------------------------------------
# Aliasing, trimming and fixed-width decimals all come from Experiment 2's
# module rather than being written again, so the two chapters render the
# same state the same way by construction. Only the trim list and the
# withheld set are Experiment 1's own.


def apply_aliases(value):
    """Rename fields for display, using EX1's subset of EX2's table."""
    if isinstance(value, dict):
        return {FIELD_ALIASES.get(k, k): apply_aliases(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [apply_aliases(v) for v in value]
    return value


def trim_state(state):
    """A copy with the blocks a serialised cell cannot use removed."""
    import copy as _copy
    out = _copy.deepcopy(state)
    for key in TRIM_STATE_KEYS:
        out.pop(key, None)
    return out


def render_state(state, condition):
    """The user-message text: trimmed, aliased, fixed-width.

    THE OPENING IS NOT WITHHELD HERE. Unlike Experiment 2, whose conditions
    are prompt-side, Experiment 1's withholding is a STATE edit and has
    already happened in analysis/probe_replay.py's state_at_rung by the
    time this is called. Doing it twice would work and would put the
    definition of a condition in two places, which is how a state edit and
    a prompt edit come to disagree. assert_state_matches_condition checks
    that the state arriving here is the one the condition calls for.
    """
    spec = condition_spec(condition)
    assert_state_matches_condition(state, condition)
    body = apply_aliases(trim_state(state))
    idle = [a["name"] for a in state["arms"]
            if a["state"] == "IDLE" and not a["disabled"]]
    ask = ("\nIdle arms right now: " + (", ".join(idle) or "none") +
           ".\nAssign the queued task to ONE of these idle arms, or answer "
           "task_id -1 if none can take it now.")
    if spec["eligible"]:
        pass                    # the glossary already names eligible_arms
    return EX2P.unmark_decimals(
        "Cell state:\n" + json.dumps(EX2P.mark_decimals(body), indent=1) + ask)


def build_ex1_prompt(state, condition, directive="none", image_b64=None,
                     mapping=None):
    """Messages for one EX1 v2 trial.

    The state passed in must ALREADY carry the state-level edits for this
    condition: the opening present or absent, names real, aliased or
    swapped, eligible_arms present or absent. state_at_rung does that work.
    This function applies the PROMPT-level part and nothing else, so the
    rule stays that the state is what the model is SHOWN and the prompt is
    what it is TOLD.
    """
    spec = condition_spec(condition)
    if not spec["names"]:
        if mapping is None:
            raise ValueError(
                f"condition {condition!r} is anonymised and no alias mapping "
                f"was given, so nothing can confirm the state was anonymised "
                f"at all. Rendering it would put real object names in the "
                f"prompt under an anonymised label.")
    elif mapping is not None:
        raise ValueError(
            f"condition {condition!r} keeps object names but an alias "
            f"mapping was given. One of the two is wrong and guessing which "
            f"would mislabel the trial.")

    content = [{"type": "text", "text": render_state(state, condition)}]
    if image_b64 is not None:
        content = [{"type": "image_url",
                    "image_url":
                        {"url": f"data:image/png;base64,{image_b64}"}}
                   ] + content
    messages = [
        {"role": "system",
         "content": system_prompt(condition, directive,
                                  has_image=image_b64 is not None)},
        {"role": "user", "content": content},
    ]
    if not spec["names"]:
        from experiments.ex1 import anonymise as A
        A.assert_clean(messages, mapping)
    return messages


# ---------------------------------------------------------------------------
# 10. Violation attribution
# ---------------------------------------------------------------------------
# The validator emits one code per rejection and its codes were numbered
# for the v1 base, where one CAPABILITY code covered three constraints.
# Separating the rules is worth nothing unless a rejection can be filed
# against the rule that was actually broken, so the split is done here,
# through the same decomposition analysis/probe_store.py uses.

VIOLATION_RULE = {
    "PARSE": None,
    "TASK_UNKNOWN": "R1", "TASK_FINISHED": "R1", "TASK_BUSY": "R1",
    "ARM_UNKNOWN": "R2", "ARM_NOT_IDLE": "R2",
    # CAPABILITY is resolved per cause; see violation_rule below.
    "CAPABILITY": None,
    "REACH_OBJECT": "R6",
    "NO_ROUTE": "R7",
    "NO_BASKETS": "R7", "BASKET_MISSING": "R7",
}

CAUSE_RULE = {"grasp": "R3", "payload": "R4", "delicate": "R5"}


def violation_rule(code, cause=None):
    """The v2 rule a rejection breaks, or None if it maps to no rule.

    `cause` is the capability sub-cause from probe_store.capability_cause.
    A CAPABILITY rejection with no cause is a real disagreement between the
    validator and the decomposition, so it returns None rather than
    guessing, and the caller reports it.
    """
    if code == "CAPABILITY":
        return CAUSE_RULE.get(cause)
    return VIOLATION_RULE.get(code)


# ---------------------------------------------------------------------------
# 11. Verification
# ---------------------------------------------------------------------------
# Every check here runs with no model calls and no probe set, except the
# two that take a state. They are what the harness calls.

_ANCHOR = "\nYOUR ANSWER"

_STATE_FIELD_NAMES = ("grasp_m", "max_grasp_m", "payload_kg", "delicate_ok",
                      "reach_ok_arms")


def assert_no_dimensions_route(condition="full", directive="none"):
    """No cell of the design states a size, an extent or a face.

    The single most consequential thing Experiment 1 must NOT acquire. A
    dimensions field, or a sentence describing how an opening follows from
    a shape, opens the derivation route and turns this chapter into a
    second study of Experiment 2's question.
    """
    text = system_prompt(condition, directive).lower()
    for phrase in ("size_upright", "resting_face", "smallest face",
                   "horizontal extent", "smaller of", "bounding box",
                   "the box that encloses", "dims_m", "height, width"):
        if phrase in text:
            raise ValueError(
                f"the {condition}/{directive} prompt contains {phrase!r}, "
                f"which opens a route from an object's shape to the opening "
                f"it needs. Experiment 1 measures retrieval and must state "
                f"no such route.")
    return True


def assert_glossary_matches_state(condition):
    """The glossary names exactly the fields the state carries.

    Both directions. A promise the state does not keep, and a rendered
    field left unglossed, each make the model solve a comprehension puzzle
    rather than the question under test.
    """
    spec = condition_spec(condition)
    text = system_prompt(condition)
    head = text[:text.index(_ANCHOR)]
    absent = () if spec["declared_width"] else (OPENING_FIELD,)
    for name in FIELD_ALIASES.values():
        named = ('"%s"' % name) in head
        if name in absent and named:
            raise ValueError(
                f"{name} is withheld from the state in {condition} but the "
                f"prompt still names it.")
        if name not in absent and not named:
            raise ValueError(
                f"{name} is rendered into the state but not glossed in "
                f"{condition}.")
    named_eligible = '"eligible_arms"' in head
    if spec["eligible"] != named_eligible:
        raise ValueError(
            f"eligible_arms is {'present' if spec['eligible'] else 'absent'} "
            f"in {condition} and the prompt says otherwise.")
    return True


def assert_r3_matches_state(condition):
    """R3 never points at a field the state does not carry.

    R3 is substituted rather than deleted where the opening is withheld.
    Deleting it would test the value of knowing the constraint exists,
    which is what the norules cells measure and not what nowidth does.
    """
    spec = condition_spec(condition)
    if spec["withhold_rule"] == "R3":
        return True                    # the ablation, checked separately
    text = system_prompt(condition)
    r3 = text[text.index("R3  Gripper opening"):text.index("R4  Load")]
    names_field = ('"%s"' % OPENING_FIELD) in r3
    if not spec["declared_width"] and names_field:
        raise ValueError(
            f"R3 names {OPENING_FIELD} in {condition}, where the field is "
            f"withheld. A model could read the rule as inapplicable, and "
            f"that would score as a retrieval failure while being a "
            f"rule-reading failure.")
    if spec["declared_width"] and not spec["eligible"] and not names_field:
        raise ValueError(f"R3 does not name {OPENING_FIELD} in {condition}.")
    return True


def assert_rules_are_separable():
    """No rule cites another, except R6's pointer at R7.

    This is the property the whole rewrite exists for. A rule that cited
    another could not be withheld alone: withholding it would leave the
    citation dangling, which is a defect rather than a manipulation, and
    that is exactly why v1 had to withhold two rules together.

    R6 to R7 is the documented exception. It is a scope statement, R7 is
    never withheld, and the reference therefore always resolves.
    """
    f = _fields()
    allowed = {"R6": {"R7"}, "R3": set(), "R4": set(), "R5": set(),
               "R1": set(), "R2": set(), "R7": set()}
    for name, block in (("R1", R1), ("R2", R2), ("R3", R3), ("R4", R4),
                        ("R5", R5), ("R6", R6), ("R7", R7)):
        body = block.format(**f).split("\n", 1)[1]
        cited = {f"R{n}" for n in "1234567" if f"R{n}" in body}
        extra = cited - allowed[name]
        if extra:
            raise ValueError(
                f"{name} cites {sorted(extra)}. A cited rule cannot be "
                f"withheld alone, so the per-constraint ablation would "
                f"leave a dangling reference.")
    return True


def assert_ablation_is_one_rule(condition):
    """A norules cell differs from full in exactly one rule block."""
    spec = condition_spec(condition)
    withheld = spec["withhold_rule"]
    if withheld is None:
        raise ValueError(f"{condition} withholds no rule.")
    full, cell = _rules(condition_spec("full")), _rules(spec)
    moved = sorted(k.upper() for k in full if full[k] != cell[k])
    if moved != [withheld]:
        raise ValueError(
            f"{condition} was meant to withhold {withheld} alone and moved "
            f"{moved}. A cell that changes two rules cannot attribute a "
            f"behaviour change to either.")
    return True


def assert_withheld_names_no_field(condition):
    """The withheld text names no state field and instructs no derivation.

    Naming a field would leave the instruction standing under a withheld
    label. "Work it out from the numbers" is the instruction the cell
    exists to remove, and putting it back in different words would make the
    cell a paraphrase of the full one.
    """
    spec = condition_spec(condition)
    withheld = spec["withhold_rule"]
    if withheld is None:
        raise ValueError(f"{condition} withholds no rule.")
    body = _rules(spec)[withheld.lower()].split("\n", 1)[1]
    for name in list(FIELD_ALIASES.values()) + list(_STATE_FIELD_NAMES):
        if ('"%s"' % name) in body:
            raise ValueError(
                f"the withheld {withheld} in {condition} names {name!r}, "
                f"which leaves the instruction standing under a withheld "
                f"label.")
    low = body.lower()
    for phrase in ("work it out", "compare", "derive", "calculate",
                   "at least", "at most"):
        if phrase in low:
            raise ValueError(
                f"the withheld {withheld} in {condition} says {phrase!r}, "
                f"which reinstates the instruction the cell removes.")
    return True


def assert_spine_is_one_removal():
    """Adjacent cells on the spine differ in exactly one flag.

    The entire design claim. If two things move at once, the gap between
    those cells is not attributable to either.
    """
    keys = ("declared_width", "names", "eligible", "mislabel",
            "withhold_rule")
    for a, b in zip(SPINE, SPINE[1:]):
        sa, sb = condition_spec(a), condition_spec(b)
        moved = [k for k in keys if sa[k] != sb[k]]
        if len(moved) != 1:
            raise ValueError(
                f"{a} to {b} moves {moved}, not one thing. The gap between "
                f"them would not be attributable.")
    return True


def assert_state_matches_condition(state, condition):
    """The state carries what the condition says it carries.

    Cheap, and it catches the mislabelling the v1 module records having
    been caught once already: task fields moved without the reachability
    marker, producing one cell's prompt under another's label.
    """
    spec = condition_spec(condition)
    has_eligible = any("eligible_arms" in t for t in state.get("tasks", []))
    if has_eligible != spec["eligible"]:
        raise ValueError(
            f"condition {condition} expects eligible_arms "
            f"{'present' if spec['eligible'] else 'absent'} and the state "
            f"says otherwise. Rendering it would put one cell's prompt under "
            f"another's label.")
    has_width = any("grasp_m" in o for o in state.get("objects", []))
    if has_width != spec["declared_width"]:
        raise ValueError(
            f"condition {condition} expects the declared opening "
            f"{'present' if spec['declared_width'] else 'absent'} and the "
            f"state says otherwise.")
    for o in state.get("objects", []):
        if "dims_m" in o or "pose" in o:
            raise ValueError(
                "the state carries a dimensions or pose field. Experiment 1 "
                "measures retrieval, and either field opens the derivation "
                "route that would make it a second study of Experiment 2's "
                "question.")
    return True


def assert_states_are_serialised(probes, sample=None):
    """Every state offers one queued task and has every arm idle.

    The property the redesign is built on, checked against the states
    rather than assumed from the flag that produced them. A set harvested
    from a contended cell renders perfectly well here and would be reported
    under a serialised label, which is the one failure this cannot leave to
    inspection.

    Returns (n_checked, n_states_with_a_busy_arm, n_states_with_two_tasks).
    Raises on the first offence, so the counts are for the passing case.
    """
    probes = probes[:sample] if sample else probes
    for p in probes:
        st = p["state"] if "state" in p else p
        busy = [a["name"] for a in st.get("arms", [])
                if not a.get("disabled") and a.get("state") != "IDLE"]
        if busy:
            raise ValueError(
                f"state {p.get('provenance', {}).get('seq')} has busy arms "
                f"{busy}. It was harvested from a contended cell, and a "
                f"contended state reported under a serialised label would "
                f"understate how often the opening can bind.")
        queued = [t for t in st.get("tasks", [])
                  if str(t.get("status", "")).startswith("queued")]
        if len(queued) > 1:
            raise ValueError(
                f"state {p.get('provenance', {}).get('seq')} offers "
                f"{len(queued)} queued tasks. Serialising exists to remove "
                f"task selection from the decision, and a state offering a "
                f"choice of tasks puts it back.")
    return len(probes), 0, 0


def cell_diff(directive="none", **kw):
    """Every condition's system prompt, for eyeballing before any spend."""
    out = {}
    for c in CONDITIONS:
        try:
            out[c] = system_prompt(c, directive, **kw)
        except ValueError as e:
            out[c] = f"REFUSED: {e}"
    return out


def verify_all():
    """Every static check, in one call. Returns a list of (name, ok, why)."""
    results = []

    def run(name, fn, *a):
        try:
            fn(*a)
            results.append((name, True, ""))
        except Exception as e:                       # noqa: BLE001
            results.append((name, False, f"{type(e).__name__}: {e}"))

    run("rules are separable", assert_rules_are_separable)
    run("spine is one removal", assert_spine_is_one_removal)
    for c in CONDITIONS:
        run(f"glossary matches state [{c}]", assert_glossary_matches_state, c)
        run(f"R3 matches state [{c}]", assert_r3_matches_state, c)
        run(f"no dimensions route [{c}]", assert_no_dimensions_route, c)
    for c in RULE_CELLS:
        run(f"ablation is one rule [{c}]", assert_ablation_is_one_rule, c)
        run(f"withheld names no field [{c}]", assert_withheld_names_no_field, c)
    for d in DIRECTIVES:
        cond = "full" if d not in _OPENING_ASKED else "nowidth"
        run(f"no dimensions route [{cond}/{d}]",
            assert_no_dimensions_route, cond, d)
    return results


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="EX1 v2 prompts: verify or show")
    ap.add_argument("--show", metavar="CONDITION",
                    help="print one condition's system prompt")
    ap.add_argument("--directive", default="none", choices=sorted(DIRECTIVES))
    ap.add_argument("--image", action="store_true",
                    help="render the condition V wording")
    args = ap.parse_args(argv)

    if args.show:
        print(system_prompt(args.show, args.directive, has_image=args.image))
        return 0

    bad = 0
    for name, ok, why in verify_all():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}"
              + (f"\n        {why}" if why else ""))
        bad += 0 if ok else 1
    print(f"\n{'ALL PASS' if not bad else str(bad) + ' FAILED'}  "
          f"EX1 v2 prompt version {EX1_V2_PROMPT_VERSION}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
