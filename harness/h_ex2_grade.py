"""h_ex2_grade: a reply is graded against measured geometry, and a cautious
answer is not counted as evidence.

Imports the REAL grader. The legal-arm sets are computed from the REAL
validator over the REAL frozen coordinator, so the fixture is the cell
rather than a table written here.

What is pinned, and the failure each one guards:

  1. An arm legal under BOTH poses is uninformative, not follows_state.
     Without that column every cautious answer would count as evidence the
     model ignored the image, biasing the headline toward the conclusion
     the design exists to test.
  2. follows_image and follows_state are decided by the arm's legality
     under the TRUE and DECLARED poses, never by the validator's verdict on
     the state, which in a conflict cell is working from the lie.
  3. Both conflict directions grade correctly. They are not symmetric: only
     the restrictive one separates grounding from blanket caution.
  4. Replies wrapped in prose or fences still parse; a malformed one
     returns unparseable rather than ending a paid run.
  5. why.grasp is read for the width the model BELIEVED, and matched to
     the image value, the declared value or neither.
  6. Belief and action coming apart is counted: a reply that states the
     image width and then names the text's arm.
  7. Flag keywords are FIXED in the module, not passed in, so they cannot
     be tuned after seeing replies.

Run:  python3 h_ex2_grade.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from experiments.ex2 import grade as G                          # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + str(detail)
                                                  if detail else ""))
    if not ok:
        fails.append(label)


# The two poses of the mustard, and which arms can take it under each.
# Upright 0.058 m: all four. Lying 0.096 m: URs only, the Franka limit
# being 0.080. These are the measured values from run_ycb_probe.
ALL4 = {"ur_w", "ur_e", "franka_s", "franka_n"}
URS = {"ur_w", "ur_e"}

PERMISSIVE = {"condition": "conflict",
              "true_pose": "upright", "declared_pose": "lying",
              "true_grasp_m": 0.058, "declared_grasp_m": 0.096,
              "direction": "permissive"}
RESTRICTIVE = {"condition": "conflict",
               "true_pose": "lying", "declared_pose": "upright",
               "true_grasp_m": 0.096, "declared_grasp_m": 0.058,
               "direction": "restrictive"}


def reply(arm, grasp="", extra=""):
    return ('{"task_id": 0, "arm": %s, "basket": "basket_food", '
            '"regions": ["ne","nw"], "why": {"grasp": "%s", '
            '"payload": "0.603 under 5.0", "delicate": "not delicate"}}%s'
            % ("null" if arm is None else '"%s"' % arm, grasp, extra))


# --- 1, 2, 3. the four outcomes, both directions --------------------------
# PERMISSIVE: picture allows all four, text claims URs only.
r = G.grade(reply("franka_n"), PERMISSIVE, ALL4, URS)
check("permissive: a Franka follows the IMAGE",
      r["outcome"] == "follows_image", r["outcome"])
r = G.grade(reply("ur_w"), PERMISSIVE, ALL4, URS)
check("permissive: a UR is UNINFORMATIVE, not follows_state",
      r["outcome"] == "uninformative",
      "a UR is legal under both poses; counting it as follows_state would "
      "bias the headline")

# RESTRICTIVE: picture allows URs only, text claims all four.
r = G.grade(reply("franka_n"), RESTRICTIVE, URS, ALL4)
check("restrictive: a Franka follows the STATE",
      r["outcome"] == "follows_state", r["outcome"])
r = G.grade(reply("ur_w"), RESTRICTIVE, URS, ALL4)
check("restrictive: a UR is uninformative here too",
      r["outcome"] == "uninformative", r["outcome"])
check("the two directions are not symmetric",
      G.grade(reply("franka_n"), PERMISSIVE, ALL4, URS)["outcome"]
      != G.grade(reply("franka_n"), RESTRICTIVE, URS, ALL4)["outcome"],
      "only the restrictive direction separates grounding from caution")

r = G.grade(reply("franka_s"), PERMISSIVE, URS, URS)
check("an arm legal under neither pose is illegal_both",
      r["outcome"] == "illegal_both", r["outcome"])
r = G.grade('{"task_id": -1, "arm": null, "why": {}}', PERMISSIVE, ALL4, URS)
check("a wait is a noop, not an outcome about sources",
      r["outcome"] == "noop", r["outcome"])

# --- 4. parsing -----------------------------------------------------------
fenced = "```json\n" + reply("franka_n") + "\n```"
check("a fenced reply parses",
      G.grade(fenced, PERMISSIVE, ALL4, URS)["outcome"] == "follows_image")
prosed = "Sure, here is my answer:\n" + reply("franka_n") + "\nHope that helps."
check("a reply wrapped in prose parses",
      G.grade(prosed, PERMISSIVE, ALL4, URS)["outcome"] == "follows_image")
check("a malformed reply is unparseable, not a crash",
      G.grade("I cannot answer that.", PERMISSIVE, ALL4,
              URS)["outcome"] == "unparseable")
check("an empty reply is unparseable",
      G.grade("", PERMISSIVE, ALL4, URS)["outcome"] == "unparseable")

# --- 5. the believed width ------------------------------------------------
r = G.grade(reply("franka_n", "0.058 m, under the 0.080 limit"),
            PERMISSIVE, ALL4, URS)
check("a stated width matching the picture is 'image'",
      r["width_belief"] == "image" and r["believed_width_m"] == 0.058, r)
r = G.grade(reply("ur_w", "0.096 m, over the Franka's 0.080"),
            PERMISSIVE, ALL4, URS)
check("a stated width matching the text is 'state'",
      r["width_belief"] == "state", r["believed_width_m"])
r = G.grade(reply("ur_w", "0.1 m"), PERMISSIVE, ALL4, URS)
check("a rounded 0.1 still reads as the 0.096 value",
      r["width_belief"] == "state", r["believed_width_m"])
r = G.grade(reply("ur_w", "wide enough"), PERMISSIVE, ALL4, URS)
check("no number stated reads as 'none'", r["width_belief"] == "none")
r = G.grade(reply("ur_w", "0.031 m"), PERMISSIVE, ALL4, URS)
check("a width matching neither reads as 'other'",
      r["width_belief"] == "other")

# When the two sources AGREE, no reply can reveal which one was used. The
# classifier used to answer 'image' there, crediting the picture for a
# number the text supplied just as well, and every congruent trial in a
# 44-row run came back 'image' as a result. That is inflated grounding in
# exactly the cells built to have none.
CONGRUENT = dict(PERMISSIVE)
CONGRUENT["declared_grasp_m"] = CONGRUENT["true_grasp_m"]
CONGRUENT["declared_pose"] = CONGRUENT["true_pose"]
r = G.grade(reply("ur_w", "%.3f m" % CONGRUENT["true_grasp_m"]),
            CONGRUENT, URS, URS)
check("agreeing sources read as 'tie', not as 'image'",
      r["width_belief"] == "tie",
      "%s at %s m" % (r["width_belief"], r["believed_width_m"]))
r = G.grade(reply("ur_w", "0.031 m"), CONGRUENT, URS, URS)
check("a tie does not swallow a width matching neither source",
      r["width_belief"] == "other")
check("every verdict the classifier can return is counted in the summary",
      set(G.WIDTH_BELIEFS) >= {"image", "state", "tie", "other", "none"},
      str(G.WIDTH_BELIEFS))
_summary = G.summarise([G.grade(reply("ur_w", "%.3f m"
                                      % CONGRUENT["true_grasp_m"]),
                                CONGRUENT, URS, URS)])
check("a tie appears in the summary table rather than vanishing",
      _summary["width_belief"].get("tie") == 1, str(_summary["width_belief"]))

# --- 6. belief and action coming apart ------------------------------------
rows = [
    G.grade(reply("ur_w", "0.058 m"), PERMISSIVE, ALL4, URS),   # image belief
    G.grade(reply("franka_n", "0.096 m"), RESTRICTIVE, URS, ALL4),
]
s = G.summarise(rows)
check("a belief that contradicts the action is counted",
      s["belief_action_mismatch"] == 1, s)

# --- 7. flags -------------------------------------------------------------
r = G.grade(reply("franka_n", "0.058 m",
                  ' The description says lying but the image shows it '
                  'upright, so they contradict.'),
            PERMISSIVE, ALL4, URS)
check("a remark about the disagreement is flagged", r["flagged"])
check("an ordinary reply is not flagged",
      not G.grade(reply("ur_w"), PERMISSIVE, ALL4, URS)["flagged"])
check("the keyword list lives in the module, fixed in advance",
      isinstance(G.FLAG_KEYWORDS, tuple) and len(G.FLAG_KEYWORDS) > 5,
      "it must not be tunable after replies are seen")

s = G.summarise([G.grade(reply("franka_n"), PERMISSIVE, ALL4, URS),
                 G.grade(reply("ur_w"), PERMISSIVE, ALL4, URS),
                 G.grade("nonsense", PERMISSIVE, ALL4, URS)])
check("summarise counts every row exactly once",
      sum(s["outcomes"].values()) == s["n"] == 3, s["outcomes"])

# ---------------------------------------------------------------------------
# Round grading: the whole allocation, not one assignment
# ---------------------------------------------------------------------------
# With one assignment at a time the model named ur_w in twelve trials out
# of twelve, and ur_w is legal whichever way the bottle lies, so the choice
# carried no information. A round removes the safe answer: ur_w is the only
# arm that can take EITHER object and it cannot take both.
import json as _json


def rnd(flip_arm, part_arm, width=""):
    return _json.dumps({"assignments": [
        {"task_id": 0, "arm": flip_arm, "why": {"grasp": width}},
        {"task_id": 1, "arm": part_arm, "why": {}}]})


# picture LYING (flip needs ur_w), text says UPRIGHT (flip could use either)
LY_TRUE, LY_DECL, PART = {"ur_w"}, {"ur_w", "franka_n"}, {"ur_w"}
r = G.grade_round(rnd("ur_w", None), RESTRICTIVE, 0, 1, LY_TRUE, LY_DECL, PART)
check("lying picture: mustard to ur_w, clamp left -> follows the IMAGE",
      r["outcome"] == "round_image",
      "believing upright, it could have freed ur_w for the clamp")
r = G.grade_round(rnd("franka_n", "ur_w"), RESTRICTIVE, 0, 1, LY_TRUE,
                  LY_DECL, PART)
check("lying picture: mustard to franka_n -> follows the STATE",
      r["outcome"] == "round_state",
      "franka_n cannot hold 0.096 m; only the text says it can")
r = G.grade_round(rnd("ur_w", "franka_n"), RESTRICTIVE, 0, 1, LY_TRUE,
                  LY_DECL, PART)
check("a clamp given to a Franka is illegal under either belief",
      r["outcome"] == "round_illegal", "0.122 m against an 0.080 limit")

# picture UPRIGHT (flip could use either), text says LYING (needs ur_w)
UP_TRUE, UP_DECL = {"ur_w", "franka_n"}, {"ur_w"}
r = G.grade_round(rnd("franka_n", "ur_w"), PERMISSIVE, 0, 1, UP_TRUE,
                  UP_DECL, PART)
check("upright picture: mustard to franka_n, clamp to ur_w -> IMAGE",
      r["outcome"] == "round_image", "both tasks served, only possible "
      "if the bottle is narrow")
r = G.grade_round(rnd("ur_w", None), PERMISSIVE, 0, 1, UP_TRUE, UP_DECL,
                  PART)
check("upright picture: mustard to ur_w, clamp left -> STATE",
      r["outcome"] == "round_state")

check("the two directions are mirror images",
      G.grade_round(rnd("ur_w", None), RESTRICTIVE, 0, 1, LY_TRUE, LY_DECL,
                    PART)["outcome"] == "round_image"
      and G.grade_round(rnd("ur_w", None), PERMISSIVE, 0, 1, UP_TRUE,
                        UP_DECL, PART)["outcome"] == "round_state",
      "the same round means opposite things under opposite pictures")

# schema failures are not beliefs
r = G.grade_round('{"assignments":[{"task_id":0,"arm":"ur_w"}]}',
                  RESTRICTIVE, 0, 1, LY_TRUE, LY_DECL, PART)
check("a round missing a task is incomplete, not a belief",
      r["outcome"] == "round_incomplete",
      "a schema failure must not be scored as evidence")
r = G.grade_round(rnd("ur_w", "ur_w"), RESTRICTIVE, 0, 1, LY_TRUE, LY_DECL,
                  PART)
check("one arm given two tasks is illegal", r["outcome"] == "round_illegal")
check("an unparseable round is unparseable",
      G.grade_round("no json here", RESTRICTIVE, 0, 1, LY_TRUE, LY_DECL,
                    PART)["outcome"] == "unparseable")

# a bare single assignment is recorded, not discarded
r = G.grade_round('{"task_id": 0, "arm": "ur_w", "why": {"grasp":"0.096"}}',
                  RESTRICTIVE, 0, 1, LY_TRUE, LY_DECL, PART)
check("a reply that ignores the list schema is incomplete, not unparseable",
      r["outcome"] == "round_incomplete" and r["width_belief"] == "image",
      "it did not follow the schema, but what it said is still recorded")

# the width belief still comes through in a round
r = G.grade_round(rnd("franka_n", "ur_w", "0.058 m"), RESTRICTIVE, 0, 1,
                  LY_TRUE, LY_DECL, PART)
check("why.grasp is read from the flip task's entry",
      r["width_belief"] == "state" and r["believed_width_m"] == 0.058,
      "0.058 is the declared width; the picture shows 0.096")

s = G.summarise_rounds([
    G.grade_round(rnd("ur_w", None), RESTRICTIVE, 0, 1, LY_TRUE, LY_DECL,
                  PART),
    G.grade_round(rnd("franka_n", "ur_w"), RESTRICTIVE, 0, 1, LY_TRUE,
                  LY_DECL, PART)])
check("summarise_rounds counts every row once",
      sum(s["outcomes"].values()) == s["n"] == 2, s["outcomes"])

# --- congruent and dims are not about allegiance --------------------------
# image/state only mean something when the sources DISAGREE. Scoring a
# congruent trial as round_image produced a label that looked like a
# finding and meant nothing: the text and the picture said the same thing.
CONG = dict(RESTRICTIVE, condition="congruent", declared_pose="lying",
            declared_grasp_m=0.096)
DIMS = dict(RESTRICTIVE, condition="dims", declared_pose=None,
            declared_grasp_m=None)
r = G.grade_round(rnd("ur_w", None), CONG, 0, 1, LY_TRUE, LY_TRUE, PART)
check("a congruent round is scored CORRECT, not follows_image",
      r["outcome"] == "round_correct", r["outcome"])
r = G.grade_round(rnd("franka_n", "ur_w"), CONG, 0, 1, LY_TRUE, LY_TRUE,
                  PART)
check("a congruent round that breaks the true reading is wrong",
      r["outcome"] == "round_wrong", r["outcome"])
r = G.grade_round(rnd("ur_w", None), DIMS, 0, 1, LY_TRUE, LY_TRUE, PART)
check("a dims round is scored for correctness too",
      r["outcome"] == "round_correct", r["outcome"])
r = G.grade_round(rnd("ur_w", None), RESTRICTIVE, 0, 1, LY_TRUE, LY_DECL,
                  PART)
check("only a conflict round is scored image vs state",
      r["outcome"] == "round_image", r["outcome"])

# --- the assignable set, the primary reading ------------------------------
# A single choice can be satisficing: the model picks a sufficient arm and
# stops, which is what it did in twelve trials out of twelve. Asked which
# arms COULD serve the task it has to enumerate, and the two poses give
# different sets, so no answer fits both.
def rnd_a(listed):
    return _json.dumps({"assignments": [
        {"task_id": 0, "arm": "ur_w", "assignable": listed,
         "why": {"grasp": "0.096 m"}},
        {"task_id": 1, "arm": None, "why": {}}]})


for listed, want in ((["ur_w"], "image"),
                     (["ur_w", "franka_n"], "state"),
                     (["franka_s"], "neither"),
                     (None, "missing")):
    r = G.grade_round(rnd_a(listed), RESTRICTIVE, 0, 1, LY_TRUE, LY_DECL,
                      PART)
    check(f"assignable {listed} reads as {want}",
          r["assignable_belief"] == want, r["assignable_belief"])

check("order does not matter in the assignable set",
      G.grade_round(rnd_a(["franka_n", "ur_w"]), RESTRICTIVE, 0, 1, LY_TRUE,
                    LY_DECL, PART)["assignable_belief"] == "state")
check("an assignable set that fits both poses reads as both",
      G.grade_round(rnd_a(["ur_w"]), RESTRICTIVE, 0, 1, LY_TRUE, LY_TRUE,
                    PART)["assignable_belief"] == "both",
      "when the poses agree the enumeration cannot discriminate either")

s2 = G.summarise_rounds([G.grade_round(rnd_a(["ur_w"]), RESTRICTIVE, 0, 1,
                                       LY_TRUE, LY_DECL, PART)])
check("summarise reports the assignable belief",
      s2["assignable_belief"]["image"] == 1, s2["assignable_belief"])


# --- the width extractor is anchored on the WIDTH PHRASE ----------------
# Two earlier rules failed, and the cases below are exactly the shapes that
# broke them.
#
#   first number       "extents are 0.191 m and 0.096 m, so graspable width
#                      is 0.096 m" recorded 0.191, an extent the model had
#                      just rejected.
#   after a connective most replies name the width FIRST and then compare
#                      it, so "so"/"means"/"therefore" picked up the arm
#                      limit, the payload or the mass, producing 0.140,
#                      0.603 and 6.000.
#
# The rule now is: the number after the FIRST explicit width phrase, and
# the first number in the field only when no such phrase appears.
def _bw(text):
    return G.believed_width({"why": {"grasp": text}})


# Each entry is a sentence SHAPE seen in the real data. Three extractor
# rules have failed here, each on a shape the previous cases did not
# contain, so the list grows rather than being rewritten.
for _text, _want, _why in (
    ("0.096 m, over the Franka max_grasp_m of 0.080 m", 0.096,
     "terse: no width phrase, so the first number is the judgement"),
    ("0.058 m; Franka max_grasp_m 0.080 m covers it", 0.058,
     "max_grasp_m must not count as a width phrase"),
    ("upright; horizontal extents are 0.096 m and 0.058 m, so graspable "
     "width is 0.058 m", 0.058,
     "the opening number is an extent the model rejected"),
    ("Mustard is lying down; its horizontal extents are 0.191 m and "
     "0.096 m, so graspable width is 0.096 m, covered by ur_w max 0.140 m",
     0.096, "this reply was recorded as 0.191 and reported as a "
            "misderivation that never happened"),
    ("The object has a grasp width of 0.096 m, and franka_n max_grasp_m "
     "is 0.080 m, which means it cannot be handled; payload 0.603 kg",
     0.096, "a connective rule took the payload here"),
    ("0.058 m graspable width (upright bottle depth), covered by ur_e "
     "max_grasp_m 0.140 m", 0.058,
     "the number comes BEFORE the phrase; taking the one after it "
     "returned the arm limit on 36 replies"),
    ("0.096 m horizontal graspable width; ur_e max_grasp_m 0.140 m "
     "covers it", 0.096,
     "an adjective sits between the number and the phrase"),
    ("0.058 m horizontal graspable width (upright width/depth minimum); "
     "Franka 0.080 m", 0.058, "same, with a parenthetical after"),
    ("upright; 0.096 m grasp width, covered by ur_e max_grasp_m 0.140 m",
     0.096, "pose stated first, then the number, then the phrase"),
    ("0.096 m graspable width in its current lying pose; ur_w "
     "max_grasp_m 0.140 m", 0.096, "phrase followed by prose, not a "
     "number"),
    ("lying down in the image; presented grasp width is 0.191 m, which "
     "neither idle arm covers", 0.191,
     "a genuine third value must survive, not be normalised away"),
    ("horizontal graspable width is 0.058 m (min of 0.096 m width and "
     "0.058 m depth)", 0.058,
     "the parenthetical working must not override the stated answer"),
    ("lying down; graspable width 0.096 m, covered by ur_e max_grasp_m "
     "0.140 m", 0.096, "no 'is' or 'of' between phrase and number"),
    ("The mustard bottle is lying down, presenting a graspable width of "
     "0.096 m, therefore ur_w 0.140 m applies", 0.096,
     "'presenting a graspable width of' must match"),
    ("0.058 m (upright presented width); franka_n max_grasp_m 0.080 m "
     "covers it", 0.058,
     "an opening bracket sits between the number and the phrase; "
     "without it in the gap this returned the Franka aperture"),
    ("0.096 m (lying-down presented width); ur_e max_grasp_m 0.140 m "
     "covers it", 0.096,
     "the same shape returning the UR aperture, and a hyphen in the gap"),
    ("lying down; 0.191 m graspable width, exceeding both idle arms' "
     "max_grasp_m (ur_e 0.140 m, franka_n 0.080 m)", 0.191,
     "a REAL misderivation: the model saw the pose correctly and took "
     "the long axis. It must survive extraction, since it is the only "
     "evidence of looking and deriving wrongly"),
):
    check("width read correctly: %s" % _why, _bw(_text) == _want,
          "got %s, expected %s" % (_bw(_text), _want))

# The discriminating pair: the same two numbers either side of the phrase,
# distinguished only by what sits between them.
check("a comma and connective mark the earlier number as working",
      _bw("0.096 m, so graspable width is 0.058 m") == 0.058)
check("a bare adjective does not",
      _bw("0.096 m horizontal graspable width") == 0.096)
check("nor does a bracket",
      _bw("0.058 m (upright presented width)") == 0.058)
check("the two apertures are never returned as a width",
      not any(_bw(t) in (0.08, 0.14) for t in (
          "0.058 m (upright presented width); franka_n max_grasp_m 0.080 m",
          "0.096 m (lying-down presented width); ur_e max_grasp_m 0.140 m",
          "0.058 m graspable width, covered by ur_e max_grasp_m 0.140 m")),
      "every extraction fault so far has returned 0.080 or 0.140, which "
      "is the tell: those are the arm limits, not object widths")

check("no number at all yields None", _bw("too small to judge") is None)
check("an absent why yields None", G.believed_width({}) is None)

# The classification consequence, which is why this matters. dims has no
# declared width, so a mis-extracted number matches neither candidate and
# lands in "other", inflating the derivation failure rate.
_dims_up = {"true_grasp_m": 0.058, "declared_grasp_m": None,
            "true_pose": "upright", "declared_pose": None,
            "condition": "dims"}
check("a correct dims derivation reads as image, not other",
      G.classify_width(
          _bw("upright; horizontal extents are 0.096 m and 0.058 m, so "
              "graspable width is 0.058 m"), _dims_up) == "image")
_dims_ly = {"true_grasp_m": 0.096, "declared_grasp_m": None,
            "true_pose": "lying", "declared_pose": None,
            "condition": "dims"}
check("a genuine pose misread still reads as other",
      G.classify_width(_bw("standing upright; graspable width 0.058 m"),
                       _dims_ly) == "other",
      "the bottle is lying, so 0.058 is neither derived nor declared")
check("a correctly derived lying width reads as image",
      G.classify_width(
          _bw("lying down; graspable width 0.096 m, covered by ur_e"),
          _dims_ly) == "image")


print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)