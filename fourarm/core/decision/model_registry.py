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

Usage:

    from core.decision.model_registry import resolve, describe
    cfg = resolve("gpt")          # endpoint, model, api_key, params
    describe("gpt")               # the same minus api_key, for stamping
"""

import json
import os

DEFAULT_ALIAS = "qwen"

# fourarm/core/decision/model_registry.py -> fourarm/env/models.env
_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ENV_FILE = os.path.join(
    os.path.dirname(os.path.dirname(_HERE)), "env", "models.env")

_loaded = False


def env_file():
    """Path to the registry file. FOURARM_MODELS_ENV overrides it, which is
    how a harness points at a fixture without touching the real one."""
    return os.environ.get("FOURARM_MODELS_ENV", DEFAULT_ENV_FILE)


def load(path=None, force=False):
    """Read the registry file into the environment WITHOUT overwriting
    anything already set. Idempotent; safe to call from anywhere.

    Returns the path read, or None when there is no file. A missing file is
    not an error: a shell that exports QWEN_ENDPOINT and QWEN_MODEL directly
    is a complete configuration on its own.
    """
    global _loaded
    if _loaded and not force and path is None:
        return env_file()
    p = path or env_file()
    if not os.path.exists(p):
        _loaded = True
        return None
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
            os.environ.setdefault(k, v)     # the environment always wins
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
            "key_var": key_var,
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
