"""EX1: the information ladder. Rung definitions and prompt construction.

EX1 asks what the allocator falls back on as capability information is
removed from the prompt one kind at a time. The spine is a data axis:

    L3          rules, reach lists, declared width, real object names
    L3-nowidth  the same, with the object's "grasp_m" removed
    L1-nowidth  the same, with object names anonymised as well

Two gaps, each removing exactly one thing. L3 to L3-nowidth asks whether
the model can supply a width it was not given. L3-nowidth to L1-nowidth
asks whether that width was coming from the object's NAME, which is the
memorisation probe the dissertation title refers to.

Off the spine:

    L4          eligible_arms supplied. Obedience control above the spine.
    L2          L3 with R3 and R4 withheld, all data still present.
                Instruction-axis contrast, reported beside the chain and
                never as a step in it, because a drop from L3-nowidth to
                L2 would confound instruction loss with the width loss
                already measured above.

WHY THIS MODULE EXISTS RATHER THAN A KEYWORD ON build_prompt.

Same reason experiments/ex2/prompts.py exists. The shared base prompt in
core/decision/state_builder.py is what the byte-identity acceptance test
replays through, and PROMPT_VERSION is what every existing episode is
stamped with. Editing that file to add an experiment's wording would move
the stamp and put the banked acceptance evidence back in question. EX1
builds on the REAL build_prompt and substitutes afterwards, so the cell
description, R1, R2, R5, R6, R7 and all of the guidance are byte-identical
to what every other experiment sends, and the diff against the base prompt
is exactly what EX1 changed.

WHY THE WITHHELD RULES ARE NEUTRALISED RATHER THAN DELETED.

The base prompt cross-references its own rules. R7 says "R3 still applies
to it, and R5 governs how it is reached", and R4's enriched text refers to
R3 by name. Deleting the R3 and R4 blocks leaves R7 citing a rule that is
no longer in the prompt, which is a defect rather than a manipulation.
Neutralising keeps every cross-reference valid, keeps the rule count and
the section structure identical to L3, and leaves the rule CONTENT as the
only difference, which is what makes the L3-to-L2 gap attributable.

The withheld text says a check exists and does not say what it is. Saying
nothing at all would let the model conclude no check applies, which is a
different manipulation. Saying "work it out from the numbers" would
reinstate the instruction the rung exists to remove.

R4's scope statement is KEPT. The base R4 bundles a rule ("the arm must
appear in reach_ok_arms"), a method ("use the list, do not work reach out
from coordinates"), a clarification ("reach is not grasp"), and a scope
statement ("reaching the destination is not required of you"). Only the
first three instruct capability reasoning. The fourth tells the model what
lies outside its job, and withholding it would make L2 differ from L3 in
two ways at once: no capability rule AND no assurance about destinations.
A model that then started weighing destination reach would look like a
model that had stopped checking capability, and the rung could not tell
them apart. The clarification goes with the rule, because it refers to R3,
which L2 also withholds.

WHAT THIS MODULE DOES NOT DO.

The width removal is a STATE edit, not a prompt edit, and lives in
harvest/probe_replay.py's state_at_rung. Anonymisation is both a state
edit and a prompt edit; its state half and its own text substitutions live
in experiments/ex1/anonymise.py. This module owns the rung table, so there
is one place that answers "what is L1-nowidth", and the rules axis.

GUIDANCE: DEPLOYED BLOCK KEPT. A TRIM WAS TESTED AND REJECTED.

On 2026-08-16 version 16a removed G1, G2, G4 and G5 (keeping G3 as a
positional-bias control), on the argument that G2/G4/G5 are the only
instructions that can turn a legal pick into a decline, and that removing
them would make a noop mean one thing. One full GPT L3 run measured the
result, against the same run under the deployed prompt:

    deployed guidance   3 of 126 picking states nooped  (2.4%)
    guidance trimmed   24 of 126 picking states nooped (19.0%)

All 24 reasons cited zone locks or inbound reservations, every one of them
REAL in the state (0 of 24 hallucinated), and none expressed uncertainty.
The mechanism: the cell description says "one arm may hold a zone at a
time" and the state prints zone_locks and zone_inbound at every rung. G2
was not licensing zone-based waiting, it was DEMOTING the zone machinery
to a preference. With the demotion removed, an under-specified constraint
with no stated owner reads as law, and the model waits on it.

So the deployed guidance stays, for three reasons. First, the dissertation
argues offline decisions equal deployed decisions, and every departure
from the deployed wording weakens that equivalence and demands its own
defence; the 16a episode is direct evidence of how unpredictable such
departures are. Second, the measured nuisance under the deployed prompt is
small and classifiable (2.4%, reasons name G2's own vocabulary), while the
trimmed prompt fogs 19% of picking states at every rung. Third, keeping it
means the original L3 run is the baseline and nothing is re-run.

The constants and trim_guidance below are KEPT, unused, as the record of
what was tested, so it is not re-proposed for EX3 without reading this.
The 16a run itself (out/ex1_gpt_L3_v2.jsonl) is a finding for the
write-up: GPT's zone-waiting is prompt-fragile in the opposite direction
to intuition, becoming MORE conservative when permissive guidance is
removed.

NOTE ON L3-nowidth AND R3. At L3-nowidth the R3 text still names
"grasp_m", a field the state no longer carries. That is deliberate and is
the manipulation itself: the model is told the check exists and told which
quantity it must supply, and is not given the quantity. The rule is not
rewritten to hide the gap.
"""

