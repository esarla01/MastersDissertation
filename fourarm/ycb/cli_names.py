"""Canonical allocator column names for the CLI (pure stdlib, no Isaac).

One source of truth shared by run_ycb_sort.py and run_experiment.py so the
two runners can never disagree about what a column name means.

Canonical names (match the thesis columns exactly):
  b1     rule baseline (submission-order walk, nearest capable idle arm)
  b2     Hungarian matcher (per-round optimal assignment)
  vlm1   VLM condition A (structured Text only), ONE decision per round
  vlm2   VLM condition V (the identical Text plus the overhead Image)
  bvlm1  BATCH VLM condition A: the model decides the WHOLE round jointly
  bvlm2  BATCH VLM condition V: batch decision with the overhead Image

The bvlm columns are the joint-decision counterpart of vlm1/vlm2: one model
call assigns every idle arm together (like b2's Hungarian matching) rather
than one task per round. Same conditions (A text-only, V text+image), same
validator; only the decision granularity differs.

Legacy aliases accepted and normalized silently: oracle -> b1, opt -> b2.
Bare "vlm" is rejected with guidance (it does not say which condition).
"""

import os
import time

COLUMNS = {
    "random": {"kind": "random", "condition": None},
    "b1":    {"kind": "rule", "condition": None},
    "b2":    {"kind": "opt",  "condition": None},
    "vlm1":  {"kind": "vlm",  "condition": "A"},
    "vlm2":  {"kind": "vlm",  "condition": "V"},
    "bvlm1": {"kind": "bvlm", "condition": "A"},
    "bvlm2": {"kind": "bvlm", "condition": "V"},
}

ALIASES = {"oracle": "b1", "opt": "b2"}

CLI_CHOICES = sorted(COLUMNS) + sorted(ALIASES)


def normalize_allocator(name):
    """Return (short_name, kind, condition) for a CLI allocator string.

    kind is one of "random" | "rule" | "opt" | "vlm" | "bvlm"; condition is
    "A" | "V" | None.
    Raises ValueError with guidance for bare "vlm" or unknown names."""
    short = ALIASES.get(name, name)
    if short == "vlm":
        raise ValueError(
            "allocator 'vlm' is ambiguous: use vlm1 (Text) or vlm2 "
            "(Text+Image)")
    if short not in COLUMNS:
        raise ValueError(
            f"unknown allocator {name!r}; choose from {CLI_CHOICES}")
    spec = COLUMNS[short]
    return short, spec["kind"], spec["condition"]


def unique_out_name(alloc_short, out_dir="out", clock=time.localtime):
    """Unique episode stem: <alloc>_<YYYYMMDD>_<HHMMSS>[, _2, _3, ...].

    The stem prefixes the allocator name so recordings and JSONs are
    identifiable at a glance; uniqueness is checked against BOTH the
    .json and .mp4 that will carry the stem. clock is injectable for
    tests."""
    stamp = time.strftime("%Y%m%d_%H%M%S", clock())
    stem = f"{alloc_short}_{stamp}"
    candidate, n = stem, 1
    while (os.path.exists(os.path.join(out_dir, candidate + ".json"))
           or os.path.exists(os.path.join(out_dir, candidate + ".mp4"))):
        n += 1
        candidate = f"{stem}_{n}"
    return candidate
