"""Optimal-assignment allocator: the solver upper bound.

Drops into the same slot as rule_based_allocate and VLMAllocator. Instead
of assigning tasks one at a time in pool order (greedy), it looks at ALL
idle arms and ALL ready tasks together and picks the pairing with the
smallest total base-to-object distance (the MiniSum objective).

Why this exists: the greedy rule and the sequential VLM protocol share a
documented weakness (Gerkey & Mataric 2002): the order tasks are offered
can waste arms, e.g. both URs taken by tasks a Franka could do, leaving a
UR-only task stranded. Joint matching cannot make that mistake within a
round. Running this allocator on the same seeds gives the performance
ceiling: rule-to-optimal is the cost of greed; VLM-to-optimal is what the
model leaves on the table.

What it deliberately does NOT do:
- No semantics: sorting tasks (dest=None) get their destination from the
  oracle resolver, same as the rule fallback. The gap the VLM closes on
  semantic tasks is measured against THAT, not against magic.
- No scheduling: it matches idle arms to tasks NOW (instantaneous
  assignment). It cannot decide to wait for a busy arm.
- No handover invention: a task no arm can do directly is delegated to
  the rule, which knows how to route via a pad.

With at most four arms the matching is found by trying every possible
pairing (at most a few hundred), so there is no solver dependency and
the result is exactly optimal, not approximate.
"""

import itertools
import math

from core.cell import cell_config as C
from core.control.tasks import Task, rule_based_allocate


LAMBDA_HANDOVER = 0.30    # surcharge for a relay route beyond its raw
                          # path length: the second pick-place cycle and
                          # coordination overhead. Makes the matcher
                          # prefer direct when direct is comparable, and
                          # authorize relays when they beat waiting.
LAMBDA_CONTENTION = 0.0   # ablation weight: price a required zone that is
                          # held/reserved by another arm. 0.0 = the pure
                          # classical baseline (default; pre-registered).
TIE_EPS = 1e-6            # deterministic tie-break: tiny cost keyed on task
                          # id so equal-cost matchings resolve identically
                          # on every run (reproducibility requirement)


def _dist(arm, xy):
    b = C.ARMS[arm]["pos"]
    return math.hypot(xy[0] - b[0], xy[1] - b[1])


def _pair_cost(arm, task, oxy, locks=None):
    """Execution-time proxy for arm doing task: approach + carry
    [+ contention surcharge when the ablation weight is on]."""
    c = _dist(arm, oxy) + math.hypot(task.dest[0] - oxy[0],
                                     task.dest[1] - oxy[1])
    if LAMBDA_CONTENTION and locks is not None:
        from core.cell.locks import zone_of
        zones = {zone_of(*oxy), zone_of(*task.dest)}
        if any(locks.is_contended(z, arm) for z in zones):
            c += LAMBDA_CONTENTION
    return c + TIE_EPS * task.id


def solve_matching(arms, tasks, feasible, cost):
    """Hungarian solve (scipy) on a padded matrix: infeasible cells get a
    sentinel far above any real cost, so the solver maximises the number
    of REAL assignments and, among those, minimises total cost. Verified
    against best_matching (exhaustive) in the harness."""
    if not arms or not tasks:
        return {}
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    real = [cost[k] for k, ok in feasible.items() if ok]
    sentinel = (max(real) if real else 1.0) * 1000.0 + 1000.0
    m = np.full((len(arms), len(tasks)), sentinel)
    for i, a in enumerate(arms):
        for j, t in enumerate(tasks):
            if feasible.get((a, t.id), False):
                m[i, j] = cost[(a, t.id)]
    rows, cols = linear_sum_assignment(m)
    return {tasks[j].id: arms[i] for i, j in zip(rows, cols)
            if m[i, j] < sentinel}


