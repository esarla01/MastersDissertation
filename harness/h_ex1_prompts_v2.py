"""h_ex1_prompts_v2: the EX1 v2 redesign holds its own design claims.

The v1 harness (h_ex1_prompts.py) pins the published experiment and is left
alone. This one pins the redesign, and every check here corresponds to a
property the redesign would be worthless without.

What is pinned, and the failure each one guards:

  1. Every condition declares all five flags. A missing flag reads as
     False or None and silently redefines a condition.
  2. Each adjacent pair on the spine differs in EXACTLY ONE flag. This is
     the whole design claim: if two things move at once, the gap between
     those cells is not attributable to either.
  3. No rule cites another, except R6's scope pointer at R7. A cited rule
     cannot be withheld alone, and that is precisely why v1 had to withhold
     its capability and reach rules as a pair.
  4. Each norules cell moves exactly one rule block and no other.
  5. The withheld text names no state field and instructs no derivation.
     Naming a field leaves the instruction standing under a withheld label;
     "work it out from the numbers" makes the cell a paraphrase of the full
     one.
  6. The glossary names exactly the fields the state carries, per
     condition, in both directions.
  7. NO CELL OPENS A DERIVATION ROUTE. No size, no extent, no resting face,
     no bounding-box convention, in any condition and under any directive.
     This is the single most consequential thing Experiment 1 must not
     acquire: with a route from shape to opening it stops being a study of
     retrieval.
  8. The field aliases ARE Experiment 2's, by identity and not by
     coincidence, minus the two entries that would open that route.
  9. The congestion language is gone from the prompt, the state and the
     answer schema, and the waiting rule survives re-scoped rather than
     removed. Removing it would cost the correct-refusal endpoint.
 10. A directive that asks for the opening is REFUSED where the state
     supplies it. Reporting a number the state just gave is a copy
     instruction, not an elicitation.
 11. The rendered state carries the aliased names and none of the original
     ones, on a real state rather than a constructed one.
 12. A contended state is REFUSED by the serialisation check. A set
     harvested from a contended cell renders perfectly well and would be
     reported under a serialised label.
 13. The serialised coordinator offers one task and holds the round until
     every arm is idle, and the contended coordinator still behaves exactly
     as it did.
 14. Unknown conditions, unknown directives, an anonymised cell with no
     mapping and a named cell with one all RAISE.

Run:
    python3 harness/h_ex1_prompts_v2.py
"""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from experiments.ex1 import prompts_v2 as P                     # noqa: E402
from experiments.ex2 import prompts as EX2P                     # noqa: E402
from experiments.ex1 import anonymise as A                      # noqa: E402

fails = []


def check(name, ok, why=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (
        "" if ok or not why else "\n          " + why))
    if not ok:
        fails.append(name)


def raises(fn, *a, **kw):
    """Exception type name, or None if the call succeeded."""
    try:
        fn(*a, **kw)
    except Exception as e:                                   # noqa: BLE001
        return type(e).__name__
    return None


FLAGS = ("declared_width", "names", "eligible", "mislabel", "withhold_rule")
PROBES = os.path.join(ROOT, "probes", "ex1_v2.json")


def serialised(probe):
    """A copy of a v1 probe made serialised: one queued task, all arms idle.

    Constructed rather than harvested because the harness must run with no
    simulator and before any v2 episode exists. It exercises the rendering
    path on a REAL state with real objects, positions and reach lists,
    which a hand-written dict would not.
    """
    p = copy.deepcopy(probe)
    st = p["state"]
    q = [t for t in st.get("tasks", [])
         if str(t.get("status", "")).startswith("queued")]
    st["tasks"] = q[:1]
    for a in st["arms"]:
        a["state"] = "IDLE"
        a["disabled"] = False
        a["holding"] = None
    return p


# ---------------------------------------------------------------------------
print("\n1. the condition table")
# ---------------------------------------------------------------------------

check("every condition declares all five flags",
      all(set(FLAGS) == set(v) for v in P.CONDITIONS.values()),
      "a flag read from a missing key defaults to False or None and "
      "quietly redefines the condition")

check("mislabel is never combined with withheld names",
      all(not v["mislabel"] or v["names"] is True
          for v in P.CONDITIONS.values()),
      "anonymising a swapped name erases the swap, so the run would be a "
      "nowidth-anon result reported under a swap label")

