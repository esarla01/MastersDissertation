"""Offline replay: render a saved decision state at a chosen rung, ask a
model, run the real validator, emit one row per decision.

This is what makes EX1, EX2 and EX3 sim-free. state_builder and tasks
import nothing from Isaac and build_prompt takes the state DICT rather than
the coordinator, so a saved consult can be re-rendered at a different rung
and re-judged without a simulator.

Nothing here reimplements a rule. The prompt comes from build_prompt, the
eligibility list from compute_eligible_arms, the verdict from
validate_decision, the routing from route_via_pad, and the violation class
from classify. This module only arranges them and records what happened.

RUNGS. The ladder strips capability information one step at a time. What
each rung supplies is declared ONCE, in experiments/ex1/prompts.py's RUNGS
table, and read from there by this module. Two places defining a rung is
how a state edit and a prompt edit come to disagree about what the rung
is, so there is one place.

    recorded    exactly as the live episode rendered it, byte for byte.
                The acceptance test uses this and nothing else, and it
                never touches the EX1 module.

    L4          eligible_arms supplied: the legal set is handed over, so
                the model is not asked to derive it. Obedience control.
    L3          rules given, model derives eligibility from the tables.
                The full-information baseline.
    L3-nowidth  grasp_m removed. The model must supply a width it was not
                given; the routes left are the object's name and the image.
    L1-nowidth  grasp_m removed AND object names anonymised. With the
                image off both routes are closed. This is the memorisation
                probe and the gap the dissertation's claim rests on.
    L2          rules withheld, all data present. Off the spine: reported
                as a contrast beside the chain, never as a step in it.

The spine is L3 -> L3-nowidth -> L1-nowidth, each step removing exactly
one kind of information. L4 sits above it as a control and L2 beside it.

TWO DESIGNS, AND THE ROWS SAY WHICH. Everything above describes v1, the
published Experiment 1, and it is the default because every run already on
disk was made under it. --design v2 selects the redesign:

    the states come from a SERIALISED cell, so one task is offered and
    every arm is idle at every decision;

    the prompt is rebuilt on Experiment 2's base rather than substituted
    into the shared one, with Experiment 2's field aliases and seven
    separated rules, so the ablation can withhold one constraint at a time;

    the conditions are named full, nowidth, anon, nowidth-anon, swap,
    nowidth-swap, givenset and norules-<constraint>, and the v1 names
    resolve to them as aliases so a command line typed from memory works;

    a --directive adds one prompt-level treatment at one anchor: recall,
    report or elicit.

The two are not poolable. Serialising draws states from a different
distribution, so a v1 rate and a v2 rate answer the same question on
different populations. Every row records its design, --resume refuses to
append across a mismatch, and a v2 run refuses a probe set whose states are
not serialised.

VIOLATION TYPING. A row records not only whether a proposal was rejected
but which constraint it broke. The validator emits one code and stops at
the first failure, which is right for a guard and wrong for a tally, so
each rejected row also carries a non-short-circuit diagnostic listing
every constraint the proposal breaks. The validator remains the ground
truth; the diagnostic is reported beside it and disagreements are flagged.

ACCEPTANCE TEST. verify_trail() replays a real episode's saved consults at
the recorded rung and requires the rebuilt prompts to be byte-identical to
what was sent, and the validator verdicts to be identical including reason
strings. Passing means every offline number is comparable to the live
episodes. Failing means the shim is lying, and it is better to know before
any model spend.

Usage:

    python3 analysis/probe_replay.py --probes probes/seed_v2.json \\
        --rung L3 --condition A --model qwen --out runs/ex1_L3_qwen.jsonl

    python3 analysis/probe_replay.py --verify \\
        out/probe_seed_v2_frames/consults.jsonl
"""

import argparse
import base64
import copy
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.cell.zones import ZoneMap                                # noqa: E402
from core.decision.state_builder import (build_prompt,             # noqa: E402
                                         compute_eligible_arms,
                                         parse_decision,
                                         prompt_version)
from core.decision.vlm_allocator import (validate_decision,        # noqa: E402
                                         classify, openai_chat,
                                         _pad_name, VIOLATION_RULE)
from core.cell import cell_config as C                             # noqa: E402
from analysis.frozen_coord import from_record, idle_arms           # noqa: E402
from analysis.probe_store import (load as load_probes,             # noqa: E402
                                  capability_cause)
from experiments.ex1 import prompts as EX1P                        # noqa: E402
from experiments.ex1 import prompts_v2 as EX1P2                    # noqa: E402
from experiments.ex1 import anonymise as EX1A                      # noqa: E402
from experiments.ex1 import mislabel as EX1M                       # noqa: E402

# "recorded" belongs to this module and to the acceptance test. Every other
# rung is defined by the EX1 table, so adding a rung there adds it here and
# the two can never drift.
RUNGS = ("recorded",) + tuple(sorted(EX1P.RUNGS))

# THE TWO DESIGNS. v1 is the published Experiment 1: the contended cell,
# the substituted base prompt and the L-named rungs. v2 is the redesign:
# the serialised cell, the prompt rebuilt on Experiment 2's base, the
# Experiment 2 field aliases and one rule ablation per constraint.
#
# The design is never defaulted per call and never inferred from the rung
# name. It is passed explicitly, recorded on every row, and checked when a
# run is resumed, because a v1 row and a v2 row answer different questions
# on states that are not comparable, and a file holding both could not be
# separated afterwards.
DESIGNS = {
    "v1": {"module": EX1P, "rungs": tuple(sorted(EX1P.RUNGS)),
           "version": EX1P.EX1_PROMPT_VERSION},
    "v2": {"module": EX1P2, "rungs": tuple(sorted(EX1P2.CONDITIONS)),
           "version": EX1P2.EX1_V2_PROMPT_VERSION},
}
RUNGS_V2 = DESIGNS["v2"]["rungs"]
DIRECTIVES = tuple(sorted(EX1P2.DIRECTIVES))


def design_spec(design):
    """The design table, or a message naming both. Never defaults."""
    if design not in DESIGNS:
        raise ValueError(
            f"unknown design {design!r}; expected one of {sorted(DESIGNS)}. "
            f"v1 is the published contended-cell experiment and v2 the "
            f"serialised redesign. They are answered on different states "
            f"and a result recorded under the wrong one would be invisible "
            f"in the output.")
    return DESIGNS[design]


