"""h_ex2_prompts: the six rungs differ in exactly the intended way, the
state renders through the aliases, and the answer schema is typed.

Builds a real state with the REAL state builder and renders through the
REAL build_ex2_prompt, so what is checked is the prompt the model would
actually receive.

Rewritten for the factor design (2026-08-26). The old file tested the
attention ladder P0 to P4, the prose "why" block, the solo/batch split and
the render-time view substitution. None of those exist any more, so it was
not a matter of renaming rungs: what is pinned had to change with them.

What is pinned, and the failure each one guards:

  1. The module's own assertions pass. They are the auditable statement of
     the factor structure and they are cheap, so they run first.
  2. Each rung equals N0 plus its own factor block and nothing else. If a
     rung differed anywhere else, a rise against N0 could be that
     difference rather than the factor.
  3. N-order adds no wording. It is the control for the report order, and
     wording in it would make D and order inseparable again.
  4. The boundary rule holds: A never names a face or an opening, C never
     says where to look or asks for a report, D never states the relation.
  5. No rung names an arm's aperture, either measured opening, or which
     face the object is on.
  6. The state renders through the aliases, and the resting-face VALUES
     are already the words the answer schema accepts. The registry, the
     state and the schema are checked against each other, including which
     face each prim actually rests on, because the prim names disagree
     with the geometry and that pairing has been got wrong once.
  7. dims withholds BOTH the resting face and the opening, and says so.
     Withholding only the opening would let the face give it away.
  8. Every number in the state carries three decimals, so 0.050 and 0.100
     reach the model at one precision.
  9. An unknown rung, condition or preference raises rather than
     defaulting.
 10. The answer schema is TYPED. A surviving prose field would put an
     extractor back between the reply and the measurement.
 11. The manipulation check asks a three-way question about the image and
     nothing else, in the same vocabulary the schema accepts.

Run:  python3 h_ex2_prompts.py
"""

import json
import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.cell import cell_config as C                          # noqa: E402
from core.cell.zones import ZoneMap                             # noqa: E402
from core.decision import state_builder as sb                   # noqa: E402
from experiments.ex2 import labels as L                         # noqa: E402
from experiments.ex2 import prompts as P                        # noqa: E402
from experiments.ex2 import transforms as T                     # noqa: E402
from experiments.ex2.run import (neutralise_baskets,            # noqa: E402
                                 queue_flip_only)
from ycb_objects import register_specs                          # noqa: E402
from ycb_scene import BASKETS                                   # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + str(detail)
                                                  if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


# The BLOCK, not the mustard. The mustard had two poses; the block has
# three across two capability classes, and the pair the design turns on is
# edge against large_face. A fixture built on the pilot object would pass
# while the current design failed.
zm = ZoneMap(os.path.join(ROOT, "core", "cell", "reachability", "rasters"))
POS = {"ycb_block_large": (0.275, 0.6), "ycb_large_clamp": (0.275, 0.175)}
for n in POS:
    register_specs(C.OBJECT_SPECS, n, n[len("ycb_"):])


class Scene:
    def __getitem__(self, name):
        x, y = POS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


arms, agents = {}, {}
for name in C.ARMS:
    arm = NS(disabled=False, _carried=None,
             ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
    arms[name] = arm
    agents[name] = NS(arm=arm, state="IDLE")
pool = [NS(id=i, obj=o,
           dest=tuple(BASKETS["basket_" + C.OBJECT_SPECS[o]["category"]]["pos"]),
           done=False, failed=False, claimed=False, waiting_on=None,
           attempts=0, dest_by=None)
        for i, o in enumerate(POS)]
live = NS(cell=NS(scene=Scene(), arms=arms), agents=agents, pool=pool,
          locks=NS(holder={}, reservations={}),
          m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))
engine = NS(active=list(POS), applied_log=[])
probe = {"state": sb.build_state(live, engine, tick=1, baskets=BASKETS,
                                 zonemap=zm),
         "positions_exact": {k: list(v) for k, v in POS.items()}}


def prepared(condition):
    """The state a driver actually sends: one task, neutral baskets."""
    state, meta = T.transform(probe, condition)
    state = neutralise_baskets(queue_flip_only(state, meta["flip_label"]))
    return state, meta


