"""Harness: metrics pipeline (imports the REAL episode_metrics.py machinery).

Generates episodes with the REAL EpisodeLogger (schema-faithful), with
spawn_xy on objects and known task timings, then checks episode_metrics.py's
per-episode numbers by hand:
  M1, M2, M8, D1 straight reads; M5 exclusive wait from the registry's
  own capability flags (banana/bowl/drill/clamp exclusive); M6/M7 relay
  precision/recall against the REAL rasters; the observed-cycle pooling;
  D2-D5 from a vlm stats block; provenance histogram; CSV row count.
Run: python3 h_analyze.py
"""
import json
import os
import subprocess
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from instrumentation.episode_logger import EpisodeLogger   # REAL logger
from analysis import analyze as az                          # REAL pipeline

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS(types.SimpleNamespace):
    pass


def mk_task(i, obj, arm, submit, claim, done, kind="primary", dest_by="given",
            waiting=None):
    return NS(id=i, obj=obj, dest=(0.1, 0.2), dest_by=dest_by, arm=arm,
              done=True, failed=False, attempts=0, submit_tick=submit,
              claim_tick=claim, done_tick=done, kind=kind,
              waiting_on=waiting, required_zones=[])


def write_episode(d, fname, alloc_name, cond, tasks, objects, stats=None,
                  log=None, makespan=1000, blocked=None):
    blocked = blocked or {"ur_w": 50, "ur_e": 30, "franka_n": 20,
                          "franka_s": 10}
    m = NS(makespan_ticks=makespan, requeued=2,
           completed={a: 1 for a in blocked}, blocked=blocked)
    coord = NS(m=m, locks=NS(ledger=[]), pool=tasks,
               agents={a: None for a in blocked},
               cell=NS(arms={a: NS(travel_m=10.0) for a in blocked}))
    alloc = NS(stats=stats, log=log or []) if stats else None
    EpisodeLogger(out_dir=d, seed=0, layout="designed",
                  allocator=alloc_name, condition=cond,
                  disruptions="none").finish(
        coord, alloc=alloc, objects=objects, verdict="PASS",
        filename=fname,
        extra_metrics={"sorted_correct": 11, "sorted_total": 11})


# spawn geometry chosen against the REAL rasters:
#   banana near franka_n, franka-reachable food basket -> direct (delicate)
#   mustard far east at ur_e, food basket far west -> relay mandatory
OBJECTS = [
    {"name": "ycb_banana", "category": "food", "dist_cm": 2.0,
     "sorted": True, "spawn_xy": [0.05, 0.30]},
    {"name": "ycb_mustard", "category": "food", "dist_cm": 3.0,
     "sorted": True, "spawn_xy": [0.95, -0.10]},
]

TASKS = [
    mk_task(0, "ycb_banana", "franka_n", 0, 100, 400),      # cycle 300
    mk_task(1, "ycb_mustard", "ur_e", 0, 50, 650,           # relayed
            waiting=2),
    mk_task(2, "ycb_mustard", "ur_w", 0, 460, 600, kind="handover_leg"),
]

VLM_STATS = {"calls": 10, "valid_first": 6, "valid_after_feedback": 1,
             "fallback": 1, "noop": 2, "rule_assigned": 1,
             "region_mismatches": 2, "latency_ms_total": 30000.0}

with tempfile.TemporaryDirectory() as d:
    write_episode(d, "ep_b1.json", "b1", None, TASKS, OBJECTS)
    write_episode(d, "ep_vlm2.json", "vlm2", "V", TASKS, OBJECTS,
                  stats=VLM_STATS, makespan=900)

    eps = []
    for f in ("ep_b1.json", "ep_vlm2.json"):
        ep = json.load(open(os.path.join(d, f)))
        ep["_file"] = f
        eps.append(ep)

    cycles = az.observed_cycles(eps)
    check("observed cycles pooled per arm",
          cycles.get("franka_n") == 300 and cycles.get("ur_w") == 140,
          str(cycles))

    m = az.episode_metrics(eps[0], cycles_by_arm=cycles)
    check("M1 completion", m["M1_completion"] == 1.0)
    check("M2 makespan", m["M2_makespan"] == 1000)
    check("M8 blocked", m["M8_blocked"] == 110, str(m["M8_blocked"]))
    check("D1 travel", m["D1_travel_m"] == 40.0, str(m["D1_travel_m"]))
    # Was 100.0 with banana as the only exclusive object. The mustard's
    # grasp_m was corrected 2026-08-02 from 0.058 to 0.096, its true lying
    # width, which puts it OVER the Franka limit and makes it UR-exclusive
    # too. So the fixture now has two exclusive objects and the metric
    # pools both. The expectation moved because the CELL changed, not
    # because the metric did.
    check("M5 exclusive wait pools every registry-exclusive object "
          "(banana Franka-only, mustard UR-only since 2026-08-02)",
          m["M5_exclusive_wait"] == 75.0, str(m["M5_exclusive_wait"]))
    check("M6 relay precision (the one relay was mandatory)",
          m["M6_relay_precision"] == 1.0, str(m["M6_relay_precision"]))
    check("M7 relay recall", m["M7_relay_recall"] == 1.0,
          str(m["M7_relay_recall"]))
    check("provenance histogram",
          m["provenance_dest_by"] == {"given": 3},
          str(m["provenance_dest_by"]))

    mv = az.episode_metrics(eps[1], cycles_by_arm=cycles)
    # Rates are over EVERY consult round, noops included (vf 6, va 1, fb 1,
    # noop 2 -> 10 rounds). Every noop measured so far was a second-attempt
    # noop after a refused proposal, so those rounds are first-pass
    # failures; excluding them overstated D2. The legacy denominator is
    # kept beside it so older reports stay reconstructable.
    check("D2 first-pass over ALL rounds", mv["D2_first_pass"] == 0.6,
          str(mv["D2_first_pass"]))
    check("D3 fallback over ALL rounds", mv["D3_fallback"] == 0.1,
          str(mv["D3_fallback"]))
    check("D6 noop rate", mv["D6_noop_rate"] == 0.2, str(mv["D6_noop_rate"]))
    check("legacy noop-excluding figures still reported",
          mv["D2_first_pass_excl_noops"] == 0.75
          and mv["D3_fallback_excl_noops"] == 0.125,
          str((mv["D2_first_pass_excl_noops"], mv["D3_fallback_excl_noops"])))
    check("the two denominators disagree, which is the point",
          mv["D2_first_pass"] < mv["D2_first_pass_excl_noops"])
    check("D4 model-authored", mv["D4_model_authored"] == 0.875,
          str(mv["D4_model_authored"]))
    check("D5 region accuracy", mv["D5_region_accuracy"] == round(1 - 2/7, 3),
          str(mv["D5_region_accuracy"]))

    # end-to-end CLI incl. CSV
    csv_path = os.path.join(d, "metrics.csv")
    r = subprocess.run([sys.executable,
                        os.path.join(os.path.dirname(__file__), "..",
                                     "fourarm", "analysis", "episode_metrics.py"),
                        os.path.join(d, "ep_b1.json"),
                        os.path.join(d, "ep_vlm2.json"),
                        "--csv", csv_path],
                       capture_output=True, text=True)
    check("CLI runs clean", r.returncode == 0, r.stderr[-120:])
    check("CSV written with 2 rows",
          os.path.exists(csv_path)
          and len(open(csv_path).read().strip().splitlines()) == 3)
    check("per-cell summary printed", "PER-CELL SUMMARY" in r.stdout)

