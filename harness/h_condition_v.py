"""Harness: two-condition prompt construction (imports the REAL state_builder).

Checks, against core.decision.state_builder as shipped:
  1. PROMPT_VERSION is the CURRENT (enriched) lineage, and the frozen
     2026-07-25d lineage is still resolvable for the older episodes.
  2. The system prompt carries the CORRECTED image orientation (top east,
     left north, matching the scene_cfg camera rotation) and is identical
     across conditions (single source).
  3. Condition V user text is byte-identical to condition A user text.
  4. Condition V content = [image block, text block]; A = [text block].
  5. Retired condition B (or any unknown condition) raises ValueError.
Run: python3 h_condition_v.py   (from this directory)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from core.decision import state_builder as sb   # REAL module, no stubs

STATE = {
    "tick": 42,
    "arms": [
        {"name": "ur_w", "type": "ur10", "state": "IDLE", "disabled": False,
         "base_xy": [-1.05, 0.0], "reach_m": 1.3, "ee_xy": [-0.6, 0.1],
         "delicate_ok": False},
        {"name": "franka_n", "type": "franka", "state": "IDLE",
         "disabled": False, "base_xy": [0.0, 0.85], "reach_m": 0.855,
         "ee_xy": [0.1, 0.5], "delicate_ok": True},
    ],
    "objects": [
        {"name": "ycb_banana", "category": "food", "delicate": True,
         "xy": [0.05, 0.30], "zone": "ne", "at_pad": None},
        {"name": "ycb_mustard", "category": "food", "delicate": False,
         "xy": [-0.4, -0.2], "zone": "sw", "at_pad": None},
    ],
    "tasks": [{"id": 0, "object": "ycb_banana", "status": "queued",
               "dest_xy": None}],
    "zone_locks": {}, "zone_inbound": {},
    "baskets": {"food": {"pos": [-0.45, 0.55]}},
    "exchange_pads": {"centre": {"pos": [0.0, 0.0], "occupied_by": None}},
    "recent_events": [],
}

FAKE_IMG = "QUJD"          # base64 of "ABC"; content is irrelevant here

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


# 1. version
check("PROMPT_VERSION is the current enriched lineage",
      sb.PROMPT_VERSION == "2026-08-01a", sb.PROMPT_VERSION)
check("the frozen 25d lineage is still addressable",
      sb.PROMPT_VERSION_BASELINE == "2026-07-25d", sb.PROMPT_VERSION_BASELINE)

# 2. orientation line in the (single, shared) system prompt. Since
#    2026-07-25c grab_frame_b64 rotates the raw east-up render 90 deg CW,
#    so the model's image really is north-up, east-right; the prompt line
#    must say exactly that and nothing about quarter turns.
sys_txt = sb.system_prompt()
check("north-up orientation line in system prompt",
      "top edge is north (+y)" in sys_txt and
      "right edge is east" in sys_txt)
check("no stale east-up or quarter-turn claim in system prompt",
      "top edge is east" not in sys_txt and
      "quarter turn" not in sys_txt)

msgs_a = sb.build_prompt(STATE, "A")
msgs_v = sb.build_prompt(STATE, "V", image_b64=FAKE_IMG)

check("system prompt identical A vs V",
      msgs_a[0]["content"] == msgs_v[0]["content"])

# 3. byte identity of the text channel
text_a = msgs_a[1]["content"][0]["text"]
blocks_v = msgs_v[1]["content"]
text_v = [b for b in blocks_v if b["type"] == "text"][0]["text"]
check("V text byte-identical to A text",
      text_a.encode("utf-8") == text_v.encode("utf-8"),
      f"A {len(text_a)} bytes, V {len(text_v)} bytes")

# 4. block structure
check("A content is exactly one text block",
      [b["type"] for b in msgs_a[1]["content"]] == ["text"])
check("V content is image block then text block",
      [b["type"] for b in blocks_v] == ["image_url", "text"])
img_url = [b for b in blocks_v if b["type"] == "image_url"][0]["image_url"]["url"]
check("V image block carries the frame",
      img_url == f"data:image/png;base64,{FAKE_IMG}")

# 5. retired / unknown conditions fail loudly
for bad in ("B", "b", "AV", None, ""):
    try:
        sb.build_prompt(STATE, bad, image_b64=FAKE_IMG)
        check(f"condition {bad!r} raises ValueError", False, "no exception")
    except ValueError:
        check(f"condition {bad!r} raises ValueError", True)

print()
# ---------------------------------------------------------------------------
# registry tints must be TUPLES
# ---------------------------------------------------------------------------
# USD wants a GfVec3f for inputs:diffuseColor. A Python list arrives as an
# array and the spawn fails with a type mismatch, NON-FATALLY: the object
# is simply never tinted, so two objects meant to be distinguishable in a
# condition V frame come out identical and nothing in the output says so.
# Found on the first EX2 capture, 2026-08-03, when the four new pose rows
# were written with list literals while every existing row used tuples.
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "..",
                                  "fourarm", "ycb"))
from ycb_objects import YCB as _YCB                              # noqa: E402

_bad = [n for n, spec in _YCB.items()
        if "tint" in spec and not isinstance(spec["tint"], tuple)]
check("every registry tint is a tuple, not a list", not _bad, str(_bad))

_wrong = [n for n, spec in _YCB.items()
          if "tint" in spec and (len(spec["tint"]) != 3
                                 or not all(0.0 <= c <= 1.0
                                            for c in spec["tint"]))]
check("every tint is three components in [0, 1]", not _wrong, str(_wrong))

print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