def best_matching_minimax(arms, tasks, feasible, cost):
    """Exhaustive bottleneck-optimal matching: assign as many tasks as
    possible; among those, minimise the MAXIMUM pair cost; break remaining
    ties on total cost, so equal-bottleneck pairings resolve identically on
    every run. Exact at this scale (at most a few hundred pairings)."""
    best, best_key = {}, None
    k = min(len(arms), len(tasks))
    for task_subset in itertools.permutations(tasks, k):
        for arm_subset in itertools.permutations(arms, k):
            pairs = [(a, t) for a, t in zip(arm_subset, task_subset)
                     if feasible.get((a, t.id), False)]
            if not pairs:
                continue
            n = len(pairs)
            worst = max(cost[(a, t.id)] for a, t in pairs)
            total = sum(cost[(a, t.id)] for a, t in pairs)
            key = (-n, worst, total)          # lexicographic: most, then
            if best_key is None or key < best_key:   # lowest bottleneck,
                best_key = key                       # then lowest total
                best = {t.id: a for a, t in pairs}
    return best


def best_matching(arms, tasks, feasible, cost):
    """Exhaustive optimal matching. arms and tasks are lists; feasible
    and cost are dicts keyed by (arm, task_id). Returns {task_id: arm}
    for the pairing that assigns as many tasks as possible, and among
    those, has the smallest total cost."""
    best, best_key = {}, (0, 0.0)
    k = min(len(arms), len(tasks))
    for task_subset in itertools.permutations(tasks, k):
        for arm_subset in itertools.permutations(arms, k):
            pairs = [(a, t) for a, t in zip(arm_subset, task_subset)
                     if feasible.get((a, t.id), False)]
            n = len(pairs)
            total = sum(cost[(a, t.id)] for a, t in pairs)
            if (n, -total) > (best_key[0], -best_key[1]):
                best_key = (n, total)
                best = {t.id: a for a, t in pairs}
    return best