# ---------------------------------------------------------------------------
# U1-U4 utilisation decomposition (REAL analyze.utilisation, REAL logger).
#
# blocked is a SUBSET of occupied, so the arithmetic under test is
#   occupied = productive + blocked   and   idle = makespan - occupied
# never idle = makespan - occupied - blocked.
# ---------------------------------------------------------------------------
def _task(tid, arm, claim, done_tick, done=True):
    return NS(id=tid, obj="ycb_soup_can", dest=(0.1, 0.2), dest_by="model",
              arm=arm, done=done, failed=False, attempts=0, submit_tick=0,
              claim_tick=claim, done_tick=done_tick, kind="primary",
              waiting_on=None, required_zones=["nw"])


with tempfile.TemporaryDirectory() as d:
    mu = NS(makespan_ticks=100, requeued=0,
            completed={"ur_w": 1, "ur_e": 2},
            blocked={"ur_w": 10, "ur_e": 0},
            contended_claims=0)
    mu.pad_wait = {}
    coord_u = NS(m=mu, locks=NS(ledger=[]), agents={"ur_w": None, "ur_e": None},
                 pool=[_task(0, "ur_w", 0, 60),          # occupied 60
                       _task(1, "ur_e", 20, 40),         # occupied 20
                       _task(2, "ur_e", 90, None, done=False)],   # open leg
                 cell=NS(arms={}))
    EpisodeLogger(out_dir=d, seed=0, layout="designed",
                  allocator="b1").finish(coord_u, verdict="PASS",
                                         filename="ep_u.json")
    ep_u = json.load(open(os.path.join(d, "ep_u.json")))

u = az.utilisation(ep_u)
w, e = u["U_by_arm"]["ur_w"], u["U_by_arm"]["ur_e"]
check("occupied read from claim/done ticks",
      w["occupied"] == 60 and e["occupied"] == 30, str(u["U_by_arm"]))
check("an unfinished leg is occupied to the makespan",
      e["occupied"] == 20 + (100 - 90), str(e))
check("blocked is subtracted OUT of occupied, not added beside it",
      w["productive"] == 50 and w["blocked"] == 10, str(w))
check("idle = makespan - occupied (blocked not double-counted)",
      w["idle"] == 40 and e["idle"] == 70, str(u["U_by_arm"]))
check("per-arm identity occupied == productive + blocked",
      all(v["occupied"] == v["productive"] + v["blocked"]
          for v in u["U_by_arm"].values()))
check("per-arm identity occupied + idle == makespan",
      all(v["occupied"] + v["idle"] == 100 for v in u["U_by_arm"].values()))
check("U1 occupied fraction over all arm-ticks",
      u["U1_occupied_frac"] == round(90 / 200, 3), str(u["U1_occupied_frac"]))
check("U2 productive fraction", u["U2_productive_frac"] == round(80 / 200, 3),
      str(u["U2_productive_frac"]))
check("U3 idle ticks total", u["U3_idle_ticks_total"] == 110,
      str(u["U3_idle_ticks_total"]))
check("U4 idle fraction", u["U4_idle_frac"] == round(110 / 200, 3),
      str(u["U4_idle_frac"]))
check("no spurious overlap warning", "U_overlap_warning" not in u, str(u))

# an episode with no per_arm section (legacy) returns nothing, not a crash
check("legacy episode without per_arm yields no U fields",
      az.utilisation({"summary": {"makespan_ticks": 10}}) == {})

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
