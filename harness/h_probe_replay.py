"""h_probe_replay: the offline replay runner renders the right prompt at
the right rung, refuses what it cannot do, and reproduces a live episode
byte for byte.

Imports the REAL prompt builder, the REAL validator, the REAL eligibility
function and the REAL runner. The trail is synthetic but built by
sb.build_state and sb.build_prompt, so it is shaped exactly like a live
consults.jsonl.

What is pinned:

  1. THE ACCEPTANCE TEST. Prompts rebuilt from a saved state must be
     byte-identical to what the live run sent. This is the claim the whole
     offline plan rests on: if the shim renders even slightly differently,
     every replayed number is wrong in the same direction and nothing looks
     broken.
  2. Rungs actually differ, and differ in the RIGHT WAY. The prompt selects
     its rules block from state["reachability"], not from the presence of
     the task field, so setting one without the other renders an L3 prompt
     under an L4 label. The first version of state_at_rung did exactly
     that and this check is why it was caught.
  3. Unbuilt and unknown rungs are refused BY NAME. A silent fallback to L3
     would report an L3 result under an L2 label with nothing in the output
     to show it.
  4. The probe set is never mutated. A run that edited the set would change
     the thing every other run is compared against.
  5. Quality fields are scored on legal decisions: basket correctness, an
     avoidable relay, and a model reason claiming direct delivery on a
     round the router had to rescue.
  6. A model error becomes a row, not a crash. A long paid run must not die
     on one timeout.

Run:  python3 h_probe_replay.py
"""

import copy
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
from analysis import probe_replay as pr                         # noqa: E402
from analysis import probe_store as store                       # noqa: E402
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
    "ycb_bowl":        (-0.30043, 0.45028),    # delicate, Frankas only
    "ycb_large_clamp": (-0.25017, -0.45061),   # 0.122 m, URs only
    "ycb_mug":         (0.30022, 0.50014),     # 0.081 m, URs only
}
for scene_name in POSITIONS:
    register_specs(C.OBJECT_SPECS, scene_name, scene_name[len("ycb_"):])

zm = ZoneMap(os.path.join(ROOT, "core", "cell", "reachability", "rasters"))
EXACT = {k: list(v) for k, v in POSITIONS.items()}


class LiveScene:
    def __getitem__(self, name):
        x, y = POSITIONS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_live(busy=()):
    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=False, _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm,
                          state=("MOVING" if name in busy else "IDLE"))
    pool = []
    for i, obj in enumerate(POSITIONS):
        cat = C.OBJECT_SPECS[obj]["category"]
        pool.append(NS(id=i, obj=obj,
                       dest=(None if i == 3
                             else tuple(BASKETS["basket_" + cat]["pos"])),
                       done=False, failed=False, claimed=False,
                       waiting_on=None, attempts=0, dest_by=None))
    return NS(cell=NS(scene=LiveScene(), arms=arms), agents=agents, pool=pool,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))


engine = NS(active=list(POSITIONS), applied_log=[])
TMP = tempfile.TemporaryDirectory()
FDIR = os.path.join(TMP.name, "ep_frames")
os.makedirs(FDIR)
TRAIL = os.path.join(FDIR, "consults.jsonl")

with open(TRAIL, "w") as f:
    for i, busy in enumerate([(), ("ur_w",), ("ur_w", "ur_e")]):
        st = sb.build_state(make_live(busy), engine, tick=i,
                            baskets=BASKETS, zonemap=zm)
        f.write(json.dumps({
            "seq": i + 1, "round": i * 100, "condition": "A",
            "prompt_version": sb.prompt_version(st),
            "enriched": True, "eligible": False,
            "model": {"alias": "qwen", "model": "qwen-vl-max"},
            "state": st, "positions_exact": EXACT, "image_file": None,
            # the REAL prompt, exactly as a live run would have sent it
            "messages": sb.build_prompt(st, "A")}) + "\n")

PS = store.harvest_trail(TRAIL, source="ep")

# ---------------------------------------------------------------------------
# 1. the acceptance test
# ---------------------------------------------------------------------------
rep = pr.verify_trail(TRAIL)
check("prompts rebuilt from saved state are byte-identical to those sent",
      rep["prompt_ok"] == rep["consults"] and not rep["prompt_mismatch"],
      f"{rep['prompt_ok']}/{rep['consults']} "
      f"first={rep['prompt_mismatch'][:1]}")
check("the acceptance test was not vacuous", rep["consults"] == 3,
      str(rep["consults"]))

# It must FAIL when the state genuinely differs, or it proves nothing.
bad_dir = os.path.join(TMP.name, "bad_frames")
os.makedirs(bad_dir)
bad_trail = os.path.join(bad_dir, "consults.jsonl")
with open(TRAIL) as src, open(bad_trail, "w") as dst:
    for i, line in enumerate(src):
        rec = json.loads(line)
        if i == 0:                       # nudge one object by 1 cm
            rec["state"]["objects"][0]["xy"][0] += 0.01
        dst.write(json.dumps(rec) + "\n")
