"""h_probe_store: probe sets count legal options correctly, cannot change
silently, and fail loudly rather than degrading.

Imports the REAL state builder, the REAL validator and the REAL probe
store. The trail it harvests is synthetic but it is rendered by
sb.build_state, so it has the same shape as a live consults.jsonl.

What is pinned, and the failure each one guards against:

  1. Legal-option counts are STABLE. validate_decision persists task.dest
     on success, so a counter that reused one coordinator would let an
     accepted basket choice change the verdict of the next pair. The count
     must be identical on a second call.
  2. The counts AGREE with the validator pair by pair. Anything reported
     legal must be accepted; anything not reported must be rejected. This
     is definitional rather than independent, which is deliberate: the
     alternative is a second copy of the rule, and a second copy is how
     the two implementations drift.
  3. Counts are non-vacuous. Some states have no legal option at all, and
     that is the point: the seed episode ended 20 noops out of 33 consults
     because most rounds offered nothing legal. A counter that reported
     every state as rich would hide exactly the thing worth stratifying on.
  4. The content hash covers identity, NOT derived metrics. Adding a metric
     must not invalidate a frozen set; changing a state must.
  5. A tampered set is refused on load. A silently mutated set turns a
     paired comparison into an unpaired one with nothing in the output to
     show it.
  6. A missing frame file raises. Replaying it as text-only would turn
     condition V into condition A without a trace.
  7. select() records what it dropped, so a results table can always say
     which states it was computed over.

Run:  python3 h_probe_store.py
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
from core.decision.vlm_allocator import validate_decision       # noqa: E402
from analysis import probe_store as store                       # noqa: E402
from analysis.frozen_coord import from_record, idle_arms        # noqa: E402
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


class LiveScene:
    def __getitem__(self, name):
        x, y = POSITIONS[name]
        return NS(data=NS(root_pos_w=np.array([[x, y, 0.9]], dtype=float)))


def make_live(busy=(), dead=()):
    arms, agents = {}, {}
    for name in C.ARMS:
        arm = NS(disabled=(name in dead), _carried=None,
                 ee_pos_w=lambda: np.array([[0.0, 0.0, 1.0]]))
        arms[name] = arm
        agents[name] = NS(arm=arm,
                          state=("MOVING" if name in busy else "IDLE"))
    pool = []
    for i, obj in enumerate(POSITIONS):
        cat = C.OBJECT_SPECS[obj]["category"]
        pool.append(NS(id=i, obj=obj,
                       # the last task has no destination: the basket is
                       # then the model's choice under R7, which is the
                       # path where an arm counts as legal only if SOME
                       # basket makes it legal
                       dest=(None if i == 3
                             else BASKETS["basket_" + cat]["pos"]),
                       done=False, failed=False, claimed=False,
                       waiting_on=None, attempts=0, dest_by=None))
    return NS(cell=NS(scene=LiveScene(), arms=arms), agents=agents, pool=pool,
              locks=NS(holder={}, reservations={}),
              m=NS(blocked={n: 0 for n in C.ARMS}, requeued=0))


engine = NS(active=list(POSITIONS), applied_log=[])
EXACT = {k: list(v) for k, v in POSITIONS.items()}

# Three consults across a widening squeeze: all four arms free, then one
# busy, then only one free. The last should offer almost nothing.
CELLS = [(), ("ur_w",), ("ur_w", "ur_e", "franka_n")]


def write_trail(d, frames=None):
    fdir = os.path.join(d, "ep_frames")
    os.makedirs(fdir, exist_ok=True)
    path = os.path.join(fdir, "consults.jsonl")
    with open(path, "w") as f:
        for i, busy in enumerate(CELLS):
            st = sb.build_state(make_live(busy), engine, tick=i,
                                baskets=BASKETS, zonemap=zm)
            f.write(json.dumps({
                "seq": i + 1, "round": i * 100, "condition": "A",
                "prompt_version": sb.PROMPT_VERSION,
                "enriched": True, "eligible": False,
                "model": {"alias": "qwen", "model": "qwen-vl-max"},
                "state": st, "positions_exact": EXACT,
                "image_file": (frames[i] if frames else None),
                "messages": []}) + "\n")
    return path, fdir


tmp = tempfile.TemporaryDirectory()
D = tmp.name
trail, frames_dir = write_trail(D)
PS = store.harvest_trail(trail, source="ep")

check("harvest produced one probe per consult", PS["n"] == len(CELLS),
      str(PS["n"]))

# The module must not depend on the CALLER having put fourarm/ycb on
# sys.path. This harness does put it there, which is exactly why the first
# real invocation from fourarm/ raised ModuleNotFoundError while the suite
# stayed green. Strip the path and the cached module, then ask again.
_saved_path = list(sys.path)
sys.path = [q for q in sys.path if not q.rstrip("/").endswith("ycb")]
sys.modules.pop("ycb_scene", None)
try:
    got = sorted(store._baskets())
    check("the baskets table resolves without ycb/ on the caller's sys.path",
          got == ["basket_food", "basket_kitchenware", "basket_tools"],
          str(got))
except Exception as e:
    check("the baskets table resolves without ycb/ on the caller's sys.path",
          False, f"{type(e).__name__}: {e}")
finally:
    sys.path = _saved_path
check("provenance survives the harvest",
      PS["probes"][0]["provenance"]["model"] == "qwen-vl-max"
      and PS["probes"][0]["provenance"]["prompt_version"] == sb.PROMPT_VERSION,
      str(PS["probes"][0]["provenance"]))

# ---------------------------------------------------------------------------
# 1 & 2. legal-option counting
# ---------------------------------------------------------------------------
again = store.harvest_trail(trail, source="ep")
check("legal-option counts are stable across a re-harvest",
      [p["derived"]["n_legal_pairs"] for p in PS["probes"]]
      == [p["derived"]["n_legal_pairs"] for p in again["probes"]],
      str([p["derived"]["n_legal_pairs"] for p in PS["probes"]]))

first = PS["probes"][0]
pairs_twice = [store.legal_options(first, BASKETS)[0] for _ in range(2)]
check("legal_options is idempotent (validate_decision mutates)",
      pairs_twice[0] == pairs_twice[1], str(pairs_twice))

# every reported pair must be accepted, every unreported pair rejected
mismatch = []
for p in PS["probes"]:
    reported = {(x[0], x[1]) for x in p["derived"]["legal_pairs"]}
    coord = from_record(p)
    arms = idle_arms(coord)
    open_ids = [t.id for t in coord.pool
                if not t.claimed and t.waiting_on is None]
    for tid in open_ids:
        for a in arms:
            accepted = False
            fresh0 = from_record(p)
            t = next(x for x in fresh0.pool if x.id == tid)
            options = [None] if t.dest is not None else list(BASKETS)
            for b in options:
                fresh = from_record(p)
                ok, _, _, _ = validate_decision(
                    {"task_id": tid, "arm": a, "basket": b}, fresh, zm,
                    BASKETS)
                if ok:
                    accepted = True
                    break
            if accepted != ((tid, a) in reported):
                mismatch.append((p["provenance"]["seq"], tid, a, accepted))
check("every counted pair is accepted and every uncounted pair rejected",
      not mismatch, str(mismatch[:3]))

counts = [p["derived"]["n_legal_pairs"] for p in PS["probes"]]
check("counts are non-vacuous and decrease as arms get busy",
      counts == sorted(counts, reverse=True) and counts[0] > counts[-1],
      str(counts))
check("the squeezed state offers at most one option", counts[-1] <= 1,
      str(counts[-1]))
check("a state with a real choice is detected",
      any(p["derived"]["n_tasks_with_choice"] >= 1 for p in PS["probes"]),
      str([p["derived"]["n_tasks_with_choice"] for p in PS["probes"]]))

# --- direct / relay split -------------------------------------------------
# Option 2 made "can pick but cannot deliver" a legal proposal, so a
# legality count that does not separate the two conflates the model finding
# a deliverer with the model finding a picker and the cell rescuing it.
splits_add_up = all(
    p["derived"]["n_legal_direct"] + p["derived"]["n_legal_relay"]
    == p["derived"]["n_legal_pairs"] for p in PS["probes"])
check("direct and relay counts sum to the total", splits_add_up,
      str([(p["derived"]["n_legal_direct"], p["derived"]["n_legal_relay"],
            p["derived"]["n_legal_pairs"]) for p in PS["probes"]]))

kinds = {x[2] for p in PS["probes"] for x in p["derived"]["legal_pairs"]}
check("every legal pair is labelled direct or relay",
      kinds and kinds <= {"direct", "relay"}, str(kinds))

# The label must be the VALIDATOR's own verdict, not a guess: a pair marked
# relay must come back with a subtask and a direct one without.
mislabelled = []
for p in PS["probes"]:
    for tid, a, kind in p["derived"]["legal_pairs"]:
        fresh0 = from_record(p)
        t = next(x for x in fresh0.pool if x.id == tid)
        opts = [None] if t.dest is not None else list(BASKETS)
        seen_kind = None
        for b in opts:
            fresh = from_record(p)
            ok, _, sub, _ = validate_decision(
                {"task_id": tid, "arm": a, "basket": b}, fresh, zm, BASKETS)
            if ok:
                seen_kind = "relay" if sub is not None else "direct"
                if seen_kind == "direct":
                    break
        if seen_kind != kind:
            mislabelled.append((tid, a, kind, seen_kind))
check("the direct/relay label matches the validator's own subtask",
      not mislabelled, str(mislabelled[:3]))

# --- destination binding --------------------------------------------------
# R5 only binds once a destination is fixed: while a task is
# destination-free the model picks the basket under R7 and some basket is
# always routable here. A probe set drawn only from round 1 would make R5
# look inert when the live episode produced two NO_ROUTE rejections.
for p in PS["probes"]:
    d = p["derived"]
    if d["n_tasks_with_dest"] + d["n_tasks_dest_free"] != d["n_tasks_open"]:
        fails.append("dest split")
check("fixed and free destination counts partition the open tasks",
      "dest split" not in fails,
      str([(p["derived"]["n_tasks_with_dest"],
            p["derived"]["n_tasks_dest_free"]) for p in PS["probes"]]))
# The fixture mixes both kinds on purpose: three tasks carry a fixed
# destination (where R5 binds) and one is destination-free (where the model
# picks the basket under R7 and R5 imposes nothing). A probe set needs the
# mix to be visible at selection time.
check("the fixture carries both destination-fixed and destination-free tasks",
      all(p["derived"]["n_tasks_with_dest"] == 3
          and p["derived"]["n_tasks_dest_free"] == 1
          for p in PS["probes"]),
      str([(p["derived"]["n_tasks_with_dest"],
            p["derived"]["n_tasks_dest_free"]) for p in PS["probes"]]))
check("selecting on a fixed destination keeps them",
      store.select(PS, require_fixed_dest=True)["n"] == PS["n"])

# ---------------------------------------------------------------------------
# 3 & 4. hashing
# ---------------------------------------------------------------------------
path = os.path.join(D, "set.json")
h = store.save(PS, path)
loaded = store.load(path)
check("a saved set reloads with a matching hash", loaded["hash"] == h)

with_metric = copy.deepcopy(loaded)
for p in with_metric["probes"]:
    p["derived"]["a_brand_new_metric"] = 42
check("adding a DERIVED metric does not change the hash",
      store.content_hash(with_metric["probes"]) == h)

changed = copy.deepcopy(loaded)
changed["probes"][0]["state"]["tasks"][0]["status"] = "in_progress"
check("changing the STATE does change the hash",
      store.content_hash(changed["probes"]) != h)

tampered = os.path.join(D, "tampered.json")
with open(tampered, "w") as f:
    json.dump(changed, f)          # written with the OLD hash still in place
try:
    store.load(tampered)
    check("a tampered set is refused on load", False, "no exception")
except ValueError as e:
    check("a tampered set is refused on load, with both hashes named",
          "mismatch" in str(e), str(e)[:70])

# ---------------------------------------------------------------------------
# 5 & 6. loud failures
# ---------------------------------------------------------------------------
d2 = tempfile.TemporaryDirectory()
trail2, fdir2 = write_trail(d2.name, frames=["a.png", "b.png", "c.png"])
try:
    store.harvest_trail(trail2, source="ep")
    check("a missing frame file raises", False, "no exception")
except ValueError as e:
    check("a missing frame raises rather than replaying V as A",
          "a.png" in str(e), str(e)[:80])

d3 = tempfile.TemporaryDirectory()
old_dir = os.path.join(d3.name, "old_frames")
os.makedirs(old_dir)
old = os.path.join(old_dir, "consults.jsonl")
with open(old, "w") as f:
    f.write(json.dumps({"seq": 1, "round": 0, "messages": []}) + "\n")
try:
    store.harvest_trail(old, source="old")
    check("a pre-2026-08-01 trail is refused", False, "no exception")
except ValueError as e:
    check("a trail with no state is refused, naming the line",
          "line 1" in str(e), str(e)[:80])

# ---------------------------------------------------------------------------
# 7. selection is never silent
# ---------------------------------------------------------------------------
sel_dr = store.select(PS, require_direct_vs_relay=True)
check("selection on a direct-versus-relay choice records its criterion",
      sel_dr["selection"]["require_direct_vs_relay"] is True
      and all(p["derived"]["n_tasks_direct_and_relay"] >= 1
              for p in sel_dr["probes"]),
      str(sel_dr["selection"]))

sel = store.select(PS, min_legal=2, note="EX3 candidates")
check("select keeps only states above the floor",
      all(p["derived"]["n_legal_pairs"] >= 2 for p in sel["probes"]))
check("select records what it dropped and why",
      sel["selection"]["kept"] + sel["selection"]["dropped"] == PS["n"]
      and sel["selection"]["min_legal"] == 2
      and sel["selection"]["from"] == PS["hash"],
      str(sel["selection"]))
check("a filtered set gets its OWN hash",
      sel["hash"] != PS["hash"] and sel["n"] == len(sel["probes"]))

empty = store.select(PS, min_legal=99)
check("an over-strict filter yields an empty set rather than an error",
      empty["n"] == 0 and empty["selection"]["dropped"] == PS["n"])

summary = store.summarise(PS)
check("summarise buckets every probe",
      sum(summary["legal_pair_buckets"].values()) == PS["n"], str(summary))

tmp.cleanup()
d2.cleanup()
d3.cleanup()

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
