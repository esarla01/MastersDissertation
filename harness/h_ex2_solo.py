"""h_ex2_solo: one queued task, one arm, and the Franka preference that
makes a single choice carry information.

Imports the REAL solo module, which imports the real transforms, legality
computation, prompt builder and grader. No live call is made.

What is pinned, and the failure each one guards:

  1. Only the flip object is queued. The clamp stays in "objects" and stays
     visible in the image, so the text never denies something plainly in
     the picture.
  2. G6 prefers a Franka, and says nothing about when it cannot be used.
     Stating the exception would name the capability check being measured
     and a correct answer would come cheaper than it should.
  3. G4 is trimmed. With one queued task it points at nothing, and it would
     push toward the Franka for the same reason G6 does, making the two
     indistinguishable.
  4. The opening line is NOT substituted. The base already asks for one
     task and one arm; the batch substitution existed only because the
     batch schema contradicted it.
  5. The correct arm DIFFERS by pose. That is the whole point: an earlier
     single-task attempt failed because the UR was legal under both poses,
     so the arm named carried no information.
  6. legal_declared equals legal_true under congruent and dims, and differs
     under conflict.
  7. An errored row is retried on resume rather than counted as answered.
  8. The command line builds.

Run:  python3 h_ex2_solo.py
"""

import argparse as _argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from experiments.ex2 import grade as G                           # noqa: E402
from experiments.ex2 import prompts as P                         # noqa: E402
from experiments.ex2 import solo as S                            # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


# The capture fixture comes from the run harness, which builds a real state
# through state_builder. Cut at the FIRST assertion: everything before it is
# setup in every version of that file, and running further hands back a
# fixture it has deliberately damaged to prove a missing frame fails loudly.
_RUN_H = os.path.join(HERE, "h_ex2_run.py")
_g = {"__name__": "fixture", "__file__": _RUN_H}
TMP = tempfile.mkdtemp()
CAP = os.path.join(TMP, "cap")
try:
    _src = open(_RUN_H).read()
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(_src[:_src.index("\ncheck(")], _RUN_H, "exec"), _g)
        shutil.copytree(_g["CAP"], CAP)
        try:
            _g["TMP"].cleanup()
        except Exception:                                  # noqa: BLE001
            pass
except Exception as exc:                                   # noqa: BLE001
    raise SystemExit("could not build the shared capture fixture: %s: %s"
                     % (type(exc).__name__, exc))

SCENES = {s["seq"]: s for s in S.load_scenes(CAP)}


def reply(arm, width="0.096 m", task_id=0):
    return json.dumps({"task_id": task_id, "arm": arm, "basket": None,
                       "regions": ["ne", "nw"],
                       "why": {"grasp": width, "payload": "0.603 kg ok",
                               "delicate": "not delicate"}})


def fixed(text):
    def _fn(messages, timeout=None, alias=None):
        return text
    return _fn


# 1. only the flip object is queued; the clamp survives as an object.
_msg, _meta = S.render(SCENES["p01_A"], "congruent")
_body = None
for _b in _msg[1]["content"]:
    if _b.get("type") == "text":
        _body, _ = json.JSONDecoder().raw_decode(
            _b["text"][_b["text"].index("{"):])
check("exactly one task is queued", len(_body["tasks"]) == 1,
      json.dumps(_body["tasks"]))
check("the queued task is the flip object",
      _body["tasks"][0]["object"] == _meta["flip_label"])
check("the clamp is still an object in the state",
      any("clamp" in o["name"] for o in _body["objects"]),
      "it is visible in the image; removing it would make the text deny "
      "something plainly there")
try:
    S.queue_flip_only({"tasks": []}, "ycb_mustard")
    check("a state with no flip task raises", False, "no exception")
except ValueError as e:
    check("a state with no flip task raises rather than sending nothing",
          "ycb_mustard" in str(e), str(e)[:60])

