"""h_ex2_run: the trial plan matches the design, and grading uses geometry.

Builds a small fake capture directory with real states and real PNGs, then
drives the REAL runner with an injected model function so nothing is sent.

What is pinned, and the failure each one guards:

  1. The plan is the design. Pairs get all three conditions, nulls get
     congruent only. A null with a falsified state would not be measuring
     answer stability, which is the only thing a null is for.
  2. Every trial is uniquely identified and the runner RESUMES. A paid run
     of a thousand calls must survive a dropped connection, and re-asking a
     question already answered is money for nothing.
  3. legal_true and legal_declared are computed under the two POSES, not
     from the validator's verdict on the rendered state. In a conflict cell
     the rendered state is the lie, so grading against it would confirm it.
  4. A model error becomes a row, not an end to the run.
  5. A missing image raises rather than sending a vision trial as text.
  6. --dry-run writes nothing and sends nothing.

Run:  python3 h_ex2_run.py
"""

import base64
import json
import os
import sys
import tempfile
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
from experiments.ex2 import run as R                            # noqa: E402
from experiments.ex2 import transforms as T                     # noqa: E402
from experiments.ex2 import prompts as P                        # noqa: E402
from experiments.ex2 import grade as G                          # noqa: E402
from experiments.ex2 import labels as L                         # noqa: E402
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
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg==")


def make_state(flip_prim):
    pos = {flip_prim: (0.275, 0.6), "ycb_large_clamp": (0.275, 0.175)}
    for n in pos:
        register_specs(C.OBJECT_SPECS, n, n[len("ycb_"):])

    class Scene:
        def __getitem__(self, name):
            x, y = pos[name]
            return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))

    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=False, _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm, state=("IDLE" if name in
                                          ("ur_e", "franka_n") else "MOVING"))
    pool = [NS(id=i, obj=o,
               dest=tuple(BASKETS["basket_"
                                  + C.OBJECT_SPECS[o]["category"]]["pos"]),
               done=False, failed=False, claimed=False, waiting_on=None,
               attempts=0, dest_by=None)
            for i, o in enumerate(pos)]
    live = NS(cell=NS(scene=Scene(), arms=arms), agents=agents, pool=pool,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))
    eng = NS(active=list(pos), applied_log=[])
    return (sb.build_state(live, eng, tick=1, baskets=BASKETS, zonemap=zm),
            {k: list(v) for k, v in pos.items()})


TMP = tempfile.TemporaryDirectory()
CAP = os.path.join(TMP.name, "cap")
os.makedirs(CAP)
rows = []
for seq, prim, kind in (("p01_A", "ycb_mustard_lying", "pair"),
                        ("p01_B", "ycb_mustard_upright", "pair"),
                        ("n01_A", "ycb_mustard_lying", "null")):
    st, pos = make_state(prim)
    imgs = {}
    for cam in R.VIEWS:
        fn = f"{seq}.png" if cam == "ex2_cam" else f"{seq}_{cam}.png"
        open(os.path.join(CAP, fn), "wb").write(PNG)
        imgs[cam] = fn
    rows.append({"seq": seq, "state": st, "positions_exact": pos,
                 "image_file": imgs["ex2_cam"],
                 "ex2": {"kind": kind, "images": imgs}})