def rung_spec(rung, design="v1"):
    """What this rung supplies, from whichever design's table."""
    mod = design_spec(design)["module"]
    if design == "v2":
        return mod.condition_spec(rung)
    return mod.rung_spec(rung)

# Kept, and empty. The mechanism is what stops a rung silently falling back
# to L3 and reporting an L3 result under another label. It cost nothing to
# leave in place for the next rung that gets designed before it is built.
NOT_BUILT = {}

_ZM = None


def zonemap():
    global _ZM
    if _ZM is None:
        _ZM = ZoneMap()
    return _ZM


def _baskets():
    from ycb_scene import BASKETS
    return BASKETS


def _strip_eligible(state):
    """The L3 base: eligible_arms removed and the marker moved with it.

    The prompt selects its rules block from state["reachability"], NOT from
    the presence of the task field. Setting one without the other renders
    an L3 prompt under an L4 label, which is the exact silent mislabelling
    the rung names exist to prevent. Found while testing: the first version
    of this function moved only the task fields and produced a
    3596-character L3 prompt stamped "L4".
    """
    for t in state.get("tasks", []):
        t.pop("eligible_arms", None)
    if str(state.get("reachability", "")).startswith("listed"):
        state["reachability"] = "listed"
    return state


def _add_eligible(state, probe):
    """The L4 base: supply the legal set.

    A state harvested without the ablation has no eligible_arms field, so
    it is derived here through the SAME function build_state uses.
    """
    coord = from_record(probe)
    zm = zonemap()
    dead = {a["name"] for a in state.get("arms", []) if a.get("disabled")}
    by_id = {t.id: t for t in coord.pool}
    for t in state.get("tasks", []):
        task = by_id[t["id"]]
        p = coord.cell.scene[task.obj].data.root_pos_w[0]
        spec = C.OBJECT_SPECS[task.obj]
        t["eligible_arms"] = compute_eligible_arms(
            task, (float(p[0]), float(p[1])), spec, zm, dead)
    if not str(state.get("reachability", "")).startswith("listed"):
        raise ValueError(
            "L4 needs a state built with a zonemap (reachability 'listed'); "
            f"this one has {state.get('reachability')!r}. Re-harvest from an "
            "episode that passed a zonemap to build_state.")
    state["reachability"] = "listed+eligible"
    return state


def _strip_width(state):
    """Remove the declared graspable width from every object.

    This is the ENTIRE L3 to L3-nowidth manipulation, and it is a state
    edit rather than a prompt edit because the width is data, not
    instruction. R3 still names "grasp_m" afterwards: the model is told the
    check exists and told which quantity it must supply, and is not given
    the quantity. That is the manipulation, not an oversight.

    No other field yields a width. The state carries no bounding-box
    dimensions, so once grasp_m is gone the only routes to a width are the
    object's name and the image, which is what makes the next step down the
    spine a memorisation probe rather than an arithmetic one.

    mass_kg stays. It is a different declared property and removing it
    would make this step remove two things instead of one.
    """
    for ob in state.get("objects", []):
        ob.pop("grasp_m", None)
    return state


def state_at_rung(probe, rung, return_map=False, design="v1"):
    """A copy of the saved state adjusted for the requested rung.

    The state is copied, never mutated in place: a probe set is frozen and
    a run that edited it would change the thing every other run is being
    compared against.

    Built from the EX1 rung table rather than from a chain of named
    branches, so what a rung supplies is declared in one place and the
    state edit cannot disagree with the prompt edit about it.

    return_map=False (default) returns the state alone, which is what every
    existing caller expects. return_map=True returns (state, mapping),
    where mapping is the alias table for an anonymised rung and None
    otherwise. The reply needs that table to be read back, and the state
    must not carry it: anything left in the state gets rendered into the
    prompt.
    """
    known = ("recorded",) + design_spec(design)["rungs"]
    if rung in NOT_BUILT:
        raise ValueError(f"rung {rung} is not built ({NOT_BUILT[rung]}). "
                         f"Available: {list(known)}.")
    if rung != "recorded" and rung not in known:
        # v2 accepts the v1 names as aliases so a command line typed from
        # memory resolves; condition_spec raises with both lists otherwise.
        if design != "v2" or rung not in EX1P2.CONDITION_ALIASES:
            raise ValueError(f"unknown rung {rung!r} for design {design!r}; "
                             f"expected one of {list(known)}. Rungs are "
                             f"never defaulted: a result reported under "
                             f"another label would be invisible in the "
                             f"output.")

    state = copy.deepcopy(probe["state"])
    if rung == "recorded":
        return (state, None) if return_map else state

    spec = rung_spec(rung, design)
    state = (_add_eligible(state, probe) if spec["eligible"]
             else _strip_eligible(state))
    if not spec["declared_width"]:
        state = _strip_width(state)
    mapping = None
    if spec.get("mislabel"):
        # Swapping names and then anonymising them would erase the very
        # thing the swap tests, and the result would look like a clean
        # anonymisation run under a different label.
        if not spec["names"]:
            raise ValueError(
                f"rung {rung!r} sets mislabel with names withheld. "
                f"Anonymisation would erase the swap, so the run would be "
                f"an L1-nowidth result reported under a swap label.")
        state, _ = EX1M.mislabel_state(state)
    if not spec["names"]:
        state, mapping = EX1A.anonymise_state(state)
    return (state, mapping) if return_map else state


def render(probe, rung="recorded", condition="A", return_map=False,
           design="v1", directive="none"):
    """(messages, state) for this probe at this rung and condition.

    return_map=True appends the alias mapping, which is None except at an
    anonymised rung. Default arity is unchanged so verify_trail and the
    dry-run path keep working exactly as before.

    "recorded" goes STRAIGHT to build_prompt and never touches the EX1
    module. That path is what the byte-identity acceptance test replays,
    and putting anything between the saved state and the prompt would make
    the test check this module rather than the shim it is meant to check.
    """
    state, mapping = state_at_rung(probe, rung, return_map=True,
                                   design=design)
    frame_b64 = None
    if condition == "V":
        path = probe.get("frame_path")
        if not path:
            raise ValueError(
                f"condition V needs a frame and probe "
                f"{probe['provenance'].get('seq')} has none. Falling back to "
                f"text would silently turn V into A.")
        with open(path, "rb") as f:
            frame_b64 = base64.b64encode(f.read()).decode("ascii")

    if rung == "recorded":
        messages = build_prompt(state, condition, image_b64=frame_b64)
    elif design == "v2":
        # v2 builds the whole prompt rather than substituting into the base:
        # the rules are renumbered per constraint and the state is rendered
        # through Experiment 2's field aliases, so there is no base text
        # left to substitute into. build_ex1_prompt runs assert_clean
        # against the mapping at an anonymised condition and refuses to
        # build one without it, exactly as v1 does.
        messages = EX1P2.build_ex1_prompt(state, rung, directive=directive,
                                          image_b64=frame_b64,
                                          mapping=mapping)
    else:
        # build_ex1_prompt runs assert_clean against the mapping at an
        # anonymised rung and REFUSES to build one without it. The check
        # reads the artefact that actually reaches the model, and it raises
        # rather than warns: one surviving object name invalidates the
        # trial, and a bad row is worse than a missing one.
        messages = EX1P.build_ex1_prompt(state, rung, condition,
                                         image_b64=frame_b64,
                                         mapping=mapping)
    return (messages, state, mapping) if return_map else (messages, state)