class OptimalAllocator:
    """Callable with the rule_based_allocate signature. Computes one
    joint matching per state change (same signature gate as the VLM
    allocator) and answers the coordinator's per-task loop from it."""

    def __init__(self, coord_ref, dest_resolver=None, verify=True,
                 objective="minisum", timing="distance",
                 lambda_contention=None):
        if objective not in ("minisum", "minimax"):
            raise ValueError(f"unknown objective {objective!r}")
        if timing not in ("distance", "estimate"):
            raise ValueError(f"unknown timing mode {timing!r}")
        self.coord_ref = coord_ref        # callable returning the Coordinator
        self.dest_resolver = dest_resolver  # task -> (x, y), the oracle
        # objective: "minisum" minimises the TOTAL cost of the matching (the
        # classical Hungarian objective, a travel proxy). "minimax" minimises
        # the MAXIMUM pair cost (bottleneck assignment), which is the
        # per-round objective aligned with makespan. Neither is an episode
        # makespan optimum: per-round optimality does not compose over a
        # horizon. Both are reported; the scope's b2 column is the stronger
        # of the two per tier.
        self.objective = objective
        # timing: "distance" prices a pair in METRES (the historical matrix,
        # byte-identical to every episode recorded before 2026-07-29).
        # "estimate" prices it in TICKS via cell_config.leg_cost, so a
        # franka metre costs 3.67x a ur10 metre and each leg carries its
        # fixed pick-place cost. A relay's second leg is priced at the
        # cheapest capable finisher, which subsumes the handover surcharge:
        # the extra fixed_ticks IS the second pick-place cycle that
        # LAMBDA_HANDOVER approximated in distance mode.
        self.timing = timing
        # per-instance contention weight; None inherits the module constant
        # (0.0, the pre-registered contention-blind default). Units follow
        # the timing mode: metres in distance mode, ticks in estimate mode.
        self.lambda_contention = (LAMBDA_CONTENTION if lambda_contention
                                  is None else lambda_contention)
        self.verify = verify              # cross-check Hungarian against the
                                          # exhaustive solve EVERY replan
                                          # (microseconds at our scale); a
                                          # disagreement is printed loudly
                                          # and counted, never hidden
        self.verify_mismatches = 0
        # stats + log mirror the VLM allocator's shape so the episode
        # logger records the opt column identically (it was previously
        # wired with alloc=None and left NO allocator section in the JSON)
        self.stats = {"replans": 0, "assignments": 0, "relays": 0,
                      "solver_mismatches": 0, "latency_ms_total": 0.0,
                      "calls": 0,
                      # what this instance ACTUALLY ran, recorded in the
                      # episode JSON so no run can be mislabelled
                      "objective": objective, "timing": timing,
                      "lambda_contention": (LAMBDA_CONTENTION
                                            if lambda_contention is None
                                            else lambda_contention)}
        self.log = []
        self.condition = None    # opt is perception-free (no A/B); the
                                 # episode logger reads alloc.condition
                                 # uniformly across allocator types
        self._sig = None
        self._plan = {}                   # task_id -> arm
        self._routes = {}                 # (arm, task_id) -> (target, pad)

    def _replan(self, coord, zonemap):
        done_ids = {t.id for t in coord.pool if t.done}
        ready = [t for t in coord.pool
                 if not t.done and not t.failed and not t.claimed
                 and (t.waiting_on is None or t.waiting_on in done_ids)]
        idle = [n for n, ag in coord.agents.items()
                if ag.state == "IDLE" and not ag.arm.disabled]

        feasible, cost = {}, {}
        self._routes = {}
        for t in ready:
            if t.dest is None and self.dest_resolver is not None:
                t.dest = self.dest_resolver(t)
                t.dest_by = "oracle"
            p = coord.cell.scene[t.obj].data.root_pos_w[0]
            oxy = (float(p[0]), float(p[1]))
            for a in idle:
                # Route each pair through B1's OWN router (single-arm
                # candidate list), so direct-vs-relay semantics, pad
                # progress rules, and second-arm existence checks are
                # byte-identical to the rule column. Fix 2 (2026-07-21):
                # the earlier direct-only matrix silently benched the
                # Frankas (whose value flows through handovers) and made
                # ur_w run seven legs while franka_s ran one; the opt
                # column was handicapped on the heterogeneity axis.
                arm_r, target, sub = rule_based_allocate(t, oxy, [a],
                                                         zonemap)
                ok = arm_r == a and target is not None
                feasible[(a, t.id)] = ok
                if not ok:
                    cost[(a, t.id)] = float("inf")
                    continue
                if sub is None:
                    if self.timing == "estimate":
                        # FULL round trip, base -> object -> destination ->
                        # home. The coefficients were fitted over a window
                        # that ends on arrival home (done_tick is stamped
                        # there, and the zone locks are released there), so
                        # pricing only base->object->destination applies them
                        # to a shorter journey than they were measured on and
                        # under-costs exactly the tasks that tie an arm up
                        # longest. Distance mode keeps the historical
                        # one-way path so every prior episode reproduces.
                        c = C.leg_cost(a, C.route_m(a, oxy, t.dest), legs=1)
                    else:
                        c = (_dist(a, oxy)
                             + math.hypot(t.dest[0] - oxy[0],
                                          t.dest[1] - oxy[1]))
                else:
                    first = (_dist(a, oxy)
                             + math.hypot(target[0] - oxy[0],
                                          target[1] - oxy[1]))
                    second_m = math.hypot(t.dest[0] - target[0],
                                          t.dest[1] - target[1])
                    if self.timing == "estimate":
                        # Each relay leg is a full round trip for its own
                        # arm: this arm fetches the object and returns home,
                        # then the finisher collects from the pad, delivers,
                        # and returns to ITS home. Second leg priced at the
                        # cheapest capable finisher. That finisher's
                        # fixed_ticks IS the second pick-place cycle, which
                        # is what LAMBDA_HANDOVER approximates in distance
                        # mode, so no separate surcharge is added here.
                        finishers = [
                            C.leg_cost(a2, C.route_m(a2, target, t.dest),
                                       legs=1)
                            for a2 in C.ARMS
                            if C.can_grasp(a2, t.obj)
                            and zonemap.reachable(a2, target[0], target[1])
                            and zonemap.reachable(a2, *t.dest)]
                        c = (C.leg_cost(a, C.route_m(a, oxy, target), legs=1)
                             + (min(finishers) if finishers else
                                C.leg_cost(a, C.route_m(a, target, t.dest),
                                           legs=1)))
                    else:
                        c = first + second_m + LAMBDA_HANDOVER
                if self.lambda_contention:
                    from core.cell.locks import zone_of
                    zones = {zone_of(*oxy), zone_of(*target)}
                    if any(coord.locks.is_contended(z, a) for z in zones):
                        c += self.lambda_contention
                cost[(a, t.id)] = c + TIE_EPS * t.id
                self._routes[(a, t.id)] = (target,
                                           sub.dest if sub else None)
        if self.objective == "minimax":
            # Bottleneck assignment. NOT plain Hungarian on transformed
            # costs: minimising the maximum needs its own criterion. At four
            # arms the exhaustive enumeration is authoritative and exact
            # (a few hundred pairings), so no threshold-search solver is
            # needed and no Hungarian cross-check applies in this mode.
            self._plan = best_matching_minimax(idle, ready, feasible, cost)
        else:
            self._plan = solve_matching(idle, ready, feasible, cost)
        self.stats["replans"] += 1
        entry = {"round": getattr(coord, "_assign_round", 0),
                 "idle": sorted(idle),
                 "matrix": {f"{a}|{t.id}": round(cost[(a, t.id)], 3)
                            for t in ready for a in idle
                            if feasible[(a, t.id)]},
                 "matching": {str(tid): a for tid, a in self._plan.items()},
                 "total_cost": round(sum(cost[(a, tid)]
                                         for tid, a in self._plan.items()), 3),
                 "relays": [str(tid) for tid, a in self._plan.items()
                            if self._routes.get((a, tid), (None, None))[1]
                            is not None]}
        # Fold consecutive identical replans: while a planned claim
        # cannot stick (e.g. its pad is occupied), the coordinator
        # re-solves the SAME situation each round and derives the same
        # answer; one episode logged 14 copies of the gelatin decision
        # and inflated "assignments" past executed legs. One entry with a
        # repeats counter keeps the audit honest.
        last = self.log[-1] if self.log else None
        if (last is not None
                and last.get("idle") == entry["idle"]
                and last.get("matrix") == entry["matrix"]
                and last.get("matching") == entry["matching"]):
            last["repeats"] = last.get("repeats", 1) + 1
        else:
            self.stats["assignments"] += len(self._plan)
            self.stats["relays"] += len(entry["relays"])
            self.log.append(entry)
        if self.verify and self.objective == "minisum":
            ref = best_matching(idle, ready, feasible, cost)
            def key(plan):     # compare OBJECTIVES, not identities: equal-
                n = len(plan)  # cost ties may resolve differently and both
                tot = sum(cost[(a, tid)] for tid, a in plan.items())
                return (n, round(tot, 9))
            entry["verify"] = "ok"
            if key(self._plan) != key(ref):
                self.verify_mismatches += 1
                self.stats["solver_mismatches"] += 1
                entry["verify"] = "MISMATCH"
                print(f"[opt] SOLVER MISMATCH: hungarian "
                      f"{key(self._plan)} vs exhaustive {key(ref)} "
                      f"(arms={idle}, tasks={[t.id for t in ready]})",
                      flush=True)

    def __call__(self, task, obj_xy, idle_arms, zonemap):
        coord = self.coord_ref()
        done_ids = {t.id for t in coord.pool if t.done}
        ready_ids = frozenset(
            t.id for t in coord.pool
            if not t.done and not t.failed and not t.claimed
            and (t.waiting_on is None or t.waiting_on in done_ids))
        idle = frozenset(n for n, ag in coord.agents.items()
                         if ag.state == "IDLE" and not ag.arm.disabled)
        sig = (idle, ready_ids)
        if sig != self._sig:
            self._sig = sig
            self._replan(coord, zonemap)

        arm = self._plan.get(task.id)
        if arm is not None and arm in idle_arms:
            del self._plan[task.id]         # consumed
            target, pad = self._routes.get((arm, task.id),
                                           (task.dest, None))
            if pad is not None:
                # relay chosen by the matching: emit the pad leg exactly
                # as the rule does (Task constructed only on consumption
                # so unselected routes never burn task ids)
                return arm, target, Task(obj=task.obj, dest=pad)
            return arm, task.dest, None
        # Not selected this round: the matching judged other work more
        # valuable for the idle arms, or no idle arm has a route. Wait;
        # relays are now IN the matrix, so no delegation path remains.
        return None, None, None