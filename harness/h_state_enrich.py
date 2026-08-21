"""Harness: the ENRICHED state variant (imports the REAL state_builder).

The enrichment must satisfy two things at once:

  1. It must be OFF by default and byte-identical to 2026-07-25d, so the
     existing vlm1/vlm2 episodes stay comparable and need no re-run.
  2. When ON, every reach_ok_arms list must equal what the REAL validator
     will enforce, point for point. A single disagreement would mean the
     model is told something the guard then refuses, which is the exact
     defect the variant exists to remove.

Also checks that the enrichment is geometry ONLY: grasp size, payload and
the idle sentence are untouched, so capability and busy-arm rejections
stay usable as untreated controls.

Run: python3 h_state_enrich.py
"""
import json
import os
import sys
import types

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from core.cell import cell_config as C                    # REAL config
from core.cell.zones import ZoneMap                       # REAL raster loader
from core.decision import state_builder as sb             # REAL builder

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


# --- a minimal cell that satisfies build_state, with REAL config values ---
class FakeScene:
    def __init__(self, positions):
        self.positions = positions

    def __getitem__(self, name):
        x, y = self.positions[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_coord(positions):
    arms = {}
    agents = {}
    for name in C.ARMS:
        arm = NS(disabled=False, _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm, state="IDLE")
    tasks = [NS(id=0, obj=list(positions)[0], dest=(-0.70, 0.50), done=False,
                failed=False, claimed=False, waiting_on=None, attempts=0)]
    return NS(cell=NS(scene=FakeScene(positions), arms=arms),
              agents=agents, pool=tasks,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))


POSITIONS = {"ycb_bowl": (-0.30, 0.55), "ycb_mug": (0.30, 0.55),
             "ycb_power_drill": (-0.65, -0.02)}

# Register the REAL YCB specs so build_state reads real categories, grasp
# sizes and masses rather than the legacy cube default.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm",
                                "ycb"))
from ycb_objects import register_specs                     # REAL registry
for scene_name in POSITIONS:
    register_specs(C.OBJECT_SPECS, scene_name, scene_name[len("ycb_"):])
BASKETS = {"basket_food": {"pos": (-0.70, 0.50)},
           "basket_kitchenware": {"pos": (0.70, 0.50)},
           "basket_tools": {"pos": (-0.70, -0.50)}}
engine = NS(active=list(POSITIONS), applied_log=[])
coord = make_coord(POSITIONS)

zm = ZoneMap(os.path.join(os.path.dirname(__file__), "..", "fourarm",
                          "core", "cell", "reachability", "rasters"))

plain = sb.build_state(coord, engine, tick=1, baskets=BASKETS)
rich = sb.build_state(coord, engine, tick=1, baskets=BASKETS, zonemap=zm)

# 1. OFF by default: nothing added anywhere
check("default state carries no reachability marker",
      "reachability" not in plain and not sb.is_enriched(plain))
check("default objects carry no reach_ok_arms",
      all("reach_ok_arms" not in o for o in plain["objects"]))
check("default baskets and pads carry no reach_ok_arms",
      all("reach_ok_arms" not in b for b in plain["baskets"].values())
      and all("reach_ok_arms" not in p
              for p in plain["exchange_pads"].values()))

# 2. the enriched state differs ONLY by the added lists
stripped = json.loads(json.dumps(rich))
stripped.pop("reachability", None)
for o in stripped["objects"]:
    o.pop("reach_ok_arms", None)
for d in (stripped["baskets"], stripped["exchange_pads"]):
    for v in d.values():
        v.pop("reach_ok_arms", None)
        v.pop("zone", None)
for a_ in stripped["arms"]:            # reach_m is dropped when enriched
    a_["reach_m"] = C.ARM_TYPES[a_["type"]]["reach"]
check("enriched state == default state, plus lists/zone, minus reach_m",
      stripped == json.loads(json.dumps(plain)),
      "differing keys: " + str([k for k in stripped
                                if stripped[k] != plain.get(k)]))

# 3. every list matches the REAL zonemap the validator uses
mismatch = []
for o in rich["objects"]:
    want = [a for a in C.ARMS if zm.reachable(a, *o["xy"])]
    if o.get("reach_ok_arms") != want:
        mismatch.append((o["name"], o.get("reach_ok_arms"), want))
