"""Layer 4: the VLM-backed task allocator.

Drops into the same slot as rule_based_allocate. The coordinator calls
`allocate(task, obj_xy, idle_arms, zonemap)` once per candidate task in an
assignment round; the VLM, however, should look at the whole scene and pick
ONE task and arm per round. So this allocator consults the model once per
round (keyed by a round token the coordinator bumps each tick), caches the
validated decision, and answers the per-task loop consistently with it.

Decision flow per round (the veto with one feedback retry):
  1. build prompt from the current state, call the model
  2. parse + VALIDATE against measured rasters and arm status
  3. if invalid, re-prompt ONCE with the rejection reason appended
  4. if the retry is also invalid (or the model errors / times out),
     fall back to rule_based_allocate for this round
The model can never cause an unsafe or infeasible action: the validator
gates every decision, and the deterministic rule is the floor. Every
outcome is logged, including first-attempt vs post-feedback validity.

The model client reads QWEN_ENDPOINT / QWEN_MODEL / QWEN_API_KEY from the
environment. The key is NEVER stored in code. For tests, pass any callable
as `model_fn` to bypass the network entirely.
"""

import base64
import json
import math
import os
import re
import time
import urllib.request
import urllib.error

from core.cell import cell_config as C
from core.decision.state_builder import (build_state, build_prompt, grab_frame_b64,
                           parse_decision, is_noop, prompt_version)
from core.control.tasks import rule_based_allocate
from core.decision.model_registry import describe as describe_model, resolve


# ---------------------------------------------------------------------------
# Model clients: one per wire protocol, chosen by the alias, never by the
# model name. chat() is the dispatcher every experiment should call.
# ---------------------------------------------------------------------------

def openai_chat(messages, timeout=30.0, alias=None,
                return_usage=False):
    """POST messages to an OpenAI-compatible endpoint, return reply text.

    return_usage=True returns (text, usage) instead, where usage is the
    provider's token accounting. Off by default so every existing caller
    keeps the old signature; EX1, EX3 and the live pipeline share this
    function and none of them expects a tuple.

    Endpoint, model id, key and request parameters all come from the model
    registry (env/models.env plus the environment), keyed on an alias. alias
    None means FOURARM_MODEL, which defaults to qwen, so every existing
    command keeps running against the model it already ran against.

    Request parameters are NOT hardcoded here. qwen carries temperature 0.0
    because that is what every episode up to 2026-08-01 used; gpt carries
    reasoning_effort instead and no temperature, because the GPT-5.x
    reasoning tiers reject a non-default one. Putting them in config rather
    than in this function is what lets the two be different without a branch
    on the model name.

    Raises on any network or protocol error so the caller can fall back.
    """
    cfg = resolve(alias)
    payload = {"model": cfg["model"], "messages": messages}
    payload.update(cfg["params"])
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        cfg["endpoint"], data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cfg['api_key']}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"]["content"]
    if return_usage:
        # The provider's own count, not an estimate. Image tokens depend on
        # resolution and the provider's tiling, so any local guess would be
        # wrong by an unknown factor and useless for reporting cost.
        return text, (data.get("usage") or {})
    return text


ANTHROPIC_VERSION = "2023-06-01"

# data:image/png;base64,AAAA...  ->  ("image/png", "AAAA...")
_DATA_URI = re.compile(r"^data:([^;,]+);base64,(.*)$", re.S)


def to_anthropic(messages):
    """Translate OpenAI-shaped messages into Anthropic's shape.

    Returns (system_text, messages). Pure: no I/O, no config, no network,
    which is what lets it be tested for free. It is the one place a silent
    shape error could hide, because a prompt that loses its image still
    returns a plausible-looking answer and grades as a real trial.

    Three differences are handled:

      1. The system prompt is a top-level field, not a message. Anthropic
         rejects role "system" inside messages, so it is lifted out. Every
         EX2 prompt has exactly one, built by prompts.build_ex2_prompt.
      2. An image is {"type": "image", "source": {...}} carrying the raw
         base64 and its media type as separate fields, not an image_url
         holding a data URI. The media type is read off the URI rather than
         assumed to be PNG, so a future JPEG capture cannot be mislabelled.
      3. Anything else in a content list passes through untouched, which
         covers the text parts.

    A content string (rather than a list) is passed through as-is; the
    Anthropic API accepts a bare string for a user turn.
    """
    system, out = [], []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            system.append(content if isinstance(content, str)
                          else json.dumps(content))
            continue
        if not isinstance(content, list):
            out.append({"role": role, "content": content})
            continue
        parts = []
        for part in content:
            if part.get("type") != "image_url":
                parts.append(part)
                continue
            url = (part.get("image_url") or {}).get("url", "")
            hit = _DATA_URI.match(url)
            if not hit:
                raise ValueError(
                    "an image_url part is not a base64 data URI, so it "
                    "cannot be sent to Anthropic, which takes the bytes "
                    "inline rather than fetching a URL. Got: %.60r" % url)
            parts.append({"type": "image",
                          "source": {"type": "base64",
                                     "media_type": hit.group(1),
                                     "data": hit.group(2)}})
        out.append({"role": role, "content": parts})
    return "\n\n".join(system), out


