"""Layer 4 (batch): the whole-round, joint VLM allocator.

Drops into the same slot as rule_based_allocate / VLMAllocator / the
Hungarian OptimalAllocator. Where VLMAllocator asks the model for ONE
(task, arm) per round and the coordinator's per-task loop is served that
single decision, this allocator asks the model for the WHOLE round at once:
one call returns a LIST of (task, arm[, basket]) assignments covering every
idle arm it wants to use, exactly the way b2 produces a joint matching, only
the matcher is the model rather than the Hungarian algorithm.

Structurally it mirrors OptimalAllocator: consult once when the decision-
relevant state changes, cache a plan {task_id: (arm, target, subtask)}, and
answer the coordinator's per-task loop from it. The coordinator applies the
whole plan across one (or, if a pad is briefly busy, a few) ticks WITHOUT
re-calling the model per claim, so the model really does decide the round as
a unit.

Validation is ALL-OR-NOTHING (Erin's choice, 2026-08-03): a batch is accepted
only if every assignment in it is individually legal AND no arm or task is
used twice. Any violation rejects the entire batch; one feedback re-prompt
carries the reason, and if the retry is also invalid (or the model errors or
times out) the round falls back to the deterministic rule, task by task,
exactly like VLMAllocator. So the model can never cause an unsafe or
infeasible action, and the rule is always the floor.

The model client, audit trail, validator, and violation taxonomy are all
reused from vlm_allocator, so the two heads are held to the identical safety
standard and differ only in decision granularity.
"""

import base64
import json
import os
import time

from core.cell import cell_config as C
from core.decision.state_builder import (build_state, build_batch_prompt,
                           grab_frame_b64, parse_batch_decision,
                           batch_prompt_version)
from core.decision.vlm_allocator import (openai_chat, validate_decision,
                           classify, VIOLATION_RULE, _reason, _pad_name)
from core.control.tasks import rule_based_allocate
from core.decision.model_registry import describe as describe_model