state_c, meta_c = prepared("congruent")
state_x, meta_x = prepared("conflict")
state_d, meta_d = prepared("dims")

RUNGS = tuple(P.RUNGS)
sys_texts = {r: P.system_prompt(r, "congruent") for r in RUNGS}


# --- 1. the module's own assertions ---------------------------------------
for name in ("assert_base_states_no_relation", "assert_rungs_isolated"):
    try:
        check("module assertion %s passes" % name, getattr(P, name)())
    except ValueError as e:                            # noqa: BLE001
        check("module assertion %s passes" % name, False, str(e)[:110])

# The glossary and R3 are per CONDITION now: dims withholds two fields, and
# both the field list and R3 follow. So both assertions run on all three.
for name in ("assert_glossary_matches_state", "assert_r3_matches_state"):
    for cond in P.CONDITIONS:
        try:
            check("module assertion %s(%s) passes" % (name, cond),
                  getattr(P, name)(cond))
        except ValueError as e:                        # noqa: BLE001
            check("module assertion %s(%s) passes" % (name, cond), False,
                  str(e)[:110])

# The assertions must also hold with no image attached and under the other
# preference: those are real cells of the design, not variants.
for kw in ({"has_image": False}, {"preference": "ur"}):
    try:
        check("rungs stay isolated with %s" % kw,
              P.assert_rungs_isolated("congruent", **kw))
    except ValueError as e:                            # noqa: BLE001
        check("rungs stay isolated with %s" % kw, False, str(e)[:110])


# --- 2, 3. each rung is N0 plus its own block -----------------------------
base = sys_texts["N0"]
anchor = "\nYOUR ANSWER"
head = lambda t: t[:t.index(anchor)]

for rung in ("N-A", "N-C"):
    check("%s is N0 plus its factor block and nothing else" % rung,
          sys_texts[rung] == base.replace(anchor,
                                          P.RUNGS[rung]["text"] + anchor, 1),
          "its contrast against N0 must carry one change")

check("N-order adds no wording at all",
      head(sys_texts["N-order"]) == head(base),
      "it is the control for the report order")
check("N-order does change the schema",
      sys_texts["N-order"] != base,
      "an identical control measures nothing")
check("N-D is N0's wording plus its block",
      head(sys_texts["N-D"]) == head(base) + P.RUNGS["N-D"]["text"])
check("N-CD is N0's wording plus C and D",
      head(sys_texts["N-CD"]) == head(base) + P.RUNGS["N-CD"]["text"])
check("N-CD contains both single blocks",
      P.C_DERIVE in sys_texts["N-CD"] and P.D_ELICIT in sys_texts["N-CD"],
      "it is the sufficiency cell, so it must be their union")

check("N0 adds no factor wording", P.RUNGS["N0"]["text"] == "",
      "N0 is where Q1 and Q2 are read; anything in it is an unlabelled cue")


# --- 4. the boundary rule -------------------------------------------------
_a = P.A_ATTEND.lower()
check("A names the image and the object",
      "image" in _a and "object" in _a, " ".join(P.A_ATTEND.split())[:60])
check("A names no face, orientation or opening",
      not any(w in _a for w in ("face", "orientation", "opening", "extent",
                                "resting")),
      "it would collapse into C and the two factors would be one")

_c = " ".join(P.C_DERIVE.split()).lower()
check("C states the relation",
      "smaller of its two horizontal extents" in _c and "resting on" in _c,
      _c[:70])
check("C never says where to look and never asks for a report",
      not any(w in _c for w in ("look", "image", "give", "report")),
      "that is A and D respectively")

_d = " ".join(P.D_ELICIT.split()).lower()
check("D requires the report and fixes its position",
      "before naming an arm" in _d and "resting_face" in _d, _d[:70])
check("D never states the relation",
      not any(w in _d for w in ("smaller of", "horizontal extent",
                                "depends on")),
      "a model without C must supply the relation itself")


# --- 5. no rung hands over the answer -------------------------------------
FORBIDDEN = ("0.080", "0.140", "0.050", "0.100", "0.130",
             "small_face", "edge", "large_face", "franka", "ur_")
for rung in RUNGS:
    blk = P.RUNGS[rung]["text"].lower()
    hit = [w for w in FORBIDDEN if w in blk]
    check("%s names no aperture, opening or face" % rung, not hit, hit)


