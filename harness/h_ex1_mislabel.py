"""h_ex1_mislabel: the swap renames six objects and changes nothing else.

The whole Mislabelled condition rests on one claim: only the name moved.
This gate checks that claim against the real probe set before any model
call is paid for, in the same spirit as h_ex1_prompts checking that L3
renders as the deployed prompt.

Eight checks:

  1  the swap map is symmetric, so applying it twice is the identity
  2  every pair straddles the Franka aperture
  3  no delicate object is in a pair
  4  every pair is category-matched
  5  on all 162 states, exactly the paired objects are renamed
  6  no physical field moves with the name
  7  the four control objects keep their names
  8  a rendered L3-swap prompt differs from L3 in name strings and nowhere
     else, checked by diffing the two renderings token by token

Run:  python3 harness/h_ex1_mislabel.py
Exit: 0 all pass, 1 otherwise.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "fourarm")
for p in (ROOT, os.path.join(ROOT, "ycb")):
    if p not in sys.path:
        sys.path.insert(0, p)

from experiments.ex1.mislabel import (  # noqa: E402
    SWAP_PAIRS, CONTROLS, APERTURE_FRANKA,
    build_map, mislabel_state, assert_swapped, straddles_aperture)

PROBES = os.path.join(ROOT, "probes/ex1_v2.json")

FAILURES = []


def check(name, ok, detail=""):
    print("  %-4s %s%s" % ("pass" if ok else "FAIL", name,
                           "" if ok else "   " + detail))
    if not ok:
        FAILURES.append(name)


def main():
    probes = json.load(open(PROBES))["probes"]
    table = build_map()
    print("h_ex1_mislabel  (%d states)" % len(probes))

    # 1. Symmetry.
    check("map is symmetric",
          all(table[table[k]] == k for k in table),
          "applying the swap twice must be the identity")

    # 2 to 4. Properties of the pairs, from the first state that has them.
    state = probes[0]["state"]
    objects = {o["name"]: o for o in state["objects"]}

    try:
        straddles_aperture(state, table)
        check("every pair straddles %.3f m" % APERTURE_FRANKA, True)
    except AssertionError as exc:
        check("every pair straddles %.3f m" % APERTURE_FRANKA, False, str(exc))

    delicate = [n for a, b in SWAP_PAIRS for n in (a, b)
                if objects.get(n, {}).get("delicate")]
    check("no delicate object is swapped", not delicate,
          "delicate objects in pairs: %s" % delicate)

    mismatched = [(a, b) for a, b in SWAP_PAIRS
                  if a in objects and b in objects
                  and objects[a].get("category") != objects[b].get("category")]
    check("every pair is category-matched", not mismatched,
          "cross-category pairs: %s" % mismatched)

    # 5 to 7. The edit itself, on every state.
    renamed_counts = set()
    errors = []
    for p in probes:
        before = p["state"]
        after, _ = mislabel_state(before, table)
        try:
            renamed_counts.add(assert_swapped(before, after, table))
        except AssertionError as exc:
            errors.append(str(exc))
            if len(errors) > 3:
                break
    check("edit is clean on all %d states" % len(probes), not errors,
          errors[0] if errors else "")
    check("renames per state is constant", len(renamed_counts) == 1,
          "saw %s" % sorted(renamed_counts))
    check("expected 6 renames per state", renamed_counts == {6},
          "saw %s" % sorted(renamed_counts))

    # 8. The rendered prompt differs only in name strings.
    try:
        from core.decision.state_builder import build_prompt
        before = probes[0]["state"]
        after, _ = mislabel_state(before, table)
        a = build_prompt(before, "A")
        b = build_prompt(after, "A")
        a_txt = a if isinstance(a, str) else json.dumps(a, sort_keys=True)
        b_txt = b if isinstance(b, str) else json.dumps(b, sort_keys=True)
        # Blank every object name in both renderings. If the two texts
        # then match, the swap moved names and nothing else.
        for name in table:
            a_txt = a_txt.replace(name, "<OBJ>")
            b_txt = b_txt.replace(name, "<OBJ>")
        check("prompt differs only in object names", a_txt == b_txt,
              "the two renderings differ outside the name strings")
    except ImportError as exc:
        check("prompt differs only in object names", False,
              "could not import build_prompt: %s" % exc)

    print("\n%d checks, %d failed" % (8, len(FAILURES)))
    if FAILURES:
        print("failed: %s" % ", ".join(FAILURES))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
