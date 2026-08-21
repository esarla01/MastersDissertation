"""Mislabel: swap object names across the Franka aperture, change nothing else.

WHAT THIS IS FOR. Anonymisation asks whether removing a name costs anything,
and can only ever return a null. A null is consistent with two different
worlds: the model never used the name, or it used the name and something
else absorbed the loss. Swapping the name asks the question directionally.
Print a true grasp_m of 0.122 and call the object a power drill. If the
model follows the number, the name is inert, and that is far stronger
evidence than removal gave, because the model resisted a misleading cue
rather than merely not missing an absent one. If it follows the name, that
is identity retrieval, and it is a positive result.

The same manoeuvre is what Experiment 2 does between the image and the
declared field. This is the text-channel version, so the two experiments
share one method.

WHICH OBJECTS SWAP. Three constraints had to hold at once, and only three
pairs satisfy all three.

  1. Straddle the aperture. The false name must sit on the opposite side of
     the Franka's 0.080 m aperture from the true width, or the swap asks
     the model nothing.

  2. No delicate objects. ycb_banana and ycb_bowl are the only delicate
     objects in cast A. Renaming either produces an object whose name
     implies delicacy while its flag says otherwise, which is a second
     conflict on a different constraint and confounds the manipulation.

  3. Category-matched. Categories drive basket choice under G1, so a
     cross-category swap would manipulate the destination as well as the
     identity.

WHAT DOES NOT CHANGE. grasp_m, mass_kg, delicate, category, zone, xy and
reach_ok_arms all stay with the true object. Only the name field moves.
assert_swapped checks this on every state rather than trusting it.

THE CONTROLS ARE INSIDE THE PROMPT. Four objects are deliberately left
alone: ycb_mug and ycb_mug2 above the aperture, ycb_banana and ycb_bowl
below it. Their error rates should not move at all. If they do, the
manipulation disturbed something other than identity, and that is
measurable in the same condition rather than needing another one.

THE PREDICTION, written down before the run so this is a test rather than
an exploration:

    names inert   error rates on swapped objects unchanged from L3nw/L1nw
    names used    the clamp-called-drill draws MORE Franka assignments and
                  the drill-called-clamp draws FEWER, so errors move in the
                  direction of the false name

The primary measure is Franka share per object, split into swapped and
unswapped. The secondary is grasp errors per opportunity per object.
"""

import copy

# (true object, object whose name it borrows). Applied in both directions.
# Widths in the comment are the true grasp_m, aperture is 0.080 m.
SWAP_PAIRS = [
    ("ycb_large_clamp", "ycb_power_drill"),   # 0.122 over  <-> 0.050 under, tools
    ("ycb_mustard", "ycb_soup_can"),          # 0.096 over  <-> 0.068 under, food
    ("ycb_meat_can", "ycb_gelatin_box"),      # 0.084 over  <-> 0.073 under, food
]

# Left alone on purpose. Not an oversight: see the module docstring.
CONTROLS = ("ycb_mug", "ycb_mug2", "ycb_banana", "ycb_bowl")

# Fields that must survive the rename untouched. If any of these moved with
# the name, the condition would be manipulating more than identity.
INVARIANT = ("grasp_m", "mass_kg", "delicate", "category", "zone",
             "reach_ok_arms", "xy")

APERTURE_FRANKA = 0.080


def build_map():
    """name -> name. Symmetric, so applying it twice is the identity."""
    table = {}
    for a, b in SWAP_PAIRS:
        table[a] = b
        table[b] = a
    return table


def _rename(node, table):
    """Rewrite object-name strings only. Never touches any other field."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in ("name", "object", "obj") and isinstance(v, str) and v in table:
                out[k] = table[v]
            else:
                out[k] = _rename(v, table)
        return out
    if isinstance(node, list):
        return [_rename(v, table) for v in node]
    return node


def mislabel_state(state, table=None):
    """(mislabelled copy of the state, table).

    The input is never mutated. A probe set is frozen, and a run that edited
    it would change the thing every other run is compared against.
    """
    table = table or build_map()
    return _rename(copy.deepcopy(state), table), table


# ---------------------------------------------------------------------------
# Verification. The claim this condition rests on is that ONLY the name
# changed. That claim is checked, not asserted.
# ---------------------------------------------------------------------------


def assert_swapped(before, after, table=None):
    """Raise unless the edit renamed exactly the six paired objects.

    Checks four things:
      * every swapped object carries its partner's name
      * every control object kept its own name
      * no object's physical fields moved with the name
      * the object multiset is unchanged, so nothing was added or dropped
    """
    table = table or build_map()
    src = {o["name"]: o for o in before.get("objects", [])}
    dst = {o["name"]: o for o in after.get("objects", [])}

    if len(src) != len(dst):
        raise AssertionError(
            "mislabel changed the object count, %d before and %d after"
            % (len(src), len(dst)))

    for control in CONTROLS:
        if control in src and control not in dst:
            raise AssertionError(
                "control object %s was renamed; controls must not move" % control)

    renamed = 0
    for true_name, obj in src.items():
        expected = table.get(true_name, true_name)
        if expected not in dst:
            raise AssertionError(
                "%s should appear as %s after the swap and does not"
                % (true_name, expected))
        if expected != true_name:
            renamed += 1
        moved = dst[expected]
        for field in INVARIANT:
            if field in obj and obj[field] != moved.get(field):
                raise AssertionError(
                    "%s carries %s=%r but %s carries %r: a physical field "
                    "moved with the name, so this condition is manipulating "
                    "more than identity"
                    % (true_name, field, obj[field], expected,
                       moved.get(field)))

    present = sum(1 for a, b in SWAP_PAIRS
                  for n in (a, b) if n in src)
    if renamed != present:
        raise AssertionError(
            "expected %d renames for the paired objects present in this "
            "state, saw %d" % (present, renamed))
    return renamed


def straddles_aperture(state, table=None):
    """Every swap must cross the Franka aperture, or it asks nothing.

    Returns the list of (true name, false name, true width, false width)
    for objects present in this state, and raises if any pair fails to
    straddle.
    """
    table = table or build_map()
    width = {o["name"]: o.get("grasp_m") for o in state.get("objects", [])}
    out = []
    for a, b in SWAP_PAIRS:
        if a not in width or b not in width:
            continue
        wa, wb = width[a], width[b]
        if wa is None or wb is None:
            continue
        if (wa > APERTURE_FRANKA) == (wb > APERTURE_FRANKA):
            raise AssertionError(
                "%s (%.3f) and %s (%.3f) sit on the same side of the "
                "%.3f m aperture, so swapping their names asks the model "
                "nothing" % (a, wa, b, wb, APERTURE_FRANKA))
        out.append((a, b, wa, wb))
        out.append((b, a, wb, wa))
    return out