check("only the norules cells withhold a rule",
      all((v["withhold_rule"] is not None) == (k in P.RULE_CELLS)
          for k, v in P.CONDITIONS.items()))

check("the spine is the three data-axis conditions in order",
      P.SPINE == ("full", "nowidth", "nowidth-anon"))

check("the spine removes exactly one thing per step",
      raises(P.assert_spine_is_one_removal) is None,
      "if two things move at once the gap is not attributable to either")

check("every v1 rung name resolves to a v2 condition",
      all(v in P.CONDITIONS for v in P.CONDITION_ALIASES.values())
      and set(P.CONDITION_ALIASES) >= {"L3", "L3-nowidth", "L1-nowidth",
                                       "L2", "L4"},
      "a command line typed from the v1 chapter must resolve rather than "
      "silently name nothing")

check("the four factorial cells are the four crossings",
      sorted(P.FACTORIAL.values())
      == sorted(["full", "nowidth", "anon", "nowidth-anon"]))

check("unknown conditions raise", raises(P.condition_spec, "L9") is not None)
check("unknown directives raise", raises(P.directive_spec, "hint") is not None)

# ---------------------------------------------------------------------------
print("\n2. the rules are separable")
# ---------------------------------------------------------------------------

check("no rule cites another except R6 -> R7",
      raises(P.assert_rules_are_separable) is None,
      "a cited rule cannot be withheld alone: withholding it leaves a "
      "dangling reference, which is a defect rather than a manipulation")

def _flat(t):
    """One line, single-spaced. The rule text is wrapped for the prompt, so
    a phrase check has to ignore where the wrapping happened."""
    return " ".join(t.split())


_SCOPE = "Reaching the destination is not required of you"
check("R6 keeps the destination scope statement, withheld or not",
      _SCOPE in _flat(P.R6) and _SCOPE in _flat(P.R6_WITHHELD)
      and _SCOPE in _flat(P.R6_ELIGIBLE),
      "without it the reach ablation differs from the full cell in two "
      "ways: no reach rule AND no assurance about destinations")

for cell in P.RULE_CELLS:
    check(f"{cell} moves exactly one rule",
          raises(P.assert_ablation_is_one_rule, cell) is None)
    check(f"{cell} withholds without naming a field or a comparison",
          raises(P.assert_withheld_names_no_field, cell) is None)

check("all four capability constraints have their own cell",
      {P.CONDITIONS[c]["withhold_rule"] for c in P.RULE_CELLS}
      == {"R3", "R4", "R5", "R6"},
      "the point of the rewrite is one cell per constraint; v1 could only "
      "withhold the capability and reach rules together")

_full = P.system_prompt("full")
check("every condition renders seven rule headers",
      all(sum(1 for n in "1234567" if f"R{n}  " in P.system_prompt(c)) == 7
          for c in P.CONDITIONS),
      "neutralising rather than deleting is what keeps the rule count and "
      "the section structure identical across cells")

# ---------------------------------------------------------------------------
print("\n3. no derivation route, in any cell")
# ---------------------------------------------------------------------------

_bad = []
for c in P.CONDITIONS:
    for d in P.DIRECTIVES:
        if d in ("report", "elicit") and P.CONDITIONS[c]["declared_width"]:
            continue
        if raises(P.assert_no_dimensions_route, c, d) is not None:
            _bad.append(f"{c}/{d}")
check(f"no cell states a size, an extent or a face ({len(_bad)} bad)",
      not _bad,
      f"{_bad}: a route from shape to opening would make Experiment 1 a "
      f"second study of Experiment 2's question")

check("the dims alias is dropped, not renamed",
      "dims_m" not in P.FIELD_ALIASES and "pose" not in P.FIELD_ALIASES,
      "keeping an alias for a field the experiment must never carry is an "
      "invitation to add it")

check("the aliases are Experiment 2's, minus those two",
      all(P.FIELD_ALIASES[k] == EX2P.FIELD_ALIASES[k]
          for k in P.FIELD_ALIASES)
      and set(EX2P.FIELD_ALIASES) - set(P.FIELD_ALIASES)
      == {"dims_m", "pose"},
      "the two chapters must describe one quantity with one word; copied "
      "aliases would drift and imported ones cannot")