# 2, 3, 4. the prompt.
_sys = _msg[0]["content"]
check("G6 prefers a Franka", "\nG6  " in _sys and "Franka" in P.SOLO_PREFERENCE)
check("G6 does not state the exception",
      "unless" not in P.SOLO_PREFERENCE.lower()
      and "cannot" not in P.SOLO_PREFERENCE.lower(),
      "naming the capability check would make a correct answer cheap")
check("G4 is trimmed in solo", "\nG4  " not in _sys,
      "it points at no other task and would duplicate G6's direction")
check("G4 survives in the batch prompt",
      "\nG4  " in P.build_ex2_prompt(_body, "P2", "congruent")[0]["content"],
      "the round still needs it")
check("the opening line is left alone in solo",
      "choose ONE queued task" in _sys,
      "the base already asks for one task; the substitution exists only "
      "because the BATCH schema contradicted it")
check("the answer schema asks for one assignment, not a round",
      '"assignments"' not in _sys and '"task_id": <int>' in _sys)
check("the why block replaces the free-text reason",
      '"why"' in _sys and '"reason"' not in _sys,
      "width belief is graded the same way in both modes")

# 5. the correct arm differs by pose. Without this the choice says nothing.
_legal = {}
for _seq in ("p01_A", "p01_B"):
    _sc = SCENES[_seq]
    _m, _mt = S.render(_sc, "congruent")
    _tid = S.flip_task_id(_sc["state"], _mt["flip_prim"])
    _legal[_mt["true_pose"]] = S.legal_arms(_sc, _mt["flip_prim"], _tid)
check("a Franka is legal for the upright bottle",
      any(a.startswith("franka") for a in _legal["upright"]),
      "0.058 m is under the 0.080 limit: %s" % sorted(_legal["upright"]))
check("no Franka is legal for the lying bottle",
      not any(a.startswith("franka") for a in _legal["lying"]),
      "0.096 m is over it: %s" % sorted(_legal["lying"]))
check("the two poses give different legal sets",
      _legal["upright"] != _legal["lying"],
      "if they matched, the arm named would carry no information and this "
      "is exactly how the first single-task attempt failed")

# 6. declared legality per condition.
_rows = S.run(CAP, out_path=os.path.join(TMP, "a.jsonl"), models=("fake",),
              kind="pair", model_fn=fixed(reply("ur_e")))
_by = {}
for _r in _rows:
    _by.setdefault(_r["condition"], []).append(_r)
for _cond in ("congruent", "dims"):
    check("%s: legal_declared equals legal_true" % _cond,
          all(r["legal_declared"] == r["legal_true"] for r in _by[_cond]),
          "computing it from the other pose scored correct assignments "
          "as wrong and voided a whole run")
check("conflict: the two legal sets differ",
      all(r["legal_declared"] != r["legal_true"] for r in _by["conflict"]),
      "%d rows" % len(_by["conflict"]))
check("every row records which arm was named",
      all("arm" in r for r in _rows))
check("congruent width belief is a tie, never an image win",
      "image" not in {r["width_belief"] for r in _by["congruent"]},
      "both sources state the same number there")

# 7. an errored row is retried.
def _raises(messages, timeout=None, alias=None):
    raise RuntimeError("connection reset")


_ep = os.path.join(TMP, "err.jsonl")
S.run(CAP, out_path=_ep, models=("fake",), kind="pair", pair="p01",
      conditions=("congruent",), model_fn=_raises)
_calls = {"n": 0}


def _recovers(messages, timeout=None, alias=None):
    _calls["n"] += 1
    return reply("ur_e")


S.run(CAP, out_path=_ep, models=("fake",), kind="pair", pair="p01",
      conditions=("congruent",), model_fn=_recovers)
check("a row that errored is retried on resume", _calls["n"] > 0,
      "%d retried" % _calls["n"])
_calls["n"] = 0
S.run(CAP, out_path=_ep, models=("fake",), kind="pair", pair="p01",
      conditions=("congruent",), model_fn=_recovers)
check("a resumed run of good rows makes no calls", _calls["n"] == 0)

# 8. the command line builds.
_reg = {}
_orig = _argparse.ArgumentParser.add_argument