# ---------------------------------------------------------------------------
# Violation typing
# ---------------------------------------------------------------------------

# One validator code to one constraint TYPE. CAPABILITY is deliberately
# absent: it pools grasp, payload and delicacy behind a single code and is
# resolved separately through capability_cause, because a derived limit
# (the width the object presents) and a lookup limit (a delicate flag) are
# different cognitive demands and reporting them pooled would hide the
# contrast EX1 exists to measure.
VIOLATION_CAUSE = {
    "PARSE": "parse",
    "TASK_UNKNOWN": "task_state",
    "TASK_FINISHED": "task_state",
    "TASK_BUSY": "task_state",
    "ARM_UNKNOWN": "arm_state",
    "ARM_NOT_IDLE": "arm_state",
    "REACH_OBJECT": "reach",
    "NO_ROUTE": "no_route",
    "NO_BASKETS": "basket",
    "BASKET_MISSING": "basket",
}

CAUSES = ("grasp", "payload", "delicate", "reach", "no_route",
          "task_state", "arm_state", "basket", "parse")


def violation_detail(why, decision):
    """(code, rule, cause, fields) for a rejection reason string.

    cause resolves CAPABILITY down to whichever of the three limits binds,
    using the arm and object the classifier already recovered from the
    message. An unrecognised reason yields None throughout rather than a
    guess, matching classify's own refusal to misfile.
    """
    code, fields = classify(why)
    if code is None:
        return None, None, None, {}
    rule = VIOLATION_RULE.get(code)
    if code == "CAPABILITY":
        cause = capability_cause(fields.get("arm"), fields.get("obj"))
    else:
        cause = VIOLATION_CAUSE.get(code)
    return code, rule, cause, fields


def all_violated(decision, probe, baskets=None):
    """Every constraint this proposal breaks, not only the first.

    WHY THIS EXISTS. validate_decision short-circuits. It checks task
    status, then arm status, then capability, then reach to the object,
    then the route, and returns at the first failure. That is correct for a
    guard, whose job is to reject, and wrong for a tally: a proposal that
    is both incapable and out of reach is counted as capability only, so
    reach is systematically undercounted. The bias is the same at every
    rung, so the GAPS are unaffected, but the composition WITHIN a rung is
    not a true incidence unless every broken constraint is recorded.

    NOT A SECOND COPY OF THE RULE. Every check below calls the same
    primitive the validator calls: capability_cause reads the same tables
    as can_grasp, reach is zonemap.reachable, and the route is
    route_via_pad. The validator remains the ground truth for legal against
    illegal. This function only removes the short circuit.

    Returns a sorted list of cause names, or None if the proposal could not
    be evaluated at all. Never raises: a diagnostic that killed a paid run
    would be worse than a diagnostic that returned nothing.
    """
    try:
        from core.control.tasks import route_via_pad
        baskets = baskets or _baskets()
        coord = from_record(probe)
        zm = zonemap()
        out = []

        tid, arm = decision.get("task_id"), decision.get("arm")
        task = next((t for t in coord.pool if t.id == tid), None)
        if task is None:
            return ["task_state"]
        if task.done or task.failed or task.claimed or (
                task.waiting_on is not None):
            out.append("task_state")

        if arm not in coord.agents:
            return sorted(set(out + ["arm_state"]))
        ag = coord.agents[arm]
        if ag.state != "IDLE" or ag.arm.disabled:
            out.append("arm_state")

        cap = capability_cause(arm, task.obj)
        if cap:
            out.append(cap)

        p = coord.cell.scene[task.obj].data.root_pos_w[0]
        oxy = (float(p[0]), float(p[1]))
        if not zm.reachable(arm, *oxy):
            out.append("reach")

        dest = task.dest
        if dest is None:
            b = decision.get("basket")
            if b not in baskets:
                out.append("basket")
                dest = None
            else:
                dest = tuple(baskets[b]["pos"])
        if dest is not None and not zm.reachable(arm, *dest):
            dead = {a for a, g in coord.agents.items() if g.arm.disabled}
            if route_via_pad(task, oxy, [arm], zm, dead)[0] is None:
                out.append("no_route")
        return sorted(set(out))
    except Exception:
        return None


def _attach_violation(row, why, decision, probe, ok, baskets=None,
                      design="v1"):
    """Write the typing fields onto a row and flag any disagreement.

    THE RULE NUMBER IS DESIGN-DEPENDENT AND THE CAUSE IS NOT. The validator
    emits one code per rejection and its codes were numbered against the v1
    base, where a single CAPABILITY code covered the gripper opening, the
    load and the delicate flag. Separating those rules buys nothing unless
    a rejection can be filed against the rule that was actually broken, so
    under v2 the rule is resolved through the same capability decomposition
    probe_store uses. The code, the cause and the validator's verdict are
    untouched: only the label changes, and only for v2 rows.
    """
    code, rule, cause, fields = violation_detail(why, decision)
    if design == "v2":
        rule = EX1P2.violation_rule(code, cause)
    row["violation"] = code
    row["violation_rule"] = rule
    row["violation_cause"] = cause
    row["violation_fields"] = fields
    every = all_violated(decision, probe, baskets)
    row["violation_all"] = every
    # The validator is the ground truth. A disagreement means one of the
    # two is reading the cell wrongly, and it is worth far more as a loud
    # column than as a silent overwrite.
    if every is not None:
        row["diagnostic_disagrees"] = bool(every) != (not ok)
    return row


