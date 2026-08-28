"""h_anthropic_client: the OpenAI-to-Anthropic message translation is
lossless, and the reply parser reads the shape Anthropic actually returns.

Imports the REAL translation function and the REAL client. Nothing here
reimplements either, and nothing here makes a network call: the transport is
stubbed so the whole file is free to run.

WHY THIS FILE EXISTS. Until 2026-08-27 no harness exercised the HTTP client
at all, because there was only one and it was OpenAI-shaped end to end. A
second wire protocol makes that a gap with teeth: a prompt that loses its
image still comes back with a plausible answer, grades as a real trial, and
is indistinguishable in the results file from a model that looked and was
wrong. Every check below is aimed at that failure.

What is pinned, and why each one is here:

  1. The system prompt is LIFTED OUT of messages. Anthropic rejects role
     "system" inside the messages array, so leaving it there is a 400 on
     every trial of a sweep.
  2. The image survives, as base64 with its media type carried separately.
     This is the silent one. An image_url part that Anthropic does not
     understand is not an error, it is a text-only trial.
  3. The media type is READ from the data URI, not assumed. A future JPEG
     capture must not be labelled image/png.
  4. Text parts and message order are untouched, so the state block still
     follows the image exactly as the OpenAI path sends it.
  5. usage is remapped onto the OpenAI field names, because every EX2 row
     ever written records prompt_tokens/completion_tokens and cost_table()
     sums those.
  6. A refusal raises rather than returning "". A silent empty reply grades
     as unparseable and counts a policy decline as a model failure.
  7. max_tokens is required, and its absence is caught before the call.

Run:  python3 h_anthropic_client.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.decision import vlm_allocator as VA                   # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


# ---------------------------------------------------------------------------
# 1. Translation, against a message list in the exact shape EX2 builds.
# ---------------------------------------------------------------------------
# Mirrors prompts.build_ex2_prompt: a system message, then a user message
# whose content is [image, text] in that order.
B64 = "iVBORw0KGgoAAAANSUhEUg"
MSGS = [
    {"role": "system", "content": "You are the task allocator."},
    {"role": "user", "content": [
        {"type": "image_url",
         "image_url": {"url": "data:image/png;base64," + B64}},
        {"type": "text", "text": "Cell state:\n{}"},
    ]},
]

system, msgs = VA.to_anthropic(MSGS)

check("the system prompt is lifted to the top level",
      system == "You are the task allocator.", repr(system))
check("no system message survives in the messages array",
      not any(m["role"] == "system" for m in msgs),
      "Anthropic rejects role 'system' inside messages, which would be a "
      "400 on every trial of a sweep")
check("the user message is kept", [m["role"] for m in msgs] == ["user"],
      str([m["role"] for m in msgs]))

parts = msgs[0]["content"]
check("part order is unchanged, image then text",
      [p["type"] for p in parts] == ["image", "text"],
      str([p["type"] for p in parts]))
check("no image_url key survives anywhere",
      "image_url" not in json.dumps(msgs),
      "an image_url part Anthropic does not understand is not an error, it "
      "is a silently text-only trial")
check("the image arrives as base64 with the bytes intact",
      parts[0]["source"] == {"type": "base64", "media_type": "image/png",
                             "data": B64},
      json.dumps(parts[0]["source"])[:120])
check("the text part is untouched",
      parts[1] == {"type": "text", "text": "Cell state:\n{}"},
      str(parts[1]))

# The media type is read, not assumed.
_, jpeg = VA.to_anthropic(
    [{"role": "user", "content": [
        {"type": "image_url",
         "image_url": {"url": "data:image/jpeg;base64," + B64}}]}])
check("the media type comes from the data URI, not a default",
      jpeg[0]["content"][0]["source"]["media_type"] == "image/jpeg",
      "a future JPEG capture must not be labelled image/png")

# A remote URL cannot be honoured: Anthropic takes the bytes inline.
try:
    VA.to_anthropic(
        [{"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": "https://example.com/a.png"}}]}])
    _raised = False
except ValueError:
    _raised = True
check("a non-data-URI image raises rather than being dropped", _raised,
      "dropping it would send a text-only prompt that still grades")

# A plain string content is legal and must pass through.
_, plain = VA.to_anthropic([{"role": "user", "content": "hello"}])
check("a bare string content passes through",
      plain == [{"role": "user", "content": "hello"}], str(plain))


# ---------------------------------------------------------------------------
# 2. The client, with the transport stubbed. No network, no key, no cost.
# ---------------------------------------------------------------------------
class _Resp:
    """Enough of the urlopen context manager for the client to read."""

    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _stub(payload, capture=None):
    def _urlopen(req, timeout=None):
        if capture is not None:
            capture["body"] = json.loads(req.data.decode("utf-8"))
            capture["headers"] = dict(req.headers)
        return _Resp(payload)
    return _urlopen


REPLY = {"content": [{"type": "text", "text": '{"task_id": 0}'}],
         "stop_reason": "end_turn",
         "usage": {"input_tokens": 3200, "output_tokens": 120}}

_real_urlopen = VA.urllib.request.urlopen
_real_resolve = VA.resolve
CFG = {"alias": "claude", "endpoint": "https://api.anthropic.com/v1/messages",
       "model": "claude-sonnet-5", "key_var": "ANTHROPIC_API_KEY",
       "api": "anthropic", "params": {"max_tokens": 1024},
       "api_key": "test-not-a-real-key"}
try:
    VA.resolve = lambda alias=None: dict(CFG)

    seen = {}
    VA.urllib.request.urlopen = _stub(REPLY, seen)
    text, usage = VA.anthropic_chat(MSGS, alias="claude", return_usage=True)

    check("the reply text is read from the content blocks",
          text == '{"task_id": 0}', repr(text))
    check("usage is remapped onto the OpenAI field names",
          usage == {"prompt_tokens": 3200, "completion_tokens": 120,
                    "total_tokens": 3320},
          "every EX2 row records prompt_tokens/completion_tokens and "
          "cost_table() sums them: %s" % usage)
    check("return_usage=False still returns a bare string",
          isinstance(VA.anthropic_chat(MSGS, alias="claude"), str),
          "EX1, EX3 and the live pipeline all expect one value")

    check("the key travels in x-api-key, not Authorization",
          any(k.lower() == "x-api-key" for k in seen["headers"])
          and not any(k.lower() == "authorization" for k in seen["headers"]),
          str(sorted(seen["headers"])))
    check("the version header is sent",
          any(k.lower() == "anthropic-version" for k in seen["headers"]),
          "the API requires it")
    check("the system prompt is sent as a top-level field",
          seen["body"].get("system") == "You are the task allocator.",
          str(seen["body"].get("system")))
    check("max_tokens reaches the wire from PARAMS",
          seen["body"].get("max_tokens") == 1024,
          str(seen["body"].get("max_tokens")))
    check("no temperature is sent",
          "temperature" not in seen["body"],
          "Sonnet 5 and later reject it with a 400, so qwen's "
          "temperature 0.0 must never follow a model here")

    # A refusal is HTTP 200 with no text block.
    VA.urllib.request.urlopen = _stub(
        {"content": [], "stop_reason": "refusal",
         "stop_details": {"type": "refusal", "category": "cyber"}})
    try:
        VA.anthropic_chat(MSGS, alias="claude")
        _refused = False
    except RuntimeError:
        _refused = True
    check("a refusal raises rather than returning an empty reply", _refused,
          "an empty reply grades as unparseable, which would count a policy "
          "decline as a model failure")

    # max_tokens missing is caught before the call, not after a 400.
    VA.resolve = lambda alias=None: dict(CFG, params={})
    VA.urllib.request.urlopen = _stub(REPLY)
    try:
        VA.anthropic_chat(MSGS, alias="claude")
        _caught = False
    except ValueError:
        _caught = True
    check("a missing max_tokens raises before the call is made", _caught,
          "the API requires it, so without this every trial of a sweep 400s")

    # And the failure must never be a TypeError.
    VA.resolve = lambda alias=None: dict(CFG)
    VA.urllib.request.urlopen = _stub({"content": [], "usage": {}})
    try:
        VA.anthropic_chat(MSGS, alias="claude", return_usage=True)
        _te = False
    except TypeError:
        _te = True
    except Exception:                                          # noqa: BLE001
        _te = False
    check("a malformed reply does not raise TypeError", not _te,
          "one_trial probes for return_usage with a bare except TypeError, "
          "so a TypeError here is read as an old signature and triggers a "
          "second, duplicate, paid call")
finally:
    VA.urllib.request.urlopen = _real_urlopen
    VA.resolve = _real_resolve


# ---------------------------------------------------------------------------
# 3. Dispatch: the alias, not the model name, chooses the client.
# ---------------------------------------------------------------------------
check("both wire protocols have a client",
      set(VA.CLIENTS) == {"openai", "anthropic"}, str(sorted(VA.CLIENTS)))
check("claude dispatches to the anthropic client",
      VA.CLIENTS["anthropic"] is VA.anthropic_chat)
check("everything else still dispatches to the OpenAI client",
      VA.CLIENTS["openai"] is VA.openai_chat,
      "EX1, EX3 and the live pipeline must be untouched by this")

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)