def anthropic_chat(messages, timeout=30.0, alias=None,
                   return_usage=False):
    """POST messages to the Anthropic Messages API, return reply text.

    Same signature and same contract as openai_chat, deliberately, so the
    two are interchangeable behind chat() and so every harness fake and
    every existing caller keeps working untouched.

    max_tokens is REQUIRED by this API and has no default, so it comes from
    {PREFIX}_PARAMS like every other request parameter. Sending temperature
    would be a 400 on Sonnet 5 and later, which is exactly why parameters
    live in config: qwen's temperature 0.0 must not follow a model here.

    usage is remapped onto the OpenAI field names. Every row written since
    EX2 began records prompt_tokens/completion_tokens/total_tokens, and
    cost_table() sums those, so reporting Anthropic's own input_tokens and
    output_tokens would silently blank the cost column for one model only.

    NEVER raises TypeError. one_trial() probes for return_usage support with
    a bare `except TypeError`, so a TypeError from inside this function
    would be read as "this client has the old signature" and would trigger
    a second, duplicate, paid call.
    """
    cfg = resolve(alias)
    system, msgs = to_anthropic(messages)
    payload = {"model": cfg["model"], "messages": msgs}
    if system:
        payload["system"] = system
    payload.update(cfg["params"])
    if "max_tokens" not in payload:
        raise ValueError(
            f"{cfg['alias']!r} needs max_tokens: the Anthropic API requires "
            f"it and has no default. Add it to "
            f"{cfg['alias'].upper()}_PARAMS in env/models.env.")
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        cfg["endpoint"], data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "x-api-key": cfg["api_key"],
                 "anthropic-version": ANTHROPIC_VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # A policy decline arrives as HTTP 200 with no text block. Raising puts
    # it in the trial's `error` field, where it reads as what it is. Letting
    # it through would grade an empty reply as an unparseable answer and
    # count a refusal as a model failure.
    if data.get("stop_reason") == "refusal":
        raise RuntimeError(
            "anthropic declined this request (stop_reason refusal, "
            "category %r)" % ((data.get("stop_details") or {})
                              .get("category"),))

    blocks = [b for b in (data.get("content") or [])
              if b.get("type") == "text"]
    text = "".join(b.get("text", "") for b in blocks)
    if return_usage:
        u = data.get("usage") or {}
        got = {}
        if "input_tokens" in u or "output_tokens" in u:
            pt = u.get("input_tokens") or 0
            ct = u.get("output_tokens") or 0
            got = {"prompt_tokens": pt, "completion_tokens": ct,
                   "total_tokens": pt + ct}
        return text, got
    return text


CLIENTS = {"openai": openai_chat, "anthropic": anthropic_chat}


def chat(messages, timeout=30.0, alias=None, return_usage=False):
    """Call whichever client the alias declares. The default model_fn.

    Dispatch is on the registry's `api` field, so adding a provider is a
    config line plus a client, never an edit to a run loop.
    """
    return CLIENTS[describe_model(alias)["api"]](
        messages, timeout=timeout, alias=alias, return_usage=return_usage)


# ---------------------------------------------------------------------------
# Validation: a model decision must survive this to execute.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Violation taxonomy: one table, used to BUILD every rejection message and to
# CLASSIFY it back again.
# ---------------------------------------------------------------------------
# EX1's endpoint is a legality rate, but the diagnostic content is the
# COMPOSITION of illegality: "62% legal" says little, while "of the illegal
# proposals, 70% capability, 20% not idle, 10% unreachable object" is a
# finding, and it is what shows whether stripping the rules block hurts
# capability reasoning specifically or just degrades instruction following.
#
# Before 2026-08-01 the reasons were inline f-strings and nothing counted
# them by class, so per-class counts meant string matching at analysis time.
# That is the fragility that produced the txt.index("R5") bug and the
# overstated "21 of 21 rejections" claim. Messages and classification now
# come from ONE table, so they cannot drift apart.
#
# The message strings are byte-identical to the inline versions they
# replaced. Trails recorded before this change still classify, and the
# offline replay acceptance test is unaffected.
VIOLATIONS = {
    "PARSE":          "reply was not valid JSON",
    "TASK_UNKNOWN":   "task {tid} does not exist",
    "TASK_FINISHED":  "task {tid} is already finished",
    "TASK_BUSY":      "task {tid} is already being handled",
    "ARM_UNKNOWN":    "unknown arm {arm}",
    "ARM_NOT_IDLE":   "arm {arm} is not idle",
    "CAPABILITY":     "arm {arm} cannot grasp object {obj}",
    "NO_BASKETS":     "task has no destination and no baskets exist",
    "BASKET_MISSING": "task {tid} needs a basket choice; options: {options}",
    "REACH_OBJECT":   "arm {arm} cannot reach the object",
    "NO_ROUTE":       ("arm {arm} cannot reach both the object and "
                       "destination, and no handover route exists with it on "
                       "the first leg"),
}

