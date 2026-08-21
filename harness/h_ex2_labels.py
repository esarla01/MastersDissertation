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

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
