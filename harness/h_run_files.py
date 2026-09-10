"""Harness: the run-file manifest (imports the REAL run_files.py).

Checks the manifest agrees with the disk, and that its two guards actually
fire -- a manifest that cannot fail is not a guard. The two failure modes it
exists to catch both happened:

  a glob over out/ pulled a smoke run into a published figure, because smoke
  and repair files land in the same (model, condition) bucket and the last
  read wins;

  out/ex1_castb_gpt_anon_r3.jsonl sat on disk as a real 324-row run that no
  list mentioned, so Table 4.11's Anonymous row went unverified while the
  notebook still reported "13 of 13 matched".

Run: python3 h_run_files.py
"""

import os
import sys
import tempfile

for p in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fourarm"),):
    if p not in sys.path:
        sys.path.insert(0, p)

import run_files as rf                                          # noqa: E402

FAILURES = []


def check(name, ok, why=""):
    print("%s %s%s" % ("PASS" if ok else "FAIL", name, ": " + why if why else ""))
    if not ok:
        FAILURES.append(name)


check("the manifest agrees with the disk", not rf.audit(verbose=False),
      "a listed file missing, a row count or rung wrong, or a .jsonl "
      "nobody has accounted for")

# Every published cast A cell, and cast B's four, are named rather than found.
check("cast A is 8 conditions x 3 models", len(rf.CAST_A) == 24)
check("cast B carries its Anonymous cell",
      ("gpt", "anon") in rf.CAST_B,
      "this was the cell with no generator, so its absence must be loud")
check("cast B has a matched single-repeat run for every cell",
      set(rf.CAST_B) == set(rf.CAST_B_R1),
      "the independent-run column needs one file per reported cell")

# No published path may resolve into a directory the manifest excludes.
check("no published file is also excluded",
      not [p for p in list(rf.CAST_A.values()) + list(rf.CAST_B.values())
           if rf.is_excluded(p)],
      "out/attic and the repair runs must never be reachable as a result")

# The guards must fire. Point the manifest at a file that is not there, and at
# a stray .jsonl, and confirm each is reported.
_saved = dict(rf.CAST_A)
rf.CAST_A[("gemini", "full")] = "out/does_not_exist.jsonl"
check("a missing file is caught",
      any("listed but missing" in p for p in rf.audit(verbose=False)))
rf.CAST_A.clear()
rf.CAST_A.update(_saved)

stray = os.path.join(rf.ROOT, "out", "h_run_files_stray_probe.jsonl")
try:
    with open(stray, "w") as fh:
        fh.write('{"note": "written by h_run_files.py, removed below"}\n')
    check("an unaccounted file is caught",
          any("in no list" in p for p in rf.audit(verbose=False)),
          "this is the check that would have caught the cast B Anonymous run")
finally:
    if os.path.exists(stray):
        os.remove(stray)

check("the manifest is clean again afterwards", not rf.audit(verbose=False),
      "the guard tests must not leave the tree dirty")

print()
print("RESULT: %s" % ("ALL PASS" if not FAILURES
                      else "%d FAILURE(S): %s" % (len(FAILURES), FAILURES)))
sys.exit(1 if FAILURES else 0)
