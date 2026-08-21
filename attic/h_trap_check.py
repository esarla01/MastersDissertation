"""h_trap_check: the G4 scarce-arm check classifies a decision correctly,
and its chance floor is computed rather than assumed.

Imports the REAL state builder, the REAL validator (through
probe_store.legal_options) and the REAL checker. The traps are constructed
so the right answer is known independently of the code under test.

The cell used here, which makes the trap arithmetic checkable by hand:

    bowl        delicate, kitchenware -> franka_n only
    large_clamp 0.122 m, tools         -> ur_w only
    soup_can    0.068 m, food          -> any idle arm, direct or relayed

The option sets are NOT assumed, they were read off the real validator
before this fixture was written. With ur_w, ur_e and franka_n idle: the
soup can takes any of the three, the bowl takes only franka_n and the clamp
only ur_w. So franka_n and ur_w are both scarce and ur_e is the single safe
choice, giving a chance floor of one in three.

Drop to ur_w and franka_n idle and BOTH remaining options are scarce, so
the model cannot comply at all: that is "all_scarce", excluded from the
rate. Use ur_e and franka_s and no other task has any option, so nothing is
scarce and complying is free: that is "no_scarcity".

What is pinned:

  1. Complying and stranding are told apart on a constructed trap where the
     answer is known.
  2. The three non-opportunity verdicts are separated rather than lumped:
     no_choice, no_scarcity and all_scarce each mean something different
     and only the first two are common.
  3. The chance floor equals safe/total on each opportunity. Without it a
     measured 70% cannot be read, because if 70% of options were safe
     anyway then 70% is what indifference looks like.
  4. Rejected proposals and noops are NOT scored: neither became an
     allocation, so neither can strand anything.
  5. Misaligned files are refused rather than zipped together.

Run:  python3 h_trap_check.py
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
from analysis import trap_check as tc                           # noqa: E402
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


# Deliberately near the centre so every arm reaches every object and the
# only thing separating them is CAPABILITY. That keeps the trap arithmetic
# hand-checkable.
POSITIONS = {
    "ycb_soup_can":    (0.10037, -0.20074),   # any arm, direct or relayed
    "ycb_bowl":        (-0.10043, 0.10028),   # delicate: Frankas only
    "ycb_large_clamp": (0.10017, 0.05061),    # 0.122 m: URs only
}
for scene_name in POSITIONS:
    register_specs(C.OBJECT_SPECS, scene_name, scene_name[len("ycb_"):])

zm = ZoneMap(os.path.join(ROOT, "core", "cell", "reachability", "rasters"))
EXACT = {k: list(v) for k, v in POSITIONS.items()}


class LiveScene:
    def __getitem__(self, name):
        x, y = POSITIONS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_live(idle):
    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=False, _carried=None,
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
SOUP, BOWL, CLAMP = 0, 1, 2


def probe_for(idle):
    st = sb.build_state(make_live(idle), engine, tick=1, baskets=BASKETS,
                        zonemap=zm)
    return {"state": st, "positions_exact": EXACT, "frame_path": None,
            "provenance": {"seq": 1, "round": 1}}


# ---------------------------------------------------------------------------
# 1. the constructed trap
# ---------------------------------------------------------------------------
# ur_w, ur_e and franka_n idle. The soup can takes all three; franka_n is
# the only arm for the bowl and ur_w the only one for the clamp; so ur_e is
# the single safe choice.
p3 = probe_for(("ur_w", "ur_e", "franka_n"))

r = tc.classify_decision(p3, SOUP, "ur_e", BASKETS)
check("giving the soup can to the un-needed arm is compliance",
      r["verdict"] == "complied" and r["safe"] == ["ur_e"]
      and set(r["scarce"]) == {"franka_n", "ur_w"}, str(r))
check("the chance floor is safe/total, not assumed",
      abs(r["chance"] - 1.0 / 3.0) < 1e-9, str(r["chance"]))

r = tc.classify_decision(p3, SOUP, "franka_n", BASKETS)
check("spending the only Franka on the soup can strands the bowl",
      r["verdict"] == "stranded" and r["stranded_tasks"] == [BOWL], str(r))

r = tc.classify_decision(p3, SOUP, "ur_w", BASKETS)
check("spending the only clamp-capable arm strands the clamp",
      r["verdict"] == "stranded" and r["stranded_tasks"] == [CLAMP], str(r))

# ---------------------------------------------------------------------------
# 2. the three non-opportunities, told apart
# ---------------------------------------------------------------------------
r = tc.classify_decision(p3, BOWL, "franka_n", BASKETS)
check("a task with one legal arm is no_choice, not a failure",
      r["verdict"] == "no_choice" and r["options"] == ["franka_n"], str(r))

# ur_e and franka_s idle: neither the bowl nor the clamp has any legal arm,
# so nothing is uniquely needed and complying is free.
p_ur = probe_for(("ur_e", "franka_s"))
r = tc.classify_decision(p_ur, SOUP, "ur_e", BASKETS)
check("with nothing scarce the decision is no_scarcity, not compliance",
      r["verdict"] == "no_scarcity", str(r))

# One Franka and one UR idle: the soup can has two arms, but franka_n is
# the only one for the bowl and ur_w the only one for the clamp, so BOTH
# options strand something and the model cannot comply.
p2 = probe_for(("ur_w", "franka_n"))
r = tc.classify_decision(p2, SOUP, "ur_w", BASKETS)
check("when every option is scarce the decision is excluded, not scored",
      r["verdict"] == "all_scarce" and set(r["options"]) == {"franka_n",
                                                             "ur_w"},
      str(r))

# ---------------------------------------------------------------------------
# 3. end to end over an episode, including what must NOT be scored
# ---------------------------------------------------------------------------
TMP = tempfile.TemporaryDirectory()
FDIR = os.path.join(TMP.name, "ep_frames")
os.makedirs(FDIR)
TRAIL = os.path.join(FDIR, "consults.jsonl")

IDLE_SETS = [("ur_w", "ur_e", "franka_n"),     # opportunity: complies
             ("ur_w", "ur_e", "franka_n"),     # opportunity: strands
             ("ur_e", "franka_s"),             # no_scarcity
             ("ur_w", "ur_e", "franka_n")]     # a noop, must not be scored
with open(TRAIL, "w") as f:
    for i, idle in enumerate(IDLE_SETS):
        st = sb.build_state(make_live(idle), engine, tick=i, baskets=BASKETS,
                            zonemap=zm)
        f.write(json.dumps({"seq": i + 1, "round": i * 10, "condition": "A",
                            "prompt_version": sb.prompt_version(st),
                            "state": st, "positions_exact": EXACT,
                            "image_file": None, "messages": []}) + "\n")

LOG = [
    {"round": 0, "result": "valid_first", "task_id": SOUP, "arm": "ur_e",
     "latency_ms": 1.0, "reason": "ur_e takes the can, sparing franka_n"},
    {"round": 10, "result": "valid_first", "task_id": SOUP, "arm": "franka_n",
     "latency_ms": 1.0, "reason": "franka_n is closest"},
    {"round": 20, "result": "valid_first", "task_id": SOUP, "arm": "ur_e",
     "latency_ms": 1.0, "reason": "ur_e is free"},
    {"round": 30, "result": "noop", "task_id": -1, "arm": None,
     "latency_ms": 1.0, "reason": "waiting"},
]
EP = os.path.join(TMP.name, "episode.json")
json.dump({"allocator": {"log": LOG}}, open(EP, "w"))

rep = tc.check_episode(TRAIL, EP, BASKETS)
s = rep["summary"]
check("only accepted decisions are scored", s["accepted_decisions"] == 3,
      str(s))
check("two G4 opportunities found, one complied and one stranded",
      s["g4_opportunities"] == 2 and s["complied"] == 1
      and s["stranded"] == 1, str(s))
check("the no_scarcity decision is counted but not scored",
      s["no_scarcity"] == 1, str(s))
check("compliance rate is over the opportunities only",
      abs(s["compliance_rate"] - 0.5) < 1e-9, str(s["compliance_rate"]))
check("chance rate is computed from the options, not assumed",
      abs(s["chance_rate"] - 1.0 / 3.0) < 1e-9, str(s["chance_rate"]))
check("the stranded row names the task it stranded",
      any(r.get("stranded_tasks") == [BOWL] for r in rep["rows"]),
      str([r.get("stranded_tasks") for r in rep["rows"]]))

# A rejected proposal never became an allocation, so it cannot strand
# anything and must not be scored.
LOG2 = list(LOG)
LOG2[0] = {"round": 0, "result": "rejected", "task_id": SOUP,
           "arm": "franka_s", "latency_ms": 1.0,
           "rejected": [{"attempt": 1, "task_id": SOUP, "arm": "franka_s",
                         "basket": None, "rejected_because": "arm franka_s "
                                                             "is not idle",
                         "unparseable": False}]}
EP2 = os.path.join(TMP.name, "episode_rej.json")
json.dump({"allocator": {"log": LOG2}}, open(EP2, "w"))
rep2 = tc.check_episode(TRAIL, EP2, BASKETS)
check("a rejected proposal is not scored against G4",
      rep2["summary"]["accepted_decisions"] == 2
      and rep2["summary"]["g4_opportunities"] == 1,
      str(rep2["summary"]))

short = {"allocator": {"log": LOG[:2]}}
EP3 = os.path.join(TMP.name, "episode_short.json")
json.dump(short, open(EP3, "w"))
rep3 = tc.check_episode(TRAIL, EP3, BASKETS)
check("misaligned files are refused rather than zipped",
      "summary" not in rep3 and rep3["notes"], str(rep3["notes"]))

TMP.cleanup()

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