# --- 6. the aliases, fields AND values ------------------------------------
# The conflict cell must cross this, or the arm choice is free.
_fr = C.ARM_TYPES["franka"]["max_grasp_m"]
user_c = P.render_state(state_c, "congruent")
check("the deployed field names never reach the model",
      not any(('"%s"' % k) in user_c for k in P.FIELD_ALIASES),
      [k for k in P.FIELD_ALIASES if ('"%s"' % k) in user_c])
check("every alias appears in the rendered state",
      all(('"%s"' % v) in user_c
          for v in ("opening_needed_m", "opening_max_m", "max_load_kg",
                    "handles_delicate", "size_upright_m", "resting_face",
                    "arms_that_can_reach")),
      user_c[:0])
check("the dropped field is gone from the state",
      not any(('"%s"' % d) in user_c for d in P.DROP_FIELDS))

# The VALUE, not only the field. One vocabulary end to end: the registry,
# the rendered state and the answer schema all say the same two words.
faces_shown = [f for f in P.RESTING_FACES if ('"%s"' % f) in user_c]
check("the resting face renders in the schema's vocabulary",
      faces_shown == [meta_c["true_pose"]],
      "shown %s, true pose %s" % (faces_shown, meta_c["true_pose"]))
check("the registry already names the faces the schema lists",
      {L.TRUE_POSE[p] for p, lab in L.POSE_ENTRIES.items()
       if lab == "ycb_block"} == set(P.RESTING_FACES),
      "no render-time translation is left to get wrong")
check("the superseded pose words appear nowhere in the state",
      not any(('"%s"' % w) in user_c
              for w in ("upright", "lying", "lying_small_face",
                        "lying_large_face")),
      "the pre-2026-08-27 vocabulary is gone from the block path")
# Read the geometry, not the prim names. ycb_block_upright rests on the
# genuinely SMALLEST face and is the small_face; the names predate the
# geometric vocabulary. This is the pairing that has been got wrong once.
for _prim, _face, _open in (("ycb_block_upright", "small_face", 0.050),
                            ("ycb_block_large", "large_face", 0.100)):
    check("%s is the %s and needs %.3f m" % (_prim, _face, _open),
          L.TRUE_POSE[_prim] == _face
          and T.POSE_FACTS_BY_LABEL["ycb_block"][_face]["grasp_m"] == _open,
          "registry says %r at %.3f"
          % (L.TRUE_POSE[_prim],
             T.POSE_FACTS_BY_LABEL["ycb_block"][L.TRUE_POSE[_prim]]["grasp_m"]))
check("only large_face crosses the Franka aperture",
      [f for f in P.RESTING_FACES
       if T.POSE_FACTS_BY_LABEL["ycb_block"][f]["grasp_m"] > _fr]
      == ["large_face"],
      "one of the two is feasible, so the face determines the arm and the "
      "contrast is the whole design")
check("the two faces sit on opposite sides of it",
      len(P.RESTING_FACES) == 2
      and (T.POSE_FACTS_BY_LABEL["ycb_block"]["small_face"]["grasp_m"] < _fr
           < T.POSE_FACTS_BY_LABEL["ycb_block"]["large_face"]["grasp_m"]),
      "with two faces there is no room for a pair that does not flip "
      "capability; every conflict must be a capability flip")
check("the conflict map is an involution",
      all(T.OTHER_POSE_BY_LABEL["ycb_block"][
              T.OTHER_POSE_BY_LABEL["ycb_block"][f]] == f
          for f in P.RESTING_FACES),
      "each face declares the other and nothing else: %s"
      % T.OTHER_POSE_BY_LABEL["ycb_block"])
# The state, the answer schema and the manipulation check must speak ONE
# language. If a face can be rendered but not replied with, the face a model
# reports can never equal the face it was shown and every agreement measure
# reads zero for a reason that has nothing to do with the model. Checked
# here rather than in the module, which no longer carries the assertion.
_probe_text = P.manipulation_check("")[1]["content"][0]["text"]
for _f in P.RESTING_FACES:
    check("%s is offered by the answer schema" % _f, _f in P._FACE_FIELD)
    check("%s is offered by the manipulation check" % _f, _f in _probe_text,
          "the control and the trial must ask the same question")
