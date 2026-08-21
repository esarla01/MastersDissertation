"""Independently recompute contended claims from an episode JSON (schema
v2), and decompose them by CAUSE.

Why this exists (2026-07-20): the stored summary.contended_claims mixes
two different situations under one number:
  same_instant : the blocking hold/reservation was created in the SAME
                 tick, by an earlier claim in the same allocation burst
                 (paper bookings tripping over each other; B1's opening
                 burst self-contends this way).
  live_traffic : the blocker had been standing for a while; the claim was
                 pointed into a zone where work was already physically
                 happening (closer to a real routing choice).
This script replays the lock ledger to the instant of each task's first
claim, lists every blocker with its AGE in ticks, recomputes the total,
and checks it against the stored stat. Isaac-free: runs anywhere.

Usage:  python3 analysis/episode/episode_verify_contention.py out/episode_*.json
"""

import json
import sys


def replay_to(ledger, idx):
    """State (holders, reservations) after applying ledger[:idx]."""
    holder, resv = {}, {}
    for e in ledger[:idx]:
        z, a, act = e["zone"], e["arm"], e["action"]
        if act == "acquire":
            holder[z] = a
            if a in resv.get(z, []):
                resv[z].remove(a)
        elif act == "release":
            if holder.get(z) == a:
                del holder[z]
        elif act == "reserve":
            resv.setdefault(z, [])
            if a not in resv[z]:
                resv[z].append(a)
        elif act == "unreserve":
            if a in resv.get(z, []):
                resv[z].remove(a)
    return holder, resv


def creation_tick(ledger, idx, zone, arm, kinds):
    """Tick of the most recent surviving entry that put (arm, zone) into
    the current state, searching backwards from idx."""
    for e in reversed(ledger[:idx]):
        if e["zone"] == zone and e["arm"] == arm and e["action"] in kinds:
            return e["tick"]
    return None


def anchor_index(ledger, arm, claim_tick):
    """Index of the claiming arm's FIRST ledger action at claim_tick: the
    claim-time contention check ran just before it. Falls back to the
    first entry with tick > claim_tick (idempotent reserves leave no
    same-tick trace)."""
    for i, e in enumerate(ledger):
        if e["tick"] == claim_tick and e["arm"] == arm:
            return i
    for i, e in enumerate(ledger):
        if e["tick"] > claim_tick:
            return i
    return len(ledger)


def analyse(path):
    data = json.load(open(path))
    if data.get("meta", {}).get("schema_version") != 2:
        print(f"{path}: not a schema-v2 episode, skipping")
        return
    ledger = data["locks"]["ledger"]
    stored = data["summary"].get("contended_claims")
    total, same_instant, live_traffic = 0, 0, 0
    print(f"\n=== {path} ===")
    print(f"{'task':>4} {'object':>18} {'claim':>6}  blockers (zone<-who, age in ticks)")
    for t in data["tasks"]:
        if t.get("claim_tick") is None:
            continue
        arm, ct = t.get("arm"), t["claim_tick"]
        idx = anchor_index(ledger, arm, ct)
        holder, resv = replay_to(ledger, idx)
        blockers = []
        for z in t.get("required_zones", []):
            h = holder.get(z)
            if h is not None and h != arm:
                born = creation_tick(ledger, idx, z, h, ("acquire",))
                blockers.append((z, h, "hold", ct - born if born is not None else None))
            for a in resv.get(z, []):
                if a != arm:
                    born = creation_tick(ledger, idx, z, a, ("reserve",))
                    blockers.append((z, a, "resv", ct - born if born is not None else None))
        if blockers:
            total += 1
            ages = [b[3] for b in blockers if b[3] is not None]
            if ages and max(ages) == 0:
                same_instant += 1
                cls = "same_instant"
            else:
                live_traffic += 1
                cls = "live_traffic"
            desc = ", ".join(f"{z}<-{a}({k},{'?' if age is None else age})"
                             for z, a, k, age in blockers)
            print(f"{t['id']:>4} {t['object']:>18} {ct:>6}  {cls:12} {desc}")
        else:
            print(f"{t['id']:>4} {t['object']:>18} {ct:>6}  clear")
    print(f"\n  recomputed contended claims: {total} "
          f"(same_instant {same_instant}, live_traffic {live_traffic})")
    print(f"  stored summary.contended_claims: {stored}  "
          f"{'MATCH' if stored == total else '*** MISMATCH ***'}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python3 analysis/episode/episode_verify_contention.py "
                         "out/episode_*.json")
    for p in sys.argv[1:]:
        analyse(p)