# ---------------------------------------------------------------------------


# What the cell says back when it refuses a proposal. The validator's own
# reason string and nothing else: no hint, no restatement of the rule, no
# naming of the field the rung removed. Adding anything here would turn the
# repair condition into a different manipulation.
REPAIR_FEEDBACK = (
    "That assignment was rejected by the cell.\n"
    "Reason: {why}\n"
    "Answer again with a different assignment, or task_id -1 to wait.")


def replay_one(probe, rung="recorded", condition="A", alias=None,
               model_fn=openai_chat, timeout=60.0, baskets=None, repair=1,
               design="v1", directive="none"):
    """One probe: render, ask, validate, record. Never raises on a model
    error; the row carries the error so a long run does not die on one
    timeout.

    REPAIR (k > 1). On a rejection the validator's reason is handed back and
    the model is asked again, up to `repair` attempts. This answers the
    standing objection that a single-shot number denies the model the
    correction loop every deployed system has: LTAA retries three times,
    LaMMA-P falls back to the LLM, SPCA allows eight repairs and reports
    that repair roughly doubles success.

    THE TOP-LEVEL FIELDS ALWAYS DESCRIBE ATTEMPT 1. result, violation,
    decision, latency and the rest are the first answer, so a repair run is
    poolable with every single-shot run already banked and Accepted@1
    cannot move. Later attempts live in repair_history, and accepted_at
    says which attempt succeeded (1, 2, ... or None).

    A NOTE ON WHAT FEEDBACK SUPPLIES. At L3-nowidth the reason reads "arm
    franka_s cannot grasp object ycb_large_clamp", which states the binding
    constraint the rung removed, in a different form. So repair is a THIRD
    route to the width, alongside the name and the image, and it must be
    reported as its own condition rather than folded into the rung's rate.
    Since the ladder has shown the other two routes closed, this is the one
    channel left worth testing.

    Only rejections are retried. An unparseable reply has no binding cause
    to return, and a noop is a decision rather than a failure."""
    baskets = baskets or _baskets()
    dspec = design_spec(design)
    if design == "v2" and rung != "recorded":
        # The CANONICAL name is recorded, never the alias that was typed.
        # A file holding both "L3" and "full" rows would need a second table
        # to be grouped, and that table would be one more place for the two
        # designs to disagree about what a cell is.
        rung = EX1P2.canonical(rung)
    if design != "v2" and directive != "none":
        raise ValueError(
            f"directive {directive!r} was given for design {design!r}. The "
            f"directives are a v2 construct and v1 has no anchor to insert "
            f"one at, so a v1 row carrying a directive label would claim a "
            f"manipulation the prompt does not contain.")
    messages, state, mapping = render(probe, rung, condition, return_map=True,
                                      design=design, directive=directive)
    derived = dict(probe.get("derived", {}))
    causes = derived.get("binding_causes") or {}

    row = {
        "provenance": dict(probe["provenance"]),
        "rung": rung,
        "condition": condition,
        # The design and the directive are separate columns, not encoded in
        # the rung name, so analysis can group by either without parsing a
        # string. "design" is v1 or v2; "directive" is a v2 treatment.
        "design": design,
        "directive": directive if design == "v2" else None,
        "prompt_version": prompt_version(state),
        "ex1_prompt_version": (None if rung == "recorded"
                               else dspec["version"]),
        "rung_flags": (None if rung == "recorded"
                       else rung_spec(rung, design)),
        "prompt_chars": len(messages[0]["content"]),
        "model_alias": alias,
        "derived": derived,
        # Stratifiers, promoted so the crossing of binding cause against
        # violation type needs no join.
        #
        # binding_cause is the MODAL cause on this state and binds_* is
        # "this cause binds at least one pair". They give very different
        # denominators (grasp: 60 states modal against 122 any-pair on the
        # frozen EX1 set), because modal labelling files a state with eight
        # grasp-binding pairs and nine reach-binding ones under reach and
        # discards its grasp evidence. Both are carried; which one defines
        # the primary endpoint is an analysis decision, not a runner one.
        "binding_cause": derived.get("binding_cause"),
        "binding_causes": causes,
        "n_legal_pairs": derived.get("n_legal_pairs"),
        "zero_legal": derived.get("n_legal_pairs") == 0,
        # Naming scheme, because BASKET_MISSING counts and basket_correct
        # are NOT comparable across schemes: at an anonymised rung the
        # sorting decision is index matching rather than semantic recall.
        "naming": "anonymised" if mapping is not None else "real",
    }
    for c in ("grasp", "reach", "delicate", "payload", "no_route"):
        row["binds_" + c] = causes.get(c, 0) > 0
    if mapping is not None:
        # Kept per row so an anonymised trial is auditable after the fact.
        # Aliases are dense per state, so the map is not reconstructable
        # from the rung name alone.
        row["alias_map"] = {"objects": mapping["objects"],
                            "baskets": mapping["baskets"]}

    t0 = time.time()
    try:
        try:
            text = model_fn(messages, timeout=timeout, alias=alias)
        except TypeError:                 # injected model_fn predates alias
            text = model_fn(messages, timeout=timeout)
        row["error"] = None
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"
        row["latency_ms"] = round((time.time() - t0) * 1000.0, 1)
        return row
    row["latency_ms"] = round((time.time() - t0) * 1000.0, 1)
    row["raw"] = text

    decision = parse_decision(text)
    row["decision"] = decision
    if decision is None:
        row["result"] = "unparseable"
        row["violation"] = "PARSE"
        row["violation_rule"] = VIOLATION_RULE.get("PARSE")
        row["violation_cause"] = "parse"
        return row

    # The validator, the router and the scorer all work in REAL names: the
    # coordinator is rebuilt from the original probe, not from the rendered
    # state. Only the reply arrives in aliases, and only its basket field
    # is affected. An unmappable value is passed through unchanged so the
    # validator rejects it, because repairing it here would turn a model
    # error into a silent pass.
    if mapping is not None:
        decision, alias_info = EX1A.deanonymise_decision(decision, mapping)
        row.update(alias_info)
        # A REAL basket name at an anonymised rung is a name the model was
        # never shown. It is legal, and it is also direct evidence of
        # retrieved identity knowledge, so it gets its own column.
        row["real_name_emitted"] = (
            alias_info.get("basket_alias") in (baskets or {}))

    if decision.get("task_id") in (-1, None):
        row["result"] = "noop"
        row["model_reason"] = decision.get("reason", "")
        return row

    coord = from_record(probe)
    # Whether the destination was OPEN before this decision. validate_decision
    # writes task.dest on success, so it has to be read first. It matters
    # because the basket field is only a DECISION when the task had no
    # destination: on a task that already has one the validator ignores the
    # field, and scoring it would report a sorting error the model was never
    # asked to make.
    _t = next((t for t in coord.pool if t.id == decision.get("task_id")), None)
    dest_was_open = _t is not None and _t.dest is None
    ok, target, sub, why = validate_decision(dict(decision), coord, zonemap(),
                                             baskets)
    row.update({
        "result": "valid" if ok else "rejected",
        "task_id": decision.get("task_id"),
        "arm": decision.get("arm"),
        "basket": decision.get("basket"),
        "model_reason": decision.get("reason", ""),
        "rejected_because": why or None,
        "route_inserted": sub is not None,
        "via_pad": _pad_name(target) if sub is not None else None,
    })
    _attach_violation(row, why, decision, probe, ok, baskets,
                      design=design)

    if ok:
        task = next(t for t in coord.pool
                    if t.id == decision.get("task_id"))
        _score_quality(row, probe, coord, task, sub, baskets,
                       dest_was_open)

    row["attempts_allowed"] = repair
    row["accepted_at"] = 1 if ok else None
    if ok or repair <= 1:
        return row

    # ---- repair -----------------------------------------------------------
    history = []
    convo = list(messages)
    for attempt in range(2, repair + 1):
        fb = REPAIR_FEEDBACK.format(why=why)
        convo = convo + [{"role": "assistant", "content": text},
                         {"role": "user", "content": fb}]
        sub_row = {"attempt": attempt, "feedback_sent": fb}
        t1 = time.time()
        try:
            try:
                text = model_fn(convo, timeout=timeout, alias=alias)
            except TypeError:
                text = model_fn(convo, timeout=timeout)
            sub_row["error"] = None
        except Exception as e:
            sub_row["error"] = f"{type(e).__name__}: {e}"
            sub_row["latency_ms"] = round((time.time() - t1) * 1000.0, 1)
            history.append(sub_row)
            break
        sub_row["latency_ms"] = round((time.time() - t1) * 1000.0, 1)
        sub_row["raw"] = text

        d2 = parse_decision(text)
        sub_row["decision"] = d2
        if d2 is None:
            sub_row.update(result="unparseable", violation="PARSE",
                           violation_cause="parse")
            history.append(sub_row)
            continue
        if mapping is not None:
            d2, info2 = EX1A.deanonymise_decision(d2, mapping)
            sub_row.update(info2)
        if d2.get("task_id") in (-1, None):
            # Declining AFTER being told why is a different act from
            # declining first: the model has been handed the binding
            # constraint and still will not commit.
            sub_row.update(result="noop",
                           model_reason=d2.get("reason", ""))
            history.append(sub_row)
            break

        coord = from_record(probe)      # fresh: the validator writes to it
        ok, target, sub, why = validate_decision(dict(d2), coord, zonemap(),
                                                 baskets)
        sub_row.update({
            "result": "valid" if ok else "rejected",
            "task_id": d2.get("task_id"), "arm": d2.get("arm"),
            "basket": d2.get("basket"),
            "model_reason": d2.get("reason", ""),
            "rejected_because": why or None,
            "route_inserted": sub is not None,
            "repeated_same_pair": (d2.get("task_id") == row.get("task_id")
                                   and d2.get("arm") == row.get("arm")),
        })
        _attach_violation(sub_row, why, d2, probe, ok, baskets,
                          design=design)
        history.append(sub_row)
        if ok:
            row["accepted_at"] = attempt
            break

    row["repair_history"] = history
    return row


