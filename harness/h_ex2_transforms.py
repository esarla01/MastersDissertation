"""h_ex2_transforms: the three descriptions say what they are meant to say,
and the falsification is complete.

Builds a real state with the REAL state builder, then applies the REAL
transforms. Nothing here restates a rule.

What is pinned, and the failure each one guards:

  1. congruent matches the picture. If it did not, the sanity check would
     be measuring something other than sanity.
  2. conflict declares the OTHER pose, and swaps grasp_m with it. A pose
     changed without its width, or the reverse, would let the model catch
     the lie by arithmetic and the experiment would measure text checking
     instead of grounding.
  3. dims withholds BOTH pose and grasp_m. If either survived, the model
     could answer without looking at the picture, which is the failure the
     condition exists to rule out.
  4. dims_m is present in every condition, identical across them, and
     always TRUE. It is intrinsic, so it leaks nothing and lying about it
     would be catchable by arithmetic.
  5. No pose suffix reaches the rendered text in any condition.
  6. The probe is never modified.
  7. meta records the truth, the declaration and the conflict direction,
     because the grader must not re-derive ground truth from a state that
     is deliberately lying.
  8. An unknown condition raises rather than defaulting: a conflict trial
     recorded as congruent would be invisible in the output.

Run:  python3 h_ex2_transforms.py
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


def build_probe(flip_prim):
    positions = {flip_prim: (0.275, 0.6), "ycb_large_clamp": (0.275, 0.175)}
    for scene_name in positions:
        register_specs(C.OBJECT_SPECS, scene_name, scene_name[len("ycb_"):])

    class Scene:
        def __getitem__(self, name):
            x, y = positions[name]
            return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))

    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=False, _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm, state="IDLE")
    pool = []
    for i, obj in enumerate(positions):
        cat = C.OBJECT_SPECS[obj]["category"]
        pool.append(NS(id=i, obj=obj,
                       dest=tuple(BASKETS["basket_" + cat]["pos"]),
                       done=False, failed=False, claimed=False,
                       waiting_on=None, attempts=0, dest_by=None))
    live = NS(cell=NS(scene=Scene(), arms=arms), agents=agents, pool=pool,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))
    engine = NS(active=list(positions), applied_log=[])
    st = sb.build_state(live, engine, tick=1, baskets=BASKETS, zonemap=zm)
    return {"state": st,
            "positions_exact": {k: list(v) for k, v in positions.items()}}


def flip_obj(state):
    return next(o for o in state["objects"] if o["name"] == "ycb_mustard")


for prim, true_pose, other in (("ycb_mustard_upright", "upright", "lying"),
                               ("ycb_mustard_lying", "lying", "upright")):
    print(f"\n--- true pose: {true_pose} ---")
    probe = build_probe(prim)
    before = copy.deepcopy(probe)

    st, meta = T.transform(probe, "congruent")
    o = flip_obj(st)
    check(f"[{true_pose}] congruent declares the true pose",
          o["pose"] == true_pose and meta["declared_pose"] == true_pose)
    check(f"[{true_pose}] congruent gives the true width",
          o["grasp_m"] == T.POSE_FACTS[true_pose]["grasp_m"], o["grasp_m"])

    st, meta = T.transform(probe, "conflict")
    o = flip_obj(st)
    check(f"[{true_pose}] conflict declares the OTHER pose",
          o["pose"] == other and meta["declared_pose"] == other)
    check(f"[{true_pose}] conflict swaps the width WITH the pose",
          o["grasp_m"] == T.POSE_FACTS[other]["grasp_m"],
          f"{o['grasp_m']} should be {T.POSE_FACTS[other]['grasp_m']}")
    check(f"[{true_pose}] conflict is internally consistent",
          all(o[k] == v for k, v in T.POSE_FACTS[other].items()),
          "a half-swap is catchable without looking at the picture")
    check(f"[{true_pose}] conflict direction is recorded",
          meta["direction"] == ("permissive" if true_pose == "upright"
                                else "restrictive"), meta["direction"])

    st, meta = T.transform(probe, "dims")
    o = flip_obj(st)
    check(f"[{true_pose}] dims withholds the pose", "pose" not in o)
    check(f"[{true_pose}] dims withholds the width", "grasp_m" not in o)
    check(f"[{true_pose}] dims declares nothing",
          meta["declared_pose"] is None and meta["declared_grasp_m"] is None)

    # dims_m: present everywhere, identical, always true
    dims = {c: flip_obj(T.transform(probe, c)[0])["dims_m"]
            for c in T.CONDITIONS}
    check(f"[{true_pose}] dims_m appears in every condition",
          all(d for d in dims.values()), dims)
    check(f"[{true_pose}] dims_m is identical across conditions",
          len({json.dumps(d, sort_keys=True) for d in dims.values()}) == 1,
          dims)
    check(f"[{true_pose}] dims_m is the measured intrinsic box",
          dims["conflict"] == {"height": 0.191, "width": 0.096,
                               "depth": 0.058}, dims["conflict"])

    for cond in T.CONDITIONS:
        blob = json.dumps(T.transform(probe, cond)[0])
        check(f"[{true_pose}] {cond} leaks no pose suffix",
              "_lying" not in blob and "_upright" not in blob)

    check(f"[{true_pose}] the probe is never modified", probe == before)
    check(f"[{true_pose}] meta carries the truth, not the declaration",
          meta["true_pose"] == true_pose
          and meta["flip_prim"] == prim
          and meta["true_grasp_m"] == T.POSE_FACTS[true_pose]["grasp_m"],
          meta)

# The two conflict directions must differ: only one of them separates a
# grounded model from one refusing the Franka out of blanket caution.
up = T.transform(build_probe("ycb_mustard_upright"), "conflict")[1]
ly = T.transform(build_probe("ycb_mustard_lying"), "conflict")[1]
print()
check("the two conflict directions are distinguished",
      up["direction"] != ly["direction"],
      f"{up['direction']} vs {ly['direction']}")
check("a permissive conflict understates the arms",
      up["declared_grasp_m"] > up["true_grasp_m"],
      "picture allows all four, text claims URs only")
check("a restrictive conflict overstates the arms",
      ly["declared_grasp_m"] < ly["true_grasp_m"],
      "picture allows URs only, text claims all four")

try:
    T.transform(build_probe("ycb_mustard_lying"), "congruant")
    check("an unknown condition raises", False, "no exception")
except ValueError as e:
    check("an unknown condition raises rather than defaulting",
          "congruant" in str(e), str(e)[:70])

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