# Which rule each class belongs to, for reporting against the prompt.
VIOLATION_RULE = {
    "PARSE": None,
    "TASK_UNKNOWN": "R1", "TASK_FINISHED": "R1", "TASK_BUSY": "R1",
    "ARM_UNKNOWN": "R2", "ARM_NOT_IDLE": "R2",
    "CAPABILITY": "R3",
    "REACH_OBJECT": "R4",
    "NO_ROUTE": "R5",
    "NO_BASKETS": "R7", "BASKET_MISSING": "R7",
}


def _reason(code, **kw):
    """Build a rejection message from the table."""
    return VIOLATIONS[code].format(**kw)


_VIOLATION_RE = None


def _violation_patterns():
    """Compile each template into an anchored, non-greedy pattern.

    Derived from the SAME table the messages come from, so a message that
    changes without its pattern changing is impossible by construction.
    """
    global _VIOLATION_RE
    if _VIOLATION_RE is None:
        pats = []
        for code, tmpl in VIOLATIONS.items():
            out, i = "", 0
            while i < len(tmpl):
                ch = tmpl[i]
                if ch == "{":
                    j = tmpl.index("}", i)
                    out += "(?P<" + tmpl[i + 1:j] + ">.+?)"
                    i = j + 1
                else:
                    out += re.escape(ch)
                    i += 1
            pats.append((code, re.compile("^" + out + "$", re.S)))
        _VIOLATION_RE = pats
    return _VIOLATION_RE


def classify(reason):
    """Reason string -> (code, fields). (None, {}) for success or unknown.

    An unrecognised reason returns None rather than a guess: a silently
    misfiled violation would corrupt the very composition EX1 reports.
    """
    if not reason:
        return None, {}
    for code, rx in _violation_patterns():
        m = rx.match(reason)
        if m:
            return code, m.groupdict()
    return None, {}


def _pad_name(xy):
    """Name of the exchange pad at xy, or None. The router returns a
    coordinate; the episode log has always carried a pad NAME, so episode_metrics.py
    and trace_episode keep working unchanged."""
    if xy is None:
        return None
    for pad, spec in C.EXCHANGE_PADS.items():
        px, py = spec["pos"]
        if math.hypot(xy[0] - px, xy[1] - py) < C.PAD_SKIP_RADIUS:
            return pad
    return None


def validate_decision(decision, coord, zonemap, baskets=None):
    """Return (ok, target, subtask, reason). Mirrors what the rule guarantees
    structurally, so a valid model choice and a rule choice are interchangeable.
    For a sorting task (task.dest is None) the decision must name a basket,
    which becomes the effective destination; the validator checks the physics
    of delivering there, NOT whether the basket is semantically right, since
    semantic choice is exactly what the experiment measures.
    reason is a short string when ok is False, for the feedback re-prompt."""
    if decision is None:
        return False, None, None, _reason("PARSE")
    tid, arm = decision.get("task_id"), decision.get("arm")

    task = next((t for t in coord.pool if t.id == tid), None)
    if task is None:
        return False, None, None, _reason("TASK_UNKNOWN", tid=tid)
    if task.done or task.failed:
        return False, None, None, _reason("TASK_FINISHED", tid=tid)
    if task.claimed or (task.waiting_on is not None):
        return False, None, None, _reason("TASK_BUSY", tid=tid)
    if arm not in coord.agents:
        return False, None, None, _reason("ARM_UNKNOWN", arm=arm)
    ag = coord.agents[arm]
    if ag.state != "IDLE" or ag.arm.disabled:
        return False, None, None, _reason("ARM_NOT_IDLE", arm=arm)
    if not C.can_grasp(arm, task.obj):
        return False, None, None, _reason("CAPABILITY", arm=arm, obj=task.obj)

    p = coord.cell.scene[task.obj].data.root_pos_w[0]
    obj_xy = (float(p[0]), float(p[1]))

    # Resolve the effective destination. Sorting tasks are born with
    # dest=None and the model must name a basket; the basket's position
    # becomes the destination the physics checks run against, and is also
    # persisted onto the task so requeues keep the semantic choice.
    dest = task.dest
    dest_from_basket = False
    basket = decision.get("basket")
    if dest is None:
        if not baskets:
            return False, None, None, _reason("NO_BASKETS")
        if basket not in baskets:
            return False, None, None, _reason("BASKET_MISSING", tid=tid,
                                              options=sorted(baskets))
        dest = tuple(baskets[basket]["pos"])
        dest_from_basket = True
        # NOTE: task.dest is deliberately NOT written here. It is persisted
        # only on the success returns below. Writing it this early meant a
        # basket named in a REJECTED decision stuck to the task: the retry
        # could never change baskets, and a later rule fallback silently
        # delivered to the model's rejected choice.
    # Reachability and capability come from the SAME zonemap and can_grasp
    # the classical heads use, so no allocator is held to a different
    # standard. What differs is only where the predicate sits: b1 and the
    # Hungarian generate options that already satisfy it, the model proposes
    # and is filtered. That gap is the research question.
    if not zonemap.reachable(arm, *obj_xy):
        return False, None, None, _reason("REACH_OBJECT", arm=arm)

    if zonemap.reachable(arm, *dest):
        task.dest = dest              # decision valid: NOW the choice may persist
        if dest_from_basket:
            task.dest_by = "model"
        return True, dest, None, ""

    # The arm can pick the object but not deliver it. Since 2026-08-01 the
    # model no longer names a pad (R5), so the cell routes the handover
    # itself with that arm on the first leg, exactly as rule_based_allocate
    # does. Any via_pad the model volunteers is ignored; the caller records
    # it as pad_named_by_model so it is visible rather than silently
    # dropped. The frozen 2026-07-25d prompt still asks for one, which is
    # the only path that should ever produce it.
    from core.control.tasks import route_via_pad, Task
    dead = {a for a in C.ARMS
            if a in coord.agents and coord.agents[a].arm.disabled}
    probe = Task(obj=task.obj, dest=dest)   # task.dest stays unwritten until valid
    first, target, sub = route_via_pad(probe, obj_xy, [arm], zonemap, dead)
    if first is None:
        return False, None, None, _reason("NO_ROUTE", arm=arm)
    sub.dest_by = "router"            # the ROUTER chose this pad, not the model
    task.dest = dest                  # decision valid: NOW the choice may persist
    if dest_from_basket:
        task.dest_by = "model"
    return True, target, sub, ""