import copy

from experiments.ex1 import anonymise as A
from core.decision.state_builder import (build_prompt,
                                         has_eligible,
                                         CAPABILITY_RULE,
                                         CAPABILITY_RULE_ELIGIBLE,
                                         REACH_RULE_ENRICHED,
                                         REACH_RULE_ELIGIBLE)

# Bumped on ANY change to the substitutions below. Recorded on every row
# alongside the base PROMPT_VERSION, because once EX1 rewrites a section
# the base stamp no longer identifies what the model actually read.
#
#   2026-08-15a  first build. R3 and R4 withheld variants for L2, rung
#                table for the full ladder, guarded substitution against
#                the base text.
#   2026-08-20a  L3-swap and L1-swap added: object names swapped across the
#                Franka aperture with every other field left on the true
#                object. Table entries plus one branch in
#                probe_replay.state_at_rung. L3, L2, L4, L3-anon,
#                L3-nowidth and L1-nowidth all render exactly as under
#                19a, so every run reported in the chapter stays valid.
#   2026-08-19a  L3-anon added: names anonymised with the width present,
#                the fourth cell of the width x names design and the
#                control for anonymisation itself. Table entry only; the
#                state edit and the prompt path both already follow the
#                flags, so no code changed and L3, L2 and L4 render byte
#                for byte as under 16b.
#   2026-08-16b  guidance REVERTED to the deployed block after one L3 run
#                under 16a measured the cost: see the guidance note below.
#                L3 prompts under 16b are byte-identical to 15a, so the
#                original L3 run is valid again and the 16a run is kept as
#                evidence, not as a baseline.
#   2026-08-16a  G1, G2, G4 and G5 removed from every EX1 rung; G3 kept
#                verbatim. Tested and REJECTED same day; see below.
#   2026-08-15c  the withheld R4 keeps R4's SCOPE statement ("reaching the
#                destination is not required of you; see R5") while still
#                dropping the rule. Base R4 carries four things: the rule,
#                how to check it, a clarification that reach is not grasp,
#                and that scope statement. Only the first three are
#                capability instruction. Dropping the fourth as well made
#                L2 differ from L3 in TWO ways, so a behaviour change at
#                L2 could not be attributed to the missing rule. Found by
#                reading the L3-to-L2 diff by eye; no automated check
#                would have caught it, because nothing knew the clause was
#                a different kind of sentence.
#   2026-08-15b  anonymised rungs accepted. build_ex1_prompt takes the
#                alias mapping and runs assert_clean on what it built, so
#                a rung labelled anonymised cannot be rendered without
#                proof that no real name survived. No wording changed, so
#                L2 and L3 prompts are byte-identical to 2026-08-15a.
EX1_PROMPT_VERSION = "2026-08-20a"


# ---------------------------------------------------------------------------
# The rung table. One place that says what each rung is.
# ---------------------------------------------------------------------------

