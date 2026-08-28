"""h_model_registry: the model registry resolves correctly, fails loudly,
and never leaks a key.

Imports the REAL registry and the REAL allocator. Nothing here reimplements
resolution logic.

What is pinned, and why each one is here:

  1. The shipped env/models.env parses and declares both aliases. If it
     stops parsing, every run silently falls back to whatever the shell
     happens to hold.
  2. The environment BEATS the file. This is the property that lets an
     existing shell keep working and a one-off override need no edit.
  3. A missing key raises, and the message names the variable. The failure
     this prevents is a 401 twenty minutes into a paid run.
  4. An unknown alias is refused, not silently defaulted. Silently
     defaulting would attribute a gpt run to qwen, which is exactly the
     mislabelling the registry exists to stop.
  5. describe() never returns the key, under any alias. It is stamped into
     audit records that get zipped and shared.
  6. The allocator stamps the resolved description, and still works with an
     injected model_fn that knows nothing about aliases (every other
     harness relies on that).

Run:  python3 h_model_registry.py
"""

import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.decision import model_registry as mr                  # noqa: E402

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail
                                                  else ""))
    if not ok:
        fails.append(label)


def fresh(**overrides):
    """Reset the process environment to a known state and reload."""
    for k in list(os.environ):
        if (k.startswith(("QWEN_", "GPT_", "FOURARM_"))
                or k in ("OPENAI_API_KEY",)):
            del os.environ[k]
    os.environ.update(overrides)
    mr._loaded = False
    mr.load(force=True)


# ---------------------------------------------------------------------------
# 1. the shipped file
# ---------------------------------------------------------------------------
fresh()
path = mr.env_file()
check("the shipped registry file exists", os.path.exists(path), path)
# Derived, not hardcoded: this read ["qwen", "gpt"] and started failing the
# moment gemini and claude were added, reporting a correct registry as
# broken.
check("it declares the aliases the file lists",
      mr.aliases() == [a.strip() for a in
                       os.environ["FOURARM_MODELS"].split(",") if a.strip()],
      str(mr.aliases()))

q = mr.describe("qwen")
g = mr.describe("gpt")
check("qwen resolves to the DashScope compatible-mode endpoint",
      q["model"] == "qwen-vl-max"
      and q["endpoint"].endswith("/chat/completions")
      and q["key_var"] == "QWEN_API_KEY", str(q))
check("qwen keeps temperature 0.0, as every episode before 2026-08-01 ran",
      q["params"] == {"temperature": 0.0}, str(q["params"]))
check("gpt resolves to OpenAI with reasoning effort pinned",
      g["model"] == "gpt-5.6-terra"
      and g["key_var"] == "OPENAI_API_KEY"
      and g["params"].get("reasoning_effort") == "low", str(g))
check("gpt sends NO temperature (the reasoning tiers reject one)",
      "temperature" not in g["params"], str(g["params"]))
check("no alias defaults silently: the default is declared in the file",
      os.environ.get("FOURARM_MODEL") == "qwen"
      and mr.describe()["alias"] == "qwen")

# ---------------------------------------------------------------------------
# 2. the environment beats the file
# ---------------------------------------------------------------------------
fresh(QWEN_MODEL="qwen-vl-plus")
check("an exported value overrides the file",
      mr.describe("qwen")["model"] == "qwen-vl-plus",
      mr.describe("qwen")["model"])
fresh()
check("and the file is restored once the override is gone",
      mr.describe("qwen")["model"] == "qwen-vl-max")

# ---------------------------------------------------------------------------
# 3. missing key, missing file, bad params
# ---------------------------------------------------------------------------
fresh()
try:
    mr.resolve("gpt")
    check("a missing key raises", False, "no exception")
except ValueError as e:
    check("a missing key raises and NAMES the variable",
          "OPENAI_API_KEY" in str(e), str(e)[:90])

