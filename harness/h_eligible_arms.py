"""Harness: the ELIGIBLE-ARMS ablation (imports the REAL state_builder).

The ablation resolves eligibility FOR the model instead of asking it to
work eligibility out: each task carries "eligible_arms", the arms that are
capable of the object and can reach both the object and its destination.

Two things must hold at once, and the first matters more than the second:

  1. OFF by default. The state, the rendered prompt and the version string
     must be byte-identical to what runs today. If the ablation leaks into
     the default path, every 2026-08-01a episode already recorded stops
     being comparable and this harness is the only thing that would catch
     it before the re-runs are wasted.
  2. ON, every list must equal an INDEPENDENT recomputation from
     cell_config plus the real zonemap: the same numbers the validator
     enforces. A list that disagrees with the guard would hand the model a
     confident wrong answer, which is worse than the arithmetic it
     replaces.

Also checks the empty list is produced and stated (no single arm can do
the task, so it needs a relay), that disabled arms are excluded, and that
R3 and R4 are the ONLY lines of the prompt that move.

Run: python3 h_eligible_arms.py
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
from core.control.tasks import route_via_pad              # REAL pad router

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


class FakeScene:
    def __init__(self, positions):
        self.positions = positions

    def __getitem__(self, name):
        x, y = self.positions[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


# large_clamp is the worked case: grasp_m 0.122 against a 0.08 m Franka,
# yet both Frankas reach it. bowl is delicate, so both URs are excluded.
POSITIONS = {"ycb_bowl": (-0.30, 0.55),
             "ycb_mug": (0.30, 0.55),
             "ycb_large_clamp": (0.10, 0.30),
             "ycb_power_drill": (-0.65, -0.02)}

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm",
                                "ycb"))
from ycb_objects import register_specs                     # REAL registry
for scene_name in POSITIONS:
    register_specs(C.OBJECT_SPECS, scene_name, scene_name[len("ycb_"):])

BASKETS = {"basket_food": {"pos": (-0.70, 0.50)},
           "basket_kitchenware": {"pos": (0.70, 0.50)},
           "basket_tools": {"pos": (-0.70, -0.50)}}
DEST = (0.70, 0.50)                       # kitchenware


def make_coord(positions, dead=()):
    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=(name in dead), _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm, state="IDLE")
    pool = [NS(id=i, obj=o, dest=DEST, done=False, failed=False,
               claimed=False, waiting_on=None, attempts=0)
            for i, o in enumerate(positions)]
    # one sorting task with no destination yet: the basket is the model's
    # choice under R7, so eligibility is scored on the object alone
    pool.append(NS(id=99, obj="ycb_power_drill", dest=None, done=False,
                   failed=False, claimed=False, waiting_on=None, attempts=0))
    return NS(cell=NS(scene=FakeScene(positions), arms=arms),
              agents=agents, pool=pool,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))


engine = NS(active=list(POSITIONS), applied_log=[])
coord = make_coord(POSITIONS)
zm = ZoneMap(os.path.join(os.path.dirname(__file__), "..", "fourarm",
                          "core", "cell", "reachability", "rasters"))

listed = sb.build_state(coord, engine, tick=1, baskets=BASKETS, zonemap=zm)
abl = sb.build_state(coord, engine, tick=1, baskets=BASKETS, zonemap=zm,
                     eligible=True)

# ---------------------------------------------------------------------------
# 1. OFF by default: the current column must not move by a single byte
# ---------------------------------------------------------------------------
default = sb.build_state(coord, engine, tick=1, baskets=BASKETS, zonemap=zm)
check("default state carries the plain 'listed' marker",
      default.get("reachability") == "listed", str(default.get("reachability")))
check("default tasks carry NO eligible_arms",
      all("eligible_arms" not in t for t in default["tasks"]))
check("default is not flagged as the ablation",
      not sb.has_eligible(default) and sb.is_enriched(default))
check("default version string is unchanged",
      sb.prompt_version(default) == sb.PROMPT_VERSION == "2026-08-01a",
      sb.prompt_version(default))

# The rendered default prompt, pinned. R3 was inlined in the template before
# this change and is now a substituted constant; if the substitution altered
# so much as a space, the 28c episodes already recorded stop being
# comparable to anything run after it.
FROZEN_R3 = ('R3  The arm must be able to handle the object, on every leg:\n'
             '      "grasp_m" at most the arm\'s "max_grasp_m"\n'
             '      "mass_kg" at most the arm\'s "payload_kg"\n'
             '      a "delicate" object needs an arm whose "delicate_ok" is'
             ' true\n')
p_def = sb.build_prompt(default, "A")[0]["content"]
check("default prompt still renders R3 byte-for-byte as before",
      FROZEN_R3 in p_def, repr(p_def[p_def.find("R3"):][:220]))
check("default prompt length pinned (3596 chars on 2026-08-01a)",
      len(p_def) == 3596, str(len(p_def)))
check("default prompt never mentions eligible_arms",
      "eligible_arms" not in p_def)

# ---------------------------------------------------------------------------
# 2. ON: every list equals an INDEPENDENT recomputation
# ---------------------------------------------------------------------------
def want(obj_name, dest, dead=()):
    """Recomputed here from cell_config and the raster, deliberately NOT by
    calling the builder's own helper: a table that agrees with itself
    proves nothing."""
    spec = C.OBJECT_SPECS[obj_name]
    out = []
    for a in C.ARMS:
        if a in dead:
            continue
        t = C.ARM_TYPES[C.ARMS[a]["type"]]
        if spec.get("delicate", False) and not t["delicate_ok"]:
            continue
        if spec["grasp_m"] > t["max_grasp_m"]:
            continue
        if spec["mass_kg"] > t["payload_kg"]:
            continue
        if not zm.reachable(a, *POSITIONS[obj_name]):
            continue
        if dest is not None and not zm.reachable(a, *dest):
            # Since 2026-08-01 an arm that cannot deliver directly is still
            # eligible when the cell can route a handover behind it. The
            # ROUTER is imported rather than re-implemented here: this
            # cross-check exists to second-guess the capability arithmetic,
            # not to keep a second copy of the pad-selection rule.
            probe = types.SimpleNamespace(obj=obj_name, dest=dest)
            if route_via_pad(probe, POSITIONS[obj_name], [a], zm, ())[0] is None:
                continue
        out.append(a)
    return out


by_id = {t["id"]: t for t in abl["tasks"]}
check("every actionable task carries an eligible_arms list",
      all("eligible_arms" in t for t in abl["tasks"]),
      str([t["id"] for t in abl["tasks"] if "eligible_arms" not in t]))

mismatch = []
for t in abl["tasks"]:
    exp = want(t["object"], DEST if t["id"] != 99 else None)
    if t["eligible_arms"] != exp:
        mismatch.append((t["id"], t["object"], t["eligible_arms"], exp))
check("every eligible_arms equals the independent recomputation",
      not mismatch, str(mismatch[:3]))

# the worked case: reach says three arms, capability says one
clamp = next(t for t in abl["tasks"] if t["object"] == "ycb_large_clamp")
clamp_obj = next(o for o in abl["objects"] if o["name"] == "ycb_large_clamp")
check("large_clamp reach lists more arms than eligibility does",
      len(clamp_obj["reach_ok_arms"]) > len(clamp["eligible_arms"]),
      f"reach {clamp_obj['reach_ok_arms']} vs eligible {clamp['eligible_arms']}")
check("neither Franka is eligible for large_clamp (0.122 m vs 0.08 m)",
      not any(a.startswith("franka") for a in clamp["eligible_arms"]),
      str(clamp["eligible_arms"]))
bowl = next(t for t in abl["tasks"] if t["object"] == "ycb_bowl")
check("no UR is eligible for the delicate bowl",
      not any(a.startswith("ur") for a in bowl["eligible_arms"]),
      str(bowl["eligible_arms"]))

# a task with no destination is scored on the object alone
drill = by_id[99]
check("a task with dest_xy null is scored on the object alone",
      drill["dest_xy"] is None
      and drill["eligible_arms"] == want("ycb_power_drill", None),
      str(drill["eligible_arms"]))

# an empty list must be PRODUCED and STATED, not omitted: it is how the
# model is told a relay is required
unreachable = (2.5, 2.5)                  # off the table entirely
coord_far = make_coord(POSITIONS)
for t in coord_far.pool:
    t.dest = unreachable
far = sb.build_state(coord_far, engine, tick=1, baskets=BASKETS, zonemap=zm,
                     eligible=True)
check("an impossible task yields an EMPTY list, present not omitted",
      all(t.get("eligible_arms") == [] for t in far["tasks"]
          if t["dest_xy"] is not None),
      str([(t["id"], t.get("eligible_arms", "MISSING"))
           for t in far["tasks"]][:3]))

# disabled arms are excluded: the field promises usable arms
victim = next(a for a in C.ARMS)
coord_dead = make_coord(POSITIONS, dead=(victim,))
dead_state = sb.build_state(coord_dead, engine, tick=1, baskets=BASKETS,
                            zonemap=zm, eligible=True)
check(f"a disabled arm ({victim}) never appears in any eligible_arms",
      all(victim not in t["eligible_arms"] for t in dead_state["tasks"]),
      str([t["eligible_arms"] for t in dead_state["tasks"]][:3]))
check("but it DOES still appear in reach_ok_arms (reach is physical)",
      any(victim in o.get("reach_ok_arms", []) for o in dead_state["objects"]))

# ---------------------------------------------------------------------------
# 3. the ablation state differs from the default ONLY by the added lists
# ---------------------------------------------------------------------------
stripped = json.loads(json.dumps(abl))
stripped["reachability"] = "listed"
for t in stripped["tasks"]:
    t.pop("eligible_arms", None)
check("ablation state == default state, plus eligible_arms",
      stripped == json.loads(json.dumps(listed)),
      "differing keys: " + str([k for k in stripped
                                if stripped[k] != listed.get(k)]))

# ---------------------------------------------------------------------------
# 4. the prompt: R3 and R4 move, nothing else does
# ---------------------------------------------------------------------------
p_abl = sb.build_prompt(abl, "A")[0]["content"]
check("ablation prompt points R3 at the list",
      "eligible_arms" in p_abl and "authoritative and final" in p_abl)
check("ablation prompt drops the arithmetic from R3",
      "max_grasp_m" not in p_abl and "payload_kg" not in p_abl
      and "delicate_ok" not in p_abl)
# Until 2026-08-01 an empty list meant "relay required", which R3 then
# forbade and R5 simultaneously demanded: the rung could be impossible to
# obey. With routing delegated the list is a true allowlist and an empty
# list simply means wait.
check("ablation prompt explains the EMPTY list as WAIT, not as a relay",
      "EMPTY list" in p_abl and "so wait" in p_abl
      and "needs a relay" not in p_abl)
check("reach_ok_arms still named, for baskets under R7",
      "reach_ok_arms" in p_abl)

# ---------------------------------------------------------------------------
# 4b. the list is an ALLOWLIST: routable arms are in it (2026-08-01)
# ---------------------------------------------------------------------------
# power_drill sits at (-0.65, -0.02) with a kitchenware destination at
# (0.70, 0.50). ur_w can pick it up and cannot reach that basket, and the
# kitchenware basket is reachable only by ur_e and franka_n. Before the
# router change this task's eligible_arms was [], which R3 read as "no arm
# may be named" while R5 demanded a first leg from someone. It must now
# name ur_w, because a handover route exists with ur_w carrying leg one.
drill = by_id[3]
check("a relay-requiring task now names its first-leg arm",
      drill["eligible_arms"] == ["ur_w"], str(drill))
check("no task carries an empty list while a route exists",
      all(t.get("eligible_arms") for t in abl["tasks"]),
      str({t["id"]: t.get("eligible_arms") for t in abl["tasks"]}))

# Every arm the list names must actually validate, and the check runs
# through the REAL validator rather than re-deriving the rule here.
from core.decision.vlm_allocator import validate_decision           # noqa: E402
allowlist_sound = True
for t in abl["tasks"]:
    for a in t.get("eligible_arms") or []:
        dec = {"task_id": t["id"], "arm": a, "basket": "basket_kitchenware"}
        ok_a, _, _, why_a = validate_decision(dec, coord, zm, BASKETS)
        if not ok_a:
            allowlist_sound = False
            print(f"     {t['object']} / {a} rejected: {why_a}")
check("every arm on the list yields a decision the validator accepts",
      allowlist_sound)


def between(txt, a, b):
    return txt[txt.index(a):txt.index(b)]


check("everything BEFORE the hard rules is byte-identical",
      p_def[:p_def.index("R3")] == p_abl[:p_abl.index("R3")])
# anchor on the RULE, not the token: the ablation's R3 text mentions "R5"
# when it explains what an empty list means, so txt.index("R5") would land
# inside R3 and the comparison would silently pass on the wrong slice.
check("everything FROM R5 onward is byte-identical",
      between(p_def, "R5  You do not", "YOUR ANSWER")
      == between(p_abl, "R5  You do not", "YOUR ANSWER")
      and p_def[p_def.index("YOUR ANSWER"):]
      == p_abl[p_abl.index("YOUR ANSWER"):])
check("guidance G1-G5 unchanged",
      between(p_def, "GUIDANCE", "YOUR ANSWER")
      == between(p_abl, "GUIDANCE", "YOUR ANSWER"))
check("the user message is unchanged apart from the state JSON itself",
      sb.build_prompt(abl, "A")[1]["content"][0]["text"].split("Idle arms")[1]
      == sb.build_prompt(listed, "A")[1]["content"][0]["text"]
      .split("Idle arms")[1])

# ---------------------------------------------------------------------------
# 5. version stamping: an ablation episode can never be pooled by accident
# ---------------------------------------------------------------------------
check("ablation stamps a DISTINCT version",
      sb.prompt_version(abl) == sb.PROMPT_VERSION_ELIGIBLE
      == "2026-08-01a+eligible" != sb.PROMPT_VERSION,
      sb.prompt_version(abl))
check("the version is derivable from the state alone",
      sb.prompt_version(json.loads(json.dumps(abl)))
      == sb.PROMPT_VERSION_ELIGIBLE)
check("the frozen 25d lineage is untouched by all of this",
      sb.prompt_version(sb.build_state(coord, engine, tick=1,
                                       baskets=BASKETS))
      == sb.PROMPT_VERSION_BASELINE == "2026-07-25d")

# ---------------------------------------------------------------------------
# 6. the allocator flag defaults OFF and threads through
# ---------------------------------------------------------------------------
from core.decision import vlm_allocator as va               # REAL allocator
seen = {}
_real = va.build_state
va.build_state = lambda c, e, tick=None, baskets=None, zonemap=None, \
    eligible=False: (seen.__setitem__("eligible", eligible)
                     or {"arms": [], "tasks": []})
va.build_prompt = lambda s, cond, image_b64=None: [
    {"role": "system", "content": "s"},
    {"role": "user", "content": [{"type": "text", "text": "t"}]}]
va.validate_decision = lambda d, c, z, b=None: (True, (0.1, 0.2), None, None)
fake = NS(cell=NS(scene="S"), agents={}, pool=[])
for flag, expect_ver in ((None, sb.PROMPT_VERSION),
                         (False, sb.PROMPT_VERSION),
                         (True, sb.PROMPT_VERSION_ELIGIBLE)):
    kw = {} if flag is None else {"eligible": flag}
    alloc = va.VLMAllocator(lambda: fake, engine=None, condition="A", **kw,
                            model_fn=lambda m, timeout=30.0:
                            '{"task_id": 0, "arm": "ur_w", "reason": "r"}')
    alloc.zonemap = "ZM"
    alloc._consult(round_token=1)
    check(f"eligible={flag} reaches build_state as {bool(flag)}",
          seen["eligible"] == bool(flag), repr(seen["eligible"]))
    check(f"eligible={flag} records the version it actually showed",
          alloc.prompt_version == expect_ver, alloc.prompt_version)
va.build_state = _real

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
