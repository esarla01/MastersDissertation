"""h_ex2_labels: pose suffixes are removed from what the model sees, and
the truth survives alongside.

Imports the REAL state builder to make a state, then the REAL transform.

What is pinned, and the failure each one guards:

  1. The rendered state says ycb_mustard, never ycb_mustard_lying or
     _upright. The suffix is the answer written into the text: in a
     conflict cell it would contradict the declared pose and let the model
     detect the lie without looking at the image.
  2. Task references are renamed too. A state whose objects say one thing
     and whose tasks say another would be internally inconsistent, and the
     validator keys on the task's object name.
  3. The input is NOT modified. A probe set is frozen; a transform that
     edited it would change the thing every other condition is compared
     against.
  4. The true prim survives in the returned map, and true_pose reads it
     from the REGISTRY rather than from the state, because in a conflict
     cell the state is deliberately wrong about exactly that.
  5. Two poses of one object in a single state raise. That cannot occur in
     a captured EX2 scene, and if it did the rename would merge two
     objects onto one label and corrupt both.
  6. Objects with only one pose are untouched.
  7. The block's three poses are named by RESTING FACE, and each prim is
     paired with the face it actually rests on. The prim names disagree
     with the geometry -- ycb_block_small rests on the MIDDLE face, so it
     is the edge -- and that pairing has been got wrong once.
  8. modernise_poses translates a pre-2026-08-27 block file and leaves a
     mustard file completely alone. A blanket rule would have rewritten
     every results file in runs/, all of which are mustard runs whose
     "upright" means the bottle standing.

Run:  python3 h_ex2_labels.py
"""

import copy
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
from ycb_objects import register_specs                          # noqa: E402
from ycb_scene import BASKETS                                   # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


POSITIONS = {"ycb_mustard_upright": (0.275, 0.6),
             "ycb_large_clamp": (0.275, 0.175)}
for scene_name in POSITIONS:
    register_specs(C.OBJECT_SPECS, scene_name, scene_name[len("ycb_"):])
zm = ZoneMap(os.path.join(ROOT, "core", "cell", "reachability", "rasters"))


class Scene:
    def __getitem__(self, name):
        x, y = POSITIONS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_live():
    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=False, _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm, state="IDLE")
    pool = []
    for i, obj in enumerate(POSITIONS):
        cat = C.OBJECT_SPECS[obj]["category"]
        pool.append(NS(id=i, obj=obj,
                       dest=tuple(BASKETS["basket_" + cat]["pos"]),
                       done=False, failed=False, claimed=False,
                       waiting_on=None, attempts=0, dest_by=None))
    return NS(cell=NS(scene=Scene(), arms=arms), agents=agents, pool=pool,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))


engine = NS(active=list(POSITIONS), applied_log=[])
state = sb.build_state(make_live(), engine, tick=1, baskets=BASKETS,
                       zonemap=zm)
before = copy.deepcopy(state)

out, prim_of = L.neutralise(state)

# 1 and 2. nothing the model reads carries a pose suffix
blob = json.dumps(out)
check("the rendered state contains no pose suffix",
      "_lying" not in blob and "_upright" not in blob,
      str([w for w in blob.split(chr(34)) if "mustard" in w][:3]))
check("the object is labelled ycb_mustard",
      any(o["name"] == "ycb_mustard" for o in out["objects"]),
      str([o["name"] for o in out["objects"]]))
check("task references are renamed with it",
      all(t["object"] != "ycb_mustard_upright" for t in out["tasks"])
      and any(t["object"] == "ycb_mustard" for t in out["tasks"]),
      str([t["object"] for t in out["tasks"]]))

# 3. the input is untouched
check("the input state is not modified", state == before,
      "a frozen probe set must not be edited in place")

# 4. the truth survives, and comes from the registry
check("the true prim is returned",
      prim_of["ycb_mustard"] == "ycb_mustard_upright", str(prim_of))
check("true_pose reads the registry, not the state",
      L.true_pose("ycb_mustard_upright") == "upright"
      and L.true_pose("ycb_mustard_lying") == "lying",
      "in a conflict cell the state is deliberately wrong about the pose")
check("an object with no pose entry has no true_pose",
      L.true_pose("ycb_large_clamp") is None)

# 5. a collision raises rather than merging
clash = copy.deepcopy(before)
clash["objects"].append(dict(clash["objects"][0], name="ycb_mustard_lying"))
try:
    L.neutralise(clash)
    check("two poses in one state raise", False, "no exception")
except ValueError as e:
    check("two poses in one state raise rather than merging",
          "merge" in str(e).lower() or "merging" in str(e).lower(),
          str(e)[:80])

# 6. single-pose objects untouched
check("the partner keeps its name",
      any(o["name"] == "ycb_large_clamp" for o in out["objects"]))
check("neutral_name is identity for a single-pose object",
      L.neutral_name("ycb_large_clamp") == "ycb_large_clamp")

# describe() reports the truth, separately from the rendered state
d = L.describe({"state": before})
check("describe reports the flip object and its true pose",
      d == {"flip_prim": "ycb_mustard_upright", "flip_label": "ycb_mustard",
            "true_pose": "upright", "others": ["ycb_large_clamp"]}, str(d))