check("no state field can carry dimensions",
      raises(P.assert_state_matches_condition,
             {"tasks": [], "objects": [{"dims_m": {"x": 1}}]},
             "full") is not None)

# ---------------------------------------------------------------------------
print("\n4. the glossary and R3 agree with the state")
# ---------------------------------------------------------------------------

for c in P.CONDITIONS:
    check(f"glossary matches the state [{c}]",
          raises(P.assert_glossary_matches_state, c) is None)
    check(f"R3 matches the state [{c}]",
          raises(P.assert_r3_matches_state, c) is None)

check("R3 states the absence rather than naming the withdrawn field",
      P.OPENING_FIELD not in P.system_prompt("nowidth").split(
          "R4  Load")[0].split("R3  Gripper opening")[1],
      "a model reading a rule that names a missing field could conclude "
      "the rule is inapplicable, and a rule-reading failure would then be "
      "scored as a retrieval failure")

# ---------------------------------------------------------------------------
print("\n5. congestion out, the waiting rule re-scoped")
# ---------------------------------------------------------------------------

_txt = P.system_prompt("full")
check("no zone vocabulary survives in the prompt",
      not any(w in _txt for w in ("zone_locks", "zone_inbound", "regions",
                                  "contention", "queue for the same")),
      "with one task at a time no zone is ever contended; an unowned "
      "constraint with no stated holder reads as law and the model waits "
      "on it (measured 2026-08-16: 3 of 126 noops became 24 of 126)")

check("the answer no longer asks for regions or a pad",
      '"regions"' not in _txt and "via_pad" not in _txt)

check("declining is still licensed",
      "Declining is a choice" in _txt,
      "correct refusal is an endpoint; with no licence a refusal is "
      "disobedience rather than a judgement and the endpoint is lost")

check("the congestion clause is gone from the waiting rule",
      "free up soon" not in _txt,
      "with every arm idle it is never true, so it invites waiting on "
      "nothing")

check("the sorting instruction survives",
      'named for its "category"' in _txt,
      "the basket choice is a scored endpoint the validator deliberately "
      "does not check; with no instruction it becomes a preference test")

check("the Franka preference is present",
      "Prefer a Franka arm" in _txt,
      "with every arm idle, naming a UR is always safe, so without it a "
      "model that never reasons about the opening would score full marks")

check("the state trim list is Experiment 2's",
      set(P.TRIM_STATE_KEYS) == set(EX2P.TRIM_STATE_KEYS))

# ---------------------------------------------------------------------------
print("\n6. the directives")
# ---------------------------------------------------------------------------

check("a reporting directive is refused where the opening is stated",
      raises(P.system_prompt, "full", "elicit") is not None
      and raises(P.system_prompt, "full", "report") is not None,
      "reporting a number the state just supplied is a copy instruction, "
      "and the number it produces is not a judgement")

check("recall is allowed everywhere",
      raises(P.system_prompt, "full", "recall") is None
      and raises(P.system_prompt, "nowidth", "recall") is None)

_r = P.system_prompt("nowidth", "recall")
_n = P.system_prompt("nowidth", "none")
check("recall adds one block and changes nothing else",
      _r.replace(P.RECALL_DIRECTIVE, "") == _n,
      "a directive that also moved the schema would confound the source "
      "instruction with the answer order")

check("recall names a source and never a number",
      "opening it needs" in P.RECALL_DIRECTIVE
      and not any(ch.isdigit() for ch in P.RECALL_DIRECTIVE),
      "naming an opening would hand over the measured quantity")

check("report and elicit differ by the instruction to USE the number",
      P.DIRECTIVES["report"]["schema"] == P.DIRECTIVES["elicit"]["schema"]
      and "choose the arm" in P.ELICIT_DIRECTIVE
      and "choose the arm" not in P.REPORT_DIRECTIVE,
      "without the pair, elicit mixes being asked for the number with "
      "being told to act on it")

check("only the reporting cells put the opening in the schema",
      P.OPENING_FIELD not in P.schema_text("base")
      and P.OPENING_FIELD in P.schema_text("opening_first"),
      "naming the opening in every cell's schema would put the quantity "
      "into the prompt of the very cells that withhold it")

# ---------------------------------------------------------------------------
print("\n7. rendering a real state")
# ---------------------------------------------------------------------------

if not os.path.exists(PROBES):
    check("probe set present", False, f"{PROBES} not found")