check("the withdrawn middle face is offered by neither",
      "edge" not in P._FACE_FIELD and "edge" not in _probe_text,
      "naming it even to exclude it would make the probe three-way with "
      "one option discouraged, which is a different measurement")
check("the probe does not say how many faces there are beyond the two",
      "three" not in _probe_text.lower(),
      _probe_text)
check("the registry's faces are exactly the schema's",
      L.block_faces() == frozenset(P.RESTING_FACES),
      "registry %s, schema %s" % (sorted(L.block_faces()),
                                  sorted(P.RESTING_FACES)))
try:
    L.require_face("lying", P.RESTING_FACES)
    check("a non-face pose raises", False, "no exception")
except ValueError as e:                                # noqa: BLE001
    check("a non-face pose raises rather than reaching the model",
          "not a resting face" in str(e), str(e)[:70])

check("a conflict declares a face on the other side of the aperture",
      (meta_x["true_grasp_m"] > _fr) != (meta_x["declared_grasp_m"] > _fr),
      "true %.3f declared %.3f against %.3f"
      % (meta_x["true_grasp_m"], meta_x["declared_grasp_m"], _fr))


# --- 7. dims withholds both -----------------------------------------------
user_d = P.render_state(state_d, "dims")
check("dims withholds the opening", '"opening_needed_m"' not in user_d)
check("dims withholds the resting face", '"resting_face"' not in user_d,
      "stating the face would let the opening be derived from text alone")
check("dims keeps the object's own dimensions", '"size_upright_m"' in user_d,
      "the opening has to be derivable once the face is read")
# dims withholds two fields, so two parts of the PROMPT follow: the field
# list and R3. A prompt that promises a field and then retracts it, or a
# rule pointing at a field that is not there, makes the model solve a
# comprehension puzzle rather than the derivation under test.
dims_sys = P.system_prompt("N0", "dims")
cong_sys = P.system_prompt("N0", "congruent")
_head = lambda t: t[:t.index("\nYOUR ANSWER")]

check("the dims glossary does not promise the withheld fields",
      not any(('"%s"' % f) in _head(dims_sys) for f in P.DIMS_WITHHELD),
      [f for f in P.DIMS_WITHHELD if ('"%s"' % f) in _head(dims_sys)])
check("the congruent glossary DOES name them",
      all(('"%s"' % f) in _head(cong_sys) for f in P.DIMS_WITHHELD))
check("the dims glossary still names what the state does carry",
      all(('"%s"' % f) in _head(dims_sys)
          for f in ("mass_kg", "size_upright_m", "arms_that_can_reach")))
check("dims states that the two fields are absent",
      "no opening and no resting" in _head(dims_sys).lower(),
      "their absence must be stated rather than left to be noticed")

_r3 = lambda t: t[t.index("R3  Gripper opening"):t.index("R4  Load")]
check("R3 survives in dims rather than being deleted",
      "R3  Gripper opening" in dims_sys and "opening_max_m" in _r3(dims_sys),
      "deleting it would test the value of knowing the constraint exists, "
      "which is not the question")
check("R3 in dims does not point at the withheld field",
      '"opening_needed_m"' not in _r3(dims_sys),
      "a model could read a rule naming a missing field as inapplicable, "
      "and that would score as a derivation failure while being a "
      "rule-reading failure")
check("R3 in dims says the opening is not stated",
      "not stated" in _r3(dims_sys).lower())
check("R3 elsewhere DOES point at the field",
      all('"opening_needed_m"' in _r3(P.system_prompt("N0", c))
          for c in ("congruent", "conflict")))
check("neither dims substitution says where the opening comes from",
      not any(w in (_head(dims_sys)).lower()
              for w in ("smaller of", "horizontal extent", "work it out")),
      "that is factor C, and putting it here would give every dims rung it")
check("neither dims substitution calls the absence an error",
      not any(w in _head(dims_sys).lower()
              for w in ("missing", "error", "should have", "incomplete")),
      "framing it as a fault would steer the model toward flagging or "
      "abstaining, and abstention is one of the measures")
check("congruent and conflict render the same prompt",
      cong_sys == P.system_prompt("N0", "conflict"),
      "a conflict manipulates the STATE, never the prompt: if the two "
      "differed, a conflict effect could be the wording")