# Each flag means the information is PRESENT. state_at_rung reads
# "declared_width" and "eligible"; this module reads "rules"; anonymise.py
# reads "names".
#
# "recorded" is deliberately absent. It is probe_replay's own rung, meaning
# "byte for byte as the live episode sent it", and it belongs to the
# acceptance test rather than to the ladder.
# "guidance" True means the DEPLOYED guidance block, untouched. It is True
# on every rung: a trim was tested on 2026-08-16 and rejected on evidence
# (see the guidance note above). The flag remains so the rung table stays
# the single answer to "what does this rung supply", and so the tested
# alternative is one flag away for anyone who reads the note and disagrees.
RUNGS = {
    "L4":         {"eligible": True,  "declared_width": True,
                   "rules": True,  "names": True,  "guidance": True},
    "L3":         {"eligible": False, "declared_width": True,
                   "rules": True,  "names": True,  "guidance": True},
    "L3-nowidth": {"eligible": False, "declared_width": False,
                   "rules": True,  "names": True,  "guidance": True},
    "L1-nowidth": {"eligible": False, "declared_width": False,
                   "rules": True,  "names": False, "guidance": True},
    "L2":         {"eligible": False, "declared_width": True,
                   "rules": False, "names": True,  "guidance": True},
    # The fourth cell of the width x names design. The name null is
    # otherwise measured only where the width is already gone, which leaves
    # open that anonymisation costs a few points on its own and happens to
    # cancel a real name benefit. If this rung matches L3, anonymisation is
    # inert and that reading is closed.
    "L3-anon":    {"eligible": False, "declared_width": True,
                   "rules": True,  "names": False, "guidance": True},
    # Mislabelled. Names are PRESENT but swapped across the Franka
    # aperture, so the name and the declared width disagree. Anonymisation
    # can only produce a null, which is consistent both with the name being
    # unused and with it being used and the loss absorbed elsewhere. A swap
    # asks the question directionally: following the number is evidence the
    # name is inert, following the name is identity retrieval. See
    # experiments/ex1/mislabel.py for which objects swap and why.
    #
    # names stays True because a name IS supplied; mislabel says it is the
    # wrong one. The two are mutually exclusive, since anonymisation would
    # erase the swap it is meant to test.
    "L3-swap":    {"eligible": False, "declared_width": True,
                   "rules": True,  "names": True,  "guidance": True,
                   "mislabel": True},
    "L1-swap":    {"eligible": False, "declared_width": False,
                   "rules": True,  "names": True,  "guidance": True,
                   "mislabel": True},
}

# The data spine, in order, for analysis code that needs the chain rather
# than the set. L4 and L2 are controls and contrasts, not steps.
SPINE = ("L3", "L3-nowidth", "L1-nowidth")

# The two removals crossed. L3-anon is the control for anonymisation: same
# information as L3 except the names.
FACTORIAL = {(True, True): "L3", (False, True): "L3-nowidth",
             (True, False): "L3-anon", (False, False): "L1-nowidth"}


def rung_spec(rung):
    """What information this rung supplies. Raises on an unknown name.

    Never defaults. A rung that quietly fell back to L3 would report an L3
    result under another label and nothing in the output would show it,
    which is the same failure mode the EX2 rung names guard against.
    """
    if rung not in RUNGS:
        raise ValueError(
            f"unknown EX1 rung {rung!r}; expected one of {sorted(RUNGS)}. "
            f"Rungs are never defaulted: a result recorded under the wrong "
            f"label would be invisible in the output.")
    return dict(RUNGS[rung])


# ---------------------------------------------------------------------------
# The withheld rule text.
# ---------------------------------------------------------------------------

# Indentation matches the base prompt's continuation style: the rule label
# occupies four columns ("R3  ") and wrapped lines are indented to match.

CAPABILITY_RULE_WITHHELD = (
    "The cell checks that the arm you name can handle the object. That\n"
    "    check is not stated here.")

REACH_RULE_WITHHELD = (
    "The cell checks that the arm you name can reach the object. That\n"
    "    check is not stated here. Reaching the destination is not\n"
    "    required of you; see R5.")

# The literal-deletion alternative, if the neutralised form is rejected.
# Substituting these leaves R7's "R3 still applies to it" pointing at an
# empty rule, which is why they are not the default. Kept as data so the
# choice is a call-site change and not a rewrite.
CAPABILITY_RULE_DELETED = ""
REACH_RULE_DELETED = ""


# The deployed GUIDANCE block and the tested-and-rejected EX1 subset.
# UNUSED at every current rung (guidance is True everywhere); kept as the
# record of the 16a test and for any future rung that re-opens it with
# cause. Held as literals because state_builder inlines the block with no
# module constant to import; _substitute_once raises if the deployed
# wording drifts from GUIDANCE_FULL.
GUIDANCE_FULL = (
    "GUIDANCE. Not enforced, but this is what a good allocation does.\n"
    "G1  Sort correctly: send each object to the basket named for its "
    "\"category\",\n"
    "    so that objects of the same kind end up together.\n"
    "G2  Avoid contention: prefer allocations that do not make arms queue "
    "for the\n"
    "    same zone. \"zone_locks\" names current holders, \"zone_inbound\" "
    "names arms\n"
    "    already heading into one.\n"
    "G3  Ignore queue order: it carries no priority. Pick the task that "
    "best fits\n"
    "    an arm that is free now, not the first one listed.\n"
    "G4  Protect scarce arms: if the arm you are about to use is the only "
    "one that\n"
    "    could serve another queued task, prefer an alternative for this "
    "one.\n"
    "G5  Waiting can be a choice, not only a last resort. If every idle "
    "arm is a\n"
    "    poor fit and a better-suited one will free up soon, wait.\n")

