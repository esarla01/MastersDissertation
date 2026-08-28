"""Model registry: an alias resolves to endpoint, model id, key and request
parameters.

Why this exists. Until 2026-08-01 the client read QWEN_ENDPOINT, QWEN_MODEL
and QWEN_API_KEY straight from the environment. That works for one model and
breaks for two: nothing in an episode or an audit record said WHICH model
produced a consult, so two models replayed over the same probe set would be
distinguishable only by filename. The prompt side already has this
discipline (PROMPT_VERSION makes it impossible to pool a pad-naming episode
with a router-delegated one) and the model side needed the same.

Where values come from, in precedence order:

  1. the real environment (an export always wins, so existing shells and
     one-off overrides need no edit to any file)
  2. env/models.env, loaded automatically on first use

Keys are NEVER read from the file. Each alias names the environment variable
that carries its key, and that variable must be exported. A missing key
raises here, immediately, naming the variable, rather than surfacing as a
401 twenty minutes into a run.

An alias also names the WIRE PROTOCOL it speaks, {PREFIX}_API, defaulting to
"openai" so no alias written before 2026-08-27 needs a line adding. See the
APIS constant below for why that is config rather than a branch on the model
name.

Usage:

    from core.decision.model_registry import resolve, describe
    cfg = resolve("gpt")          # endpoint, model, api_key, params, api
    describe("gpt")               # the same minus api_key, for stamping
"""

import json
import os

DEFAULT_ALIAS = "qwen"

# The wire protocol an alias speaks. Everything up to 2026-08-27 was
# OpenAI-shaped, so "openai" is the default and no existing alias needs a
# line adding. Anthropic's own API is a different shape entirely -- POST
# /v1/messages, an x-api-key header, a required anthropic-version header,
# the system prompt as a top-level field rather than a message, and a reply
# that arrives as content blocks rather than choices[0].message.content.
#
# This lives in config rather than being sniffed from the model name for
# the same reason the request parameters do: qwen carries temperature 0.0
# and gpt carries reasoning_effort, and a branch on the model name would
# have to learn every future model id to keep telling them apart.
APIS = ("openai", "anthropic")
DEFAULT_API = "openai"

# fourarm/core/decision/model_registry.py -> fourarm/env/models.env
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ENV_FILE = os.path.join(
    os.path.dirname(os.path.dirname(_HERE)), "env", "models.env")

_loaded = False
_stamp = None          # (path, mtime, size) of the last successful read
_mine = {}             # every key this module put into the environment


def env_file():
    """Path to the registry file. FOURARM_MODELS_ENV overrides it, which is
    how a harness points at a fixture without touching the real one."""
    return os.environ.get("FOURARM_MODELS_ENV", DEFAULT_ENV_FILE)


def _fingerprint(p):
    try:
        st = os.stat(p)
    except OSError:
        return None
    return (p, st.st_mtime_ns, st.st_size)


def load(path=None, force=False):
    """Read the registry file into the environment. Idempotent; safe to
    call from anywhere.

    An export ALWAYS wins. A value this function put there itself does not:
    it is overwritten when the file changes.

    WHY THAT DISTINCTION EXISTS. Before 2026-08-27 every value was written
    with setdefault and the file was read once per process. Editing
    env/models.env in a live kernel therefore did nothing at all, and worse,
    did nothing SELECTIVELY: a newly added variable arrived, because nothing
    held that name yet, while an edited one kept whatever the first read had
    put there. The registry that resulted was half old and half new. It cost
    sixty paid calls failing on a max_tokens the file plainly set, and the
    error named the file, which is the one place the value was correct.

    Re-reading on a changed file cannot be done by ignoring the environment,
    because a real export must still win. So the keys THIS function set are
    remembered, and only those are refreshed. Anything a shell exported, or
    that another tool put there, is still left exactly alone.

    Returns the path read, or None when there is no file. A missing file is
    not an error: a shell that exports QWEN_ENDPOINT and QWEN_MODEL directly
    is a complete configuration on its own.
    """
    global _loaded, _stamp
    p = path or env_file()
    fresh = _fingerprint(p)
    if _loaded and not force and path is None and fresh == _stamp:
        return env_file()
    if not os.path.exists(p):
        _loaded = True
        _stamp = None
        return None
    _stamp = fresh
    with open(p) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            # An export wins. A value we wrote ourselves is ours to update.
            if k not in os.environ or os.environ.get(k) == _mine.get(k):
                os.environ[k] = v
                _mine[k] = v
    _loaded = True
    return p


def aliases():
    """Every alias the registry knows, in declaration order."""
    load()
    raw = os.environ.get("FOURARM_MODELS", DEFAULT_ALIAS)
    return [a.strip().lower() for a in raw.split(",") if a.strip()]


def _prefix(alias):
    return alias.strip().upper()


def describe(alias=None):
    """Everything about an alias EXCEPT its key.

    This is what gets stamped into episode meta and audit records, so it
    must never carry the secret. The key is deliberately absent rather than
    masked: a masked key in a JSON file is still a key-shaped string that
    someone will one day try to use.
    """
    load()
    alias = (alias or os.environ.get("FOURARM_MODEL")
             or DEFAULT_ALIAS).strip().lower()
    known = aliases()
    if alias not in known:
        raise ValueError(
            f"unknown model alias {alias!r}; known aliases are {known}. "
            f"Add it to FOURARM_MODELS in {env_file()}.")
    p = _prefix(alias)
    endpoint = os.environ.get(f"{p}_ENDPOINT")
    model = os.environ.get(f"{p}_MODEL")
    key_var = os.environ.get(f"{p}_KEY_VAR", f"{p}_API_KEY")
    api = os.environ.get(f"{p}_API", DEFAULT_API).strip().lower()
    if api not in APIS:
        raise ValueError(
            f"unknown {p}_API {api!r}; expected one of {sorted(APIS)}. The "
            f"wire protocol is never guessed from the model name: an "
            f"Anthropic model addressed as OpenAI fails with a KeyError on "
            f"'choices' after the call has been paid for.")
    raw_params = os.environ.get(f"{p}_PARAMS", "{}")
    try:
        params = json.loads(raw_params)
    except ValueError as e:
        raise ValueError(f"{p}_PARAMS is not valid JSON: {raw_params!r} "
                         f"({e})")
    if not isinstance(params, dict):
        raise ValueError(f"{p}_PARAMS must be a JSON object, got "
                         f"{type(params).__name__}")
    if not endpoint:
        raise ValueError(f"{p}_ENDPOINT is not set (alias {alias!r})")
    if not model:
        raise ValueError(f"{p}_MODEL is not set (alias {alias!r})")
    return {"alias": alias, "endpoint": endpoint, "model": model,
            "key_var": key_var, "api": api,
            # sorted so the stamp is stable across runs and two records can
            # be compared byte for byte
            "params": dict(sorted(params.items()))}


def resolve(alias=None):
    """describe() plus the key. Raises if the key variable is unset."""
    cfg = describe(alias)
    key = os.environ.get(cfg["key_var"])
    if not key:
        raise ValueError(
            f"no API key for model alias {cfg['alias']!r}: environment "
            f"variable {cfg['key_var']} is not set. Export it in your shell; "
            f"it is never stored in {env_file()} or anywhere else in the "
            f"tree.")
    out = dict(cfg)
    out["api_key"] = key
    return out