def _record(self, *args, **kw):
    for a in args:
        if isinstance(a, str) and a.startswith("--"):
            _reg[a] = _reg.get(a, 0) + 1
    return _orig(self, *args, **kw)


_argparse.ArgumentParser.add_argument = _record
try:
    try:
        S.main(["--dry-run", "--probes", CAP])
        _built = True
    except SystemExit as e:
        _built = e.code in (0, None)
    except _argparse.ArgumentError as e:
        _built = False
        print("   argparse rejected the CLI:", e)
finally:
    _argparse.ArgumentParser.add_argument = _orig
check("the command line parses without an argparse conflict", _built)
check("no flag is registered more than once",
      not {k: v for k, v in _reg.items() if v > 1},
      str({k: v for k, v in _reg.items() if v > 1}))

# 9. what the schema no longer asks for, and what it still must.
check("regions is dropped from the solo answer",
      '"regions"' not in _sys,
      "grading never reads it: legal_arms calls the validator with "
      "task_id, arm and basket only, and no EX2 scene takes a zone lock")
check("the regions explanation goes with it",
      "copy those two values" not in _sys,
      "three lines about a field that is no longer requested")
check("G3 is trimmed in solo", "\nG3  " not in _sys,
      "with one queued task there is no order to ignore")
check("G3 survives in the batch prompt",
      "\nG3  " in P.build_ex2_prompt(_body, "P2", "congruent")[0]["content"])

# basket, R5, R7 and G1 all STAY, and each depends on the captures rather
# than on the prompt. An EX2 task carries "dest_xy": null, so R7 fires on
# every trial and the model has to name a basket; G1 says which; R5 says
# how it is reached when the named arm cannot reach it directly.
check("basket is still requested", '"basket"' in _sys,
      "dest_xy is null in every capture, so R7 fires and a basket is "
      "required")
for _tag in ("R5", "R7"):
    check("%s survives in solo" % _tag, ("\n" + _tag + "  ") in _sys,
          "dest_xy is null in every capture, so a destination is still "
          "named and R5 still governs how it is reached")
check("waiting is still expressible",
      "task_id -1" in _sys and "\nG5  " in _sys,
      "a wait is never correct here, so choosing it is a signal rather "
      "than noise, and the grader scores it as noop")
check("the grasp-width sentence stays in the RUNG, not in R3",
      "presents" in P.RUNG_TEXT["P2"] and "presents" not in P.RUNG_TEXT["P0"],
      "moving it into R3 would put the hint in P0 and destroy the ladder")

# 10. the baskets carry no category, and every arm has one it can reach.
_names = list(_body["baskets"])
check("no basket is named for a category",
      not any(k in n for n in _names
              for k in ("food", "kitchen", "tool")),
      str(_names))
check("G1 is trimmed in solo", "\nG1  " not in _sys,
      "it points at a category the baskets no longer carry")
check("G1 survives in the batch prompt",
      "\nG1  " in P.build_ex2_prompt(_body, "P2", "congruent")[0]["content"])
check("the object keeps its true category",
      any(o.get("category") for o in _body["objects"]),
      "it is true and now decides nothing")
check("the answer says the boxes are interchangeable",
      "interchangeable" in _sys)

# THIS is the property the whole redesign rests on. basket_food was
# reachable by ur_w and not ur_e, so a correctly assigned lying bottle in
# an east scene needed a handover and a west one did not, putting a
# delivery cost on the arm choice under test. If any idle arm in any scene
# has no reachable box, that asymmetry is back.
_missing = []
for _s in SCENES.values():
    if _s["kind"] != "pair":
        continue
    _st = S.neutralise_baskets(_s["state"])
    _idle = {a["name"] for a in _st.get("arms", [])
             if a.get("state") == "IDLE" and not a.get("disabled")}
    for _arm in _idle:
        if not any(_arm in b.get("reach_ok_arms", [])
                   for b in _st["baskets"].values()):
            _missing.append((_s["seq"], _arm))
check("every idle arm can reach a box in every scene", not _missing,
      "%s; if not, the arm choice carries a delivery cost again"
      % (_missing or "checked"))

