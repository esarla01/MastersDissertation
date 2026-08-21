"""h_ex1_prompts: the EX1 rung table encodes one removal per step, and the
L2 substitution changes R3 and R4 and nothing else.

Renders through the REAL build_prompt against the REAL frozen probe set,
so what is checked is the prompt the model would actually receive on the
states the experiment will actually run.

What is pinned, and the failure each one guards:

  1. Every rung declares all four flags. A missing flag would read as
     False and silently redefine a rung.
  2. Each adjacent pair on the SPINE differs in EXACTLY ONE flag. This is
     the entire design claim of EX1. If two things move at once, the gap
     between those rungs is not attributable to either.
  3. L2 and L4 are each one flag off L3 and neither is on the spine. They
     are a contrast and a control, not steps in the chain.
  4. L3 is byte-identical to the base build_prompt. EX1 adds nothing at
     its own baseline; if it did, every gap would be measured against a
     contaminated reference.
  5. The L2 prompt agrees with the base everywhere before R3 and
     everywhere from R5 onward, on every probe in the frozen set. One
     contiguous change, nowhere else.
  6. The base rule text is GONE from the L2 prompt and PRESENT in the L3
     prompt. Isolation alone would pass if the substitution silently did
     nothing.
  7. The withheld text names none of the state fields the rule used:
     grasp_m, max_grasp_m, mass_kg, payload_kg, delicate_ok,
     reach_ok_arms. Naming one would leave the instruction standing under
     a withheld label.
  8. The withheld text does not instruct derivation. "Work it out from
     the numbers" is the instruction L2 exists to remove, and putting it
     back in different words would make L2 a paraphrase of L3.
  9. R3 and R4 keep their headers and R7's references to R3 and R5 still
     resolve. This is why the rules are neutralised rather than deleted:
     a prompt citing a rule that is not in it is a defect, not a
     manipulation.
 10. Substitution against text missing the block RAISES. The drift guard
     is the only thing standing between a state_builder edit and a run of
     unmodified prompts recorded under EX1 rung labels.
 11. Unknown rungs, condition V without an image, and a rung whose state
     disagrees with it all raise rather than defaulting.
 12. An anonymised rung refuses while anonymise.py is absent, rather than
     sending real object names under an anonymised label.

Run:  python3 h_ex1_prompts.py
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

from core.decision import state_builder as sb                   # noqa: E402
from experiments.ex1 import prompts as P                        # noqa: E402

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
    except Exception as e:
        return type(e).__name__
    return None


PROBES = os.path.join(ROOT, "probes", "ex1_v1.json")
FLAGS = ("eligible", "declared_width", "rules", "names",
         "guidance")
# The first line of R5 in the base prompt. Everything from here on must be
# untouched by EX1, so it anchors the tail comparison.
TAIL = "R5  You do not choose"


# ---------------------------------------------------------------------------
print("\n1. rung table")
# ---------------------------------------------------------------------------

check("every rung declares all five required flags",
      all(set(FLAGS) <= set(v) for v in P.RUNGS.values()),
      "a flag read from a missing key would default to False and quietly "
      "redefine the rung")

# Optional flags are allowed, but only ones this harness knows about, so a
# typo cannot introduce a silent no-op key that reads as False forever.
OPTIONAL = {"mislabel"}
check("no rung declares an unrecognised flag",
      all(set(v) <= set(FLAGS) | OPTIONAL for v in P.RUNGS.values()),
      "an unknown key is either a typo or a manipulation nothing reads; "
      "add it to OPTIONAL here when it is deliberate")

check("mislabel is never combined with withheld names",
      all(not v.get("mislabel") or v["names"] is True
          for v in P.RUNGS.values()),
      "anonymising a swapped name erases the swap, so the run would be an "
      "L1-nowidth result reported under a swap label")

check("guidance is ON (deployed) on every rung, so it is not an axis",
      all(v["guidance"] is True for v in P.RUNGS.values()),
      "the trim was tested on 2026-08-16 and rejected: it tripled noops "
      "on legal work (3 -> 24 of 126). If one rung trimmed it, its gap "
      "would mix that effect with whatever the step was meant to remove")

check("the spine is the three data-axis rungs in order",
      P.SPINE == ("L3", "L3-nowidth", "L1-nowidth"))

check("every spine rung is in the table",
      all(r in P.RUNGS for r in P.SPINE))


def _diff(a, b):
    return [f for f in FLAGS if P.RUNGS[a][f] != P.RUNGS[b][f]]


for lo, hi in zip(P.SPINE, P.SPINE[1:]):
    d = _diff(lo, hi)
    check(f"{lo} to {hi} removes exactly one kind of information: {d}",
          len(d) == 1,
          "two things moving at once makes the gap unattributable, which "
          "is the design property the whole experiment rests on")

check("the spine only ever removes, never adds",
      all(P.RUNGS[lo][f] >= P.RUNGS[hi][f]
          for lo, hi in zip(P.SPINE, P.SPINE[1:]) for f in FLAGS),
      "a rung that restored information would not be a step down a ladder")

check("L2 is one flag off L3, and it is the rules flag",
      _diff("L3", "L2") == ["rules"])

check("L4 is one flag off L3, and it is the eligible flag",
      _diff("L3", "L4") == ["eligible"])

check("neither L2 nor L4 sits on the spine",
      "L2" not in P.SPINE and "L4" not in P.SPINE,
      "L2 inside the chain would confound instruction loss with the width "
      "loss already measured above it")

check("rung_spec refuses an unknown rung",
      raises(P.rung_spec, "L9") == "ValueError",
      "a rung that defaulted to L3 would report an L3 result under "
      "another label and nothing in the output would show it")

_s = P.rung_spec("L3")
_s["rules"] = "corrupted"
check("rung_spec returns a copy, not the table itself",
      P.RUNGS["L3"]["rules"] is True,
      "handing out the live dict lets one caller's edit change every "
      "later rung in the process")

check("EX1_PROMPT_VERSION is set",
      isinstance(P.EX1_PROMPT_VERSION, str) and P.EX1_PROMPT_VERSION.strip())


# ---------------------------------------------------------------------------
print("\n1b. guidance (deployed, trim rejected)")
# ---------------------------------------------------------------------------

check("trim_guidance still raises when the block is missing",
      raises(P.trim_guidance, "no guidance here") == "ValueError",
      "kept as the drift guard for GUIDANCE_FULL: if the deployed wording "
      "moves, this stops matching and the 16a record becomes stale")
check("GUIDANCE_FULL matches what the base prompt actually renders",
      raises(P.trim_guidance,
             sb.system_prompt(True, False)) is None,
      "if this fails, state_builder's guidance wording has drifted from "
      "the literal here and the 16a comparison no longer describes the "
      "current prompt")


# ---------------------------------------------------------------------------
print("\n2. withheld rule text")
# ---------------------------------------------------------------------------

WITHHELD = P.CAPABILITY_RULE_WITHHELD + "\n" + P.REACH_RULE_WITHHELD
LEAKS = ("grasp_m", "max_grasp_m", "mass_kg", "payload_kg", "delicate_ok",
         "reach_ok_arms")
_leaked = [w for w in LEAKS if w in WITHHELD]
check("the withheld text names no state field the rule used",
      not _leaked,
      f"leaked: {_leaked}. Naming one leaves the instruction standing "
      f"under a withheld label")

DERIVE = ("work it out", "derive", "compare", "infer", "calculate",
          "at most", "check that", "you must")
_told = [w for w in DERIVE if w in WITHHELD.lower()]
check("the withheld text does not instruct derivation",
      not _told,
      f"found: {_told}. Telling the model to work the rule out is the "
      f"instruction L2 exists to remove")

check("the withheld text still says a check exists",
      "checks that" in WITHHELD,
      "saying nothing at all is a different manipulation: the model would "
      "be entitled to conclude no capability check applies")

check("the deletion alternatives are available and empty",
      P.CAPABILITY_RULE_DELETED == "" and P.REACH_RULE_DELETED == "")


# ---------------------------------------------------------------------------
print("\n3. substitution against the frozen probe set")
# ---------------------------------------------------------------------------

if not os.path.exists(PROBES):
    check("frozen EX1 probe set is present", False,
          f"{PROBES} not found; the prompt checks below cannot run against "
          f"the states the experiment will use")
else:
    ps = json.load(open(PROBES))
    probes = ps["probes"]
    print(f"          probe set {ps.get('hash', '')[:16]}, n={len(probes)}")

    head_ok = tail_ok = base_ok = 0
    gone_ok = present_ok = 0
    for p in probes:
        st = p["state"]
        base = sb.build_prompt(st, "A")[0]["content"]
        l3 = P.build_ex1_prompt(st, "L3", "A")[0]["content"]
        l2 = P.build_ex1_prompt(st, "L2", "A")[0]["content"]
        base_ok += l3 == base
        # Compared against L3, not the base: both L2 and L3 trim guidance,
        # so the base's tail legitimately differs from both. L3 is EX1's
        # baseline and L2 is the contrast against it, which is the
        # comparison the rung is actually read as.
        head_ok += l3[:l3.find("R3  ")] == l2[:l2.find("R3  ")]
        tail_ok += l3[l3.find(TAIL):] == l2[l2.find(TAIL):]
        gone_ok += (sb.CAPABILITY_RULE not in l2
                    and sb.REACH_RULE_ENRICHED not in l2)
        present_ok += (sb.CAPABILITY_RULE in l3
                       and sb.REACH_RULE_ENRICHED in l3)

    n = len(probes)
    check(f"L3 is byte-identical to the base prompt ({base_ok}/{n})",
          base_ok == n,
          "EX1 adds nothing at its own baseline, so every gap is measured "
          "against the deployed prompt itself")
    check(f"L2 matches L3 everywhere before R3 ({head_ok}/{n})",
          head_ok == n)
    check(f"L2 matches L3 everywhere from R5 on ({tail_ok}/{n})",
          tail_ok == n)
    check(f"the base rule text is absent from L2 ({gone_ok}/{n})",
          gone_ok == n,
          "isolation alone would pass if the substitution did nothing")
    check(f"the base rule text is present at L3 ({present_ok}/{n})",
          present_ok == n,
          "if it were absent here the drift guard has stopped matching "
          "and the comparison above is vacuous")

    _l3 = P.build_ex1_prompt(probes[0]["state"], "L3", "A")[0]["content"]
    for _g in ("G1  Sort correctly", "G2  Avoid contention",
               "G3  Ignore queue order", "G4  Protect scarce",
               "G5  Waiting can be"):
        check(f"{_g.split()[0]} is present in the rendered L3 prompt",
              _g in _l3,
          "guidance is the deployed block at every rung; a missing rule "
          "means the trim is back on or the base wording drifted")

    st0 = probes[0]["state"]
    l2 = P.build_ex1_prompt(st0, "L2", "A")[0]["content"]
    check("L2 keeps the R3 and R4 headers",
          "\nR3  " in l2 and "\nR4  " in l2,
          "deleting them leaves R7 citing a rule that is not in the "
          "prompt, which is a defect rather than a manipulation")
    check("R7's reference to R3 still resolves",
          "R3 still applies" in l2 and "\nR3  " in l2)
    check("R5 is still present for R7 to refer to",
          "\nR5  " in l2 and "R5 governs" in l2)


# ---------------------------------------------------------------------------
print("\n4. guards")
# ---------------------------------------------------------------------------

if os.path.exists(PROBES):
    st0 = json.load(open(PROBES))["probes"][0]["state"]

    check("withhold_rules raises when the block is missing",
          raises(P.withhold_rules, "no rules in here", st0) == "ValueError",
          "this is the only thing between a state_builder edit and a run "
          "of unmodified prompts recorded under EX1 rung labels")

    check("an unknown rung raises",
          raises(P.build_ex1_prompt, st0, "L9", "A") == "ValueError")

    check("condition V without an image raises",
          raises(P.build_ex1_prompt, st0, "L3", "V") == "ValueError",
          "falling back to text would silently turn V into A")

    check("an unknown condition raises",
          raises(P.build_ex1_prompt, st0, "L3", "B") == "ValueError")

    check("L4 against a state with no eligible_arms raises",
          raises(P.build_ex1_prompt, st0, "L4", "A") == "ValueError",
          "the prompt picks its rules from the state, so this would "
          "render an L3 prompt stamped L4")

    # The mirror case: an eligible state asked for at an L3-family rung.
    st_e = copy.deepcopy(st0)
    st_e["reachability"] = "listed+eligible"
    for t in st_e.get("tasks", []):
        t["eligible_arms"] = []
    check("L3 against an eligible state raises",
          raises(P.build_ex1_prompt, st_e, "L3", "A") == "ValueError")

    check("L4 builds when the state does carry eligible_arms",
          raises(P.build_ex1_prompt, st_e, "L4", "A") is None)

    # ---- anonymised rungs ------------------------------------------------
    from experiments.ex1 import anonymise as A                  # noqa: E402

    check("an anonymised rung refuses without an alias mapping",
          raises(P.build_ex1_prompt, st0, "L1-nowidth", "A") == "ValueError",
          "with no mapping nothing can confirm the state was anonymised, "
          "so the prompt could carry real names under an anonymised label")

    an, mp = A.anonymise_state(st0)
    check("an anonymised rung builds when state and mapping agree",
          raises(P.build_ex1_prompt, an, "L1-nowidth", "A",
                 mapping=mp) is None)

    check("a NAMED state at an anonymised rung is caught",
          raises(P.build_ex1_prompt, st0, "L1-nowidth", "A",
                 mapping=mp) == "ValueError",
          "this is the failure the rung cannot survive: real object names "
          "rendered under an anonymised label")

    check("a mapping at a NAMED rung is refused",
          raises(P.build_ex1_prompt, st0, "L3", "A", mapping=mp)
          == "ValueError",
          "one of the two is wrong and guessing which would mislabel it")

    _msgs = P.build_ex1_prompt(an, "L1-nowidth", "A", mapping=mp)
    _txt = _msgs[0]["content"] + _msgs[1]["content"][0]["text"]
    check("no real object, category or basket name survives an L1 prompt",
          A.find_leaks(_txt, mp) == [],
          "the rung measures what the model does WITHOUT the name, so one "
          "surviving name invalidates the trial")
    check("the alias scheme is present in the L1 prompt",
          "Object1" in _txt and "CategoryA" in _txt and "Basket1" in _txt)
    check("the anonymised NAME carries no category prefix",
          "CategoryA_Object" not in _txt and "Category" not in
          _txt.split('"name": "')[1].split('"')[0],
          "the name must be a label and nothing more; grouping is the "
          "category field's job, in the named condition and this one alike")

    # Every probe in the set, not just the first: a leak that appears on
    # one state in a hundred is still a leak.
    _bad = 0
    for _p in json.load(open(PROBES))["probes"]:
        _a, _m = A.anonymise_state(_p["state"])
        _mm = P.build_ex1_prompt(_a, "L1-nowidth", "A", mapping=_m)
        if A.find_leaks(_mm[0]["content"] + _mm[1]["content"][0]["text"], _m):
            _bad += 1
    check(f"every probe renders a clean L1 prompt ({_bad} leaking)",
          _bad == 0)


print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)