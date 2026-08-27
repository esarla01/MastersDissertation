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
# The BLOCK, not the mustard. The mustard is the pilot object and has two
# posture words, not faces, so rendering it now raises in
# labels.require_face -- correctly, since the answer schema lists three
# face names a bottle does not have.
for seq, prim, kind in (("p01_A", "ycb_block_large", "pair"),
                        ("p01_B", "ycb_block_upright", "pair"),
                        ("n01_A", "ycb_block_large", "null")):
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
      and {t["rung"] for t in plan} == set(R.RUNGS))
# Derived from the design rather than hardcoded: the count moves whenever
# a rung is added or removed, and a fixed number would report a correct
# plan as broken.
_pairs = sum(1 for s in scenes if s["kind"] == "pair")
_nulls = sum(1 for s in scenes if s["kind"] == "null")
_expected = (len(R.VIEWS) * len(R.RUNGS)
             * (_pairs * len(T.CONDITIONS) + _nulls))
check("the trial count is what the design implies", len(plan) == _expected,
      "%d planned, %d implied by %d pairs, %d nulls, %d conditions, "
      "%d rungs, %d views"
      % (len(plan), _expected, _pairs, _nulls, len(T.CONDITIONS),
         len(R.RUNGS), len(R.VIEWS)))

# --- 3. legality is computed per POSE, not from the rendered state --------
scene = {s["seq"]: s for s in scenes}["p01_B"]        # truly upright
tid = R.flip_task_id(scene["state"], "ycb_block")
up = R.legal_arms(scene, "ycb_block_upright", tid)
ly = R.legal_arms(scene, "ycb_block_large", tid)
check("the two resting faces give different legal sets",
      up != ly, f"small_face {sorted(up)} vs large_face {sorted(ly)}")
check("the small face admits a Franka and the large face does not",
      any(a.startswith("franka") for a in up)
      and not any(a.startswith("franka") for a in ly),
      "0.050 m is under the Franka limit, 0.100 m is over it")

# --- 3d. the idle UR is the one that can actually reach the object -------
# Every block capture was made with capture_ex2_scene's default
# --idle "ur_w,franka_n", which is right for the west positions and wrong
# for the east ones: there the object is reached by ur_e, so idle & reach
# collapses to {franka_n} and large_face has no legal arm at all. The whole
# east half carried no contrast. This is the fix, and it is checked against
# the REAL validator rather than against the arm list.
_e = {s["seq"]: s for s in scenes}
_flip = lambda st: [o for o in st["objects"] if "block" in o["name"]][0]

for _seq, _s in _e.items():
    _obj = _flip(_s["state"])
    _idle = {a["name"] for a in _s["state"]["arms"]
             if a["state"] == "IDLE" and not a["disabled"]}
    _urs = {a["name"] for a in _s["state"]["arms"]
            if a["name"].startswith("ur")}
    _reach = set(_obj.get("reach_ok_arms") or [])
    check("%s: exactly one UR is idle" % _seq, len(_idle & _urs) == 1,
          sorted(_idle & _urs))
    check("%s: the idle UR is one that reaches the object" % _seq,
          (_idle & _urs) <= _reach,
          "idle UR %s, reach %s" % (sorted(_idle & _urs), sorted(_reach)))
    check("%s: franka_n stays idle" % _seq, "franka_n" in _idle)

check("the idle UR is recorded on the scene",
      all(s["idle_ur"] in ("ur_w", "ur_e") for s in scenes),
      "a row must be traceable to the idle set it was asked under")

# The raw captures are still readable unchanged, which is what makes this a
# presentation choice rather than an edit to the record.
_raw = R.load_scenes(CAP, present_ur=False)
check("present_ur=False reads the captures as written",
      all(s["idle_ur"] is None for s in _raw))
check("the normalisation changes only arm states",
      all(R.present_reachable_ur(r["state"])[0].get("objects")
          == r["state"].get("objects") for r in _raw),
      "it must not touch an object, a task or a basket")

# It must FAIL rather than guess when no single UR is nearer.
_nostate = {"objects": [{"name": "ycb_block_large", "reach_ok_arms": []}],
            "arms": [], "tasks": []}