def _score_quality(row, probe, coord, task, sub, baskets,
                   dest_was_open=True):
    """Measured, never vetoed: the things a legal decision can still get
    wrong. Each of these is invisible to the legality rate."""
    zm = zonemap()
    p = coord.cell.scene[task.obj].data.root_pos_w[0]
    oxy = (float(p[0]), float(p[1]))

    # Semantic sorting (G1). Under the 2026-08-01 rules a wrong but
    # reachable basket is perfectly legal, so nothing else catches it.
    spec = C.OBJECT_SPECS.get(task.obj, {})
    cat = spec.get("category")
    if cat and dest_was_open and row.get("basket") in baskets:
        row["basket_expected"] = f"basket_{cat}"
        row["basket_correct"] = row["basket"] == row["basket_expected"]

    # A two-trip handover chosen while a one-trip arm was free. This is the
    # judgement measure that replaced unnecessary_pad once the model
    # stopped naming pads.
    if sub is not None and task.dest is not None:
        direct = [a for a in idle_arms(coord)
                  if C.can_grasp(a, task.obj)
                  and zm.reachable(a, *oxy)
                  and zm.reachable(a, *task.dest)]
        row["avoidable_relay"] = bool(direct)
        row["direct_idle_arms"] = direct

        # The model claiming a direct delivery on a round the router had to
        # rescue. In the seed episode it said "ur_e can reach the drill and
        # deliver it to basket_tools" when ur_e cannot reach that basket at
        # all. The action was legal; the belief behind it was false, and
        # only the reason text shows that.
        txt = (row.get("model_reason") or "").lower()
        row["claimed_direct_but_routed"] = any(
            k in txt for k in ("deliver", "directly", "take it to",
                               "bring it to"))
    return row


