"""h_buffer_density: the availability-buffer counterfactual promotes the
right arms and counts the resulting choice correctly.

Imports the REAL state builder, the REAL validator (through
probe_store.legal_options) and the REAL measurement. The episode is
synthetic so the arithmetic is checkable by hand.

What is pinned:

  1. A buffer of 0 changes nothing. If it did, every comparison against the
     unbuffered baseline would be against a moved goalpost.
  2. An arm is promoted only when it frees within the window, using
     done_tick, which is stamped on arrival home, the instant the zone
     locks release and the arm is genuinely free again.
  3. Promotion increases the number of tasks with a real choice. That is
     the whole point of the mechanism and it must be visible.
  4. A disabled arm is never promoted, however soon its task ends. It is
     frozen for the episode.
  5. Misaligned files are refused rather than zipped together.

Run:  python3 h_buffer_density.py
"""

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
from analysis.episode import episode_buffer_density as bd                       # noqa: E402
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


POSITIONS = {
    "ycb_soup_can":    (0.10037, -0.20074),
    "ycb_bowl":        (-0.10043, 0.10028),
    "ycb_large_clamp": (0.10017, 0.05061),
}
for scene_name in POSITIONS:
    register_specs(C.OBJECT_SPECS, scene_name, scene_name[len("ycb_"):])
zm = ZoneMap(os.path.join(ROOT, "core", "cell", "reachability", "rasters"))
EXACT = {k: list(v) for k, v in POSITIONS.items()}


class LiveScene:
    def __getitem__(self, name):
        x, y = POSITIONS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_live(idle, dead=()):
    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=(name in dead), _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm,
                          state=("IDLE" if name in idle else "MOVING"))
    pool = []
    for i, obj in enumerate(POSITIONS):
        cat = C.OBJECT_SPECS[obj]["category"]
        pool.append(NS(id=i, obj=obj,
                       dest=tuple(BASKETS["basket_" + cat]["pos"]),
                       done=False, failed=False, claimed=False,
                       waiting_on=None, attempts=0, dest_by=None))
    return NS(cell=NS(scene=LiveScene(), arms=arms), agents=agents, pool=pool,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))


engine = NS(active=list(POSITIONS), applied_log=[])
SOUP = 0

# One consult at tick 1000 with only ur_e idle. ur_w frees at 1150, so a
# 200-tick buffer promotes it and a 100-tick one does not. franka_n frees
# at 1900, far outside any window tested.
TICK = 1000
TASKS = [
    {"id": 90, "arm": "ur_w", "exec_start_tick": 800, "done_tick": 1150},
    {"id": 91, "arm": "franka_n", "exec_start_tick": 900, "done_tick": 1900},
    {"id": 92, "arm": "franka_s", "exec_start_tick": 900, "done_tick": 1050},
]

TMP = tempfile.TemporaryDirectory()
FDIR = os.path.join(TMP.name, "ep_frames")
os.makedirs(FDIR)
TRAIL = os.path.join(FDIR, "consults.jsonl")
st = sb.build_state(make_live(("ur_e",)), engine, tick=TICK, baskets=BASKETS,
                    zonemap=zm)
with open(TRAIL, "w") as f:
    f.write(json.dumps({"seq": 1, "round": TICK, "condition": "A",
                        "prompt_version": sb.prompt_version(st),
                        "state": st, "positions_exact": EXACT,
                        "image_file": None, "messages": []}) + "\n")
EP = os.path.join(TMP.name, "episode.json")
json.dump({"tasks": TASKS,
           "allocator": {"log": [{"round": TICK, "result": "valid_first",
                                  "task_id": SOUP, "arm": "ur_e",
                                  "latency_ms": 1.0, "reason": "ur_e"}]}},
          open(EP, "w"))

probe = {"state": st, "positions_exact": EXACT, "frame_path": None,
         "provenance": {"seq": 1, "round": TICK}}

_, promoted = bd.apply_buffer(probe, TASKS, 0)
check("a zero buffer promotes nothing", promoted == [], str(promoted))

_, promoted = bd.apply_buffer(probe, TASKS, 100)
check("an arm freeing in 150 ticks is NOT promoted by a 100-tick buffer",
      [n for n, _ in promoted] == ["franka_s"], str(promoted))

_, promoted = bd.apply_buffer(probe, TASKS, 200)
check("a 200-tick buffer promotes it, with the wait recorded",
      sorted(n for n, _ in promoted) == ["franka_s", "ur_w"]
      and dict(promoted)["ur_w"] == 150, str(promoted))

# franka_n frees at 1900, so it waits 900 ticks from this consult. Inside
# a 1000-tick window, outside an 800-tick one. Both directions checked, so
# the boundary is pinned rather than assumed.
_, promoted = bd.apply_buffer(probe, TASKS, 800)
check("an arm waiting 900 ticks is outside an 800-tick window",
      "franka_n" not in dict(promoted), str(promoted))
_, promoted = bd.apply_buffer(probe, TASKS, 1000)
check("and inside a 1000-tick one",
      dict(promoted).get("franka_n") == 900, str(promoted))

# A disabled arm is frozen for the episode and must never be promoted.
st_dead = sb.build_state(make_live(("ur_e",), dead=("ur_w",)), engine,
                         tick=TICK, baskets=BASKETS, zonemap=zm)
probe_dead = {"state": st_dead, "positions_exact": EXACT, "frame_path": None,
              "provenance": {"seq": 1, "round": TICK}}
_, promoted = bd.apply_buffer(probe_dead, TASKS, 400)
check("a disabled arm is never promoted, however soon its task ends",
      "ur_w" not in dict(promoted), str(promoted))

rep = bd.measure(TRAIL, EP, (0, 100, 200), BASKETS)
by_n = {r["buffer_ticks"]: r for r in rep["results"]}
check("promotion increases the number of tasks with a real choice",
      by_n[200]["tasks_with_choice"] > by_n[0]["tasks_with_choice"],
      str([(r["buffer_ticks"], r["tasks_with_choice"])
           for r in rep["results"]]))
check("the zero-buffer row is the unbuffered baseline",
      by_n[0]["arms_promoted"] == 0)
check("every buffer row scores the same decisions",
      len({r["decisions_scored"] for r in rep["results"]}) == 1,
      str([r["decisions_scored"] for r in rep["results"]]))

json.dump({"tasks": TASKS, "allocator": {"log": []}}, open(EP, "w"))
rep2 = bd.measure(TRAIL, EP, (0,), BASKETS)
check("misaligned files are refused rather than zipped",
      not rep2["results"] and rep2["notes"], str(rep2["notes"]))

TMP.cleanup()
print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