try:
    S.neutralise_baskets({"baskets": {}})
    check("a state with no baskets raises", False, "no exception")
except ValueError as e:
    check("a state with no baskets raises rather than sending nothing",
          "baskets" in str(e), str(e)[:50])

# 11. the self-contradiction detector, which is arithmetic not keywords.
_lim = {"franka_n": 0.08, "ur_e": 0.14}
check("a stated width over the named arm's limit is contradicted",
      G.self_contradicted(0.096, "franka_n", _lim) is True,
      "five qwen replies said 0.096 exceeds 0.08 and assigned franka_n "
      "anyway; they were scored follows_state, which counts a reply at "
      "war with itself as evidence the model believed the text")
check("a width within the limit is not contradicted",
      G.self_contradicted(0.096, "ur_e", _lim) is False
      and G.self_contradicted(0.058, "franka_n", _lim) is False)
check("no stated width gives no verdict, not a false one",
      G.self_contradicted(None, "franka_n", _lim) is None)
check("an unknown arm gives no verdict",
      G.self_contradicted(0.096, "nobody", _lim) is None)
check("the tolerance does not swallow the real gap",
      G.self_contradicted(0.081, "franka_n", _lim) is False
      and G.self_contradicted(0.096, "franka_n", _lim) is True,
      "0.006 covers rounding, not a 16 mm overshoot")
check("arm limits are read from the state, not hardcoded",
      G.arm_limits({"arms": [{"name": "a", "max_grasp_m": 0.5}]})
      == {"a": 0.5})

# reasoning categories, reported as secondary because they are keywords.
check("a reply citing only numbers reads as state_only",
      G.classify_reasoning({"grasp": "0.058 m, within 0.08 m"})
      == "state_only")
check("a reply mentioning the picture reads as image_referenced",
      G.classify_reasoning({"grasp": "the image shows it lying"})
      == "image_referenced")
check("a reply naming a disagreement reads as conflict_flagged",
      G.classify_reasoning({"grasp": "the text disagrees with the picture"})
      == "conflict_flagged")
check("an empty why reads as none",
      G.classify_reasoning({}) == "none"
      and G.classify_reasoning(None) == "none")

# every solo row carries both fields, and limits reach the grader.
check("solo rows carry the contradiction verdict",
      all("self_contradicted" in r for r in _rows))
check("solo rows carry a reasoning category",
      all(r.get("reasoning") for r in _rows))

# 12. rescoring deduplicates by trial id.
# A row that failed to parse is retried and both end up in the file.
# Reading every line counted the failure and its replacement as two
# trials, which put 24 rows in a 22-scene cell and two phantom
# unparseables in the reasoning column.
from experiments.ex2 import rescore as RS  # noqa: E402

_dup = os.path.join(TMP, "dupes.jsonl")
with open(_dup, "w") as _fh:
    _base = {"seq": "p01_A", "condition": "conflict", "model": "fake",
             "true_pose": "lying", "arm": None, "believed_width_m": None,
             "why": None}
    _fh.write(json.dumps(dict(_base, trial_id="t1",
                              outcome="unparseable")) + "\n")
    _fh.write(json.dumps(dict(_base, trial_id="t1", arm="ur_e",
                              believed_width_m=0.096,
                              why={"grasp": "0.096 m"},
                              outcome="uninformative")) + "\n")
    _fh.write(json.dumps(dict(_base, trial_id="t2", arm="ur_e",
                              believed_width_m=0.096,
                              why={"grasp": "0.096 m"},
                              outcome="uninformative")) + "\n")
_rs = RS.rescore(_dup, CAP)
check("a retried trial is counted once, not twice", len(_rs) == 2,
      "%d rows from 3 lines with one duplicated id" % len(_rs))
check("the retry replaces the failure it superseded",
      all(r["outcome"] != "unparseable" for r in _rs),
      "last write wins, as solo.py's own table already does")