try:
    L.describe({"state": {"objects": [{"name": "ycb_large_clamp"}]}})
    check("a scene with no flip object raises", False, "no exception")
except ValueError as e:
    check("a scene with no flip object raises", True, str(e)[:60])

# 7. the block is named by its resting face, and the pairing is geometric.
#
#     prim               face down       vertical  opening  name
#     ycb_block_upright  0.100 x 0.050     0.130    0.050   small_face
#     ycb_block_large    0.130 x 0.100     0.050    0.100   large_face
#
# 0.100 x 0.050 is the SMALLEST face of a 0.130 x 0.100 x 0.050 block, so
# the prim that rests on it is the small_face however its name reads.
for _prim, _face in (("ycb_block_upright", "small_face"),
                     ("ycb_block_large", "large_face")):
    check("%s rests on the %s" % (_prim, _face),
          L.TRUE_POSE[_prim] == _face, L.TRUE_POSE[_prim])
check("the block's faces are two distinct names",
      len({L.TRUE_POSE[p] for p, lab in L.POSE_ENTRIES.items()
           if lab == "ycb_block"}) == 2)
# The third prim is still on disk and still spawnable. It must not be a
# registry pose entry, or a capture of it would load and be scored as if
# the design still used it.
check("the withdrawn middle face is not a registry entry",
      "ycb_block_small" not in L.POSE_ENTRIES
      and "ycb_block_small" not in L.TRUE_POSE,
      "it was removed on 2026-08-27; its 34 captures remain on disk and "
      "experiments.ex2.run.load_scenes skips them by name")
check("and 'edge' is not a face of the block any more",
      "edge" not in L.block_faces(), str(sorted(L.block_faces())))
check("no block pose is a posture word",
      not any(L.TRUE_POSE[p] in ("upright", "lying")
              for p, lab in L.POSE_ENTRIES.items() if lab == "ycb_block"),
      "posture is not what the opening follows from, so the name must be "
      "geometric or it could be read off as an outcome")
check("the mustard pilot keeps its posture words",
      L.TRUE_POSE["ycb_mustard_upright"] == "upright"
      and L.TRUE_POSE["ycb_mustard_lying"] == "lying",
      "a bottle has no faces, and its rows must stay readable")
check("pose_prim inverts the pairing",
      L.pose_prim("ycb_block", "small_face") == "ycb_block_upright"
      and L.pose_prim("ycb_block", "large_face") == "ycb_block_large")
check("and the withdrawn face inverts to nothing",
      L.pose_prim("ycb_block", "edge") is None,
      "a stale caller must get None, not a prim that is still spawnable")
check("a superseded pose word resolves to no prim",
      all(L.pose_prim("ycb_block", w) is None
          for w in ("lying_large_face", "lying_small_face")),
      "an old command must fail to resolve rather than silently pick one")

# 8. the shim, and what it refuses to touch.
_mustard = [{"true_pose": "upright", "declared_pose": "lying"},
            {"true_pose": "lying", "declared_pose": "upright"}]
check("a mustard file is left completely alone",
      L.modernise_poses(_mustard) == 0
      and _mustard[0]["true_pose"] == "upright",
      "every results file in runs/ is a mustard run, and its 'upright' "
      "means the bottle standing, not the block's smallest face")

_block = [{"true_pose": "upright", "declared_pose": "lying_large_face"},
          {"true_pose": "lying_small_face", "declared_pose": "lying_large_face"},
          {"true_pose": "lying_large_face", "declared_pose": "upright"}]
check("a block file is translated, every row", L.modernise_poses(_block) == 3)
check("the ambiguous word is translated only inside a block file",
      _block[0]["true_pose"] == "small_face",
      "'upright' is only read as the block's smallest face when the file "
      "also carries a word that only ever named the block")
check("the unambiguous words translate",
      _block[1]["true_pose"] == "edge"
      and _block[2]["true_pose"] == "large_face")
check("including to a face the design has withdrawn",
      _block[1]["true_pose"] not in L.block_faces(),
      "runs/ex2_q1_cue_*.jsonl are kept as the evidence for withdrawing "
      "it, so the shim must still READ them. Translating to 'edge' and "
      "letting require_face reject it downstream is the loud failure; "
      "deleting the mapping would leave the old word untranslated and the "
      "failure harder to read")
check("declared_pose is translated with true_pose",
      [r["declared_pose"] for r in _block]
      == ["large_face", "large_face", "small_face"],
      "translating one and not the other would leave a conflict row "
      "disagreeing with itself")
check("every translated word is a pose word this module knows",
      all(r[f] in set(L.TRUE_POSE.values()) | {"edge"} for r in _block
          for f in ("true_pose", "declared_pose")),
      "'edge' is knowable and no longer current: see the check above")
check("translating twice changes nothing more",
      L.modernise_poses(_block) == 0,
      "the shim must be safe to run on an already-current file")
check("a current block file is untouched",
      L.modernise_poses([{"true_pose": "edge",
                          "declared_pose": "large_face"}]) == 0)

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