bad = pr.verify_trail(bad_trail)
check("a changed state makes the acceptance test FAIL",
      bad["prompt_ok"] == 2 and len(bad["prompt_mismatch"]) == 1,
      f"{bad['prompt_ok']}/{bad['consults']}")
check("the mismatch report locates the difference",
      "char" in (bad["prompt_mismatch"][0] or {}),
      str(bad["prompt_mismatch"][0])[:120])

# --- the VERDICT half -----------------------------------------------------
# The first version of verify_trail promised verdict comparison in its
# docstring and implemented only the prompt half, so it reported a clean
# pass on a check it never ran. The live run exposed it as
# verdicts_checked: 0. Both halves are now pinned, including the case where
# the episode JSON is absent.
check("without an episode JSON, no verdict is claimed as checked",
      rep["verdicts_checked"] == 0 and rep["verdict_ok"] == 0
      and any("no episode" in n for n in rep["notes"]),
      str(rep["notes"]))

# Build an allocator log aligned to the trail: one entry per consult, with
# a mix of accepted decisions and rejected proposals whose reason strings
# come from the REAL validator.
from analysis.frozen_coord import from_record as _fr                # noqa
from core.decision.vlm_allocator import validate_decision as _vd    # noqa

def _live_verdict(probe, decision):
    return _vd(dict(decision), _fr(probe), zm, BASKETS)

EP = os.path.join(TMP.name, "episode.json")
log = []
for probe in PS["probes"]:
    rnd = probe["provenance"]["round"]
    # one rejection: a UR on the delicate bowl (task 1)
    bad_dec = {"task_id": 1, "arm": "ur_w", "basket": "basket_kitchenware"}
    _, _, _, why = _live_verdict(probe, bad_dec)
    # latency_ms is present because a real consulted round always has one.
    # It is the second signal the aligner cross-checks against the result
    # label, so the fixture must carry it or the cross-check fires on a
    # fixture artefact rather than a real disagreement.
    entry = {"round": rnd, "result": "valid_after_feedback",
             "task_id": 1, "arm": "franka_n", "latency_ms": 1234.5,
             "basket": "basket_kitchenware",
             "rejected": [dict(bad_dec, attempt=1, model_reason="",
                               rejected_because=why, unparseable=False)]}
    log.append(entry)
json.dump({"allocator": {"log": log}}, open(EP, "w"))

rep2 = pr.verify_trail(TRAIL, EP)
check("with an episode JSON, verdicts are actually checked",
      rep2["verdicts_checked"] == 2 * PS["n"], str(rep2["verdicts_checked"]))
check("the two consult signals agree on a well-formed log",
      not any("disagree" in n for n in rep2["notes"]), str(rep2["notes"]))
check("offline verdicts match the live ones, reason strings included",
      rep2["verdict_ok"] == rep2["verdicts_checked"]
      and not rep2["verdict_mismatch"],
      str(rep2["verdict_mismatch"][:1]))

# It must FAIL when a verdict genuinely differs.
wrong = json.load(open(EP))
wrong["allocator"]["log"][0]["rejected"][0]["rejected_because"] = \
    "arm ur_w cannot reach the object"
EP2 = os.path.join(TMP.name, "episode_wrong.json")
json.dump(wrong, open(EP2, "w"))
rep3 = pr.verify_trail(TRAIL, EP2)
check("a wrong reason string makes the verdict half FAIL",
      len(rep3["verdict_mismatch"]) == 1
      and rep3["verdict_ok"] == rep3["verdicts_checked"] - 1,
      str(rep3["verdict_mismatch"][:1])[:150])

# An accepted entry with no basket cannot be rebuilt and must be reported
# rather than skipped or wrongly failed.
older = json.load(open(EP))
for e in older["allocator"]["log"]:
    e.pop("basket")
EP3 = os.path.join(TMP.name, "episode_old.json")
json.dump(older, open(EP3, "w"))
rep4 = pr.verify_trail(TRAIL, EP3)
check("an accepted decision with no basket is reported as unverifiable",
      rep4["verdicts_unverifiable"] == PS["n"]
      and rep4["verdicts_checked"] == PS["n"]
      and any("basket" in n for n in rep4["notes"]),
      f"{rep4['verdicts_unverifiable']} {rep4['notes']}")

# A rule_assigned round has NO consult behind it: the rule allocator
# handled it without asking the model. The first version of this alignment
# assumed one log entry per consult and refused a perfectly good pair of
# files because of it. Insert two such rounds and the alignment must still
# work.
with_rule = json.load(open(EP))
with_rule["allocator"]["log"].insert(
    1, {"round": 50, "result": "rule_assigned", "task_id": 0,
        "arm": "ur_w", "arm_by": "rule", "dest_by": "oracle"})