def _load_done(path, probe_set, rung, condition, alias,
               design="v1", directive="none"):
    """Rows already on disk, as {(seq, source, repeat)}, for --resume.

    Refuses to resume across a mismatch. A file whose probe set hash, rung,
    condition or model differs from the run being started is a DIFFERENT
    experiment, and appending to it would splice two of them into one file
    that nothing downstream could separate. Better to stop here than to
    discover it in a results table.

    Rows carrying an error are NOT counted as done: a timeout or a 429 is
    exactly what a resume exists to retry.

    A process killed mid-write leaves a truncated final line. That line is
    dropped and counted, because silently discarding data is worse than the
    crash that caused it.
    """
    done, bad, errored = set(), 0, 0
    keep = []
    want_hash = probe_set.get("hash")
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                bad += 1
                continue
            for field, want, got in (("probe set", want_hash,
                                      r.get("probe_set_hash")),
                                     ("rung", rung, r.get("rung")),
                                     ("condition", condition,
                                      r.get("condition")),
                                     ("model", alias, r.get("model_alias")),
                                     # A v1 row and a v2 row answer
                                     # different questions on states that
                                     # are not comparable, and a directive
                                     # is a different manipulation of the
                                     # same cell. Splicing either pair into
                                     # one file would be unrecoverable.
                                     ("design", design, r.get("design")),
                                     ("directive",
                                      directive if design == "v2" else None,
                                      r.get("directive"))):
                if want is not None and got is not None and want != got:
                    raise ValueError(
                        f"cannot resume {path}: it holds rows with "
                        f"{field} {got!r} but this run is {want!r}. "
                        f"Appending would splice two experiments into one "
                        f"file. Use a new --out path.")
            if r.get("error"):
                errored += 1
                continue
            prov = r.get("provenance") or {}
            key = (prov.get("seq"), prov.get("source"), r.get("repeat", 1))
            if key in done:
                bad += 1          # duplicate from an earlier bad resume
                continue
            done.add(key)
            keep.append(line)

    # Rewrite the file with only the clean rows before anything is appended.
    # A process killed mid-write leaves a truncated final line with no
    # newline, and appending after it would CONCATENATE the next row onto
    # the fragment, producing a line that every downstream reader crashes
    # on. Errored and duplicate rows are dropped here too, because they are
    # about to be retried and two rows for one (state, repeat) would be
    # counted twice in every rate.
    #
    # Written to a temp file and renamed, so an interruption during the
    # rewrite cannot destroy a paid run: either the old file survives whole
    # or the new one does.
    if bad or errored:
        tmp = path + ".resume-tmp"
        with open(tmp, "w") as f:
            for line in keep:
                f.write(line + "\n")
        os.replace(tmp, path)
    return done, bad, errored


def replay_set(probe_set, rung="recorded", condition="A", alias=None,
               model_fn=openai_chat, timeout=60.0, out=None, baskets=None,
               progress=False, repeats=1, repair=1, resume=False,
               design="v1", directive="none"):
    """Run every probe, optionally several times each.

    repeats defaults to 1, so nothing already run changes meaning. Each row
    carries "repeat" (1-based) and "n_repeats".

    Repeats are asked STATE BY STATE (r1, r2, r3 for probe 1, then probe 2)
    rather than in passes over the whole set, so a crash or quota
    exhaustion leaves complete triples for every finished state instead of
    one complete pass and two useless partial ones. Nothing is seeded or
    de-duplicated: sampling variance is the thing being measured.

    WHAT REPEATS BUY, AND WHAT TO COMPUTE FROM THEM. 78 percent of picking
    states admit more than one legal pair (median 4), so "did the model
    answer the same three times" is meaningless as a consistency measure: a
    competent model may legitimately alternate between right answers.
    Consistency is therefore measured on the OUTCOME (valid, rejected,
    noop), where flipping between valid and rejected on the same state is
    the signature of guessing. CHOICE consistency (same task and arm all
    three times) is meaningful only on states with exactly one legal pair,
    28 of 126 in ex1_v2, and is reported on that subset alone. Per-scene
    majority over repeats remains the unit of analysis, as in EX2.
    """
    if repeats < 1:
        raise ValueError(f"repeats={repeats}: a run that asks nothing "
                         f"writes an empty file that looks like a result")
    if resume and not out:
        raise ValueError("--resume needs --out: there is nothing to resume "
                         "from without a file on disk")

    done = set()
    if resume and out and os.path.exists(out):
        done, bad, errored = _load_done(out, probe_set, rung, condition,
                                        alias, design, directive)
        if progress:
            print(f"resuming {out}: {len(done)} rows already complete"
                  + (f", {errored} errored rows will be retried"
                     if errored else "")
                  + (f", {bad} unusable line(s) dropped and the file "
                     f"rewritten clean" if bad else ""),
                  file=sys.stderr)

    rows = []
    n = len(probe_set["probes"])
    fh = open(out, "a" if (resume and done) else "w") if out else None
    try:
        for i, probe in enumerate(probe_set["probes"], 1):
            for rep in range(1, repeats + 1):
                prov = probe["provenance"]
                if (prov.get("seq"), prov.get("source"), rep) in done:
                    continue
                row = replay_one(probe, rung, condition, alias, model_fn,
                                 timeout, baskets, repair=repair,
                                 design=design, directive=directive)
                row["probe_set_hash"] = probe_set.get("hash")
                row["repeat"] = rep
                row["n_repeats"] = repeats
                rows.append(row)
                if fh:
                    fh.write(json.dumps(row, default=str) + "\n")
                    fh.flush()      # a long paid run must survive a crash
                if progress:
                    tag = (f"[{i}/{n}]" if repeats == 1
                           else f"[{i}/{n} r{rep}]")
                    status = (row.get("result")
                              or (f"error {row['error']}" if row.get("error")
                                  else "?"))
                    print(f"{tag} {status}"
                          f"{'' if not row.get('violation') else ' ' + row['violation']}",
                          file=sys.stderr)
    finally:
        if fh:
            fh.close()
    return rows


# ---------------------------------------------------------------------------
# acceptance test
# ---------------------------------------------------------------------------

