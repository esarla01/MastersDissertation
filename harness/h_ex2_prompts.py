"""h_ex2_prompts: the four rungs differ in exactly the intended way, and
the answer schema carries the structured justification.

Builds a real state with the REAL state builder and renders through the
REAL build_prompt, so what is checked is the prompt the model would
actually receive.

What is pinned, and the failure each one guards:

  1. Every rung shares one base prompt. If the rungs differed anywhere
     else, a rise from P0 to P2 could be that difference rather than the
     attention cue.
  2. The rungs are strictly nested: each adds to the one below. A ladder
     whose steps are not nested cannot attribute a rise to a single added
     idea.
  3. P0 adds nothing at all. It is the floor; anything in it would be an
     unlabelled cue.
  4. P1 says LOOK without saying what to look for. If it mentioned pose or
     width it would collapse into P2 and the ladder would lose a rung.
  5. P2 states the pose-to-width rule. P3 adds the ordering requirement.
  6. The free-text reason is REPLACED, not supplemented. why.grasp is what
     records the width the model believed; a surviving "reason" field
     invites prose instead.
  7. The dims rule appears in the dims condition and NOWHERE else. It
     explains where a graspable width comes from when none is given, which
     would be a hint in the other conditions.
  8. An unknown rung raises rather than defaulting.
  9. The manipulation check contains no rules, no state and no arms: it
     asks only what the image shows.

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
from experiments.ex2 import prompts as P                        # noqa: E402
from experiments.ex2 import transforms as T                     # noqa: E402
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


zm = ZoneMap(os.path.join(ROOT, "core", "cell", "reachability", "rasters"))
POS = {"ycb_mustard_upright": (0.275, 0.6), "ycb_large_clamp": (0.275, 0.175)}
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

state_c, _ = T.transform(probe, "congruent")
state_d, _ = T.transform(probe, "dims")

texts = {r: P.build_ex2_prompt(state_c, r, "congruent")[0]["content"]
         for r in P.RUNGS}

# 1, 2, 3. nested, and P0 is the floor
check("P0 adds nothing to the base prompt", P.RUNG_TEXT["P0"] == "")
nested = all(texts[a] in texts[b] for a, b in
             (("P0", "P1"), ("P1", "P2"), ("P2", "P3")))
check("the rungs are strictly nested", nested,
      "a ladder whose steps are not nested cannot attribute a rise")
check("every rung shares one base prompt",
      all(t.startswith(texts["P0"]) for t in texts.values()))
check("each rung is strictly longer than the one below",
      len(texts["P0"]) < len(texts["P1"]) < len(texts["P2"])
      < len(texts["P3"]),
      {r: len(t) for r, t in texts.items()})

# 4, 5. what each rung says
p1_add = texts["P1"][len(texts["P0"]):]
p2_add = texts["P2"][len(texts["P1"]):]
p3_add = texts["P3"][len(texts["P2"]):]
check("P1 tells the model to look", "image" in p1_add.lower()
      and "check it against" in p1_add.lower(), p1_add.strip()[:60])
check("P1 does NOT mention pose or width",
      not any(w in p1_add.lower() for w in
              ("pose", "width", "upright", "lying", "stands", "lies")),
      "it would collapse into P2 and the ladder would lose a rung")
# Compared with newlines collapsed: the prompt is hard-wrapped, so a
# phrase can be split across lines and a literal search would miss it.
_flat = " ".join(p2_add.split())
check("P2 states the pose-to-width rule",
      "graspable width" in _flat and "stands up or lies down" in _flat,
      _flat[:70])
_flat3 = " ".join(p3_add.split())
check("P3 requires the justification BEFORE the arm is chosen",
      "BEFORE deciding which arm" in _flat3 and "why" in _flat3,
      _flat3[:70])
check("P3 adds ordering, not a new field",
      '"why"' in texts["P0"] and '"why"' in texts["P3"],
      "all four rungs share one schema")

# 6. the reason field is replaced, not supplemented
for r, t in texts.items():
    check(f"{r} carries the structured why block",
          '"why"' in t and '"grasp"' in t and '"payload"' in t
          and '"delicate"' in t)
check("the free-text reason is gone",
      '"reason": "<one short sentence>"' not in texts["P0"],
      "a surviving reason field invites prose instead of the widths")

# 7. the dims rule is scoped to the dims condition
dims_text = P.build_ex2_prompt(state_d, "P0", "dims")[0]["content"]
check("the dims condition explains where a width comes from",
      "dims_m" in dims_text and "No graspable width is given" in dims_text)
for cond in ("congruent", "conflict"):
    t = P.build_ex2_prompt(state_c, "P0", cond)[0]["content"]
    check(f"the dims rule does NOT appear in {cond}",
          "No graspable width is given" not in t,
          "it would be a hint about pose in a condition that states it")

# 8. unknown rung
try:
    # "P9" rather than a name that might later become real: "P4"
    # was used here and stopped being unknown when the ceiling
    # rung was added, so the check silently passed nothing.
    P.build_ex2_prompt(state_c, "P9", "congruent")
    check("an unknown rung raises", False, "no exception")
except ValueError as e:
    check("an unknown rung raises rather than defaulting",
          "P4" in str(e), str(e)[:70])

# 9. the manipulation check asks only about the image
mc = P.manipulation_check("Zm9v")
blob = json.dumps(mc)
check("the manipulation check carries an image", "image_url" in blob)
check("the manipulation check states no rules and no arms",
      not any(w in blob for w in ("R3", "max_grasp_m", "ur_w", "franka",
                                  "task_id")),
      "it must ask what the picture shows, nothing else")
check("the manipulation check asks for one word",
      "one word" in blob and "upright" in blob and "lying" in blob)

# rung_diff is the eyeball tool used before any spend
d = P.rung_diff(state_c)
check("rung_diff returns one entry per rung and P0 is empty",
      set(d) == set(P.RUNGS) and d["P0"] == "", {k: len(v) for k, v in d.items()})

# --- the camera convention must match the camera -------------------------
# The base prompt says the image is overhead with north at the top. That is
# true for table_cam and false for ex2_cam, which looks from the south. A
# prompt that misdescribes the view gives the model a plausible reason to
# misread a pose, which would look like a grounding failure.
# An image must be attached: the camera convention describes a picture, so
# in text-only mode it is dropped rather than substituted.
over = P.build_ex2_prompt(state_c, "P0", "congruent", image_b64="Zm9v",
                          view="table_cam")[0]["content"]
obliq = P.build_ex2_prompt(state_c, "P0", "congruent", image_b64="Zm9v",
                           view="ex2_cam")[0]["content"]
check("table_cam keeps the overhead convention",
      "top edge is north" in over)
check("ex2_cam describes the oblique view instead",
      "from the south of the table" in obliq
      and "top edge is north" not in obliq,
      " ".join(P.VIEW_TEXT["ex2_cam"].split())[:60])
check("the two views differ only in that sentence",
      len(over) != len(obliq) and over.split("HARD RULES")[1]
      == obliq.split("HARD RULES")[1])
try:
    P.build_ex2_prompt(state_c, "P0", "congruent", view="webcam")
    check("an unknown view raises", False, "no exception")
except ValueError as e:
    check("an unknown view raises", "webcam" in str(e), str(e)[:60])

# --- the EX2 trim ---------------------------------------------------------
# exchange_pads is the largest block in the user message and no EX2 scene
# admits a handover, so it is not merely noise: a model reasoning about
# routes that cannot exist would land that confusion in the headline as a
# grounding failure.
full = P.build_ex2_prompt(state_c, "P0", "congruent", image_b64="Zm9v",
                          trim=False, describe_scene=False)
trim = P.build_ex2_prompt(state_c, "P0", "congruent", image_b64="Zm9v")


def user_text(msgs):
    return [b for b in msgs[1]["content"] if b.get("type") == "text"][0]["text"]


check("the trim removes the pad block",
      "exchange_pads" in user_text(full)
      and "exchange_pads" not in user_text(trim))
check("the trim removes the empty bookkeeping",
      not any(k in user_text(trim) for k in
              ("zone_locks", "zone_inbound", "recent_events", "metrics")))
check("R6 and G2 go with the fields they refer to",
      "R6  " not in trim[0]["content"] and "G2  " not in trim[0]["content"],
      "G2 names zone_locks and zone_inbound, which the trim deletes")
check("R5 and R7 SURVIVE the trim",
      "R5  " in trim[0]["content"] and "R7  " in trim[0]["content"],
      "a handover can still be arranged, and EX2 tasks have dest_xy null")
check("the arms block survives with max_grasp_m",
      "max_grasp_m" in user_text(trim),
      "it is the number the whole experiment turns on")
check("objects, tasks and baskets survive",
      all(k in user_text(trim) for k in
          ("ycb_mustard", '"tasks"', "basket_food")))
check("the trim is a real saving",
      len(user_text(trim)) < 0.75 * len(user_text(full)),
      f"{len(user_text(full))} -> {len(user_text(trim))} chars")

# The scene description names FIXED FURNITURE only. Anything about the
# objects or the pose would be an attention cue and P0 would stop being
# the neutral rung.
check("the scene line describes the furniture",
      "three coloured" in trim[0]["content"]
      and "five white crosses" in trim[0]["content"])
check("the scene line says NOTHING about the objects or pose",
      not any(w in P.SCENE_TEXT.lower() for w in
              ("mustard", "upright", "lying", "clamp", "width", "grasp")),
      "it would be an attention cue and P0 would not be neutral")
# Text-only gets the SAME paragraph with the image references removed,
# not the paragraph deleted. Keeping mode A byte-identical to V, as the
# shared build_prompt does, would describe a side view that is not
# attached; deleting the paragraph outright would take the furniture
# description with it and make the two conditions differ by more than
# necessary.
_noimg = P.build_ex2_prompt(state_c, "P0", "congruent")[0]["content"]
check("the text-only prompt still describes the furniture",
      "three coloured" in _noimg and "five white crosses" in _noimg)
check("the text-only prompt mentions no image and no camera",
      "image" not in _noimg.lower() and "camera" not in _noimg.lower(),
      "a model asked to check an absent picture is being tested on "
      "something other than modality")
check("the camera convention is dropped, not substituted, without an image",
      "from the south of the table" not in _noimg
      and "top edge is north" not in _noimg)

# The trim must not silently skip a rule whose wording has moved.
try:
    P._drop_rule("nothing here", "R6")
    check("a missing rule raises", False, "no exception")
except ValueError as e:
    check("a rule the trim cannot find raises rather than being skipped",
          "R6" in str(e), str(e)[:70])

# Every rung still nests after trimming: the ladder is unaffected.
tt = {r: P.build_ex2_prompt(state_c, r, "congruent",
                            image_b64="Zm9v")[0]["content"]
      for r in P.RUNGS}
check("the rungs still nest after the trim",
      all(tt[a] in tt[b] for a, b in
          (("P0", "P1"), ("P1", "P2"), ("P2", "P3"))))


# --- the prompt must not ask for ONE task and EVERY task at once --------
# The base prompt opens by telling the model to choose one queued task.
# EX2 replaces the ANSWER section with a batch schema, but for a while it
# left that opening line in place, so the first instruction and the schema
# contradicted each other. The model obeyed the first one: eleven of
# eleven congruent upright rounds assigned the mustard, left the clamp,
# and then explained correctly why the clamp needed the arm just spent.
# That was read as an inability to coordinate two assignments, which it
# may not have been.
_sys = P.build_ex2_prompt(state_c, "P2", "congruent",
                          image_b64="Zm9v", view="ex2_cam")[0]["content"]
check("the prompt does not ask for ONE queued task",
      "choose ONE queued task" not in _sys,
      "the opening line must be substituted, not only the answer section")
check("the prompt asks for every queued task",
      "EVERY queued task" in _sys)
check("exactly one instruction about how many tasks to assign",
      _sys.count("ONE queued task") == 0,
      "two contradicting instructions is worse than either alone")
check("leaving a task for later is still permitted",
      "later" in _sys or "null" in _sys,
      "a round where nothing free can serve a task has to be expressible")

for _cond in ("congruent", "conflict", "dims"):
    for _rung in P.RUNGS:
        _st = state_d if _cond == "dims" else state_c
        _t = P.build_ex2_prompt(_st, _rung, _cond, image_b64="Zm9v",
                                view="ex2_cam")[0]["content"]
        check("no single-task instruction survives in %s/%s"
              % (_cond, _rung), "choose ONE queued task" not in _t)

check("EX2 carries its own prompt version",
      isinstance(P.EX2_PROMPT_VERSION, str) and P.EX2_PROMPT_VERSION,
      "EX2 rewrites the base prompt, so the base version no longer "
      "identifies what the model read: %s" % P.EX2_PROMPT_VERSION)


# --- the trim removes machinery no EX2 scene can exercise --------------
# Every EX2 task is captured with a destination already set and no zone
# lock is ever taken, so R7, G1 and the zone-lock clause describe
# mechanisms the model cannot use. Text it cannot act on is not neutral:
# it is context the model must read past to reach the rules that bind.
_trimmed = P.build_ex2_prompt(state_c, "P2", "congruent",
                              image_b64="Zm9v", view="ex2_cam")[0]["content"]
for _tag in ("R6", "G2"):
    check("%s is trimmed" % _tag, ("\n" + _tag + "  ") not in _trimmed)
check("the zone-lock clause is gone",
      "zone at a time" not in _trimmed,
      "G2 was already dropped; this was the last mention of a mechanism "
      "an EX2 scene never triggers")
check("the zone sentence still reads as a sentence",
      "quadrants nw, ne, sw, se." in _trimmed,
      "removing the clause must not leave a dangling comma")

# What must SURVIVE the trim, and why each one matters here.
for _tag, _why in (("R3", "the capability rule the whole experiment turns on"),
                   ("R4", "reach, which is genuinely used"),
                   ("R5", "R4 ends with 'see R5', so dropping it would "
                          "dangle, and it carries the direct-delivery "
                          "preference"),
                   ("R7", "an EX2 task is captured with dest_xy null, so "
                          "the model must name a basket on every trial"),
                   ("G1", "and G1 is what tells it which basket"),
                   ("G3", "queue order is a live question"),
                   ("G4", "scarce arms: the model must be TOLD, or a "
                          "coordination failure is unfair to report"),
                   ("G5", "deferral is the correct answer in every lying "
                          "round and must be licensed")):
    check("%s survives the trim" % _tag, ("\n" + _tag + "  ") in _trimmed,
          _why)

check("no rule references one that was trimmed",
      "R6" not in _trimmed,
      "a dangling cross-reference reads as something withheld")
check("untrimmed builds keep the full prompt",
      "zone at a time" in P.build_ex2_prompt(state_c, "P2", "congruent",
                                             trim=False)[0]["content"],
      "trim=False must be a real escape hatch")


# --- the scene text points at both sources, without weighting either -----
_scene = P.build_ex2_prompt(state_c, "P0", "congruent", image_b64="Zm9v",
                            view="ex2_cam")[0]["content"]
check("the prompt says the written state follows",
      "follows below" in _scene)
check("the pointer names both sources",
      "side view" in _scene and "description of the same scene" in _scene,
      "reworded at 2026-08-06e: the base now names the image as evidence "
      "rather than only saying where it is")
check("the pointer does not tell the model how to weigh them",
      "check it against" not in P.SCENE_TEXT
      and "carefully" not in P.SCENE_TEXT.lower(),
      "attention instructions belong in the RUNG: putting one in the base "
      "would make P0 stop being the neutral rung")

# The ladder must stay a ladder. P0 carries no image instruction at all.
check("P0 adds nothing", P.RUNG_TEXT["P0"].strip() == "",
      "P0 is the unprompted baseline: %r" % P.RUNG_TEXT["P0"][:40])
check("P1 adds the image-check instruction",
      "as it is now" in P.RUNG_TEXT["P1"])
check("P2 adds the graspable-width fact",
      "presents" in P.RUNG_TEXT["P2"]
      and "presents" not in P.RUNG_TEXT["P1"])
check("the width fact is NOT in the rules",
      "presents to the gripper" not in _scene.split("YOUR ANSWER")[0],
      "moving it into R3 would put it in P0 and collapse P0, P1 and P2 "
      "into the same prompt")


# --- the ladder must stay a gradient, and P0 must stay the neutral rung --
# Across 132 solo trials not one reply mentioned the image, and the base
# never said it was evidence. The base now names it; how much to WEIGH it
# stays in the rung, which is what the ladder varies.
_base = P.build_ex2_prompt(state_c, "P0", "congruent", image_b64="Zm9v",
                           view="ex2_cam")[0]["content"]
check("the base says the image is a side view of this cell",
      "side view" in _base and "same scene" in _base)
check("the base does not tell the model how to weigh the image",
      "disagree" not in _base and "check it against" not in _base.lower(),
      "that is the rung's job; putting it here makes P0 stop being "
      "neutral")
check("the base says nothing about the object's pose",
      "lying" not in _base and "upright" not in _base
      and "stands up" not in _base,
      "naming the property would hand over the manipulation")

check("P0 adds nothing", P.RUNG_TEXT["P0"] == "")
for _i in range(len(P.RUNGS) - 1):
    _lo, _hi = P.RUNGS[_i], P.RUNGS[_i + 1]
    check("%s is a superset of %s" % (_hi, _lo),
          P.RUNG_TEXT[_lo].strip() in P.RUNG_TEXT[_hi],
          "a ladder whose rungs are not nested cannot be read as strength")

# Every step adds exactly one thing, and the ONE step that adds no words
# must instead change the schema. P2 bundled arbitration with derivation
# and P3 bundled the reorder with the orientation clause, so neither step
# could attribute its effect; P2a and P3a split them.
check("P2a adds arbitration and not derivation",
      "disagree" in P.RUNG_TEXT["P2a"] and "presents" not in
      P.RUNG_TEXT["P2a"])
check("P2 adds derivation over P2a",
      "presents" in P.RUNG_TEXT["P2"])
check("P3a adds NO words over P2",
      P.RUNG_TEXT["P3a"] == P.RUNG_TEXT["P2"],
      "the only difference must be the field order, or the reorder cannot "
      "be measured on its own")
check("P3a nonetheless differs from P2 in the schema",
      P.build_ex2_prompt(state_c, "P3a", "congruent", solo=True)[0]["content"]
      != P.build_ex2_prompt(state_c, "P2", "congruent", solo=True)[0]["content"])
check("P3a puts why before arm",
      (lambda t: t.index('"why"') < t.index('"arm"'))(
          P.build_ex2_prompt(state_c, "P3a", "congruent",
                             solo=True)[0]["content"]))
check("P3a does not ask for the orientation",
      "orientation" not in P.RUNG_TEXT["P3a"],
      "that clause is what invites a description, which is where "
      "prototype substitution appears")
check("P3 adds the orientation clause over P3a",
      "orientation" in P.RUNG_TEXT["P3"])
check("every rung has text and every text has a rung",
      set(P.RUNGS) == set(P.RUNG_TEXT), str(P.RUNGS))
check("only one RUNGS definition survives",
      open(os.path.join(os.path.dirname(HERE), "fourarm",
                        "experiments", "ex2", "prompts.py")).read()
      .count("\nRUNGS = ") == 1,
      "a second definition would shadow the first and the extra rungs "
      "would silently not exist")
check("P2 escalates rather than only repeating P1",
      "disagree" in P.RUNG_TEXT["P2"] and "disagree" not in P.RUNG_TEXT["P1"],
      "P2 previously repeated P1 and added the width fact, which is "
      "barely a step up")
check("the width fact stays in the rung, not in R3",
      "presents" in P.RUNG_TEXT["P2"] and "presents" not in _base,
      "moving it into R3 would put the hint in P0 and flatten the ladder")
check("no rung names the object or its pose",
      not any(w in P.RUNG_TEXT[r] for r in P.RUNGS
              for w in ("mustard", "bottle")),
      "the rung may say the image wins, never what to look for")


# --- every number in the state is written to the same precision ---------
# json prints 0.08 as "0.08" and 0.096 as "0.096", so the two widths the
# experiment turns on arrived at different precisions. One reply echoed the
# Franka limit back as "0.080", which suggests the model was normalising
# formats before comparing. A comparison that decides the trial should not
# also ask it to reconcile notation.
import re as _re  # noqa: E402

_um = P.build_ex2_prompt(state_c, "P2", "congruent", image_b64="Zm9v",
                         view="ex2_cam")
_utext = ""
for _b in (_um[1]["content"] if isinstance(_um[1]["content"], list)
           else [{"type": "text", "text": _um[1]["content"]}]):
    if isinstance(_b, dict) and _b.get("type") == "text":
        _utext += _b["text"]

check("no marker survives into the prompt",
      "@F@" not in _utext and "@F@" not in _um[0]["content"],
      "sending a marker to the model would corrupt a measurement it has "
      "to compare")
check("no escaped marker survives either",
      "u0000" not in _utext,
      "a control-character marker is escaped by json, so the regex misses "
      "it and the guard checks a form that is no longer there")
_floats = _re.findall(r":\s*(-?\d+\.\d+)", _utext)
check("every float is written to three decimals", bool(_floats)
      and all(len(f.split(".")[1]) == 3 for f in _floats),
      "%d floats, offenders %s"
      % (len(_floats), [f for f in _floats
                        if len(f.split(".")[1]) != 3][:6]))
check("the two widths under test are written alike",
      "0.080" in _utext and "0.096" in _utext,
      "38 mm apart and now at the same precision")
check("numbers are numbers, not quoted strings",
      '"0.080"' not in _utext and '"0.096"' not in _utext,
      "a quoted measurement invites the model to read it as text")
check("three decimals keeps the two widths apart",
      "0.058" in _utext or "0.096" in _utext,
      "fewer places would round 0.096 and 0.058 together and destroy the "
      "manipulation")
check("marking then unmarking is a round trip",
      P.unmark_decimals(json.dumps(P.mark_decimals({"a": 0.1})))
      == '{"a": 0.100}')
try:
    P.unmark_decimals("a stray @F@ mark")
    check("a surviving marker raises", False, "no exception")
except ValueError:
    check("a surviving marker raises rather than reaching the model", True)


# --- P4, the ceiling rung -----------------------------------------------
# Not a further step on either dimension: it bundles what to know with how
# to report and comes close to handing over the answer procedure. Its value
# is as a BOUND. Zero image belief at P0, P1 and P2a and 36 percent at P2
# leaves a large residual, and P4 says whether that residual is a choice or
# a limit.
check("P4 is the top of the ladder", P.RUNGS[-1] == "P4")
check("P4 is a superset of P3", P.RUNG_TEXT["P3"] in P.RUNG_TEXT["P4"])
check("P4 names the two poses explicitly",
      "upright" in P.RUNG_TEXT["P4"] and "lying" in P.RUNG_TEXT["P4"],
      "every rung below stops short of naming the distinction; this is "
      "the step from a general fact to a specific procedure")
check("no rung below P4 names the poses",
      not any(w in P.RUNG_TEXT[r] for r in P.RUNGS[:-1]
              for w in ("upright", "lying")),
      "naming them lower down would leak the manipulation into the "
      "unprompted rungs")
check("P4 stops at the width check and does not name an arm",
      "max_grasp_m" in P.RUNG_TEXT["P4"]
      and "franka" not in P.RUNG_TEXT["P4"].lower()
      and "ur_" not in P.RUNG_TEXT["P4"],
      "telling the model which arm to pick would test compliance, not "
      "perception")
check("P4 never says the description is wrong",
      not any(w in P.RUNG_TEXT["P4"].lower()
              for w in ("false", "incorrect", "wrong", "may be out of date")),
      "the same rung has to be usable in the congruent condition, and "
      "saying so would give the manipulation away")
check("P4 keeps the why-first schema",
      "P4" in P.WHY_FIRST_RUNGS,
      "it inherits P3, so the order must be inherited too")
_p4 = P.build_ex2_prompt(state_c, "P4", "congruent", image_b64="Zm9v",
                         view="ex2_cam", solo=True)[0]["content"]
check("P4 builds and carries its own sentence",
      "decide whether the object is" in _p4)

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)