with_rule["allocator"]["log"].append(
    {"round": 999, "result": "rule_assigned", "task_id": 2,
     "arm": "ur_e", "arm_by": "rule", "dest_by": "oracle"})
EP5 = os.path.join(TMP.name, "episode_rule.json")
json.dump(with_rule, open(EP5, "w"))
rep6 = pr.verify_trail(TRAIL, EP5)
check("rule_assigned rounds are skipped, not treated as misalignment",
      rep6["verdicts_checked"] == 2 * PS["n"]
      and rep6["verdict_ok"] == rep6["verdicts_checked"]
      and any("rule_assigned" in n for n in rep6["notes"]),
      f"checked={rep6['verdicts_checked']} notes={rep6['notes']}")

# And when the two signals genuinely disagree, say so rather than
# proceeding quietly on one of them.
odd = json.load(open(EP))
odd["allocator"]["log"][0].pop("latency_ms")
EP6 = os.path.join(TMP.name, "episode_odd.json")
json.dump(odd, open(EP6, "w"))
rep7 = pr.verify_trail(TRAIL, EP6)
check("disagreeing consult signals are reported, not silently resolved",
      any("disagree" in n for n in rep7["notes"]), str(rep7["notes"])[:120])

# Misaligned files must still be refused, not zipped together silently.
short = json.load(open(EP))
short["allocator"]["log"] = short["allocator"]["log"][:1]
EP4 = os.path.join(TMP.name, "episode_short.json")
json.dump(short, open(EP4, "w"))
rep5 = pr.verify_trail(TRAIL, EP4)
check("a log of the wrong length is refused rather than zipped",
      rep5["verdicts_checked"] == 0
      and any("cannot be aligned" in n for n in rep5["notes"]),
      str(rep5["notes"]))

# ---------------------------------------------------------------------------
# 2. rungs
# ---------------------------------------------------------------------------
probe = PS["probes"][0]
rendered = {}
for rung in ("recorded", "L3", "L4"):
    st = pr.state_at_rung(probe, rung)
    msgs = sb.build_prompt(st, "A")
    rendered[rung] = (st, msgs[0]["content"])

check("recorded and L3 are identical on a state harvested without eligible",
      rendered["recorded"][1] == rendered["L3"][1])
check("L4 renders a DIFFERENT prompt from L3",
      rendered["L4"][1] != rendered["L3"][1],
      f"L4={len(rendered['L4'][1])} L3={len(rendered['L3'][1])}")
check("L4 flips the reachability marker, not just the task field",
      rendered["L4"][0]["reachability"] == "listed+eligible"
      and rendered["L3"][0]["reachability"] == "listed",
      f"{rendered['L4'][0]['reachability']} / "
      f"{rendered['L3'][0]['reachability']}")
check("L4 stamps the eligible prompt version",
      sb.prompt_version(rendered["L4"][0]).endswith("+eligible")
      and not sb.prompt_version(rendered["L3"][0]).endswith("+eligible"),
      sb.prompt_version(rendered["L4"][0]))
check("L4 supplies a list for every task",
      all(t.get("eligible_arms") is not None
          for t in rendered["L4"][0]["tasks"]),
      str([t.get("eligible_arms") for t in rendered["L4"][0]["tasks"]]))
check("L3 supplies none",
      all(t.get("eligible_arms") is None
          for t in rendered["L3"][0]["tasks"]))

# The L4 list must be the SAME rule the live builder uses, not a lookalike.
live_eligible = sb.build_state(make_live(), engine, tick=0, baskets=BASKETS,
                               zonemap=zm, eligible=True)
by_id = {t["id"]: t for t in live_eligible["tasks"]}
offline = {t["id"]: t["eligible_arms"] for t in rendered["L4"][0]["tasks"]}
check("offline L4 reproduces build_state's own eligible_arms",
      all(by_id[i]["eligible_arms"] == offline[i] for i in offline),
      f"{offline} vs {{i: by_id[i]['eligible_arms'] for i in offline}}")

# "L1" stays on this list on purpose. The built rung is "L1-nowidth"; a
# bare "L1" is the OLD name from the ladder before it was reordered so that
# each adjacent step removes exactly one thing, and accepting it would let
# a stale command line report an anonymised-with-width result under the
# anonymised-without-width label.
for rung, why in (("L1", "unknown"), ("L5", "unknown"),
                  ("l4", "unknown"), ("", "unknown")):
    try:
        pr.state_at_rung(probe, rung)
        check(f"rung {rung!r} is refused ({why})", False, "no exception")
    except ValueError as e:
        check(f"rung {rung!r} is refused ({why}), by name",
              (rung or "unknown") in str(e) or "unknown rung" in str(e),
              str(e)[:70])