else:
    _probes = json.load(open(PROBES))["probes"]
    _p = serialised(_probes[0])
    _state = _p["state"]

    check("the serialisation check passes a serialised state",
          raises(P.assert_states_are_serialised, [_p]) is None)

    check("the serialisation check REFUSES a contended state",
          raises(P.assert_states_are_serialised, [_probes[0]]) is not None,
          "a contended set renders perfectly well and would be reported "
          "under a serialised label, understating how often the opening "
          "can bind")

    _msgs = P.build_ex1_prompt(_state, "full")
    _user = _msgs[1]["content"][0]["text"]
    check("the rendered state uses the aliased names",
          all(('"%s"' % v) in _user for v in
              (P.OPENING_FIELD, P.OPENING_MAX_FIELD, P.LOAD_FIELD,
               P.DELICATE_FIELD, P.REACH_FIELD)))
    check("no original field name survives into the state",
          not any(('"%s"' % k) in _user for k in P.FIELD_ALIASES),
          "one unaliased name and the two chapters are describing the same "
          "quantity with two words again")
    check("the trimmed blocks are gone from the rendered state",
          not any(('"%s"' % k) in _user for k in P.TRIM_STATE_KEYS))

    # The opening is a STATE edit, so a full-condition state rendered under
    # nowidth must be refused rather than quietly rendered.
    check("a state and a condition that disagree RAISE",
          raises(P.build_ex1_prompt, _state, "nowidth") is not None,
          "rendering it would put one cell's prompt under another's label")

    _nw = copy.deepcopy(_state)
    for _o in _nw["objects"]:
        _o.pop("grasp_m", None)
    check("the withheld opening is absent from the rendered state",
          ('"%s"' % P.OPENING_FIELD)
          not in P.build_ex1_prompt(_nw, "nowidth")[1]["content"][0]["text"])

    check("an anonymised cell with no mapping RAISES",
          raises(P.build_ex1_prompt, _nw, "nowidth-anon") is not None,
          "nothing could then confirm the state was anonymised at all")

    _an, _map = A.anonymise_state(copy.deepcopy(_nw))
    check("a named cell given a mapping RAISES",
          raises(P.build_ex1_prompt, _state, "full", mapping=_map)
          is not None)

    _bad = 0
    for _q in _probes:
        _s = serialised(_q)["state"]
        for _o in _s["objects"]:
            _o.pop("grasp_m", None)
        _a, _m = A.anonymise_state(_s)
        _mm = P.build_ex1_prompt(_a, "nowidth-anon", mapping=_m)
        if A.find_leaks(_mm[0]["content"] + _mm[1]["content"][0]["text"], _m):
            _bad += 1
    check(f"every probe renders a clean anonymised prompt ({_bad} leaking)",
          _bad == 0,
          "a leak on one state in a hundred is still a leak")

# ---------------------------------------------------------------------------
print("\n8. the serialised coordinator")
# ---------------------------------------------------------------------------
# The gate is checked directly on a stub rather than through a simulator,
# because the harness must run with no Isaac. What is under test is the
# gate's own logic: hold until every arm is idle, offer one task, end the
# round either way.


class _Arm:
    def __init__(self, disabled=False):
        self.disabled = disabled


class _Agent:
    def __init__(self, state="IDLE", disabled=False):
        self.state = state
        self.arm = _Arm(disabled)
        self.claimed = None

    def claim(self, task, target):
        self.claimed = task
        self.state = "BUSY"


class _Task:
    _n = 0

    def __init__(self, obj):
        _Task._n += 1
        self.id = _Task._n
        self.obj = obj
        self.dest = (0.0, 0.0)
        self.done = self.claimed = self.failed = self.held = False
        self.waiting_on = None
        self.dest_by = None
        self.kind = None
        self.submit_tick = 0


class _Scene(dict):
    def __getitem__(self, k):
        class _D:
            class data:
                root_pos_w = [[0.0, 0.0, 0.0]]
        return _D