for coll in ("baskets", "exchange_pads"):
    for name, v in rich[coll].items():
        want = [a for a in C.ARMS if zm.reachable(a, *v["xy"])]
        if v.get("reach_ok_arms") != want:
            mismatch.append((name, v.get("reach_ok_arms"), want))
check("every reach_ok_arms equals zonemap.reachable", not mismatch,
      str(mismatch[:3]))

# 4. the worked example: franka_s could not do bowl -> kitchenware, and
#    under enrichment it is absent from both lists, so the error the model
#    actually made at vlm2 round 1480 becomes unstateable from the lists
bowl = [o for o in rich["objects"] if o["name"] == "ycb_bowl"][0]
kw = rich["baskets"]["basket_kitchenware"]
both = [a for a in bowl["reach_ok_arms"] if a in kw["reach_ok_arms"]]
check("bowl -> kitchenware intersects to a non-empty arm set",
      len(both) >= 1, str(both))
check("franka_s is excluded by the intersection",
      "franka_s" not in both, str(both))

# 5. geometry ONLY: the untreated controls are untouched
check("grasp/payload fields unchanged (capability stays a control)",
      all(a["max_grasp_m"] == C.ARM_TYPES[a["type"]]["max_grasp_m"]
          and a["payload_kg"] == C.ARM_TYPES[a["type"]]["payload_kg"]
          for a in rich["arms"]))
check("arm state fields unchanged (busy_arm stays a control)",
      [a["state"] for a in rich["arms"]] == [a["state"] for a in plain["arms"]])
check("reach_m REMOVED when enriched (the competing signal)",
      all("reach_m" not in a for a in rich["arms"])
      and all("reach_m" in a for a in plain["arms"]))
check("base_xy retained (travel comparison still needs positions)",
      all("base_xy" in a for a in rich["arms"]))
check("baskets and pads state their own zone (regions become a copy)",
      all("zone" in b for b in rich["baskets"].values())
      and all("zone" in p_ for p_ in rich["exchange_pads"].values()))
# 6. prompts: baseline byte-identical, enriched differs by ONE rule
p_plain = sb.build_prompt(plain, "A")
p_rich = sb.build_prompt(rich, "A")
txt = p_rich[0]["content"]
check("baseline system prompt is byte-identical to the 25d wording",
      p_plain[0]["content"] == sb.SYSTEM_PROMPT.format(
          tx=C.TABLE_TOP[0], ty=C.TABLE_TOP[1], cr=C.CENTER_RADIUS,
          reach_rule=sb.REACH_RULE_BASELINE))
check("the two lineages use SEPARATE templates (they now differ wholesale)",
      sb.SYSTEM_PROMPT_SECTIONED is not sb.SYSTEM_PROMPT
      and "1. THE CELL" not in p_plain[0]["content"])
# The 25d rule, copied verbatim from the frozen delivered file
# (state_builder.py md5 44045f20ee471430a35dfd20689c8f58). If a future edit
# reflows this wording, the baseline column stops being comparable to the
# episodes already recorded, so pin it here rather than trusting the
# constant to be its own witness.
FROZEN_25D_RULE = (
    "transported to destinations. An arm can only do a task if BOTH the object\n"
    "and the destination are within its reach, AND the object fits within its\n"
    "grasp size and payload limits; large or heavy objects are UR-only. "
    "If no single")
check("baseline still renders the FROZEN 25d reach wording verbatim",
      FROZEN_25D_RULE in p_plain[0]["content"],
      p_plain[0]["content"][160:420])
check("baseline prompt contains the radius rule, not the list rule",
      "within its reach" in p_plain[0]["content"]
      and "reach_ok_arms" not in p_plain[0]["content"])
check("enriched prompt swaps in the list rule",
      "reach_ok_arms" in txt
      and "authoritative" in txt)
diff = [a == b for a, b in zip(p_plain[0]["content"].split("\n"),
                               txt.split("\n"))]
SECTIONS = ("THE CELL", "HARD RULES", "GUIDANCE", "YOUR ANSWER")
check("four sections present, in order",
      all(h in txt for h in SECTIONS)
      and [txt.index(h) for h in SECTIONS]
      == sorted(txt.index(h) for h in SECTIONS),
      str([h for h in SECTIONS if h not in txt]))
# the split mirrors the architecture: the validator enforces R1-R7 and
# vetoes nothing in G1-G5. If a rule ever migrates across that line the
# prompt would be claiming an enforcement the guard does not perform.
check("R1-R7 present and stated as rejectable",
      all(f"R{i}" in txt for i in range(1, 8))
      and "is rejected" in txt.split("GUIDANCE")[0])