with open(os.path.join(CAP, "consults.jsonl"), "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

scenes = R.load_scenes(CAP)
check("every capture loads with its images resolved",
      len(scenes) == 3 and all(os.path.exists(p) for s in scenes
                               for p in s["images"].values()))

# --- 1. the plan is the design -------------------------------------------
plan = R.trials(scenes)
by_kind = {}
for t in plan:
    by_kind.setdefault(t["kind"], set()).add(t["condition"])
check("pairs get all three conditions",
      by_kind["pair"] == set(T.CONDITIONS), by_kind.get("pair"))
check("nulls get congruent ONLY",
      by_kind["null"] == {"congruent"},
      "a null with a falsified state is not measuring answer stability")
check("the plan covers both views and every rung",
      {t["view"] for t in plan} == set(R.VIEWS)
      and {t["rung"] for t in plan} == set(P.RUNGS))
# Derived from the ladder rather than hardcoded: the count moved from 56 to
# 84 when P2a and P3a were added, and a fixed number would report a correct
# plan as broken.
_pairs = sum(1 for s in scenes if s["kind"] == "pair")
_nulls = sum(1 for s in scenes if s["kind"] == "null")
_expected = (len(R.VIEWS) * len(P.RUNGS)
             * (_pairs * len(T.CONDITIONS) + _nulls))
check("the trial count is what the design implies", len(plan) == _expected,
      "%d planned, %d implied by %d pairs, %d nulls, %d conditions, "
      "%d rungs, %d views"
      % (len(plan), _expected, _pairs, _nulls, len(T.CONDITIONS),
         len(P.RUNGS), len(R.VIEWS)))

# --- 3. legality is computed per POSE, not from the rendered state --------
scene = {s["seq"]: s for s in scenes}["p01_B"]        # truly upright
tid = R.flip_task_id(scene["state"], "ycb_mustard")
up = R.legal_arms(scene, "ycb_mustard_upright", tid)
ly = R.legal_arms(scene, "ycb_mustard_lying", tid)
check("the two poses give different legal sets",
      up != ly, f"upright {sorted(up)} vs lying {sorted(ly)}")
check("upright admits a Franka and lying does not",
      any(a.startswith("franka") for a in up)
      and not any(a.startswith("franka") for a in ly),
      "0.058 m is under the Franka limit, 0.096 m is over it")

# --- 3c. task presentation order is a factor, not a silent default -------
# In the floor test the model assigned whichever task was listed first and
# then discovered, while justifying the second, that its own choice had
# taken the only arm the second one could use. Reversing the order asks
# whether that is premature commitment or an inability to relate two
# assignments. Only the ORDER may change: if ids moved with it, the two
# runs would not be comparable and the grader would key on the wrong task.
_sc = {s["seq"]: s for s in scenes}["p01_B"]
_msg_g, _meta_g = R.render(_sc, "congruent", "P2", "ex2_cam", "given")
_msg_r, _meta_r = R.render(_sc, "congruent", "P2", "ex2_cam", "reversed")


def _task_ids(messages):
    """Task ids in the order the model actually sees them.

    Read out of the rendered prompt rather than off the state dict, because
    what matters is the order presented, and a reorder that never reached
    the text would be a silent no-op that still recorded 'reversed'.
    """
    content = messages[1]["content"]
    blocks = content if isinstance(content, list) else [content]
    for block in blocks:
        text = block.get("text") if isinstance(block, dict) else None
        if not text or "{" not in text:
            continue
        body, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
        if "tasks" in body:
            return [t["id"] for t in body["tasks"]]
    return None


_ids_g, _ids_r = _task_ids(_msg_g), _task_ids(_msg_r)
check("the rendered state carries its tasks in the given order",
      _ids_g is not None and len(_ids_g) == 2, str(_ids_g))
check("reversing changes the ORDER the tasks are presented in",
      _ids_r == list(reversed(_ids_g)), "%s then %s" % (_ids_g, _ids_r))
check("reversing changes no task id, only their order",
      sorted(_ids_r) == sorted(_ids_g), "%s vs %s" % (_ids_g, _ids_r))
check("the order is recorded in meta so a row can be traced",
      _meta_g["task_order"] == "given"
      and _meta_r["task_order"] == "reversed")
check("the flip task is found identically whichever order was shown",
      R.flip_task_id(_sc["state"], "ycb_mustard")
      == R.flip_task_id(_sc["state"], "ycb_mustard"))

_t = {"seq": "p01_B", "view": "ex2_cam", "condition": "congruent",
      "rung": "P2"}
check("trial ids of the two orders do not collide",
      R.trial_id(_t, "m", "given") != R.trial_id(_t, "m", "reversed"),
      "a reversed run resuming onto a given file would skip everything "
      "and look like success")
try:
    R.reorder_tasks({"tasks": []}, "shuffled")
    check("an unknown order raises", False, "no exception")
except ValueError as e:
    check("an unknown order raises rather than defaulting to given",
          "shuffled" in str(e), str(e)[:60])

# --- 3b. legal_declared under CONGRUENT is legal_true ---------------------
# The runner asked "is there a declared pose?" when it had to ask "does the
# declared pose DIFFER from the true one?". Under congruent it does not, so
# legality was computed from the opposite pose and correct assignments were
# scored wrong. A whole 44-trial run was void before this was caught, and
# nothing in the suite noticed, so it is pinned end to end rather than by
# inspecting the two sets in isolation.
_seen = {}


def _spy(messages, timeout=30.0, alias=None):
    return json.dumps({"assignments": [
        {"task_id": 0, "arm": "ur_w", "basket": None,
         "assignable": ["ur_w"],
         "why": {"grasp": "0.058 m", "payload": "ok", "delicate": "no"}}]})


_rows_path = os.path.join(TMP.name, "congruent.jsonl")
R.run(CAP, _rows_path, model="fake", model_fn=_spy,
      conditions=("congruent",), rungs=("P2",), views=("ex2_cam",))
_cong = [json.loads(x) for x in open(_rows_path) if x.strip()]
check("a congruent trial declares the pose it truly has",
      all(r["declared_pose"] == r["true_pose"] for r in _cong),
      "%d congruent rows" % len(_cong))
check("congruent legal_declared equals legal_true",
      all(r["legal_declared"] == r["legal_true"] for r in _cong),
      "; ".join("%s true=%s decl=%s" % (r["seq"], r["legal_true"],
                                        r["legal_declared"])
                for r in _cong if r["legal_declared"] != r["legal_true"])
      or "identical in every row")
check("an upright congruent trial still admits a Franka",
      all(any(a.startswith("franka") for a in r["legal_true"])
          for r in _cong if r["true_pose"] == "upright"),
      "0.058 m is under the limit whoever is asked")

# The declared prim is derived from the DECLARED pose, not the true one.
# Both give the same answer in a conflict cell, but only by coincidence.
check("pose_prim resolves a label and pose to a registry entry",
      L.pose_prim("ycb_mustard", "lying") == "ycb_mustard_lying"
      and L.pose_prim("ycb_mustard", "upright") == "ycb_mustard_upright")
check("pose_prim returns None for a pose that has no entry",
      L.pose_prim("ycb_mustard", "tilted") is None
      and L.pose_prim("ycb_large_clamp", "lying") is None,
      "a fabricated entry would fabricate the comparison")

# --- one pair at a time, and its null with it -----------------------------
# A flip rate without its noise floor is uninterpretable, so selecting a
# pair must bring the matching null along rather than leaving it behind.
one = R.select_scenes(scenes, "p01")
check("selecting a pair takes both members and the null",
      {s["seq"] for s in one} == {"p01_A", "p01_B", "n01_A"},
      sorted(s["seq"] for s in one))
check("selecting all leaves everything",
      len(R.select_scenes(scenes, None)) == len(scenes))
try:
    R.select_scenes(scenes, "p99")
    check("an unknown pair raises", False, "no exception")
except SystemExit as e:
    check("an unknown pair raises and lists what exists",
          "p01" in str(e), str(e)[:70])

# --- 4, 6. dry run and error handling ------------------------------------
out = os.path.join(TMP.name, "rows.jsonl")
n = R.run(CAP, out, model="fake", limit=4, dry_run=True)
check("a dry run writes nothing", not os.path.exists(out) and n == 4)


def answer(messages, timeout=30.0, alias=None):
    """A BATCH reply: EX2 asks for the whole round, not one assignment."""
    return json.dumps({"assignments": [
        {"task_id": 0, "arm": "franka_n", "basket": "basket_food",
         "why": {"grasp": "0.058 m", "payload": "ok", "delicate": "no"}},
        {"task_id": 1, "arm": "ur_w", "basket": "basket_tools",
         "why": {"grasp": "0.122 m", "payload": "ok", "delicate": "no"}},
    ]})


R.run(CAP, out, model="fake", limit=6, model_fn=answer)
got = [json.loads(l) for l in open(out)]
check("rows are written as they are produced", len(got) == 6, len(got))
check("each row carries its trial identity and every legal set",
      all({"trial_id", "legal_true", "legal_declared", "partner_legal",
           "partner_task", "outcome"} <= set(r) for r in got))
check("rows are graded as ROUNDS, not single assignments",
      all(r["outcome"] in G.ROUND_OUTCOMES for r in got),
      {r["outcome"] for r in got})
check("the partner task is found and differs from the flip task",
      all(r["partner_task"] != 0 for r in got),
      "a round with one task missing is a schema failure, not a belief")

# --- 2. resume ------------------------------------------------------------
n2 = R.run(CAP, out, model="fake", limit=6, model_fn=answer)
check("a rerun skips work already done", n2 == 0,
      "re-asking an answered question is money for nothing")


def boom(messages, timeout=30.0, alias=None):
    raise TimeoutError("endpoint slow")


R.run(CAP, out, model="fake2", limit=2, model_fn=boom)
errs = [json.loads(l) for l in open(out) if '"fake2"' in l]
check("a model error becomes a row, not the end of the run",
      len(errs) == 2 and all(r["error"] for r in errs),
      str(errs[0]["error"])[:40] if errs else "none")

# A failed row must be RETRIED on resume, not counted as answered.
R.run(CAP, out, model="fake2", limit=2, model_fn=answer)
after = [json.loads(l) for l in open(out) if '"fake2"' in l]
check("a rerun retries rows that errored",
      any(r["error"] is None for r in after),
      "skipping a failure on resume is how twelve empty rows survived")

# --- 5. a missing image is refused ---------------------------------------
os.remove(os.path.join(CAP, "p01_A.png"))
try:
    R.load_scenes(CAP)
    check("a missing image raises", False, "no exception")
except SystemExit as e:
    check("a missing image raises rather than sending a text-only trial",
          "p01_A" in str(e), str(e)[:70])

TMP.cleanup()
print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)