before = copy.deepcopy(PS)
for rung in ("recorded", "L3", "L4"):
    pr.state_at_rung(PS["probes"][0], rung)
check("rendering never mutates the probe set",
      PS == before and store.content_hash(PS["probes"]) == PS["hash"])

# ---------------------------------------------------------------------------
# 3. replay rows and quality scoring
# ---------------------------------------------------------------------------
def fixed(reply):
    def fn(messages, timeout=30.0, alias=None):
        return reply if isinstance(reply, str) else json.dumps(reply)
    return fn


row = pr.replay_one(probe, "L3", "A", model_fn=fixed(
    {"task_id": 1, "arm": "franka_n", "basket": "basket_kitchenware",
     "regions": ["nw", "ne"], "reason": "franka_n delivers it directly"}))
check("a legal decision is recorded as valid",
      row["result"] == "valid" and row["violation"] is None, str(row)[:120])
check("basket correctness is NOT scored when the task already had a "
      "destination",
      "basket_correct" not in row,
      str(row.get("basket_correct")))

# Task 3 is the mug, kitchenware, and destination-free, so the basket IS
# the model's decision. Sending it to the food basket is the exact error
# the live seed episode made with the bowl: legal, delivered, wrong.
row = pr.replay_one(probe, "L3", "A", model_fn=fixed(
    {"task_id": 3, "arm": "ur_e", "basket": "basket_food",
     "regions": ["ne", "nw"], "reason": "ur_e takes the mug"}))
check("a wrong basket is caught even though the decision is legal",
      row["result"] == "valid" and row.get("basket_correct") is False
      and row.get("basket_expected") == "basket_kitchenware",
      f"{row.get('result')} {row.get('basket')} vs "
      f"{row.get('basket_expected')}")

row = pr.replay_one(probe, "L3", "A", model_fn=fixed(
    {"task_id": 3, "arm": "ur_e", "basket": "basket_kitchenware",
     "regions": ["ne", "ne"], "reason": "ur_e takes the mug"}))
check("a right basket scores correct",
      row.get("basket_correct") is True, str(row.get("basket_correct")))

row = pr.replay_one(probe, "L3", "A", model_fn=fixed(
    {"task_id": 1, "arm": "ur_w", "basket": "basket_kitchenware",
     "regions": ["nw", "ne"], "reason": "ur_w picks up the bowl"}))
check("a UR on a delicate bowl is rejected and classified",
      row["result"] == "rejected" and row["violation"] == "CAPABILITY",
      f"{row['violation']} {row['rejected_because']}")

row = pr.replay_one(probe, "L3", "A", model_fn=fixed(
    {"task_id": -1, "arm": None, "reason": "nothing legal, waiting"}))
check("a wait is recorded as a noop with the model's reason",
      row["result"] == "noop" and "waiting" in row["model_reason"])

row = pr.replay_one(probe, "L3", "A", model_fn=fixed("not json at all"))
check("an unparseable reply is recorded as PARSE, not a crash",
      row["result"] == "unparseable" and row["violation"] == "PARSE")


def boom(messages, timeout=30.0, alias=None):
    raise TimeoutError("endpoint took too long")


row = pr.replay_one(probe, "L3", "A", model_fn=boom)
check("a model error becomes a row rather than killing the run",
      row["error"] and "TimeoutError" in row["error"], str(row.get("error")))

check("rows carry the rung, condition and probe provenance",
      row["rung"] == "L3" and row["condition"] == "A"
      and row["provenance"].get("seq") == 1)

# A model_fn with the OLD signature must still work, as every other
# harness in this suite supplies one.
def blind(messages, timeout=30.0):
    return json.dumps({"task_id": -1, "arm": None, "reason": "wait"})


row = pr.replay_one(probe, "L3", "A", model_fn=blind)
check("an alias-blind model_fn is still accepted", row["result"] == "noop")

rows = pr.replay_set(PS, "L4", "A", model_fn=blind)
check("replay_set covers every probe and stamps the set hash",
      len(rows) == PS["n"]
      and all(r["probe_set_hash"] == PS["hash"] for r in rows))

out = os.path.join(TMP.name, "rows.jsonl")
pr.replay_set(PS, "L3", "A", model_fn=blind, out=out)
written = [json.loads(x) for x in open(out) if x.strip()]
check("rows are written to disk as they are produced",
      len(written) == PS["n"], str(len(written)))

# condition V without a frame must fail loudly
try:
    pr.render(probe, "recorded", "V")
    check("condition V with no frame is refused", False, "no exception")
except ValueError as e:
    check("condition V with no frame is refused rather than sent as text",
          "frame" in str(e), str(e)[:70])

TMP.cleanup()

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)