check("G1-G5 present and stated as NOT enforced",
      all(f"G{i}" in txt for i in range(1, 6))
      and "Not enforced" in txt)
check("hard rules come before guidance",
      txt.index("HARD RULES") < txt.index("GUIDANCE"))
check("basket choice is GUIDANCE (sorted_correct is measured, not vetoed)",
      "G1" in txt and txt.index("G1") > txt.index("GUIDANCE"))
check("prompt got shorter, not longer", len(txt) < 3600, str(len(txt)))
check("capability stated ONCE, in section 2 (25d stated it twice)",
      txt.count("max_grasp_m") == 1
      and txt.count("payload_kg") == 1)
check("the UR-only category heuristic is gone",
      "UR-only" not in txt)
check("undefined urgency is gone from BOTH messages",
      "urgent" not in txt
      and "urgent" not in p_rich[1]["content"][0]["text"]
      and "urgent" in p_plain[1]["content"][0]["text"])
check("scarce-resource guidance present, makespan instruction absent",
      "could serve another queued task" in txt   # G4, wrapped
      and "makespan" not in txt.lower() and "sequence" not in txt.lower())
check("the idle SET is identical in both (only the ask differs)",
      p_plain[1]["content"][0]["text"].split("Idle arms right now:")[1]
      .split(".")[0]
      == p_rich[1]["content"][0]["text"].split("Idle arms right now:")[1]
      .split(".")[0])

# the trap that doubled capability errors: the list must NOT be readable
# as permission, so the prompt has to say so in as many words
check("R4 says the list is reach only and points back at R3",
      "says nothing about R3" in txt
      and "cannot pick up" in txt
      and "max_grasp_m" in txt and "payload_kg" in txt
      and "delicate_ok" in txt)
check("prompt no longer states arm radii in prose",
      "reach 1.30 m" not in txt
      and "reach 0.855 m" not in txt)
check("cube-era wording gone: category, not colour",
      "colour" not in txt)
check("regions are copied from the zone fields, not computed",
      "states its own" in txt
      and "x>=0,y>=0 is ne" not in txt)

# 7. version strings are distinct and derivable from the state alone
check("frozen baseline lineage still resolves to 25d",
      sb.prompt_version(plain) == sb.PROMPT_VERSION_BASELINE == "2026-07-25d",
      sb.prompt_version(plain))
check("enriched is the CURRENT PROMPT_VERSION",
      sb.prompt_version(rich) == sb.PROMPT_VERSION == "2026-08-01a"
      and sb.PROMPT_VERSION != sb.PROMPT_VERSION_BASELINE,
      sb.prompt_version(rich))
check("defaults are enriched: system_prompt() and prompt_version()",
      "reach_ok_arms" in sb.system_prompt()
      and sb.prompt_version() == sb.PROMPT_VERSION)

# 8. the allocator flag defaults OFF and only then passes a zonemap
from core.decision import vlm_allocator as va               # REAL allocator
seen = {}
_real_build_state = va.build_state
va.build_state = lambda c, e, tick=None, baskets=None, zonemap=None, \
    eligible=False: (seen.__setitem__("zonemap", zonemap)
                     or {"arms": [], "tasks": []})
va.build_prompt = lambda s, cond, image_b64=None: [
    {"role": "system", "content": "s"},
    {"role": "user", "content": [{"type": "text", "text": "t"}]}]
va.validate_decision = lambda d, c, z, b=None: (True, (0.1, 0.2), None, None)
fake = NS(cell=NS(scene="S"), agents={}, pool=[])
for flag, expect in ((False, None), (True, "ZM"), (None, "ZM")):
    kw = {} if flag is None else {"enriched": flag}   # None = rely on the default
    alloc = va.VLMAllocator(lambda: fake, engine=None, condition="A", **kw,
                            model_fn=lambda m, timeout=30.0:
                            '{"task_id": 0, "arm": "ur_w", "reason": "r"}')
    alloc.zonemap = "ZM"
    alloc._consult(round_token=1)
    check(f"enriched={flag} passes zonemap={expect!r} to build_state",
          seen["zonemap"] == expect, repr(seen["zonemap"]))
    check(f"enriched={flag} records the version it actually showed",
          alloc.prompt_version == sb.prompt_version(bool(flag) if flag is not None
                                                    else True),
          alloc.prompt_version)
va.build_state = _real_build_state

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