# ---------------------------------------------------------------------------
# The allocator.
# ---------------------------------------------------------------------------

class VLMAllocator:
    """Callable with the rule_based_allocate signature. Consults the model
    once per assignment round, caches the validated decision, and answers the
    coordinator's per-task loop consistently. Falls back to the rule."""

    def __init__(self, coord_ref, engine, condition="A", model_fn=openai_chat,
                 max_feedback=1, timeout=30.0, baskets=None,
                 fallback_resolver=None, audit_dir=None, enriched=True,
                 eligible=False, model_alias=None,
                 audit_cameras=("table_cam",)):
        self.coord_ref = coord_ref          # set after Coordinator exists
        self.engine = engine
        self.condition = condition
        self.model_fn = model_fn
        # Which model this allocator talks to. None means the registry
        # default (FOURARM_MODEL, itself defaulting to qwen), so nothing
        # that already worked changes. The RESOLVED description is stamped
        # into every audit record: two models replayed over one probe set
        # must never be distinguishable only by filename.
        self.model_alias = model_alias
        try:
            self.model_desc = describe_model(model_alias)
        except Exception as e:
            # An injected model_fn (every harness) needs no registry at all.
            # Recording the reason beats a bare None when a real run later
            # produces unstamped records.
            self.model_desc = {"alias": model_alias,
                               "unresolved": f"{type(e).__name__}: {e}"}
        self.max_feedback = max_feedback
        self.timeout = timeout
        self.baskets = baskets              # sorting scenes: name -> {pos}
        self.fallback_resolver = fallback_resolver  # task -> dest xy (oracle)
        self.enriched = enriched            # reach_ok_arms lists in the state
        # ABLATION: eligibility resolved for the model, not by it. Each task
        # carries eligible_arms (capability and reach together) and R3/R4
        # point at that list. Off by default, so baselines are unaffected.
        self.eligible = eligible
        # The version the model is ACTUALLY shown. Record THIS in meta, not
        # the module constant: a mismatch between the two is the drift that
        # already produced two false CHECK lines once.
        self.prompt_version = prompt_version(enriched, eligible)
        self.zonemap = None                 # set on the first __call__
        self.audit_dir = audit_dir          # per-consult prompt+frame trail
        self._audit_seq = 0                 # (None = auditing off)
        # VIEWPOINTS SAVED PER CONSULT (2026-08-13). The frame SENT to the
        # model is unchanged and is still grabbed above; this list only
        # controls what the audit additionally records. EX2 established that
        # a viewpoint has to be validated against the specific visual
        # requirement of an experiment (the overhead view cannot resolve
        # upright from lying; the oblique view occludes the region between
        # the Frankas). Re-running Isaac to change a camera decision is the
        # one expensive step in the plan, so every harvest saves both views
        # and the choice is deferred to replay time. Default is the single
        # primary camera, so nothing that already ran changes.
        self.audit_cameras = tuple(audit_cameras or ())
        self._sig = None                    # (idle arms, ready task ids) at last consult
        self._cached = None                 # (task_id, arm, target, subtask)
        self.disabled = ()                  # set per call by the coordinator
        self._noop_since = None             # round token of the standing noop
        self.noop_watchdog = 240            # ticks; 0 disables the watchdog
        self.log = []                       # per-round outcome records
        self.stats = {"region_mismatches": 0,
                      "calls": 0, "valid_first": 0, "valid_after_feedback": 0,
                      "fallback": 0, "noop": 0, "errors": 0,
                      "rule_assigned": 0, "oracle_resolved": 0,
                      "latency_ms_total": 0.0,
                      # unnecessary_pad retired 2026-08-01: the model can no
                      # longer name a pad, so it cannot propose a needless
                      # one. A permanently-zero counter ends up in a results
                      # table by accident.
                      "violations": {}}

    def invalidate(self):
        """Drop the cached decision and force a re-consult next tick.

        Called by the coordinator when it DECLINES a decision it cannot
        execute yet, currently a handover onto an occupied pad. Without
        this the decision stays consumed and the re-consult signature
        stays unchanged, so the leg is never re-offered even once the pad
        clears."""
        self._cached = None
        self._sig = None
        self._noop_since = None
        self.stats["invalidated"] = self.stats.get("invalidated", 0) + 1

    def _consult(self, round_token):
        """Ask the model for one decision this round; validate with up to
        max_feedback corrective retries. Store the result (or None to signal
        fall-back-to-rule for this round)."""
        coord = self.coord_ref()
        state = build_state(coord, self.engine, tick=round_token,
                            baskets=self.baskets,
                            # enriched: hand the model the SAME reachability
                            # the validator enforces, so a reach rejection
                            # can only mean it ignored the list
                            zonemap=(self.zonemap if self.enriched else None),
                            eligible=self.eligible)
        image = None
        if self.condition == "V":
            image = grab_frame_b64(coord.cell.scene)
        messages = build_prompt(state, self.condition, image_b64=image)

        # Audit trail (verification workflow, 2026-07-25): the EXACT frame
        # sent to the API and the full initial prompt, one jsonl record per
        # consult. Joins the decision log on "round". Feedback re-prompts
        # are the fixed template plus the logged rejection reason, so the
        # initial record plus the decision log reconstructs every call.
        if self.audit_dir is not None:
            self._audit_seq += 1
            os.makedirs(self.audit_dir, exist_ok=True)
            img_file = None
            stem = f"consult_{self._audit_seq:03d}_round{round_token}"
            if image is not None:
                img_file = f"{stem}.png"
                with open(os.path.join(self.audit_dir, img_file), "wb") as f:
                    f.write(base64.b64decode(image))
            # EXTRA VIEWPOINTS. Grabbed from permanently-present camera
            # prims on the SAME tick as the decision, so every saved view
            # shows the state the model was actually deciding on. rot_k is
            # per camera: table_cam renders east-up and needs the -1
            # north-up correction, a camera at any other angle does not
            # (same rule as capture_ex2_scene.py). Failures are recorded,
            # never raised: an audit write must not kill a paid run.
            frames, frame_errors = {}, {}
            if img_file is not None:
                frames["primary"] = img_file
            for cam in self.audit_cameras:
                try:
                    b64 = grab_frame_b64(coord.cell.scene, camera=cam,
                                         rot_k=(-1 if cam == "table_cam"
                                                else 0))
                    fn = f"{stem}_{cam}.png"
                    with open(os.path.join(self.audit_dir, fn), "wb") as f:
                        f.write(base64.b64decode(b64))
                    frames[cam] = fn
                except Exception as e:
                    frame_errors[cam] = f"{type(e).__name__}: {e}"
            # EXACT object positions, added 2026-08-01. The state rounds xy
            # to 2 dp for the prompt, but validate_decision reaches into
            # coord.cell.scene at full precision. Replaying from the rounded
            # value would feed the validator a position up to 5 mm from the
            # live one, and this cell demonstrably places objects at 97% of
            # an arm's reach, so a boundary verdict could flip. The prompt is
            # untouched: the model still sees 2 dp, so prompt byte-identity
            # holds and only the validator's input becomes exact.
            positions_exact, position_errors = {}, {}
            for o in state.get("objects", []):
                nm = o.get("name")
                try:
                    p_ex = coord.cell.scene[nm].data.root_pos_w[0]
                    positions_exact[nm] = [float(p_ex[0]), float(p_ex[1])]
                except Exception as e:
                    # Recorded, never raised: an audit write must not kill a
                    # paid run. A silent skip would be worse, because the
                    # replay would fall back to the rounded value without
                    # anyone knowing.
                    position_errors[nm] = f"{type(e).__name__}: {e}"
            sanitized = []
            for m in messages:
                c = m["content"]
                if isinstance(c, list):
                    c = [({"type": "image_file", "file": img_file}
                          if b.get("type") == "image_url" else b)
                         for b in c]
                sanitized.append({"role": m["role"], "content": c})
            # TRUNCATE on the first consult of an episode. Append mode
            # alone silently concatenated trails whenever a run reused an
            # --out-name, so consults.jsonl held 50 records for an episode
            # with 28 consults and every positional join in input_audit
            # read the wrong state. The episode JSON is overwritten on a
            # re-run; its audit trail must be too.
            mode = "w" if self._audit_seq == 1 else "a"
            with open(os.path.join(self.audit_dir, "consults.jsonl"),
                      mode) as f:
                # The STATE DICT, added 2026-08-01, is what makes offline
                # replay possible. The rendered prompt alone cannot be
                # re-rendered at a different rung or prompt level, so every
                # EX1 and EX2 condition would need its own live episode.
                # It is already JSON-safe: build_prompt json.dumps this same
                # object into the user message, so if it were not
                # serialisable the live call would have failed first.
                f.write(json.dumps({"seq": self._audit_seq,
                                    "round": round_token,
                                    "condition": self.condition,
                                    "image_file": img_file,
                                    # image_file stays the frame the model
                                    # was SENT, so probe_store and
                                    # verify_trail are untouched. frames is
                                    # the additive record of every saved
                                    # viewpoint, camera name -> filename.
                                    "frames": frames,
                                    "frame_errors": frame_errors,
                                    "prompt_version": prompt_version(
                                        self.enriched, self.eligible),
                                    "enriched": self.enriched,
                                    "eligible": self.eligible,
                                    "state": state,
                                    "positions_exact": positions_exact,
                                    "position_errors": position_errors,
                                    "model": self.model_desc,
                                    "messages": sanitized}) + "\n")

        reason = None
        latency_ms = 0.0                # summed over this round's attempts
        # Every rejected proposal, verbatim (2026-07-26): logging only the
        # rejection REASON hid WHAT was rejected, so a fallback could not be
        # attributed to a specific model choice. Attached to fallback and
        # valid_after_feedback entries.
        rejected = []
        for attempt in range(self.max_feedback + 1):
            if reason is not None:          # feedback re-prompt
                idle_now = [n for n, ag in coord.agents.items()
                            if ag.state == "IDLE" and not ag.arm.disabled]
                messages = messages + [
                    {"role": "assistant", "content": json.dumps(self._last_raw)},
                    {"role": "user",
                     "content": f"That choice was rejected: {reason}. "
                                f"Idle arms right now: "
                                f"{', '.join(idle_now) or 'none'}. "
                                f"Choose again, obeying the reach and grasp "
                                f"limits. If no valid assignment exists right "
                                f"now, answer with task_id -1 and arm null; "
                                f"waiting for a busy arm to free up is a "
                                f"legitimate choice."}]
            try:
                self.stats["calls"] += 1
                t0 = time.time()
                try:
                    text = self.model_fn(messages, timeout=self.timeout,
                                         alias=self.model_alias)
                except TypeError:       # injected model_fn predates alias
                    text = self.model_fn(messages, timeout=self.timeout)
                dt = (time.time() - t0) * 1000.0
                latency_ms += dt
                self.stats["latency_ms_total"] = round(
                    self.stats["latency_ms_total"] + dt, 1)
            except Exception as e:           # ANY model failure -> rule fallback
                dt = (time.time() - t0) * 1000.0
                latency_ms += dt
                self.stats["latency_ms_total"] = round(
                    self.stats["latency_ms_total"] + dt, 1)
                self.stats["errors"] += 1
                self.log.append({"round": round_token, "result": "error",
                                 "latency_ms": round(latency_ms, 1),
                                 "detail": f"{type(e).__name__}: {str(e)[:100]}"})
                self._cached = None
                return
            decision = parse_decision(text)
            self._last_raw = decision if decision is not None else {"raw": text[:80]}

            if is_noop(decision):
                self.stats["noop"] += 1
                # rejected[] on noops (schema v4): a noop reached on the
                # SECOND attempt was preceded by a refused proposal, and
                # dropping it hid 9 proposals per episode, inflating
                # first-pass validity and disguising corrected retreats
                # as proactive waiting.
                self.log.append({"round": round_token, "result": "noop",
                                 "latency_ms": round(latency_ms, 1),
                                 "rejected": rejected,
                                 "attempt": attempt + 1,
                                 "reason": (decision or {}).get("reason",
                                                                "")})
                self._cached = ("noop",)
                return

            ok, target, sub, why = validate_decision(decision, coord,
                                                      self.zonemap, self.baskets)
            if ok:
                task_obj = next((t for t in coord.pool
                                 if t.id == decision["task_id"]), None)
                key = "valid_first" if attempt == 0 else "valid_after_feedback"
                self.stats[key] += 1
                entry = {"round": round_token, "result": key,
                         "task_id": decision["task_id"],
                         "arm": decision["arm"],
                         # basket, added 2026-08-01. rejected[] has carried
                         # it since schema v4 because an offline audit could
                         # not otherwise tell WHICH delivery was refused.
                         # The same argument applies to an ACCEPTED decision
                         # and was simply missed: for a sorting task with
                         # dest_xy null the basket IS the decision, and
                         # without it the decision dict cannot be rebuilt
                         # for offline replay. dest_by says who chose, not
                         # what was chosen.
                         "basket": decision.get("basket"),
                         "rejected": rejected,   # [] when valid_first
                         "arm_by": "model",
                         "dest_by": (task_obj.dest_by if task_obj
                                     is not None else None),
                         # via_pad is now the ROUTER's choice, not the
                         # model's, and pad_by says so. episode_metrics.py joins on
                         # via_pad, so the key keeps its name and meaning
                         # (which pad this task went through) while pad_by
                         # records who decided it.
                         "via_pad": _pad_name(target) if sub is not None
                                    else None,
                         "pad_by": "router" if sub is not None else None,
                         "route_inserted": sub is not None,
                         "latency_ms": round(latency_ms, 1),
                         "reason": decision.get("reason", "")}
                # The frozen 2026-07-25d prompt still asks for via_pad, and a
                # model may volunteer one anyway. It is ignored, but never
                # silently: an ignored field that nobody counts is how a
                # condition gets mislabelled.
                if decision.get("via_pad") not in (None, "null"):
                    entry["pad_named_by_model"] = decision.get("via_pad")
                    self.stats["pad_named_by_model"] = \
                        self.stats.get("pad_named_by_model", 0) + 1
                # Semantic sorting correctness (G1), measured and never
                # vetoed. The validator deliberately checks only the
                # PHYSICS of delivering to a named basket, because the
                # semantic choice is what the experiment measures. Nothing
                # counted it until now, so a bowl sent to the food basket
                # surfaced only as a MISPLACED verdict at the end of an
                # episode, with no way to attribute it to a round. Under
                # the 2026-08-01 rules it is also invisible to the legality
                # metrics: naming a wrong-but-reachable basket is legal.
                if (task_obj is not None
                        and decision.get("basket") in (self.baskets or {})):
                    spec = C.OBJECT_SPECS.get(task_obj.obj, {})
                    cat = spec.get("category")
                    expected = f"basket_{cat}" if cat else None
                    if expected is not None:
                        entry["basket_expected"] = expected
                        entry["basket_correct"] = (decision["basket"]
                                                   == expected)
                        if not entry["basket_correct"]:
                            self.stats["basket_wrong"] = \
                                self.stats.get("basket_wrong", 0) + 1
                # Region-declaration quality (measured, never vetoed):
                # compare the model's declared zones with the true zones its
                # assignment occupies. Scored against the OBJECT and the
                # DESTINATION, which is what the prompt asks for. When the
                # router inserts a handover the first physical target is a
                # pad, but the model was never asked to predict that and must
                # not be marked wrong for it.
                from core.cell.locks import zone_of
                required = None
                if task_obj is not None and task_obj.dest is not None:
                    p = coord.cell.scene[task_obj.obj].data.root_pos_w[0]
                    required = sorted({zone_of(float(p[0]), float(p[1])),
                                       zone_of(task_obj.dest[0],
                                               task_obj.dest[1])})
                declared = decision.get("regions")
                if isinstance(declared, list):
                    declared = sorted({str(z).lower() for z in declared})
                else:
                    declared = None
                entry["regions_declared"] = declared
                entry["regions_required"] = required
                if required is not None:
                    entry["region_mismatch"] = declared != required
                    if declared != required:
                        self.stats["region_mismatches"] += 1
                # Efficiency is measured, never vetoed. unnecessary_pad
                # retired 2026-08-01: the model cannot name a pad any more,
                # so it cannot propose a needless one. Its replacement is a
                # JUDGEMENT measure rather than a lookup error: the model
                # chose an arm that forced a two-trip handover while some
                # idle arm could have delivered the task in one.
                if sub is not None and task_obj is not None \
                        and task_obj.dest is not None:
                    p = coord.cell.scene[task_obj.obj].data.root_pos_w[0]
                    oxy = (float(p[0]), float(p[1]))
                    direct_idle = [
                        n for n, ag in coord.agents.items()
                        if ag.state == "IDLE" and not ag.arm.disabled
                        and C.can_grasp(n, task_obj.obj)
                        and self.zonemap.reachable(n, *oxy)
                        and self.zonemap.reachable(n, *task_obj.dest)]
                    entry["avoidable_relay"] = bool(direct_idle)
                    entry["direct_idle_arms"] = direct_idle
                    if direct_idle:
                        self.stats["avoidable_relay"] = \
                            self.stats.get("avoidable_relay", 0) + 1
                self.log.append(entry)
                self._cached = (decision["task_id"], decision["arm"], target, sub)
                return
            _v_code, _ = classify(why)
            if _v_code is not None:
                self.stats["violations"][_v_code] = \
                    self.stats["violations"].get(_v_code, 0) + 1
            else:
                self.stats["violations_unclassified"] = \
                    self.stats.get("violations_unclassified", 0) + 1
            rejected.append({
                "attempt": attempt + 1,
                "task_id": (decision or {}).get("task_id"),
                "arm": (decision or {}).get("arm"),
                "via_pad": (decision or {}).get("via_pad"),
                # basket (schema v4): for a sorting task the model also
                # names the destination, and without it an offline audit
                # cannot tell WHICH delivery was refused. Two reach
                # rejections were mis-attributed for exactly this reason.
                "basket": (decision or {}).get("basket"),
                "model_reason": (decision or {}).get("reason", ""),
                "rejected_because": why,
                # Machine-readable class alongside the human string, so
                # per-class counts never depend on matching text at
                # analysis time. None means the reason did not match the
                # table, which is a bug worth seeing rather than a bucket
                # to guess at.
                "violation": _v_code,
                "violation_rule": VIOLATION_RULE.get(_v_code),
                "unparseable": decision is None,
            })
            reason = why                     # loop for one feedback retry

        # exhausted retries -> rule fallback for this round
        self.stats["fallback"] += 1
        self.log.append({"round": round_token, "result": "fallback",
                         "latency_ms": round(latency_ms, 1),
                         "rejected": rejected,
                         "last_reason": reason})
        self._cached = None

    # ---- the rule_based_allocate-compatible entry point -------------------
    def __call__(self, task, obj_xy, idle_arms, zonemap, disabled=()):
        self.zonemap = zonemap
        self.disabled = disabled
        coord = self.coord_ref()
        # Consult the model only when the decision-relevant state has changed:
        # the set of idle arms and the set of ready (assignable) tasks. The
        # round token alone would consult every tick, and a lingering
        # idle-arm-plus-unassignable-task state then makes a synchronous
        # network call per physics step, which is the observed 'hang'. With
        # this gate, a stable state costs one call; any claim, completion,
        # requeue, or arm status change alters the signature and re-consults.
        done_ids = {t.id for t in coord.pool if t.done}
        ready = frozenset(
            t.id for t in coord.pool
            if not t.done and not t.failed and not t.claimed
            and (t.waiting_on is None or t.waiting_on in done_ids))
        idle = frozenset(n for n, ag in coord.agents.items()
                         if ag.state == "IDLE" and not ag.arm.disabled)
        sig = (idle, ready)
        # LIVENESS. The gate only re-consults when (idle arms, ready tasks)
        # changes. A noop changes neither, so if the model declines while
        # every arm is idle nothing will ever change again and the cell
        # sits until the tick limit with work still queued. Rather than
        # override the decision, which would veto an efficiency choice and
        # destroy the strategic-noop measurement, force a FRESH consult
        # once a noop has stood for noop_watchdog ticks.
        now = getattr(coord, "_assign_round", 0)
        stale_noop = False
        if self._cached == ("noop",) and self.noop_watchdog:
            if self._noop_since is None:
                self._noop_since = now
            elif now - self._noop_since >= self.noop_watchdog:
                stale_noop = True
        else:
            self._noop_since = None
        if sig != self._sig or stale_noop:
            self._sig = sig
            if stale_noop:
                self._noop_since = now
                self.stats["noop_watchdog_fired"] = \
                    self.stats.get("noop_watchdog_fired", 0) + 1
            self._consult(now)

        if self._cached is None:             # model failed/declined -> rule
            if task.dest is None and self.fallback_resolver is not None:
                task.dest = self.fallback_resolver(task)
                task.dest_by = "oracle"
                self.stats["oracle_resolved"] += 1
            arm, target, sub = rule_based_allocate(task, obj_xy, idle_arms,
                                                   zonemap, disabled)
            if sub is not None and task.dest is not None:
                # Patient floor. The greedy rule never waits: if only busy
                # arms can deliver directly, it invents a handover, which is
                # how the observed extra hop (pad_ne -> center -> basket)
                # arose after a model failure. As a SAFETY NET the rule may
                # only (a) assign direct legs, or (b) build a handover when
                # NO arm, idle or busy, could ever do the task directly.
                # Otherwise it offers nothing and the task waits for the
                # right arm. Same policy as the optimal allocator. The
                # standalone rule baseline keeps its greedy character.
                # Same reasoning inverted: a DEAD arm that could have
                # delivered directly must not suppress a handover that is
                # now genuinely required.
                direct_ever = any(
                    a not in disabled
                    and C.can_grasp(a, task.obj)
                    and zonemap.reachable(a, *obj_xy)
                    and zonemap.reachable(a, *task.dest)
                    for a in C.ARMS)
                if direct_ever:
                    return None, None, None
            if arm is not None:              # the rescue is never silent
                # ... but it must not be REPEATED either. While a handover
                # leg's pad is occupied, the coordinator re-runs allocation
                # every tick and lands here each time; one blocked episode
                # once produced 33 identical entries and inflated
                # rule_assigned from ~3 to 35, breaking the stats
                # arithmetic episode_metrics.py depends on. Consecutive identical
                # rescues fold into ONE entry with a repeats counter; the
                # stat counts unique rescues.
                last = self.log[-1] if self.log else None
                if (last is not None
                        and last.get("result") == "rule_assigned"
                        and last.get("task_id") == task.id
                        and last.get("arm") == arm):
                    last["repeats"] = last.get("repeats", 1) + 1
                else:
                    self.stats["rule_assigned"] += 1
                    self.log.append({"round": getattr(coord,
                                                      "_assign_round", 0),
                                     "result": "rule_assigned",
                                     "task_id": task.id, "arm": arm,
                                     "arm_by": "rule",
                                     "dest_by": task.dest_by})
            return arm, target, sub
        if self._cached[0] in ("noop", "consumed"):   # nothing (more) this round
            return None, None, None

        tid, arm, target, sub = self._cached
        if task.id == tid and arm in idle_arms:
            # Consume with a sentinel, NOT None: None means 'model failed, use
            # the rule', and reusing it here let the rule silently allocate
            # every remaining task in the round with no log or fallback count.
            self._cached = ("consumed",)
            return arm, target, sub
        # the model's chosen task is not this one; offer nothing for others,
        # so the round yields exactly the model's single decision
        return None, None, None