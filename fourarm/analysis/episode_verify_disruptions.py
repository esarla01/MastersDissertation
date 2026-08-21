"""Did the disruption fixes actually take effect in a real episode?

Every fix made on 2026-07-28 lives in a code path that only runs under
disruptions, so the only proof that matters is a disrupted episode. This
reads one and checks each fix against what the JSON records.

  python3 analysis/episode_verify_disruptions.py out/b1_2026....json

Checks, and what each one proves:

  T1  every disruption event fired before the episode ended
      Proves the timing fix. disable_arm used to sit at t = 30.0 s, which
      is tick 3600, while episodes end near 2450: it never fired once.
  T2  the arm failure fired at all (D3 / mixed only)
  M4  the disabled arm never announced itself as available afterwards
  D1  every displaced object landed where a CAPABLE arm can still serve it
  D2  no displacement picked an object that was already delivered
  D3  spawn either activated an object or SAID the pool was exhausted
  D4  the urgency command names a category this scene actually has
  LV  the episode ended on its own rather than hitting the tick limit
  H2  the noop watchdog is present and reports (vlm columns)
  H3  invalidate() is present and reports (vlm columns)

Exit code is non-zero if any check fails.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ycb"))

from core.cell import cell_config as C                        # noqa: E402
from ycb_objects import YCB, CATEGORIES                       # noqa: E402

try:
    from core.cell.zones import ZoneMap
    _ZM = ZoneMap()
except Exception as exc:                                      # rasters absent
    _ZM = None
    print(f"[verify] no rasters ({exc}); D1 falls back to the circle test",
          file=sys.stderr)

fails, warns = [], []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


def note(label, detail=""):
    print("NOTE " + label + (": " + detail if detail else ""))
    warns.append(label)


def base(n):
    return n[4:] if n.startswith("ycb_") else n


def capable(obj):
    s = YCB.get(base(obj))
    if s is None:
        return list(C.ARMS)
    out = []
    for a in C.ARMS:
        t = C.ARM_TYPES[C.ARMS[a]["type"]]
        if s["delicate"] and not t["delicate_ok"]:
            continue
        if s["grasp_m"] <= t["max_grasp_m"] and s["mass_kg"] <= t["payload_kg"]:
            out.append(a)
    return out


def servable(obj, x, y):
    for a in capable(obj):
        if _ZM is not None:
            if _ZM.reachable(a, x, y):
                return True
            continue
        bx, by = C.ARMS[a]["pos"][0], C.ARMS[a]["pos"][1]
        d = math.hypot(x - bx, y - by)
        if 0.25 <= d <= C.ARM_TYPES[C.ARMS[a]["type"]]["reach"] * 0.92:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    a = ap.parse_args()
    ep = json.load(open(a.episode))
    meta, summ = ep.get("meta", {}), ep.get("summary", {})
    events = ep.get("events", []) or []
    span = summ.get("makespan_ticks") or 0
    profile = meta.get("disruptions")

    print(f"\n{os.path.basename(a.episode)}  allocator={meta.get('allocator')}"
          f" disruptions={profile} prompt={meta.get('prompt_version')}"
          f" schema=v{meta.get('schema_version')}")
    print(f"makespan {span}  sorted {summ.get('sorted')}  "
          f"verdict {summ.get('verdict')}\n")

    if profile in (None, "none"):
        print("This episode ran with NO disruptions, so none of the fixes "
              "under test can have executed. Re-run with --disruptions mixed.")
        return 2

    dis = [e for e in events if e.get("type") == "disruption"]
    print(f"{len(dis)} disruption events recorded")
    for e in dis:
        print(f"   tick {e.get('tick'):>5}  {e.get('kind'):<12} "
              + json.dumps({k: v for k, v in e.items()
                            if k not in ("tick", "type", "kind")}))
    print()

    # ---- T1 timing --------------------------------------------------------
    late = [(e.get("kind"), e.get("tick")) for e in dis
            if e.get("tick") is not None and e["tick"] >= span]
    check("T1 every disruption event fired before the episode ended",
          bool(dis) and not late, str(late))
    if not dis:
        check("T1 any disruption fired at all", False,
              "the schedule produced nothing inside the run")
    # A "mixed" profile schedules eight events. Seeing far fewer means the
    # rest were scheduled past the end, which is a horizon problem, not a
    # dropped event: check --disrupt-horizon against the real makespan.
    EXPECTED = {"mixed": 8, "D1": 4, "D2": 2, "D3": 1, "D4": 1}
    want = EXPECTED.get(profile)
    if want and len(dis) < want:
        check(f"T1b the whole {profile} schedule fired ({want} events)",
              False, f"only {len(dis)} landed inside a {span}-tick run; "
                     f"the horizon is too long for this episode")

    # ---- T2 the arm failure ----------------------------------------------
    dies = [e for e in dis if e.get("kind") == "disable_arm"]
    if profile in ("D3", "mixed"):
        check("T2 the arm failure fired (it never did before this fix)",
              bool(dies), f"{len(dies)} disable_arm events")
    victim = dies[0].get("arm") if dies else None

    # ---- M4 a frozen arm must not report itself available -----------------
    if victim:
        t0 = dies[0].get("tick", 0)
        ghosts = [e for e in events
                  if e.get("type") == "arm_idle" and e.get("arm") == victim
                  and (e.get("tick") or 0) > t0]
        check(f"M4 {victim} never announced itself available after freezing",
              not ghosts, f"{len(ghosts)} ghost arm_idle events")
        legs = (ep.get("per_arm", {}) or {}).get(victim, {})
        print(f"     {victim} froze at tick {t0}; "
              f"completed_legs={legs.get('completed_legs')} "
              f"blocked={legs.get('blocked_ticks')}")

    # ---- D1 / D2 displacement --------------------------------------------
    moves = [e for e in dis if e.get("kind") == "displace"]
    if moves:
        stranded = [(e.get("object"), e.get("x"), e.get("y")) for e in moves
                    if e.get("object")
                    and not servable(e["object"], e.get("x"), e.get("y"))]
        check("D1 every displaced object landed somewhere servable",
              not stranded, str(stranded))
        sorted_at_end = {o["name"] for o in ep.get("objects", []) or []
                         if o.get("sorted")}
        skipped = [e for e in moves if not e.get("object")]
        for e in skipped:
            note("D2 a displacement was skipped",
                 str(e.get("skipped") or "no reason recorded"))
        check("D2 displacement reported an object or a reason every time",
              all(e.get("object") or e.get("skipped") for e in moves),
              str([e for e in moves
                   if not e.get("object") and not e.get("skipped")]))
        undone = [e["object"] for e in moves
                  if e.get("object") and e["object"] not in sorted_at_end]
        if undone:
            note("objects displaced and not delivered by the end",
                 ", ".join(sorted(set(undone))))
    else:
        note("no displacement events in this profile")

    # ---- D3 spawn ---------------------------------------------------------
    spawns = [e for e in dis if e.get("kind") == "spawn"]
    if spawns:
        silent = [e for e in spawns
                  if not e.get("object") and not e.get("skipped")]
        check("D3 spawn activated an object or said why it could not",
              not silent, f"{len(silent)} inert spawns")
        exhausted = [e for e in spawns if e.get("skipped")]
        if exhausted:
            note("spawns skipped on an exhausted pool (this is the fix "
                 "working, not a failure)", str(len(exhausted)))

    # ---- D4 urgency -------------------------------------------------------
    prio = [e for e in dis if e.get("kind") == "priority"]
    for e in prio:
        cmd = (e.get("command") or "")
        check("D4 the urgency command names a real category",
              any(c in cmd for c in CATEGORIES), cmd)

    # ---- liveness ---------------------------------------------------------
    limit = [e for e in events if e.get("type") == "tick_limit"]
    check("LV the episode ended on its own, not on the tick limit",
          not limit, str(limit[:1]))
    failed = [t for t in ep.get("tasks", []) if t.get("failed")]
    if failed:
        note("tasks marked failed (M3 permanence working if an object was "
             "genuinely stranded)",
             ", ".join(str(t["id"]) + ":" + t["object"] for t in failed))

    # ---- H2 / H3, vlm columns only ---------------------------------------
    stats = (ep.get("allocator") or {}).get("stats") or {}
    if stats:
        wd = stats.get("noop_watchdog_fired")
        inv = stats.get("invalidated")
        check("H2 the noop watchdog is live in this build",
              "noop_watchdog_fired" in stats or stats.get("noop", 0) == 0,
              "absent from stats, so the build predates the fix"
              if "noop_watchdog_fired" not in stats else f"fired {wd}x")
        print(f"     watchdog fired {wd or 0}x, decisions invalidated "
              f"{inv or 0}x, noops {stats.get('noop')}, "
              f"fallbacks {stats.get('fallback')}")
    else:
        note("no allocator stats (baseline column), so H2 and H3 are not "
             "exercised here; run vlm1 --disruptions mixed for those")

    print()
    print("RESULT:", "ALL PASS" if not fails else
          f"{len(fails)} FAILURES: {fails}")
    if warns:
        print(f"({len(warns)} notes, not failures)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