try:
    R.present_reachable_ur(_nostate)
    check("an ambiguous idle set raises", False, "no exception")
except ValueError as exc:
    check("an ambiguous idle set raises rather than defaulting",
          "Exactly one must" in str(exc), str(exc)[:60])

# --- 3c. REMOVED 2026-08-27 ----------------------------------------------
# This section checked a task-presentation-order factor: R.reorder_tasks,
# a "task_order" key in meta, a fifth argument to R.render and a third to
# R.trial_id. None of those exist in run.py and none ever did in this
# tree, so the section raised TypeError on import and the whole file
# reported nothing. It was already failing before the prompt module was
# replaced.
#
# It is deleted rather than skipped: a harness that skips is a harness
# that passes while measuring nothing. If the order factor is wanted, it
# has to be built in run.py first and pinned here afterwards. Note that
# a trial now queues ONE task, so a presentation order over two tasks no
# longer describes anything the model sees.

# --- 3b. legal_declared under CONGRUENT is legal_true ---------------------
# The runner asked "is there a declared pose?" when it had to ask "does the
# declared pose DIFFER from the true one?". Under congruent it does not, so
# legality was computed from the opposite pose and correct assignments were
# scored wrong. A whole 44-trial run was void before this was caught, and
# nothing in the suite noticed, so it is pinned end to end rather than by
# inspecting the two sets in isolation.
_seen = {}


def _spy(messages, timeout=30.0, alias=None):
    """A reply in the CURRENT schema: one task, one arm, typed fields."""
    return json.dumps({"task_id": 0, "arm": "ur_w", "basket": "box_1",
                       "opening_needed_m": 0.100})


_rows_path = os.path.join(TMP.name, "congruent.jsonl")
R.run(CAP, _rows_path, model="fake", model_fn=_spy,
      conditions=("congruent",), rungs=("N0",), views=("ex2_cam",))
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
      "0.050 m is under the limit whoever is asked")

# The declared prim is derived from the DECLARED pose, not the true one.
# Both give the same answer in a conflict cell, but only by coincidence.
check("pose_prim resolves a label and pose to a registry entry",
      L.pose_prim("ycb_block", "small_face") == "ycb_block_upright"
      and L.pose_prim("ycb_block", "large_face") == "ycb_block_large",
      "read the geometry, not the prim names: ycb_block_upright rests on "
      "the SMALLEST face, and the names predate the geometric vocabulary")
check("a face the design no longer uses resolves to nothing",
      L.pose_prim("ycb_block", "edge") is None,
      "the middle face was withdrawn on 2026-08-27; a stale caller must "
      "get None rather than a prim that is still on disk")
check("pose_prim returns None for a pose that has no entry",
      L.pose_prim("ycb_block", "tilted") is None
      and L.pose_prim("ycb_large_clamp", "large_face") is None,
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
    """A single-assignment reply. The batch round is gone: the prompt asks
    for ONE task and ONE arm, so a round reply would not be in schema."""
    return json.dumps({"task_id": 0, "resting_face": "large_face",
                       "opening_needed_m": 0.100, "arm": "ur_w",
                       "basket": "box_1"})


R.run(CAP, out, model="fake", limit=6, model_fn=answer)
got = [json.loads(l) for l in open(out)]
check("rows are written as they are produced", len(got) == 6, len(got))
check("each row carries its trial identity and every legal set",
      all({"trial_id", "legal_true", "legal_declared", "flip_task",
           "preference", "outcome"} <= set(r) for r in got),
      sorted(set(got[0]) & {"trial_id", "legal_true", "legal_declared",
                            "flip_task", "preference", "outcome"}))
check("rows are graded as SINGLE assignments, not rounds",
      all(r["outcome"] in G.OUTCOMES for r in got),
      {r["outcome"] for r in got})
check("only the flip task is queued",
      all(r["flip_task"] is not None for r in got),
      "the prompt asks for ONE task, so a scene with two queued would let "
      "the model answer about the partner and measure nothing")
check("the typed fields reach the row",
      all(r["opening_needed_m"] == 0.100 and r["resting_face"] == "large_face"
          for r in got),
      "no extractor stands between the reply and the measurement")

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