# --- 8. one precision for every number ------------------------------------
import re                                              # noqa: E402
bad = [m for m in re.findall(r":\s*(-?\d+\.\d+)", user_c)
       if len(m.split(".")[1]) != 3]
check("every number in the state carries three decimals", not bad, bad[:6])
check("no marker survives into the prompt", P._MARK not in user_c)


# --- 9. nothing is defaulted ----------------------------------------------
for kind, args in (("rung", ("P2", "congruent")),
                   ("condition", ("N0", "sideways")),
                   ("preference", ("N0", "congruent"))):
    try:
        if kind == "preference":
            P.system_prompt(*args, preference="either")
        else:
            P.system_prompt(*args)
        check("an unknown %s raises" % kind, False, "no exception")
    except ValueError as e:                            # noqa: BLE001
        check("an unknown %s raises rather than defaulting" % kind,
              True, str(e)[:70])
check("the old P-rungs are refused by name",
      all(r not in P.RUNGS for r in ("P0", "P1", "P2a", "P2", "P3a", "P3",
                                     "P4")),
      "a P0 result silently recorded as N0 would be invisible")


# --- 10. the schema is typed ----------------------------------------------
for rung in RUNGS:
    t = sys_texts[rung]
    check("%s asks for the opening as a number" % rung,
          '"opening_needed_m": <number>' in t)
    check("%s carries no prose justification field" % rung,
          '"why"' not in t and '"reason"' not in t,
          "a prose field puts an extractor back between reply and number")

check("only the D rungs ask for the resting face",
      [r for r in RUNGS if '"resting_face": "<' in sys_texts[r]]
      == ["N-D", "N-CD"],
      "asking for it elsewhere would tell the model the face matters")

# Measured inside the ANSWER section only. The glossary and R3 both name
# "opening_needed_m" forty lines earlier, so searching the whole prompt
# found those and reported every base rung as reordered.
schema_of = lambda r: sys_texts[r][sys_texts[r].index(anchor):]
for rung in ("N0", "N-A", "N-C"):
    t = schema_of(rung)
    check("%s commits the arm BEFORE the opening" % rung,
          t.index('"arm"') < t.index('"opening_needed_m"'))
for rung in ("N-order", "N-D", "N-CD"):
    t = schema_of(rung)
    check("%s reports the opening BEFORE the arm" % rung,
          t.index('"opening_needed_m"') < t.index('"arm"'),
          "a model generates left to right, so the schema must agree with "
          "the instruction or the instruction cannot bite")

check("a wait may carry a null opening",
      "null if you cannot" in sys_texts["N0"],
      "demanding a number from a model that has just said it cannot "
      "produce one corrupts the measure where it is most informative")


# --- 11. the manipulation check -------------------------------------------
mc = P.manipulation_check("Zm9v")
blob = json.dumps(mc)
check("the manipulation check carries an image", "image_url" in blob)
check("the manipulation check states no rules and no arms",
      not any(w in blob for w in ("R3", "opening_max_m", "ur_w", "franka",
                                  "task_id")),
      "it must ask what the picture shows, nothing else")
check("the manipulation check asks for one word",
      "one word" in blob)
check("it is a THREE-way question in the schema's vocabulary",
      all(f in blob for f in P.RESTING_FACES),
      "a standing-or-flat probe would pass while edge against large_face "
      "still failed")
check("it never names an opening or an arm aperture",
      not any(w in blob for w in ("0.080", "0.140", "opening")),
      "naming the number it is meant to elicit would test compliance")


# --- the eyeball tool -----------------------------------------------------
d = P.rung_diff("congruent")
check("rung_diff returns one entry per rung",
      set(d) == set(P.RUNGS), sorted(d))


# --- the built messages ---------------------------------------------------
msgs = P.build_ex2_prompt(state_c, "N-CD", "congruent", image_b64="Zm9v")
check("an image trial sends the picture first",
      msgs[1]["content"][0]["type"] == "image_url",
      "and the state second, so the model reads the scene before the text")
check("the image trial describes the camera",
      P.VIEW_TEXT in msgs[0]["content"] and P.SCENE_WITH_IMAGE
      in msgs[0]["content"])
text_only = P.build_ex2_prompt(state_c, "N-CD", "congruent")
check("a text-only trial attaches nothing",
      len(text_only[1]["content"]) == 1
      and text_only[1]["content"][0]["type"] == "text")
