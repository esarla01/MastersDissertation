"""Random-valid allocator: the zero-knowledge floor (random greedy matching).

Drops into the same slot as rule_based_allocate, OptimalAllocator and
VLMAllocator. Once per state change it builds a plan: shuffle the ready
tasks, walk them in that random order, and give each a uniformly random
arm among the arms that could LEGALLY take it, while idle arms remain. It
then answers the coordinator's per-task calls from that plan, exactly the
way b2 answers from its matching. It never proposes an infeasible move, so
it makes zero legality errors and maximal quality errors: the floor every
other allocator must beat to justify its existence.

WHY A PLAN AND NOT A PER-PICK COIN FLIP. The first version of this floor
randomised only the arm for whatever task the coordinator offered next, in
pool order. Measured on the designed layout, every such pick had exactly
one legal arm (n_legal=1 on all 14 assignments of rnd_smoke_0), so the
floor reproduced b1 tick for tick: the freedom it randomised was empty.
The allocation decision that actually matters is WHICH TASK gets the arm,
and b1-style per-offer answering cedes that to pool order. Shuffling the
ready set per replan randomises the task dimension too, making this a
random GREEDY MATCHING: random task order, random legal arm, greedy walk.
It is deliberately greedy, like b1, so the floor differs from b1 only in
knowledge, not in protocol. (Uniform sampling over maximal matchings is a
harder problem and is not claimed.)

FEASIBILITY IS NOT REIMPLEMENTED. Legality of each (task, arm) option
comes from calling the REAL rule_based_allocate with a single candidate
arm, exactly as OptimalAllocator does, so relays, the strict-progress pad
rule, and the capability checks are byte-identical to b1 and b2. A relay's
finishing leg is excluded until its parent completes (the same waiting_on
filter b2 uses), so the shuffle can never start a finish before its start.

DETERMINISM. The plan's RNG is seeded on (episode seed, sorted idle arms,
sorted ready task ids), so an identical state yields an identical plan no
matter the call order, and re-running an episode reproduces to the tick.
No global RNG state.

invalidate() mirrors b2/vlm: when the coordinator declines a planned
decision it cannot execute yet (an occupied pad), the plan is dropped so
the next tick replans instead of stalling on a consumed cache.
"""

import hashlib
import random
import struct

from core.control.tasks import rule_based_allocate


class RandomValidAllocator:
    """Callable with the rule_based_allocate signature. Plans one random
    greedy matching per state change and answers the coordinator's
    per-task loop from it."""

    def __init__(self, coord_ref, seed=0):
        self.coord_ref = coord_ref        # callable returning the Coordinator
        self.seed = seed
        # stats + log mirror the other allocators' shape so the episode
        # logger records this column identically (condition None, like opt)
        self.condition = None
        self.stats = {"calls": 0, "replans": 0, "assignments": 0,
                      "relays": 0, "no_legal_option": 0, "invalidated": 0}
        self.log = []
        self._sig = None                  # (idle, ready, disabled) at last plan
        self._plan = {}                   # task_id -> (arm, target, subtask)

    def invalidate(self):
        """Drop the cached plan and force a replan on the next call. The
        coordinator calls this when it DECLINES a planned decision it
        cannot execute yet (an occupied pad); without it the consumed plan
        entry would stall the leg until the signature happens to change."""
        self._plan = {}
        self._sig = None
        self.stats["invalidated"] += 1

    def _rng(self, idle, ready_ids):
        """A random.Random seeded on the DECISION STATE, not on a call
        counter: identical (seed, idle set, ready set) always produces the
        identical plan, independent of when or how often it is asked.
        Reproducible across process runs."""
        key = "|".join((str(self.seed),
                        ",".join(sorted(idle)),
                        ",".join(str(i) for i in sorted(ready_ids)),
                        )).encode("ascii")
        (val,) = struct.unpack(">Q", hashlib.sha256(key).digest()[:8])
        return random.Random(val)

    def _replan(self, coord, zonemap, disabled):
        done_ids = {t.id for t in coord.pool if t.done}
        ready = [t for t in coord.pool
                 if not t.done and not t.failed and not t.claimed
                 and (t.waiting_on is None or t.waiting_on in done_ids)
                 and t.dest is not None]
        idle = [n for n, ag in coord.agents.items()
                if ag.state == "IDLE" and not ag.arm.disabled]

        rng = self._rng(idle, [t.id for t in ready])
        order = list(ready)
        rng.shuffle(order)                # the task dimension, randomised

        remaining = sorted(idle)          # sorted: pick index is the only
        plan, n_legal, relays = {}, {}, []  # randomness, not set ordering
        for t in order:
            if not remaining:
                break
            p = coord.cell.scene[t.obj].data.root_pos_w[0]
            oxy = (float(p[0]), float(p[1]))
            # Legal options among STILL-UNASSIGNED idle arms, one arm at a
            # time through the REAL rule allocator (relay routing included)
            opts = []
            for a in remaining:
                arm_r, target, sub = rule_based_allocate(
                    t, oxy, [a], zonemap, disabled)
                if arm_r == a and target is not None:
                    opts.append((a, target, sub))
            n_legal[t.id] = len(opts)
            if not opts:
                self.stats["no_legal_option"] += 1
                continue
            arm, target, sub = opts[rng.randrange(len(opts))]
            plan[t.id] = (arm, target, sub)
            remaining.remove(arm)
            if sub is not None:
                relays.append(t.id)

        self._plan = plan
        self.stats["replans"] += 1
        if not plan:
            return
        # No "round" key on purpose: trace_episode reconstructs consult
        # rounds only for logs that carry one, and prints these verbatim
        entry = {
            "order": [t.id for t in order],
            "matching": {str(tid): arm
                         for tid, (arm, _, _) in sorted(plan.items())},
            "n_legal": {str(tid): n for tid, n in sorted(n_legal.items())},
            "relays": relays}
        # Fold consecutive identical replans, exactly as b2 does. While a
        # planned relay's pad is occupied, the coordinator declines, calls
        # invalidate(), and the unchanged state reproduces the identical
        # plan every tick: rnd_m_5 logged the same entry several hundred
        # times and inflated "assignments" past executed legs. One entry
        # with a repeats counter keeps the audit honest; retrying itself is
        # correct and continues regardless.
        last = self.log[-1] if self.log else None
        if (last is not None
                and last.get("order") == entry["order"]
                and last.get("matching") == entry["matching"]
                and last.get("n_legal") == entry["n_legal"]):
            last["repeats"] = last.get("repeats", 1) + 1
        else:
            self.stats["assignments"] += len(plan)
            self.stats["relays"] += len(relays)
            self.log.append(entry)

    def __call__(self, task, obj_xy, idle_arms, zonemap, disabled=()):
        self.stats["calls"] += 1
        coord = self.coord_ref()

        done_ids = {t.id for t in coord.pool if t.done}
        ready_ids = frozenset(
            t.id for t in coord.pool
            if not t.done and not t.failed and not t.claimed
            and (t.waiting_on is None or t.waiting_on in done_ids))
        idle = frozenset(n for n, ag in coord.agents.items()
                         if ag.state == "IDLE" and not ag.arm.disabled)
        sig = (idle, ready_ids, frozenset(disabled))
        if sig != self._sig:
            self._sig = sig
            self._replan(coord, zonemap, disabled)

        entry = self._plan.get(task.id)
        if entry is not None and entry[0] in idle_arms:
            del self._plan[task.id]       # consumed
            arm, target, sub = entry
            return arm, target, sub
        # Not selected by this plan's shuffle, or its arm is gone: wait.
        return None, None, None