# 13. the arm preference is counterbalanced, and it actually reaches the
# prompt. A Franka is legal only at 0.058 m, which is the TEXT's number on
# a lying scene and the IMAGE's on an upright one, so a model that merely
# leans Franka scores follows_state in one direction and follows_image in
# the other and cannot be told from one reading the picture.
_pref_text = {}
for _p in S.PREFERENCES:
    _pref_text[_p] = S.render(SCENES["p01_A"], "conflict",
                              _p)[0][0]["content"]
check("both preferences are offered", set(S.PREFERENCES) == {"franka", "ur"})
check("the franka preference names a Franka",
      "Prefer a Franka" in _pref_text["franka"])
check("the ur preference names a UR",
      "Prefer a UR" in _pref_text["ur"])
check("the two prompts actually differ",
      _pref_text["franka"] != _pref_text["ur"],
      "reading a module constant instead of the argument rendered the "
      "Franka wording under both and silently voided the counterbalance")
check("the ur preference does not mention a Franka in G6",
      "Prefer a Franka" not in _pref_text["ur"])
check("neither wording states the exception",
      not any(w in t.lower() for t in S.PREFERENCES
              for w in ("unless", "cannot handle")),
      "naming the capability check would make a correct answer cheap")
check("the preference changes nothing else in the prompt",
      len(_pref_text["franka"]) - len(_pref_text["ur"]) == len("Franka")
      - len("UR"),
      "only the arm word may differ")

_cb = os.path.join(TMP, "cb.jsonl")
_seen = []


def _watch(messages, timeout=None, alias=None):
    _seen.append("Prefer a UR" in messages[0]["content"])
    return reply("ur_e")


S.run(CAP, out_path=_cb, models=("fake",), conditions=("conflict",),
      preferences=("franka", "ur"), kind="pair", pair="p01",
      model_fn=_watch)
check("both preferences are actually sent", set(_seen) == {True, False},
      "sent %d prompts, ur wording in %d" % (len(_seen), sum(_seen)))
_rows_cb = [json.loads(x) for x in open(_cb) if x.strip()]
check("every row records which preference it ran under",
      {r.get("preference") for r in _rows_cb} == {"franka", "ur"})
check("the two preferences do not collide on trial id",
      len({r["trial_id"] for r in _rows_cb}) == len(_rows_cb),
      "without the preference in the id, the second run would resume onto "
      "the first and make no calls")
check("the table separates the preferences",
      "franka/" in S.table(_rows_cb) and "ur/" in S.table(_rows_cb),
      "the column now reads pref/rung")


# 14. P3 asks for justification first, and the SCHEMA must agree.
# Saying "fill in why before deciding" while listing "arm" first does
# nothing: generation runs left to right, so the arm is committed before a
# word of justification exists. Same failure as the opening line that
# asked for ONE task while the schema asked for EVERY.
import re as _re  # noqa: E402

_p2 = S.render(SCENES["p01_A"], "conflict", "franka", "P2")[0][0]["content"]
_p3 = S.render(SCENES["p01_A"], "conflict", "franka", "P3")[0][0]["content"]
check("P2 lists the arm before why",
      _p2.index('"arm"') < _p2.index('"why"'))
check("P3 lists why before the arm",
      _p3.index('"why"') < _p3.index('"arm"'),
      "an instruction to justify first cannot bite while the schema puts "
      "the arm first")
check("P3 still says to justify first",
      "BEFORE deciding which arm" in _p3)
check("P3 asks for the orientation, singular",
      "the\nobject's orientation" in _p3 or "the object's orientation"
      in _p3.replace("\n", " "),
      "solo queues one object, so 'each object' was wrong")

for _name, _sch in (("P0-P2", P.SOLO_SCHEMA),
                    ("P3", P.SOLO_SCHEMA_WHY_FIRST)):
    _body = _sch[_sch.index("{"):_sch.rindex("}") + 1]
    _t = _re.sub(r"<[^>]*>", '"x"', _body).replace('""x""', '"x"')
    try:
        json.loads(_t)
        _ok = True
    except Exception:
        _ok = False
    check("the %s answer template is itself valid JSON" % _name, _ok,
          "a malformed template invites a malformed reply; the first "
          "version omitted the comma after the why block")