fresh(OPENAI_API_KEY="sk-test-not-a-real-key")
cfg = mr.resolve("gpt")
check("with the key exported, resolve returns it",
      cfg["api_key"] == "sk-test-not-a-real-key")

with tempfile.TemporaryDirectory() as d:
    missing = os.path.join(d, "absent.env")
    fresh(FOURARM_MODELS_ENV=missing, QWEN_ENDPOINT="https://x/y",
          QWEN_MODEL="m", QWEN_API_KEY="k")
    check("a missing registry file is not an error when the shell is complete",
          mr.load(force=True) is None
          and mr.resolve("qwen")["model"] == "m")

    bad = os.path.join(d, "bad.env")
    open(bad, "w").write("FOURARM_MODELS=x\nX_ENDPOINT=e\nX_MODEL=m\n"
                         "X_PARAMS={not json}\n")
    fresh(FOURARM_MODELS_ENV=bad)
    try:
        mr.describe("x")
        check("malformed PARAMS raises", False, "no exception")
    except ValueError as e:
        check("malformed PARAMS raises and shows the offending value",
              "X_PARAMS" in str(e), str(e)[:80])

# ---------------------------------------------------------------------------
# 4. unknown alias
# ---------------------------------------------------------------------------
fresh()
try:
    # "nosuchmodel" rather than a name that might later become real:
    # "gemini" was used here and stopped being unknown when it was added to
    # the registry, so the check silently passed on nothing.
    mr.describe("nosuchmodel")
    check("an unknown alias is refused", False, "no exception")
except ValueError as e:
    check("an unknown alias is refused, not silently defaulted",
          "gemini" in str(e) and "qwen" in str(e), str(e)[:90])

# ---------------------------------------------------------------------------
# 5. describe() must never carry the key
# ---------------------------------------------------------------------------
fresh(QWEN_API_KEY="sk-secret-qwen", OPENAI_API_KEY="sk-secret-gpt")
leaked = []
for a in mr.aliases():
    blob = json.dumps(mr.describe(a))
    if "sk-secret" in blob:
        leaked.append(a)
check("describe() leaks no key for any alias", not leaked, str(leaked))
check("describe() carries the key VARIABLE NAME instead",
      mr.describe("gpt")["key_var"] == "OPENAI_API_KEY")

# ---------------------------------------------------------------------------
# 6. the allocator stamps it, and still takes an alias-blind model_fn
# ---------------------------------------------------------------------------
from core.decision import vlm_allocator as va                   # noqa: E402


class NS(types.SimpleNamespace):
    pass


def blind_model_fn(messages, timeout=30.0):
    """An injected fn with the OLD signature. Every other harness uses one
    of these, so the allocator must not require the alias argument."""
    blind_model_fn.calls += 1
    return json.dumps({"task_id": -1, "arm": None, "reason": "wait"})


blind_model_fn.calls = 0

fresh(QWEN_API_KEY="sk-secret-qwen")
alloc = va.VLMAllocator(lambda: None, engine=None, condition="A",
                        model_fn=blind_model_fn, model_alias="gpt")
check("the allocator resolved and stored a model description",
      alloc.model_desc.get("model") == "gpt-5.6-terra", str(alloc.model_desc))
check("the stored description carries no key",
      "sk-secret" not in json.dumps(alloc.model_desc))

alloc_default = va.VLMAllocator(lambda: None, engine=None, condition="A",
                                model_fn=blind_model_fn)
check("no alias given means the registry default (qwen)",
      alloc_default.model_desc.get("model") == "qwen-vl-max",
      str(alloc_default.model_desc.get("model")))

fresh(FOURARM_MODELS_ENV="/nonexistent/models.env")
alloc_unres = va.VLMAllocator(lambda: None, engine=None, condition="A",
                              model_fn=blind_model_fn, model_alias="gpt")
check("an unresolvable alias records WHY rather than a bare None",
      "unresolved" in alloc_unres.model_desc,
      str(alloc_unres.model_desc))