def verify_trail(path, episode=None, baskets=None):
    """Replay a live episode's consults and demand exact agreement.

    Two claims, and BOTH must be checked or the test is worthless.

    1. The prompt this module builds from the saved state is BYTE-IDENTICAL
       to the prompt the live run sent. Needs only the trail.
    2. The validator run against the rebuilt coordinator returns the same
       verdict, including the reason string, for every decision the live
       run judged. Needs the EPISODE JSON as well, because the trail holds
       states and prompts while the decisions and their verdicts live in
       the allocator log.

    Passing both means every offline number is comparable to the live
    episodes. Failing either means the shim is lying, and every replayed
    number would be wrong in the same direction with nothing looking
    obviously broken.

    Called without `episode` the report says verdicts_checked = 0. That is
    a HALF-DONE test, not a pass. An earlier version of this function
    silently offered only claim 1.
    """
    baskets = baskets or _baskets()
    frames_dir = os.path.dirname(os.path.abspath(path))
    report = {"trail": path, "episode": episode, "consults": 0,
              "prompt_ok": 0, "prompt_mismatch": [], "verdict_ok": 0,
              "verdict_mismatch": [], "verdicts_checked": 0,
              "verdicts_unverifiable": 0, "notes": []}
    probes = []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            report["consults"] += 1
            probe = {"state": rec["state"],
                     "positions_exact": rec.get("positions_exact"),
                     "frame": rec.get("image_file"),
                     "frame_path": (os.path.join(frames_dir,
                                                 rec["image_file"])
                                    if rec.get("image_file") else None),
                     "provenance": {"seq": rec.get("seq"),
                                    "round": rec.get("round")}}

            probes.append(probe)

            sent = rec.get("messages") or []
            built, _ = render(probe, "recorded", rec.get("condition", "A"))
            if _prompts_match(built, sent):
                report["prompt_ok"] += 1
            else:
                report["prompt_mismatch"].append(
                    _first_difference(rec.get("seq"), built, sent))

    if episode:
        _verify_verdicts(report, probes, episode, baskets)
    else:
        report["notes"].append(
            "no episode JSON given, so no verdict was checked. Pass "
            "--episode out/<name>.json for the other half of the test.")
    return report


def _decisions_of(entry):
    """(decision, expected_ok, expected_reason) for one allocator log entry.

    Rejected proposals carry task_id, arm and basket since schema v4.
    Accepted ones only carry basket from 2026-08-01 onward, so an older
    trail cannot have its accepted decisions rebuilt: without the basket a
    destination-free task would be re-judged as BASKET_MISSING, which would
    be a false alarm about the shim. Those are reported as unverifiable
    rather than silently skipped or wrongly failed.
    """
    out, unverifiable = [], 0
    for r in entry.get("rejected", []) or []:
        if r.get("unparseable") or r.get("task_id") is None:
            continue
        out.append(({"task_id": r["task_id"], "arm": r.get("arm"),
                     "basket": r.get("basket")},
                    False, r.get("rejected_because") or ""))
    if str(entry.get("result", "")).startswith("valid"):
        if "basket" in entry:
            out.append(({"task_id": entry["task_id"], "arm": entry.get("arm"),
                         "basket": entry.get("basket")}, True, ""))
        else:
            unverifiable += 1
    return out, unverifiable


def _consult_entries(log):
    """Allocator log entries that came from a MODEL CONSULT.

    Not every log entry has a consult behind it. A "rule_assigned" round is
    one the rule allocator handled without the model being asked, so it is
    written to the log and leaves no trail record: no prompt, no state, no
    latency. An earlier version of this function assumed one entry per
    consult and refused to align a perfectly good pair of files.

    Two independent signals are used and cross-checked, because getting
    this wrong silently would misalign every verdict comparison: the
    result label, and the presence of latency_ms, which only a round that
    actually called a model can have.
    """
    by_result = [e for e in log if e.get("result") != "rule_assigned"]
    by_latency = [e for e in log if "latency_ms" in e]
    return by_result, by_latency


def _verify_verdicts(report, probes, episode, baskets=None):
    baskets = baskets or _baskets()
    with open(episode) as f:
        data = json.load(f)
    raw_log = (data.get("allocator") or {}).get("log") or []
    log, by_latency = _consult_entries(raw_log)
    skipped = len(raw_log) - len(log)
    if skipped:
        report["notes"].append(
            f"{skipped} rule_assigned round(s) skipped: the rule allocator "
            f"handled them without consulting the model, so they have no "
            f"trail record to align against.")
    if len(by_latency) != len(log):
        report["notes"].append(
            f"the two consult signals disagree: {len(log)} entries are not "
            f"rule_assigned but {len(by_latency)} carry latency_ms. "
            f"Alignment used the result label; treat the verdict half as "
            f"unconfirmed until this is understood.")

    if len(log) != len(probes):
        report["notes"].append(
            f"after removing rule_assigned rounds the allocator log has "
            f"{len(log)} entries against {len(probes)} consults, so they "
            f"cannot be aligned. A difference here means the two files are "
            f"from different runs.")
        return

    for probe, entry in zip(probes, log):
        p_round = probe["provenance"].get("round")
        if p_round is not None and entry.get("round") != p_round:
            report["verdict_mismatch"].append(
                {"seq": probe["provenance"].get("seq"),
                 "why": f"round {entry.get('round')} vs {p_round}"})
            continue
        decisions, unver = _decisions_of(entry)
        report["verdicts_unverifiable"] += unver
        for decision, want_ok, want_why in decisions:
            # A FRESH coordinator per decision: validate_decision persists
            # task.dest on success, so reusing one would let an earlier
            # accepted basket change a later verdict.
            coord = from_record(probe)
            ok, _, _, why = validate_decision(dict(decision), coord,
                                              zonemap(), baskets)
            report["verdicts_checked"] += 1
            if ok == want_ok and (why or "") == (want_why or ""):
                report["verdict_ok"] += 1
            else:
                report["verdict_mismatch"].append(
                    {"seq": probe["provenance"].get("seq"),
                     "decision": decision,
                     "live": {"ok": want_ok, "why": want_why},
                     "offline": {"ok": ok, "why": why}})
    if report["verdicts_unverifiable"]:
        report["notes"].append(
            f"{report['verdicts_unverifiable']} accepted decisions could not "
            f"be rebuilt: this trail predates the accepted-decision 'basket' "
            f"field (added 2026-08-01). Rejections are unaffected. A fresh "
            f"episode verifies both halves.")


def _text_of(messages):
    """System text plus the user's TEXT blocks. Image bytes are excluded:
    the audit trail sanitises them to a placeholder, so comparing them
    would compare the sanitiser, not the prompt."""
    out = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, list):
            for b in c:
                if b.get("type") == "text":
                    out.append(b.get("text", ""))
    return out


def _prompts_match(built, sent):
    return _text_of(built) == _text_of(sent)