def _coord(serialised_flag, agent_states, n_tasks):
    from core.control import tasks as T
    c = T.Coordinator.__new__(T.Coordinator)
    c.serialised = serialised_flag
    c.agents = {f"a{i}": _Agent(s) for i, s in enumerate(agent_states)}
    c.pool = [_Task(f"obj{i}") for i in range(n_tasks)]
    c.cell = type("C", (), {"scene": _Scene()})()
    # The refusal branch prints a diagnostic that queries reachability, so
    # the stub answers it. What is under test is the gate, not the geometry.
    c.zonemap = type("Z", (), {"reachable": staticmethod(
        lambda *a, **kw: True)})()
    c._warned = set()
    c.m = type("M", (), {"makespan_ticks": 0, "pad_wait": {}})()
    c.allocate = lambda task, xy, idle, zm, disabled=(): (idle[0], (0, 0),
                                                          None)
    c.event = lambda *a, **kw: None
    c._permanently_unallocatable = lambda t: False
    c._pad_available = lambda xy, obj: True
    return c


_c = _coord(True, ["IDLE", "IDLE", "BUSY"], 3)
_c._assign()
check("serialised: the round is HELD while any arm is busy",
      all(a.claimed is None for a in _c.agents.values()),
      "a round that fired with an arm still folding would harvest a state "
      "with a busy arm under a serialised label")

_c = _coord(True, ["IDLE", "IDLE", "IDLE"], 3)
_c._assign()
check("serialised: exactly one task is claimed per round",
      sum(1 for a in _c.agents.values() if a.claimed is not None) == 1,
      "offering the rest hands task selection back to the allocator, which "
      "is the other half of what serialising buys")

_c = _coord(True, ["IDLE", "IDLE", "IDLE"], 3)
_c.allocate = lambda task, xy, idle, zm, disabled=(): (None, None, None)
_c._assign()
check("serialised: a refused task ends the round rather than offering the "
      "next",
      all(a.claimed is None for a in _c.agents.values()))

_c = _coord(False, ["IDLE", "IDLE", "BUSY"], 3)
_c._assign()
check("contended: the round still fills every idle arm",
      sum(1 for a in _c.agents.values() if a.claimed is not None) == 2,
      "the default must reproduce every episode recorded before the flag "
      "existed, tick for tick")

_c = _coord(True, ["IDLE", "IDLE"], 3)
_c.agents["a1"].arm.disabled = True
_c.agents["a1"].state = "DISABLED"
_c._assign()
check("serialised: a disabled arm never holds the round",
      sum(1 for a in _c.agents.values() if a.claimed is not None) == 1,
      "a disabled arm never reaches IDLE, so counting it would hold every "
      "round forever")

# --- the held queue -------------------------------------------------------
# Serialising the OFFER is only half of it. build_state renders coord.pool,
# so without a held queue every queued task stays visible and the model is
# still choosing which task to serve, which is the thing the redesign
# removes. These exercise the real submit and _release.

from core.control import tasks as T                            # noqa: E402


def _fresh(serialised_flag, n):
    c = _coord(serialised_flag, ["IDLE", "IDLE"], 0)
    c.pool = []
    for i in range(n):
        T.Coordinator.submit(c, f"obj{i}", (0.0, 0.0))
    return c


_c = _fresh(True, 4)
check("serialised: submit holds every task but the first",
      sum(1 for t in _c.pool if not t.held) == 1,
      "a held task is invisible to build_state; without the hold the model "
      "sees the whole queue and picks the task itself")

_c.pool[0].done = True
T.Coordinator._release(_c)
check("serialised: finishing the live task releases exactly one more",
      sum(1 for t in _c.pool if not t.held and not t.done) == 1)

T.Coordinator._release(_c)
check("serialised: release is a no-op while a task is live",
      sum(1 for t in _c.pool if not t.held and not t.done) == 1,
      "releasing a second task would put a choice of tasks back into the "
      "state the model is shown")

_c = _fresh(False, 4)
check("contended: submit holds nothing",
      not any(t.held for t in _c.pool),
      "the default must reproduce every episode recorded before the flag "
      "existed")

_c = _fresh(True, 3)
T.Coordinator._assign(_c)
check("serialised: _assign never offers a held task",
      sum(1 for a in _c.agents.values() if a.claimed is not None) == 1)

check("held defaults to False on every Task",
      "held" in T.Task.__dataclass_fields__
      and T.Task.__dataclass_fields__["held"].default is False,
      "anything recorded before the flag existed must be unaffected")

# ---------------------------------------------------------------------------
print("\n9. the module's own verification")
# ---------------------------------------------------------------------------

for _name, _ok, _why in P.verify_all():
    check(_name, _ok, _why)


print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