# The rung is part of the trial id, or a P3 run resumes onto a P2 file.
_rr = os.path.join(TMP, "rungs.jsonl")
S.run(CAP, out_path=_rr, models=("fake",), conditions=("conflict",),
      preferences=("franka",), rungs=("P2", "P3"), kind="pair", pair="p01",
      model_fn=fixed(reply("ur_e")))
_rows_r = [json.loads(x) for x in open(_rr) if x.strip()]
check("the two rungs do not collide on trial id",
      len({r["trial_id"] for r in _rows_r}) == len(_rows_r),
      "without the rung in the id a P3 run would find every trial present "
      "and report itself complete having spent nothing")
check("every row records its rung",
      {r["rung"] for r in _rows_r} == {"P2", "P3"})
check("the table separates the rungs",
      "franka/P2" in S.table(_rows_r) and "franka/P3" in S.table(_rows_r))


# 15. text-only modality: the floor the image conditions are read against.
_v = S.render(SCENES["p01_A"], "conflict", "franka", "P0", "V")[0]
_a = S.render(SCENES["p01_A"], "conflict", "franka", "P0", "A")[0]
check("V attaches an image block",
      any(b.get("type") == "image_url" for b in _v[1]["content"]))
check("A attaches no image block",
      not any(b.get("type") == "image_url" for b in _a[1]["content"]))
_ta = _a[0]["content"]
check("the text-only prompt never mentions an image",
      "image" not in _ta.lower(),
      "build_prompt keeps mode A byte-identical to V on purpose, which "
      "would describe a side view that is not attached")
check("the text-only prompt never mentions a camera",
      "camera" not in _ta.lower())
check("the text-only prompt still describes the cell contents",
      "sorting baskets" in _ta and "exchange points" in _ta,
      "only the image references go, not the scene description")
check("the state still reaches the text-only prompt",
      "max_grasp_m" in json.dumps(_a[1]["content"]))

_mo = os.path.join(TMP, "modality.jsonl")
S.run(CAP, out_path=_mo, models=("fake",), conditions=("conflict",),
      preferences=("franka",), rungs=("P0",), modalities=("V", "A"),
      kind="pair", pair="p01", model_fn=fixed(reply("ur_e")))
_rows_m = [json.loads(x) for x in open(_mo) if x.strip()]
check("the two modalities do not collide on trial id",
      len({r["trial_id"] for r in _rows_m}) == len(_rows_m),
      "without modality in the id an A run would resume onto a V file")
check("every row records its modality",
      {r["modality"] for r in _rows_m} == {"V", "A"})

# 16. token usage is the provider's, recorded per call, and optional.
def _with_usage(messages, timeout=None, alias=None, return_usage=False):
    text = reply("ur_e")
    if return_usage:
        return text, {"prompt_tokens": 1200, "completion_tokens": 80,
                      "total_tokens": 1280}
    return text


_tu = os.path.join(TMP, "usage.jsonl")
S.run(CAP, out_path=_tu, models=("fake",), conditions=("conflict",),
      preferences=("franka",), rungs=("P0",), kind="pair", pair="p01",
      model_fn=_with_usage)
_rows_u = [json.loads(x) for x in open(_tu) if x.strip()]
check("token counts are recorded per call",
      all(r["prompt_tokens"] == 1200 and r["completion_tokens"] == 80
          for r in _rows_u))
check("latency is recorded per call",
      all(r.get("latency_ms") for r in _rows_u))
check("a client without usage support still works",
      all("prompt_tokens" in r for r in _rows_m)
      and all(r["prompt_tokens"] is None for r in _rows_m),
      "the fake model_fn takes no return_usage and must not break the run")
check("the cost table reports means and a median latency",
      "prompt" in S.cost_table(_rows_u)
      and "totals:" in S.cost_table(_rows_u))
check("errored rows are excluded from the cost means",
      "n=" not in S.cost_table([]) )


print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)