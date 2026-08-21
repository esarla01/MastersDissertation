"""Harness: VLM consult audit trail (imports the REAL allocator).

Drives the REAL VLMAllocator._consult with fake collaborators and an
audit_dir, for condition A (no image) and condition V (fake frame), then
verifies:
  1. consults.jsonl exists with one record per consult, joinable on
     "round" with the decision log.
  2. The V record names an image file; the file exists and its bytes are
     EXACTLY the frame that was captured (byte compare).
  3. The sanitized messages contain no base64 data URL, but an
     image_file block naming the saved PNG; the text block is intact.
  4. The A record has image_file null and text-only messages.
  5. audit_dir=None (default) writes nothing.
Run: python3 h_audit_trail.py
"""
import base64
import json
import os
import sys
import tempfile

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


FRAME_BYTES = b"PNGBYTES-not-a-real-png-but-byte-exact"
FRAME_B64 = base64.b64encode(FRAME_BYTES).decode("ascii")


# The state rounds xy to 2 dp for the prompt. The audit record must carry
# the UNROUNDED value from the scene, because that is what the validator
# reads live. Two objects: one whose exact position differs from the
# rounded one in the fourth decimal place, and one missing from the scene,
# so the error path is exercised rather than assumed.
EXACT = {"ycb_soup_can": (0.10037, -0.20074)}

def fake_build_state(coord, engine, tick=None, baskets=None, zonemap=None,
                     eligible=False):
    return {"arms": [], "tasks": [],
            "objects": [{"name": "ycb_soup_can", "xy": [0.1, -0.2]},
                        {"name": "ycb_ghost", "xy": [0.0, 0.0]}]}


def fake_grab(scene):
    return FRAME_B64


def fake_build_prompt(state, condition, image_b64=None):
    content = [{"type": "text", "text": "THE-TEXT"}]
    if image_b64 is not None:
        content = [{"type": "image_url",
                    "image_url":
                        {"url": f"data:image/png;base64,{image_b64}"}},
                   ] + content
    return [{"role": "system", "content": "SYS"},
            {"role": "user", "content": content}]


def fake_model(messages, timeout=30.0):
    return '{"task_id": -1, "arm": null}'


va.build_state = fake_build_state
va.grab_frame_b64 = fake_grab
va.build_prompt = fake_build_prompt

class FakeScene:
    """Only __getitem__ is used, and a missing name must raise so the
    allocator records the failure instead of silently falling back to the
    rounded value."""
    def __getitem__(self, name):
        x, y = EXACT[name]          # KeyError for ycb_ghost, on purpose
        return NS(data=NS(root_pos_w=[[x, y, 0.9]]))


coord = NS(cell=NS(scene=FakeScene()), agents={})

