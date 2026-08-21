"""Harness: perception floor test plumbing (imports the REAL script).

Runs analysis/ex2/ex2_perception_floor.py's main() with an injected fake model
(no network, no key) over a real tiny PNG and verifies: the image is
base64-encoded into the request, both built-in probes run per frame, the
orientation probe grades PASS/CHECK against its expectation, and the
exit code reflects failures.
Run: python3 h_floor_test.py
"""
import base64
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fourarm"))

from analysis import perception_floor as pf   # REAL module

fails = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (": " + detail if detail else ""))
    if not ok:
        fails.append(label)


from PIL import Image
buf = io.BytesIO()
Image.new("RGB", (4, 4), (200, 100, 50)).save(buf, format="PNG")
PNG = buf.getvalue()

seen = []


def fake_model(messages, timeout=60.0):
    seen.append(messages)
    q = [b["text"] for b in messages[1]["content"]
         if b.get("type") == "text"][0]
    if "north Franka" in q:
        return '{"answer": "top"}'          # correct orientation answer
    return 'Sure: {"answer": "no", "object": null}'


with tempfile.TemporaryDirectory() as d:
    frame = os.path.join(d, "consult_001_round0.png")
    open(frame, "wb").write(PNG)

    sys.argv = ["ex2_perception_floor.py", frame]
    rc = pf.main(model_fn=fake_model)

    check("exit code 0 when graded probes pass", rc == 0, str(rc))
    check("both built-in probes ran", len(seen) == 2, f"{len(seen)} calls")
    url = seen[0][1]["content"][0]["image_url"]["url"]
    check("frame base64 reaches the request",
          url == "data:image/png;base64," + base64.b64encode(PNG).decode())

    # now a wrong orientation answer must grade CHECK and exit 1
    seen.clear()

    def wrong_model(messages, timeout=60.0):
        return '{"answer": "left"}'

    sys.argv = ["ex2_perception_floor.py", frame, "--probes", "orientation"]
    rc = pf.main(model_fn=wrong_model)
    check("wrong answer -> exit 1", rc == 1, str(rc))

check("extract_json tolerates prose around JSON",
      pf.extract_json('noise {"answer": "no"} noise') == {"answer": "no"})

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