# --- gemini and claude, added 2026-08-07 --------------------------------
# A third and fourth model turn a two-model dissociation into a claim about
# the class. gemini is reached through an OpenAI-compatible surface; claude
# is spoken natively since 2026-08-27, so what needs checking is that the
# registry resolves both, that each is routed to the right wire protocol,
# and that nothing here carries a secret.
# Earlier checks repoint the registry at a fixture, so the real file has to
# be restored before asserting anything about its contents.
os.environ.pop("FOURARM_MODELS_ENV", None)
for _k in list(os.environ):
    if _k.startswith(("QWEN_", "GPT_", "GEMINI_", "CLAUDE_", "FOURARM_")):
        if not _k.endswith("_API_KEY"):
            os.environ.pop(_k, None)
mr.load(force=True)
check("the real registry file is readable", mr.env_file()
      and os.path.exists(mr.env_file()), str(mr.env_file()))
for _alias in ("gemini", "claude"):
    check("%s is in the registry" % _alias,
          _alias in mr.aliases(), str(sorted(mr.aliases())))
    _d = mr.describe(_alias)
    check("%s names an endpoint, a model and a key variable" % _alias,
          _d["endpoint"] and _d["model"] and _d["key_var"], str(_d))
    check("%s describe() carries no key" % _alias,
          "api_key" not in _d,
          "describe() is what gets stamped into episode records")

check("gemini uses the OpenAI compatibility shim",
      "/openai/" in mr.describe("gemini")["endpoint"],
      "the trailing /openai/ segment is what maps the OpenAI wire format "
      "onto Gemini's own API")
check("gemini points at chat/completions",
      mr.describe("gemini")["endpoint"].endswith("/chat/completions"))
# Until 2026-08-27 this asserted the endpoint still said REPLACE, because
# the alias could not work: openai_chat cannot speak to /v1/messages. Now
# that anthropic_chat exists the thing worth pinning is that the two travel
# together. An Anthropic endpoint reached by the OpenAI client fails with a
# KeyError on "choices" AFTER the call has been paid for, so the pairing is
# checked here rather than discovered mid-run.
check("claude points at the native Anthropic messages endpoint",
      mr.describe("claude")["endpoint"].endswith("/v1/messages"),
      str(mr.describe("claude")["endpoint"]))
check("claude is routed to the anthropic client",
      mr.describe("claude")["api"] == "anthropic",
      "an Anthropic endpoint addressed with the OpenAI wire format fails "
      "on the reply shape, after the money is spent")
check("claude carries max_tokens",
      "max_tokens" in mr.describe("claude")["params"],
      "the Anthropic API requires it and has no default, so a missing one "
      "is a 400 on every trial of a paid sweep")
check("every OpenAI-shaped alias still says so",
      all(mr.describe(a)["api"] == "openai"
          for a in mr.aliases() if a != "claude"),
      "api defaults to openai, so an alias written before the field "
      "existed must be unaffected by it")

# This compared model ids alone and started failing the moment gpt_hi was
# added, because gpt and gpt_hi share gpt-5.6-terra deliberately and differ
# only in reasoning_effort. Sharing a model id is the POINT of that pair.
# What must stay distinct is the model PLUS its request parameters, because
# that pair is what a row's alias actually stands for.
_ident = {(mr.describe(a)["model"],
           json.dumps(mr.describe(a)["params"], sort_keys=True))
          for a in mr.aliases()}
check("every alias asks a distinct question",
      len(_ident) == len(mr.aliases()),
      "two aliases resolving to the same model AND the same parameters "
      "would be indistinguishable in a results file")
check("no key value is written in the registry file",
      not any(tok in open(mr.env_file()).read()
              for tok in ("sk-", "AIza", "sk-ant")),
      "the file ships inside every zip")

print("\nRESULT: " + ("ALL PASS" if not fails
                      else f"{len(fails)} FAILURE(S): {fails}"))
sys.exit(1 if fails else 0)