check("a text-only trial does not describe an absent image",
      P.VIEW_TEXT not in text_only[0]["content"]
      and P.SCENE_WITH_IMAGE not in text_only[0]["content"]
      and P.SCENE_NO_IMAGE in text_only[0]["content"],
      "a model asked to check an image that is not there is being tested "
      "on something other than modality")

check("the idle arms are named in the user message",
      "Idle arms right now:" in user_c and "franka_n" in user_c)
check("the preference is the only guidance that names an arm type",
      P.PREFERENCE_TEXT["franka"] in base
      and P.PREFERENCE_TEXT["ur"] not in base)
check("the version string is present and non-empty",
      isinstance(P.EX2_PROMPT_VERSION, str) and P.EX2_PROMPT_VERSION,
      P.EX2_PROMPT_VERSION)
check("every rung declares its factors and its schema",
      all(set(v) == {"text", "schema", "factors"} for v in P.RUNGS.values())
      and all(v["schema"] in P.SCHEMAS for v in P.RUNGS.values()))
check("every factor named by a rung carries a recorded prediction",
      {f for v in P.RUNGS.values() for f in v["factors"]}
      <= set(P.PREDICTIONS),
      "a prediction recorded after the fact is not a prediction")

# ---------------------------------------------------------------------------
# conflict_face, added 2026-08-28. The condition that makes a text-following
# result mean something.
#
# WHY IT EXISTS. In "conflict" the state supplies opening_needed_m and R3
# names that field, so a model that reads the number and applies R3 has
# broken no rule. A text-following result there cannot be told apart from
# rule-COMPLIANCE. And no rule mentions resting_face, so the false face is
# inert -- nothing asks the model to consult it. conflict_face withholds the
# number, which puts R3 into the form that names no field, so the false face
# in the text and the true face in the image compete on the one quantity
# that decides the arm, with neither privileged by a rule.
# ---------------------------------------------------------------------------
_cf = P.system_prompt("N0", "conflict_face")
_cf_head = _cf[:_cf.index("\nYOUR ANSWER")]
check("conflict_face glosses resting_face",
      '"resting_face"' in _cf_head)
check("conflict_face does NOT gloss opening_needed_m",
      '"opening_needed_m"' not in _cf_head,
      "the state does not carry it, and a prompt promising a field the "
      "state omits makes the model solve a comprehension puzzle instead")
_r3 = _cf[_cf.index("R3  Gripper opening"):_cf.index("R4  Load")]
check("conflict_face's R3 names no field and says the opening is not stated",
      '"opening_needed_m"' not in _r3 and "not stated" in _r3,
      "this is the whole point: with R3 naming the field, following the "
      "text is rule-compliance and the sign of the contrast is unreadable")
check("conflict_face renders a DIFFERENT prompt from conflict",
      _cf != P.system_prompt("N0", "conflict"),
      "conflict and congruent are byte-identical by design; conflict_face "
      "must not be, or it would carry the same R3")
check("congruent and conflict are still byte-identical",
      P.system_prompt("N0", "congruent") == P.system_prompt("N0", "conflict"),
      "the manipulation lives in the state, so no prompt difference can "
      "explain the contrast between those two")
# The 2x2 the design now is: {number supplied, number withheld} x {face true,
# face false}. Each ROW must render an identical prompt, so that within a row
# no wording difference can explain a contrast; the two rows must differ, or
# withholding the number did nothing.
check("congruent_face and conflict_face render identical prompts",
      P.system_prompt("N0", "congruent_face")
      == P.system_prompt("N0", "conflict_face"),
      "they are a matched pair differing only in whether the stated face is "
      "true, which is what isolates precedence from derivation")
check("the withheld-number row differs from the supplied-number row",
      P.system_prompt("N0", "congruent_face")
      != P.system_prompt("N0", "congruent"),
      "R3 must change form when the field goes away")
check("congruent_face withholds the number but keeps the face",
      "grasp_m" not in str(P.CONDITIONS["congruent_face"]["object_fields"])
      and '"resting_face"' in P.CONDITIONS["congruent_face"]["object_fields"])

check("every condition declares what it withholds",
      all("withheld" in v for v in P.CONDITIONS.values()),
      "render_state and both assertions read it from there, so a condition "
      "cannot render a field the prompt does not gloss")


print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
