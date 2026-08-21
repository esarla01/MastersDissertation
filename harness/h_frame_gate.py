"""Harness: VLMAllocator frame-capture gate (imports the REAL allocator).

Instantiates the REAL VLMAllocator for conditions A and V and drives one
_consult round with the module's collaborators intercepted (build_state,
grab_frame_b64, build_prompt recorded; model_fn returns a noop). Verifies
the camera is grabbed for V only, never for A (condition B retired
2026-07-25), and that the captured frame reaches build_prompt.

Run: python3 h_frame_gate.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from core.decision import vlm_allocator as va   # REAL module

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


calls = {}


def fake_build_state(coord, engine, tick=None, baskets=None, zonemap=None,
                     eligible=False):
    return {"arms": [], "tasks": []}


def fake_grab(scene):
    calls["grabbed"] = calls.get("grabbed", 0) + 1
    return "FRAME64"


def fake_build_prompt(state, condition, image_b64=None):
    calls["image_b64"] = image_b64
    return [{"role": "system", "content": "s"},
            {"role": "user", "content": [{"type": "text", "text": "t"}]}]


def fake_model(messages, timeout=30.0):
    return '{"task_id": -1, "arm": null}'


va.build_state = fake_build_state
va.grab_frame_b64 = fake_grab
va.build_prompt = fake_build_prompt

coord = NS(cell=NS(scene="SCENE"), agents={})

for cond, expect_img in (("A", False), ("V", True)):
    calls.clear()
    alloc = va.VLMAllocator(lambda: coord, engine=None, condition=cond,
                            model_fn=fake_model)
    alloc._consult(round_token=0)
    grabbed = calls.get("grabbed", 0)
    img = calls.get("image_b64")
    if expect_img:
        check(f"condition {cond}: frame grabbed once and passed",
              grabbed == 1 and img == "FRAME64",
              f"grabbed={grabbed}, image={img!r}")
    else:
        check(f"condition {cond}: no frame grabbed, image None",
              grabbed == 0 and img is None,
              f"grabbed={grabbed}, image={img!r}")

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