GUIDANCE_EX1 = (
    "GUIDANCE. Not enforced, but this is what a good allocation does.\n"
    "G3  Ignore queue order: it carries no priority. Pick the task that "
    "best fits\n"
    "    an arm that is free now, not the first one listed.\n")


# ---------------------------------------------------------------------------
# Substitution, guarded.
# ---------------------------------------------------------------------------

def _expected_rules(state):
    """The R3 and R4 body text the base prompt will have rendered for this
    state.

    Derived from the state_builder constants rather than copied, so the two
    files cannot drift apart. If the base wording is edited, the constants
    move with it and the substitution keeps working; if a rule is RENAMED
    or restructured the guard below fails loudly, which is the outcome we
    want.

    build_prompt selects its rule text from the state, not from a flag, so
    the selection is repeated here on the same input.
    """
    if has_eligible(state):
        return CAPABILITY_RULE_ELIGIBLE, REACH_RULE_ELIGIBLE
    return CAPABILITY_RULE, REACH_RULE_ENRICHED


def _substitute_once(text, old, new, label):
    """Replace `old` with `new`, requiring exactly one occurrence.

    A missing block means the base prompt changed and EX1 would silently
    send an unmodified rung. A repeated block means the substitution would
    hit somewhere it was not meant to. Both are failures, and both are
    louder here than in a results table three days later.
    """
    n = text.count(old)
    if n != 1:
        raise ValueError(
            f"EX1 cannot substitute {label}: the base prompt contains it "
            f"{n} times, expected exactly 1. core/decision/state_builder.py "
            f"has changed and this module must be updated to match rather "
            f"than sending an unmodified prompt under an EX1 rung label.")
    return text.replace(old, new, 1)


def withhold_rules(sys_text, state, capability=CAPABILITY_RULE_WITHHELD,
                   reach=REACH_RULE_WITHHELD):
    """R3 and R4 replaced with the withheld text. Everything else untouched.

    Returns the modified system text. The caller owns the messages list.
    """
    cap_old, reach_old = _expected_rules(state)
    sys_text = _substitute_once(sys_text, cap_old, capability, "R3")
    sys_text = _substitute_once(sys_text, reach_old, reach, "R4")
    return sys_text


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------

def trim_guidance(sys_text, keep=GUIDANCE_EX1):
    """Replace the deployed GUIDANCE block with EX1's subset."""
    return _substitute_once(sys_text, GUIDANCE_FULL, keep, "GUIDANCE")


def build_ex1_prompt(state, rung, condition, image_b64=None, mapping=None):
    """Messages for one EX1 trial at one rung.

    The state passed in must ALREADY carry the state-level edits for this
    rung: eligible_arms present or absent, grasp_m present or absent, names
    real or anonymised. state_at_rung in harvest/probe_replay.py does that
    work, because it owns the frozen-coordinator rebuild that L4 needs.
    This function applies the PROMPT-level part and nothing else.

    Splitting it that way keeps one rule: the state is what the model is
    shown, and the prompt is what the model is told. Rungs that differ only
    in what they are shown never touch this function at all.
    """
    spec = rung_spec(rung)

    if condition not in ("A", "V"):
        raise ValueError(f"unknown condition {condition!r}; expected A or V")
    if condition == "V" and image_b64 is None:
        raise ValueError(
            "condition V without an image would silently be condition A. "
            "Pass the frame or ask for A.")

    # Consistency check between the rung and the state it arrived with.
    # Cheap, and it catches the mislabelling that state_at_rung's own
    # comment records having been caught once already: task fields moved
    # without the reachability marker, producing an L3 prompt stamped L4.
    if has_eligible(state) != spec["eligible"]:
        raise ValueError(
            f"rung {rung} expects eligible_arms "
            f"{'present' if spec['eligible'] else 'absent'} but the state "
            f"says otherwise. The prompt selects its rules from the state, "
            f"so this would render one rung's prompt under another's label.")

    messages = build_prompt(state, condition, image_b64=image_b64)
    sys_text = messages[0]["content"]

    if not spec["guidance"]:
        sys_text = trim_guidance(sys_text)

    if not spec["rules"]:
        sys_text = withhold_rules(sys_text, state)

    if sys_text != messages[0]["content"]:
        messages = copy.deepcopy(messages)
        messages[0]["content"] = sys_text

    if not spec["names"]:
        if mapping is None:
            raise ValueError(
                f"rung {rung} is anonymised and no alias mapping was given, "
                f"so nothing can confirm the state was anonymised at all. "
                f"Rendering it would put real object names in the prompt "
                f"under an anonymised label.")
        A.assert_clean(messages, mapping)
    elif mapping is not None:
        raise ValueError(
            f"rung {rung} keeps object names but an alias mapping was "
            f"given. One of the two is wrong and guessing which would "
            f"mislabel the trial.")
    return messages