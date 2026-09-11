"""Harness: the frozen probe sets (imports the REAL probe_audit).

The probe sets are the input to both experiments and cannot be re-harvested
without Isaac Lab, so the guarantee they carry is that they still hold what
they held when they were frozen. This gate checks that guarantee and checks
that the guard detecting a break actually works.

Run: python3 h_probe_sets.py
"""

import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "fourarm"))

from harvest import probe_audit as pa                           # noqa: E402
from harvest.probe_store import content_hash                    # noqa: E402

FAILURES = []


def check(name, ok, why=""):
    print("%s %s%s" % ("PASS" if ok else "FAIL", name, ": " + why if why else ""))
    if not ok:
        FAILURES.append(name)


check("every probe set verifies against its hash and Appendix D",
      not pa.audit(verbose=False),
      "content hash, the 278 -> 185 -> 162 derivation, and the six source counts")

# A tampered state must move the hash. If it does not, the sets are not
# content-addressed in any useful sense and the run files cannot be tied to
# the states they were answered on.
_d = pa.load("ex1_v2.json")
_before = content_hash(_d["probes"])
_tampered = copy.deepcopy(_d["probes"])
for _p in _tampered:
    _objs = _p.get("state", {}).get("objects")
    if isinstance(_objs, list) and _objs and "grasp_m" in _objs[0]:
        _objs[0]["grasp_m"] = round(_objs[0]["grasp_m"] + 0.05, 3)
        break
else:
    _tampered[0]["provenance"]["seq"] = -999      # fallback: move an id field
check("editing one state moves the content hash",
      content_hash(_tampered) != _before,
      "otherwise a state could be changed without invalidating the runs")

# seed_v3 is excluded from the reported set because it predates the mustard
# width correction. Its absence is the whole reason ex1_v2 exists.
_v2 = {pa.identity(p) for p in pa.load("ex1_v2.json")["probes"]}
_seed = {pa.identity(p) for p in pa.load("seed_v3.json")["probes"]}
check("no seed_v3 state reaches the reported set", not (_v2 & _seed),
      "they carry the uncorrected 0.058 m mustard width")

check("the reported set is exactly 162 states", len(_v2) <= 162 and
      len(pa.load("ex1_v2.json")["probes"]) == 162)

print()
print("RESULT: %s" % ("ALL PASS" if not FAILURES
                      else "%d FAILURE(S): %s" % (len(FAILURES), FAILURES)))
sys.exit(1 if FAILURES else 0)
