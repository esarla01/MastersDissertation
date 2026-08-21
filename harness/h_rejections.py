"""Harness: rejected-proposal logging (imports the REAL VLMAllocator).

Drives the REAL _consult with the validator stubbed to reject, and
checks that every rejected proposal is recorded verbatim:
  1. Two rejections -> fallback entry carries rejected[] with both
     attempts: task_id, arm, via_pad, model_reason, rejected_because.
  2. Reject then accept -> valid_after_feedback carries rejected[] with
     exactly the first attempt; valid_first carries an empty list.
  3. An unparseable reply is marked unparseable, not silently dropped.
  4. A NOOP reached on the second attempt carries the rejected first
     attempt (schema v4): dropping it hid 9 proposals per episode.
  5. rejected[] records the basket the model named on a sorting task.
Run: python3 h_rejections.py
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


va.build_state = lambda coord, engine, tick=None, baskets=None, zonemap=None, eligible=False: {
    "arms": [], "tasks": []}
va.build_prompt = lambda state, condition, image_b64=None: [
    {"role": "system", "content": "s"},
    {"role": "user", "content": [{"type": "text", "text": "t"}]}]

coord = NS(cell=NS(scene="SCENE"), agents={}, pool=[])


def run(replies, validator):
    """One _consult with a scripted model and validator. Returns log."""
    seq = list(replies)

    def model(messages, timeout=30.0):
        return seq.pop(0)

    va.validate_decision = validator
    alloc = va.VLMAllocator(lambda: coord, engine=None, condition="A",
                            model_fn=model)
    alloc.zonemap = None
    alloc._consult(round_token=7)
    return alloc.log, alloc.stats


def REJECT(d, c, z, b=None):
    # mirrors the real validator's None handling (reply was not JSON)
    if d is None:
        return False, None, None, "reply was not valid JSON"
    return False, None, None, f"arm {d.get('arm')} is not idle"


ACCEPT = lambda d, c, z, b=None: (True, (0.1, 0.2), None, None)

P1 = '{"task_id": 3, "arm": "ur_w", "via_pad": null, "reason": "nearest"}'
P2 = '{"task_id": 4, "arm": "ur_e", "via_pad": "center", "reason": "relay"}'

# 1. two rejections -> fallback
log, stats = run([P1, P2], REJECT)
fb = log[-1]
check("fallback entry recorded", fb.get("result") == "fallback", str(fb))
rej = fb.get("rejected") or []
check("both attempts recorded", len(rej) == 2, str(len(rej)))
check("attempt 1 proposal verbatim",
      rej and rej[0]["task_id"] == 3 and rej[0]["arm"] == "ur_w"
      and rej[0]["model_reason"] == "nearest"
      and rej[0]["rejected_because"] == "arm ur_w is not idle", str(rej[:1]))
check("attempt 2 keeps via_pad",
      len(rej) > 1 and rej[1]["task_id"] == 4 and rej[1]["via_pad"] == "center",
      str(rej[1:]))
check("attempt numbers are 1,2",
      [r["attempt"] for r in rej] == [1, 2], str([r["attempt"] for r in rej]))

# 2. reject then accept
calls = {"n": 0}


def reject_then_accept(d, c, z, b=None):
    calls["n"] += 1
    if calls["n"] == 1:
        return False, None, None, "arm ur_w cannot grasp object ycb_mug"
    return True, (0.1, 0.2), None, None


log, stats = run([P1, P2], reject_then_accept)
va_entry = [e for e in log if e.get("result") == "valid_after_feedback"]
check("valid_after_feedback recorded", len(va_entry) == 1, str(log))
if va_entry:
    r = va_entry[0].get("rejected") or []
    check("exactly the first attempt kept", len(r) == 1 and r[0]["arm"] == "ur_w",
          str(r))
    check("its rejection reason kept",
          r and "cannot grasp" in r[0]["rejected_because"], str(r))

# 3. valid on the first try -> empty list
log, _ = run([P1], ACCEPT)
vf = [e for e in log if e.get("result") == "valid_first"]
check("valid_first has empty rejected list",
      vf and vf[0].get("rejected") == [], str(vf))

# 4. unparseable reply is flagged
log, _ = run(["not json at all", "still not json"], REJECT)
rej = (log[-1].get("rejected") or [])
check("unparseable attempts flagged",
      len(rej) == 2 and all(r["unparseable"] for r in rej), str(rej))

# 5. a noop on the SECOND attempt keeps its rejected first attempt
NOOP = '{"task_id": -1, "arm": null, "reason": "waiting for ur_w"}'
log, stats = run([P1, NOOP], REJECT)
noop = [e for e in log if e.get("result") == "noop"]
check("second-attempt noop logged", len(noop) == 1, str(log))
if noop:
    r = noop[0].get("rejected") or []
    check("noop carries the rejected first attempt",
          len(r) == 1 and r[0]["task_id"] == 3 and r[0]["arm"] == "ur_w",
          str(r))
    check("noop records which attempt it answered on",
          noop[0].get("attempt") == 2, str(noop[0].get("attempt")))
    check("noop keeps its reason", noop[0].get("reason") == "waiting for ur_w")

# a FIRST-attempt noop has an empty list, not a missing key
log, _ = run([NOOP], REJECT)
noop = [e for e in log if e.get("result") == "noop"][0]
check("first-attempt noop has an empty rejected list",
      noop.get("rejected") == [] and noop.get("attempt") == 1, str(noop))

# 6. the basket the model named is recorded on a rejected proposal
PB = ('{"task_id": 5, "arm": "franka_n", "via_pad": null, '
      '"basket": "basket_food", "reason": "food goes to the food basket"}')
log, _ = run([PB, PB], REJECT)
r = (log[-1].get("rejected") or [])
check("rejected proposal records the named basket",
      len(r) == 2 and all(x["basket"] == "basket_food" for x in r), str(r[:1]))

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
sys.exit(1 if fails else 0)
