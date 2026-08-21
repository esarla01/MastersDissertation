"""Perception floor test: can the model READ the frame at all?

Feeds saved consult frames (from the VLM audit trail) to the model with
direct perception questions. Zero simulation cost: this runs on PNGs.
This is the designed cheap gate for E6: if the model cannot answer
"is anything on the centre pad?" from a frame, E6's anomaly test cannot
work, and we find that out here for pennies instead of in episodes.

Needs DASHSCOPE_API_KEY (same endpoint/model as the allocator; the call
path is IMPORTED from the real vlm_allocator, not reimplemented).

Usage:
  python3 analysis/ex2/ex2_perception_floor.py out/vlm2_*_frames/consult_001*.png
  python3 analysis/ex2/ex2_perception_floor.py FRAMES... --question "How many \
      white tiles are visible?" --key custom
  python3 analysis/ex2/ex2_perception_floor.py FRAMES... --probes orientation

Built-in probes:
  orientation  "Which arm base is nearest the TOP edge?" expect franka_n
               (proves the north-up rotation end to end: the north arm
               must be at the top of what the model sees)
  centre_pad   "Is any object resting on the white tile at the centre?"
               expect unoccupied in a normal early-episode frame; run it
               on an anomaly frame later and the answer must flip
"""

import argparse
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.decision.vlm_allocator import openai_chat   # REAL call path

PROBES = {
    "orientation": {
        "question": ("This is an overhead view of a four-arm robot cell. "
                     "Robot arm bases are the coloured circles at the four "
                     "edges of the table. Which EDGE OF THE IMAGE (top, "
                     "bottom, left, right) is the north Franka arm base "
                     "nearest to? Answer ONLY JSON: "
                     '{"answer": "top|bottom|left|right"}'),
        "expect": "top",
    },
    "centre_pad": {
        "question": ("Look at the white square tile at the CENTRE of the "
                     "table. Is any object currently resting on that tile? "
                     "Answer ONLY JSON: "
                     '{"answer": "yes|no", "object": "<name or null>"}'),
        "expect": None,     # expectation depends on the frame; report only
    },
}


def extract_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def ask(frame_path, question, model_fn=openai_chat, timeout=60.0):
    with open(frame_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    messages = [
        {"role": "system",
         "content": "You answer questions about images, ONLY in the JSON "
                    "format the question specifies. No prose."},
        {"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/png;base64,{b64}"}},
            {"type": "text", "text": question},
        ]},
    ]
    return extract_json(model_fn(messages, timeout=timeout))


def main(model_fn=openai_chat):
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", nargs="+", help="PNG frame paths")
    ap.add_argument("--probes", nargs="+", default=list(PROBES),
                    choices=list(PROBES), help="built-in probes to run")
    ap.add_argument("--question", default=None,
                    help="additional free-form question (reported, "
                         "not graded)")
    a = ap.parse_args()

    fails = 0
    for frame in a.frames:
        print(f"\n== {frame}")
        for name in a.probes:
            probe = PROBES[name]
            d = ask(frame, probe["question"], model_fn=model_fn)
            ans = (d or {}).get("answer")
            if probe["expect"] is not None:
                ok = (str(ans).lower() == probe["expect"])
                fails += 0 if ok else 1
                print(f"  [{'PASS ' if ok else 'CHECK'}] {name}: "
                      f"answer={ans!r} expected={probe['expect']!r} "
                      f"raw={d}")
            else:
                print(f"  [INFO ] {name}: {d}")
        if a.question:
            print(f"  [INFO ] custom: {ask(frame, a.question, model_fn=model_fn)}")

    print(f"\nRESULT: {'ALL PASS' if fails == 0 else str(fails) + ' graded probe(s) off-expectation'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