with tempfile.TemporaryDirectory() as d:
    # ONE audit dir per episode. The allocator truncates its trail on its
    # first consult, so two allocators must not share a directory: that is
    # exactly the re-run collision the truncation exists to prevent.
    lines, audit = [], None
    for cond, rnd in (("A", 3), ("V", 7)):
        adir = os.path.join(d, f"frames_{cond}")
        audit = adir if cond == "V" else audit
        alloc = va.VLMAllocator(lambda: coord, engine=None, condition=cond,
                                model_fn=fake_model, audit_dir=adir)
        alloc._consult(round_token=rnd)
        recs = [json.loads(l) for l in
                open(os.path.join(adir, "consults.jsonl"))]
        check(f"one record per consult ({cond})", len(recs) == 1,
              f"{len(recs)} records")
        lines += recs
    rec_a = next(l for l in lines if l["condition"] == "A")
    rec_v = next(l for l in lines if l["condition"] == "V")

    check("records joinable on round",
          rec_a["round"] == 3 and rec_v["round"] == 7)

    # V: image file saved byte-exact
    check("V record names an image file",
          bool(rec_v["image_file"]), str(rec_v["image_file"]))
    img_path = os.path.join(audit, rec_v["image_file"] or "")
    saved = open(img_path, "rb").read() if os.path.exists(img_path) else None
    check("saved frame is byte-exact", saved == FRAME_BYTES,
          f"{len(saved or b'')} bytes")

    # V: sanitization
    v_user = rec_v["messages"][1]["content"]
    types = [b.get("type") for b in v_user]
    check("V messages: image_file block, no base64",
          types == ["image_file", "text"]
          and "base64" not in json.dumps(rec_v),
          str(types))
    check("V text block intact",
          any(b.get("text") == "THE-TEXT" for b in v_user))

    # A: no image
    check("A record image_file is null", rec_a["image_file"] is None)
    a_user = rec_a["messages"][1]["content"]
    check("A messages text-only",
          [b.get("type") for b in a_user] == ["text"])

    # The state dict, added 2026-08-01. Every offline experiment replays
    # saved consults through the real prompt builder at a DIFFERENT rung,
    # and a rendered prompt cannot be re-rendered. Without this field the
    # probe harness has nothing to work from.
    for cond, rec in (("A", rec_a), ("V", rec_v)):
        check(f"{cond} record carries the structured state",
              rec.get("state") == fake_build_state(None, None),
              str(rec.get("state")))
        check(f"{cond} record carries UNROUNDED object positions",
              rec.get("positions_exact", {}).get("ycb_soup_can")
              == [0.10037, -0.20074],
              str(rec.get("positions_exact")))
        check(f"{cond} state still shows the ROUNDED value to the model",
              rec["state"]["objects"][0]["xy"] == [0.1, -0.2],
              str(rec["state"]["objects"][0]))
        check(f"{cond} an object missing from the scene is recorded, not skipped",
              "ycb_ghost" in rec.get("position_errors", {})
              and "ycb_ghost" not in rec.get("positions_exact", {}),
              str(rec.get("position_errors")))
        check(f"{cond} record stamps which model produced it",
              isinstance(rec.get("model"), dict)
              and ("model" in rec["model"] or "unresolved" in rec["model"]),
              str(rec.get("model")))
        check(f"{cond} record stamps the rung it was built at",
              rec.get("prompt_version") is not None
              and "enriched" in rec and "eligible" in rec,
              f"{rec.get('prompt_version')} enriched={rec.get('enriched')} "
              f"eligible={rec.get('eligible')}")

    # default off
    alloc_off = va.VLMAllocator(lambda: coord, engine=None, condition="V",
                                model_fn=fake_model)
    alloc_off._consult(round_token=1)
    check("audit off by default: no files outside the audit dirs",
          sorted(os.listdir(d)) == ["frames_A", "frames_V"],
          str(sorted(os.listdir(d))))

# ---------------------------------------------------------------------------
# The trail must be TRUNCATED per episode, not appended across runs.
# Re-running with the same --out-name used to concatenate: an episode with
# 28 consults carried 50 records, and every positional join in input_audit
# then read the wrong state for the wrong decision.
# ---------------------------------------------------------------------------
import tempfile as _tf, json as _json, os as _os
with _tf.TemporaryDirectory() as _d:
    def _run_one():
        al = va.VLMAllocator(lambda: coord, engine=None, condition="A",
                             model_fn=fake_model, audit_dir=_d)
        al.zonemap = None
        al._consult(round_token=1)
        al._consult(round_token=2)
        return al
    _run_one()
    n1 = len(open(_os.path.join(_d, "consults.jsonl")).read().strip().split("\n"))
    _run_one()                                   # same out-name, second run
    n2 = len(open(_os.path.join(_d, "consults.jsonl")).read().strip().split("\n"))
    check("a re-run REPLACES the trail instead of appending to it",
          n1 == 2 and n2 == 2, f"first run {n1} records, second run {n2}")
    seqs = [_json.loads(l)["seq"]
            for l in open(_os.path.join(_d, "consults.jsonl"))]
    check("seq numbers restart at 1 for the new episode", seqs == [1, 2],
          str(seqs))

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