def _first_difference(seq, built, sent):
    a, b = _text_of(built), _text_of(sent)
    if len(a) != len(b):
        return {"seq": seq, "why": f"block count {len(a)} vs {len(b)}"}
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            for j, (cx, cy) in enumerate(zip(x, y)):
                if cx != cy:
                    return {"seq": seq, "block": i, "char": j,
                            "built": x[max(0, j - 40):j + 40],
                            "sent": y[max(0, j - 40):j + 40]}
            return {"seq": seq, "block": i,
                    "why": f"length {len(x)} vs {len(y)}",
                    "built_tail": x[len(y):][:80],
                    "sent_tail": y[len(x):][:80]}
    return {"seq": seq, "why": "unknown"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", help="probe set JSON")
    ap.add_argument("--rung", default="recorded")
    ap.add_argument("--design", default="v1", choices=sorted(DESIGNS),
                    help="v1 is the published contended-cell experiment; "
                         "v2 is the serialised redesign, with the prompt "
                         "rebuilt on Experiment 2's base, its field aliases "
                         "and one rule ablation per constraint. Recorded on "
                         "every row and checked on --resume: the two are "
                         "answered on states that are not comparable")
    ap.add_argument("--directive", default="none", choices=list(DIRECTIVES),
                    help="v2 only. A prompt-level treatment added at one "
                         "anchor: recall names memory as a source to use, "
                         "report asks for the judged opening before the arm "
                         "is named, elicit additionally asks the arm to be "
                         "chosen to fit it")
    ap.add_argument("--condition", default="A", choices=["A", "V"])
    ap.add_argument("--model", default=None, help="registry alias")
    ap.add_argument("--out", default=None, help="JSONL output")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true",
                    help="allow --out to overwrite an existing file")
    ap.add_argument("--resume", action="store_true",
                    help="skip rows already in --out and append. Retries "
                         "any row that carries an error.")
    ap.add_argument("--repair", type=int, default=1, metavar="K",
                    help="attempts per probe; on rejection the validator's "
                         "reason is handed back. 1 = current behaviour")
    ap.add_argument("--repeats", type=int, default=1,
                    help="model calls per state (default 1); rows carry "
                         "'repeat' so analysis can group by state")
    ap.add_argument("--dry-run", action="store_true",
                    help="render prompts only, no model call, no spend")
    ap.add_argument("--verify", metavar="CONSULTS_JSONL",
                    help="acceptance test against a live trail")
    ap.add_argument("--episode", metavar="EPISODE_JSON",
                    help="episode JSON for the verdict half of --verify")
    args = ap.parse_args(argv)

    if args.verify:
        rep = verify_trail(args.verify, args.episode)
        print(json.dumps({k: v for k, v in rep.items()
                          if k not in ("prompt_mismatch",
                                       "verdict_mismatch")}, indent=1))
        bad = False
        if rep["prompt_mismatch"]:
            bad = True
            print("\nFIRST PROMPT MISMATCHES:")
            for m in rep["prompt_mismatch"][:3]:
                print(json.dumps(m, indent=1))
        if rep["verdict_mismatch"]:
            bad = True
            print("\nFIRST VERDICT MISMATCHES:")
            for m in rep["verdict_mismatch"][:3]:
                print(json.dumps(m, indent=1, default=str))
        if bad:
            return 1
        print(f"\nACCEPTANCE")
        print(f"  prompts  byte-identical on "
              f"{rep['prompt_ok']}/{rep['consults']} consults")
        if rep["verdicts_checked"]:
            print(f"  verdicts identical on "
                  f"{rep['verdict_ok']}/{rep['verdicts_checked']} decisions, "
                  f"reason strings included")
        else:
            print("  verdicts NOT CHECKED. This is half a test: pass "
                  "--episode out/<name>.json for the other half.")
            return 2
        return 0

    if not args.probes:
        ap.error("--probes is required unless --verify is given")
    ps = load_probes(args.probes)
    # A run file is a PAID artefact: replay_set opens --out with "w", so an
    # existing file is truncated the moment the new run starts, and 27
    # minutes of model calls are unrecoverable from that point. A command
    # recalled from shell history is exactly how that happens (it did, on
    # 2026-08-16: the first GPT L1-nowidth run, 486 rows, was destroyed by
    # re-running its own command line). refreeze_probe_set already refuses
    # to overwrite probe sets for the same reason.
    # --resume is the one safe case: replay_set opens the file with "a",
    # reads what is already there, and skips it. Blocking it here would
    # make the guard forbid the very thing that recovers an interrupted
    # run, which is the situation the guard exists to protect against.
    if (args.out and os.path.exists(args.out)
            and not args.force and not args.resume):
        raise SystemExit(
            f"{args.out} already exists ({os.path.getsize(args.out)} bytes). "
            f"Refusing to overwrite a run file: it would be truncated the "
            f"moment this run starts, and the rows in it cost real model "
            f"calls. Pass --resume to continue it, choose a new name, or "
            f"pass --force if destroying it is intended.")

    if args.limit:
        ps = dict(ps, probes=ps["probes"][:args.limit])

    # The serialisation check runs before any spend, not after it. A v2 run
    # on a contended set renders perfectly well and would be reported under
    # a serialised label, understating how often the opening can bind.
    if args.design == "v2" and args.rung != "recorded":
        EX1P2.assert_states_are_serialised(ps["probes"])

    if args.dry_run:
        for probe in ps["probes"]:
            messages, _ = render(probe, args.rung, args.condition,
                                 design=args.design,
                                 directive=args.directive)
            print(f"seq {probe['provenance'].get('seq')} rung {args.rung} "
                  f"chars {len(messages[0]['content'])}")
        return 0

    rows = replay_set(ps, args.rung, args.condition, args.model,
                      out=args.out, progress=True, repeats=args.repeats,
                      repair=args.repair, resume=args.resume,
                      design=args.design, directive=args.directive)
    counts, viol, cause, rule, first_only = {}, {}, {}, {}, 0
    for r in rows:
        counts[r.get("result", "error")] = counts.get(
            r.get("result", "error"), 0) + 1
        if r.get("violation"):
            viol[r["violation"]] = viol.get(r["violation"], 0) + 1
        if r.get("violation_cause"):
            cause[r["violation_cause"]] = cause.get(
                r["violation_cause"], 0) + 1
        if r.get("violation_rule"):
            rule[r["violation_rule"]] = rule.get(r["violation_rule"], 0) + 1
        # Every constraint broken, not only the one the guard stopped at.
        for c in (r.get("violation_all") or []):
            first_only = first_only or {}
            first_only[c] = first_only.get(c, 0) + 1
    print(json.dumps({"n": len(rows), "results": counts,
                      "violations": viol,
                      "cause_first": cause,
                      "cause_all": first_only or {},
                      "rule": rule,
                      "disagreements": sum(1 for r in rows
                                           if r.get("diagnostic_disagrees")),
                      "probe_set_hash": ps.get("hash", "")[:12]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())