class BatchVLMAllocator:
    """Callable with the rule_based_allocate signature. Consults the model
    ONCE per round for a whole-round assignment list, validates it
    all-or-nothing, caches the plan, and answers the coordinator's per-task
    loop from it. Falls back to the rule for the round on failure."""

    def __init__(self, coord_ref, engine, condition="A", model_fn=openai_chat,
                 max_feedback=1, timeout=30.0, baskets=None,
                 fallback_resolver=None, audit_dir=None, enriched=True,
                 eligible=False, model_alias=None, noop_watchdog=240):
        self.coord_ref = coord_ref
        self.engine = engine
        self.condition = condition
        self.model_fn = model_fn
        self.model_alias = model_alias
        try:
            self.model_desc = describe_model(model_alias)
        except Exception as e:
            self.model_desc = {"alias": model_alias,
                               "unresolved": f"{type(e).__name__}: {e}"}
        self.max_feedback = max_feedback
        self.timeout = timeout
        self.baskets = baskets
        self.fallback_resolver = fallback_resolver
        self.enriched = enriched
        self.eligible = eligible
        self.prompt_version = batch_prompt_version(enriched, eligible)
        self.zonemap = None
        self.disabled = ()
        self.audit_dir = audit_dir
        self._audit_seq = 0
        # Cached whole-round plan and the situation it was solved for.
        # _plan maps task_id -> (arm, target, subtask). It is NOT consumed on
        # serve: the coordinator's own claimed-guard stops a claimed task
        # being re-offered, while a plan entry whose leg could not be claimed
        # yet (a busy pad) is deliberately re-offered next tick until it can.
        self._plan = {}
        self._sig = None                 # (idle arms, ready tasks) at last consult
        self._noop = False               # model chose to wait this situation
        self._noop_since = None
        self.noop_watchdog = noop_watchdog
        self.condition = condition
        self.log = []
        self.stats = {"calls": 0, "valid_first": 0, "valid_after_feedback": 0,
                      "fallback": 0, "noop": 0, "errors": 0,
                      "rule_assigned": 0, "oracle_resolved": 0,
                      "latency_ms_total": 0.0,
                      # batch-specific: how many whole-round plans were
                      # accepted, their total size (mean = size/batches), and
                      # rejections caused by two picks sharing an arm/task.
                      "batches": 0, "batch_size_total": 0, "batch_conflicts": 0,
                      "violations": {}}

    def invalidate(self):
        """Called by the coordinator when it declines a leg it cannot execute
        yet (a handover onto an occupied pad). Unlike the sequential VLM this
        is a counted NO-OP: the plan is kept, so the same leg is simply re-
        offered next tick until the pad frees, which is the desired 'wait for
        the pad' behaviour and avoids paying for a whole new model call every
        tick a pad is briefly busy."""
        self.stats["invalidated"] = self.stats.get("invalidated", 0) + 1

    # ---- per-round consultation ------------------------------------------
    def _audit(self, round_token, state, messages, image, coord):
        if self.audit_dir is None:
            return
        self._audit_seq += 1
        os.makedirs(self.audit_dir, exist_ok=True)
        img_file = None
        if image is not None:
            img_file = f"batch_{self._audit_seq:03d}_round{round_token}.png"
            with open(os.path.join(self.audit_dir, img_file), "wb") as f:
                f.write(base64.b64decode(image))
        positions_exact, position_errors = {}, {}
        for o in state.get("objects", []):
            nm = o.get("name")
            try:
                p = coord.cell.scene[nm].data.root_pos_w[0]
                positions_exact[nm] = [float(p[0]), float(p[1])]
            except Exception as e:
                position_errors[nm] = f"{type(e).__name__}: {e}"
        sanitized = []
        for m in messages:
            c = m["content"]
            if isinstance(c, list):
                c = [({"type": "image_file", "file": img_file}
                      if b.get("type") == "image_url" else b) for b in c]
            sanitized.append({"role": m["role"], "content": c})
        mode = "w" if self._audit_seq == 1 else "a"
        with open(os.path.join(self.audit_dir, "batch_consults.jsonl"),
                  mode) as f:
            f.write(json.dumps({"seq": self._audit_seq, "round": round_token,
                                "condition": self.condition,
                                "image_file": img_file,
                                "prompt_version": self.prompt_version,
                                "enriched": self.enriched,
                                "eligible": self.eligible,
                                "state": state,
                                "positions_exact": positions_exact,
                                "position_errors": position_errors,
                                "model": self.model_desc,
                                "messages": sanitized}) + "\n")

    def _rej(self, a, why, code, unparseable=False):
        """A rejected-proposal record, mirroring VLMAllocator's schema."""
        a = a or {}
        return {"task_id": a.get("task_id"), "arm": a.get("arm"),
                "via_pad": a.get("via_pad"), "basket": a.get("basket"),
                "model_reason": a.get("reason", ""),
                "rejected_because": why, "violation": code,
                "violation_rule": VIOLATION_RULE.get(code),
                "unparseable": unparseable}

    def _count_violation(self, code):
        if code is not None:
            self.stats["violations"][code] = \
                self.stats["violations"].get(code, 0) + 1
        else:
            self.stats["violations_unclassified"] = \
                self.stats.get("violations_unclassified", 0) + 1

    def _validate_batch(self, assignments, coord):
        """All-or-nothing joint validation.

        Each assignment must pass the SAME validate_decision the sequential
        head uses, AND no arm or task may appear twice. On any failure the
        whole batch is rejected and every task.dest that validate_decision
        wrote for an earlier (individually valid) assignment is rolled back,
        so a rejected batch leaves no residue for the rule fallback to
        deliver against. Returns (ok, plan, reason, rejected_records)."""
        seen_arms, seen_tasks, plan, snaps, rej = set(), set(), {}, [], []
        for a in assignments:
            tid, arm = a.get("task_id"), a.get("arm")
            if tid in seen_tasks:
                why = _reason("TASK_BUSY", tid=tid) + " (duplicated in batch)"
                self.stats["batch_conflicts"] += 1
                self._rollback(snaps)
                rej.append(self._rej(a, why, "TASK_BUSY"))
                return False, {}, why, rej
            if arm in seen_arms:
                why = f"arm {arm} is used by two assignments in the batch"
                self.stats["batch_conflicts"] += 1
                self._rollback(snaps)
                rej.append(self._rej(a, why, "ARM_NOT_IDLE"))
                return False, {}, why, rej
            task = next((t for t in coord.pool if t.id == tid), None)
            if task is not None:             # snapshot BEFORE validate mutates
                snaps.append((task, task.dest, task.dest_by))
            ok, target, sub, why = validate_decision(a, coord, self.zonemap,
                                                     self.baskets)
            if not ok:
                code, _ = classify(why)
                self._count_violation(code)
                self._rollback(snaps)
                rej.append(self._rej(a, why, code, unparseable=False))
                return False, {}, why, rej
            seen_tasks.add(tid)
            seen_arms.add(arm)
            plan[tid] = (arm, target, sub)
        return True, plan, "", rej

    @staticmethod
    def _rollback(snaps):
        for task, dest, dest_by in reversed(snaps):
            task.dest = dest
            task.dest_by = dest_by

    def _consult(self, round_token):
        """Ask the model for the whole round's assignments; validate all-or-
        nothing with up to max_feedback corrective retries. Sets self._plan
        (accepted), self._noop (strategic wait), or leaves both empty (fall
        back to the rule for this round)."""
        coord = self.coord_ref()
        state = build_state(coord, self.engine, tick=round_token,
                            baskets=self.baskets,
                            zonemap=(self.zonemap if self.enriched else None),
                            eligible=self.eligible)
        image = grab_frame_b64(coord.cell.scene) if self.condition == "V" else None
        messages = build_batch_prompt(state, self.condition, image_b64=image)
        self._audit(round_token, state, messages, image, coord)

        reason, latency, rejected = None, 0.0, []
        for attempt in range(self.max_feedback + 1):
            if reason is not None:            # feedback re-prompt
                idle_now = [n for n, ag in coord.agents.items()
                            if ag.state == "IDLE" and not ag.arm.disabled]
                messages = messages + [
                    {"role": "assistant",
                     "content": json.dumps(self._last_raw)},
                    {"role": "user",
                     "content": f"That batch was rejected: {reason}. The whole "
                                f"batch is discarded when any assignment is "
                                f"illegal. Idle arms right now: "
                                f"{', '.join(idle_now) or 'none'}. Return the "
                                f"FULL corrected assignments list, each arm and "
                                f"each task used at most once, obeying the reach "
                                f"and grasp limits. If nothing can be assigned "
                                f"now, return an empty assignments list with a "
                                f"reason."}]
            try:
                self.stats["calls"] += 1
                t0 = time.time()
                try:
                    text = self.model_fn(messages, timeout=self.timeout,
                                         alias=self.model_alias)
                except TypeError:             # injected model_fn predates alias
                    text = self.model_fn(messages, timeout=self.timeout)
                dt = (time.time() - t0) * 1000.0
                latency += dt
                self.stats["latency_ms_total"] = round(
                    self.stats["latency_ms_total"] + dt, 1)
            except Exception as e:            # ANY model failure -> rule fallback
                dt = (time.time() - t0) * 1000.0
                latency += dt
                self.stats["latency_ms_total"] = round(
                    self.stats["latency_ms_total"] + dt, 1)
                self.stats["errors"] += 1
                self.log.append({"round": round_token, "result": "error",
                                 "latency_ms": round(latency, 1),
                                 "detail": f"{type(e).__name__}: {str(e)[:100]}"})
                self._plan, self._noop = {}, False
                return

            assignments = parse_batch_decision(text)
            self._last_raw = (assignments if assignments is not None
                              else {"raw": text[:80]})

            if assignments is None:
                reason = _reason("PARSE")
                self._count_violation("PARSE")
                rejected.append(self._rej(None, reason, "PARSE",
                                          unparseable=True))
                continue

            if len(assignments) == 0:         # strategic (or forced) wait
                self.stats["noop"] += 1
                self.log.append({"round": round_token, "result": "noop",
                                 "latency_ms": round(latency, 1),
                                 "rejected": rejected,
                                 "attempt": attempt + 1})
                self._plan, self._noop = {}, True
                return

            ok, plan, why, rej_items = self._validate_batch(assignments, coord)
            rejected.extend(rej_items)
            if ok:
                key = "valid_first" if attempt == 0 else "valid_after_feedback"
                self.stats[key] += 1
                self.stats["batches"] += 1
                self.stats["batch_size_total"] += len(plan)
                self._record_batch_quality(plan, coord, round_token, key,
                                           rejected, latency)
                self._plan, self._noop = plan, False
                return
            reason = why

        # retries exhausted -> rule fallback for the whole round
        self.stats["fallback"] += 1
        self.log.append({"round": round_token, "result": "fallback",
                         "latency_ms": round(latency, 1),
                         "rejected": rejected, "last_reason": reason})
        self._plan, self._noop = {}, False

    def _record_batch_quality(self, plan, coord, round_token, key, rejected,
                              latency):
        """Log the accepted plan plus measured, never-vetoed quality per
        assignment: semantic sort correctness (G1) and whether the model
        forced a handover an idle arm could have delivered directly. Same
        measures the sequential head records, applied to each pick."""
        assignments = []
        for tid, (arm, target, sub) in plan.items():
            t = next((x for x in coord.pool if x.id == tid), None)
            rec = {"task_id": tid, "arm": arm, "arm_by": "model",
                   "dest_by": (t.dest_by if t is not None else None),
                   "via_pad": _pad_name(target) if sub is not None else None,
                   "pad_by": "router" if sub is not None else None,
                   "route_inserted": sub is not None}
            if t is not None and (self.baskets or {}):
                spec = C.OBJECT_SPECS.get(t.obj, {})
                cat = spec.get("category")
                if cat is not None:
                    expected = f"basket_{cat}"
                    rec["basket_expected"] = expected
                    # dest_by == 'model' means the model named the basket
                    if t.dest_by == "model" and t.dest is not None:
                        bx, by = t.dest
                        chosen = next((nm for nm, s in self.baskets.items()
                                       if abs(s["pos"][0] - bx) < 1e-6
                                       and abs(s["pos"][1] - by) < 1e-6), None)
                        rec["basket"] = chosen
                        rec["basket_correct"] = (chosen == expected)
                        if chosen is not None and chosen != expected:
                            self.stats["basket_wrong"] = \
                                self.stats.get("basket_wrong", 0) + 1
            assignments.append(rec)
        self.log.append({"round": round_token, "result": key,
                         "assignments": assignments, "batch_size": len(plan),
                         "rejected": rejected, "latency_ms": round(latency, 1)})

    # ---- the rule_based_allocate-compatible entry point -------------------
    def _prune_plan(self, coord, idle):
        """Drop plan entries that can no longer be offered: the task has been
        claimed, completed, failed, or gone, or its arm is no longer idle.
        Claimed tasks leave the plan naturally as the coordinator's own
        claimed-guard stops offering them; this keeps _plan a true picture of
        what is still outstanding from the current batch."""
        if not self._plan:
            return
        pool_by_id = {t.id: t for t in coord.pool}
        for tid in list(self._plan):
            arm = self._plan[tid][0]
            t = pool_by_id.get(tid)
            if (t is None or t.done or t.failed or t.claimed
                    or t.waiting_on is not None or arm not in idle):
                del self._plan[tid]

    def _rule_fallback(self, task, obj_xy, idle_arms, zonemap, disabled, coord):
        """The patient rule floor, identical in policy to VLMAllocator's
        fallback: resolve a missing destination via the oracle, then let the
        rule assign only direct legs or a handover no arm could ever do
        directly, so a model failure never makes the cell greedier than b2."""
        if task.dest is None and self.fallback_resolver is not None:
            task.dest = self.fallback_resolver(task)
            task.dest_by = "oracle"
            self.stats["oracle_resolved"] += 1
        arm, target, sub = rule_based_allocate(task, obj_xy, idle_arms,
                                               zonemap, disabled)
        if sub is not None and task.dest is not None:
            direct_ever = any(
                a not in disabled and C.can_grasp(a, task.obj)
                and zonemap.reachable(a, *obj_xy)
                and zonemap.reachable(a, *task.dest)
                for a in C.ARMS)
            if direct_ever:
                return None, None, None
        if arm is not None:
            last = self.log[-1] if self.log else None
            if (last is not None and last.get("result") == "rule_assigned"
                    and last.get("task_id") == task.id
                    and last.get("arm") == arm):
                last["repeats"] = last.get("repeats", 1) + 1
            else:
                self.stats["rule_assigned"] += 1
                self.log.append({"round": getattr(coord, "_assign_round", 0),
                                 "result": "rule_assigned",
                                 "task_id": task.id, "arm": arm,
                                 "arm_by": "rule", "dest_by": task.dest_by})
        return arm, target, sub

    def __call__(self, task, obj_xy, idle_arms, zonemap, disabled=()):
        self.zonemap = zonemap
        self.disabled = disabled
        coord = self.coord_ref()
        done_ids = {t.id for t in coord.pool if t.done}
        ready = frozenset(
            t.id for t in coord.pool
            if not t.done and not t.failed and not t.claimed
            and (t.waiting_on is None or t.waiting_on in done_ids))
        idle = frozenset(n for n, ag in coord.agents.items()
                         if ag.state == "IDLE" and not ag.arm.disabled)
        now = getattr(coord, "_assign_round", 0)

        self._prune_plan(coord, idle)

        # Re-consult ONLY when the current batch is exhausted. While the plan
        # still holds an offerable entry the model is not called again, so one
        # consultation really does decide the whole round; the coordinator
        # applies the cached plan across this tick (and any tick a pad leg
        # waits on an occupied pad). When the plan is empty we consult afresh
        # if the situation changed and there is assignable work, mirroring the
        # OptimalAllocator's signature gate. The noop watchdog preserves
        # liveness: a standing wait re-consults after noop_watchdog rounds so
        # a strategic wait can never wedge the cell to the tick limit.
        if not self._plan:
            stale_noop = False
            if self._noop and self.noop_watchdog:
                if self._noop_since is None:
                    self._noop_since = now
                elif now - self._noop_since >= self.noop_watchdog:
                    stale_noop = True
            else:
                self._noop_since = None
            sig = (idle, ready)
            if (sig != self._sig or stale_noop) and idle and ready:
                self._sig = sig
                self._noop = False
                if stale_noop:
                    self._noop_since = now
                    self.stats["noop_watchdog_fired"] = \
                        self.stats.get("noop_watchdog_fired", 0) + 1
                self._consult(now)

        entry = self._plan.get(task.id)
        if entry is not None:
            arm, target, sub = entry
            if arm in idle_arms:
                return arm, target, sub
            return None, None, None
        if self._plan or self._noop:
            # A batch is in force for other arms, or the model chose to wait:
            # offer nothing for this task, so the round yields exactly the
            # model's joint decision and no greedy rule assignment leaks in.
            return None, None, None
        # No plan and not a deliberate wait -> the model errored or its batch
        # was rejected: the rule floor keeps the cell moving.
        return self._rule_fallback(task, obj_xy, idle_arms, zonemap,
                                   disabled, coord)
