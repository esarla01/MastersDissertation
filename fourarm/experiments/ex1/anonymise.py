"""EX1 L1-nowidth: object identity removed from the state.

The memorisation probe. At L3-nowidth the declared width is gone and the
model must supply one; the only routes left are the object's NAME and the
image. This module closes the name route, so that with the image off both
are closed and what remains is whatever else was doing the work.

THE SCHEME

    ycb_soup_can (food)        ->  Object5   (category CategoryA)
    basket_food                ->  Basket1

Identity is removed, grouping is not: the category FIELD still says which
objects belong together, exactly as it does at L3. "Object5" carries no
width prior, no mass prior and no fragility prior the way "ycb_banana"
does.

WHY THE NAME CARRIES NO CATEGORY PREFIX

An earlier version wrote Type1_Object3, folding the category into the name
so that grouping survived even if the category field were ignored. That
was insurance against a sorting task that does not exist: every task in
the EX1 set already carries its own dest_xy, so the model never chooses a
basket and never sorts. The prefix bought nothing and cost something,
because it made the anonymised NAME carry strictly more structure than a
plain label, which is not what "anonymised" should mean. The name is now a
label and nothing else, and the category field does the grouping work in
both the named and the anonymised condition. That keeps the L3-nowidth to
L1-nowidth step a change of identity only.

Categories are lettered by sorted real category name, so the map is the
same in every state: food, kitchenware, tools become CategoryA, CategoryB,
CategoryC. Baskets are numbered to match, so Basket1 is the basket for
CategoryA. Objects are numbered densely WITHIN a state, sorted by real
name, with no gaps.

Dense per-state numbering means the same real object can carry different
aliases in different states. That is deliberate. The model has no memory
between calls so it cannot benefit from a stable alias, a global index
would advertise how many objects exist outside this state, and a stable
alias invites analysis code to key on it, which would quietly reintroduce
the identity the rung exists to remove.

WHAT IS AND IS NOT TOUCHED

Anonymised: object names wherever they appear in the state, object
categories, and basket names including the keys of the "baskets" block.

NOT anonymised: arm names. franka and ur10 carry aperture and payload
priors from pretraining just as ycb_mug carries a width prior, so arm
identity remains a residual memorisation channel at L1-nowidth. This is a
declared scope limit, not an oversight, and it belongs in the write-up.

Also not touched: the SYSTEM PROMPT. It was scanned against every object,
category and basket name in the frozen EX1 set and contains none of them.
G1 says "the basket named for its category", which stays true under the
new scheme, and the answer schema says "basket name" generically. The
scan is repeated at run time by assert_clean rather than trusted, because
a later edit to state_builder could introduce a name.

THE TRANSFORM IS A WALK, NOT A FIELD LIST

Names appear at /objects[]/name, /objects[]/category, /tasks[]/object,
/arms[]/holding and as the keys of /baskets. A hardcoded list of those
five would be shorter and would silently miss the sixth. recent_events
carries disruption parameters and is empty in this probe set but is not
empty in general, so the walk visits everything and replaces on exact
string equality. assert_clean is the backstop: it reads the RENDERED
prompt, which is the only artefact that actually matters.

WHY THE VALIDATOR NEVER SEES AN ALIAS

harvest/probe_replay.py rebuilds the coordinator with from_record(probe),
which reads the ORIGINAL probe, so the validator, the router and the
scorer all work in real names throughout. Only the model's reply comes
back in aliases, and of its fields only "basket" is affected: task_id is
an integer, arm is unchanged by design, and regions are zone names.
deanonymise_decision handles that one field and nothing else.
"""

import copy
import re

# Letters for categories and digits for objects, so the two can never be
# mistaken for one another in a reply or in a grep of the logs.
CATEGORY_FMT = "Category{L}"
OBJECT_FMT = "Object{j}"
BASKET_FMT = "Basket{i}"
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _category_of_basket():
    """basket name -> category, from the cell's own table.

    Inverted from CATEGORY_BASKET rather than derived by stripping the
    "basket_" prefix. The prefix is a naming convention and a convention
    can change; the table is what the scene actually uses.
    """
    from ycb_scene import CATEGORY_BASKET
    return {b: c for c, b in CATEGORY_BASKET.items()}


def build_map(state):
    """Alias map for one state.

    Returns a dict with five entries:

        categories  real category   -> CategoryA, CategoryB, ...
        objects     real object     -> Object1, Object2, ...
        baskets     real basket     -> Basket1, Basket2, ...
        objects_inv, baskets_inv    the reverse of the two above

    Raises rather than guessing on anything it cannot place. An object
    with no category or a basket outside the cell's table would otherwise
    pass through under its real name and defeat the whole rung.
    """
    objects = state.get("objects") or []
    cats = set()
    for ob in objects:
        c = ob.get("category")
        if not c:
            raise ValueError(
                f"object {ob.get('name')!r} has no category, so it cannot be "
                f"grouped. Anonymising it under an ungrouped alias would "
                f"change the sorting task rather than only the identity.")
        cats.add(c)

    basket_cat = _category_of_basket()
    baskets = list((state.get("baskets") or {}))
    for b in baskets:
        if b not in basket_cat:
            raise ValueError(
                f"basket {b!r} is not in CATEGORY_BASKET, so its category is "
                f"unknown and it cannot be renamed consistently with the "
                f"objects that belong in it.")
        cats.add(basket_cat[b])

    ordered = sorted(cats)
    if len(ordered) > len(_LETTERS):
        raise ValueError(
            f"{len(ordered)} categories but only {len(_LETTERS)} letters "
            f"available. Extend _LETTERS rather than reusing one, because a "
            f"repeated alias would silently merge two groups.")
    # Sorted, so the category map is identical in every state.
    cat_alias = {c: CATEGORY_FMT.format(L=_LETTERS[i])
                 for i, c in enumerate(ordered)}
    # Baskets numbered to match: Basket1 serves CategoryA.
    cat_index = {c: i + 1 for i, c in enumerate(ordered)}

    # Dense within the state, sorted by real name. The NUMBER carries no
    # grouping information; the category field does that.
    obj_alias = {}
    for j, ob in enumerate(sorted(objects, key=lambda o: o["name"]), start=1):
        obj_alias[ob["name"]] = OBJECT_FMT.format(j=j)

    # A task can name an object no longer in the objects list (delivered,
    # despawned). It still needs an alias or the task would name a real
    # object in an anonymised prompt. Numbering continues from the objects
    # present, so no alias is reused.
    nxt = len(obj_alias)
    for t in state.get("tasks") or []:
        o = t.get("object")
        if o and o not in obj_alias:
            nxt += 1
            obj_alias[o] = OBJECT_FMT.format(j=nxt)

    bask_alias = {b: BASKET_FMT.format(i=cat_index[basket_cat[b]])
                  for b in baskets}

    return {
        "categories": cat_alias,
        "objects": obj_alias,
        "baskets": bask_alias,
        "objects_inv": {v: k for k, v in obj_alias.items()},
        "baskets_inv": {v: k for k, v in bask_alias.items()},
    }


def _replacements(mapping):
    """One flat real -> alias table for the walk."""
    out = {}
    out.update(mapping["objects"])
    out.update(mapping["categories"])
    out.update(mapping["baskets"])
    return out


def _walk(node, table):
    """Deep copy with every string EXACTLY equal to a key replaced.

    Exact equality, never substring. A substring pass would corrupt free
    text and would turn "ycb_mug2" into the alias for "ycb_mug" followed
    by a stray 2. Dict keys are substituted too, which is what renames the
    "baskets" block.
    """
    if isinstance(node, dict):
        return {table.get(k, k) if isinstance(k, str) else k: _walk(v, table)
                for k, v in node.items()}
    if isinstance(node, list):
        return [_walk(v, table) for v in node]
    if isinstance(node, str):
        return table.get(node, node)
    return node


def anonymise_state(state, mapping=None):
    """(anonymised copy of the state, mapping).

    The input is never mutated. A probe set is frozen and a run that
    edited it would change the thing every other run is compared against.
    """
    mapping = mapping or build_map(state)
    return _walk(copy.deepcopy(state), _replacements(mapping)), mapping


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def real_terms(mapping):
    """Every real term that must not survive into a rendered prompt."""
    return (sorted(mapping["objects"]) + sorted(mapping["baskets"])
            + sorted(mapping["categories"]))


def find_leaks(text, mapping):
    """Real terms still present in `text`. Empty list means clean.

    Object and basket names are matched as substrings because they are
    long and distinctive. Category names are single common words, so they
    are matched on word boundaries to avoid flagging an unrelated
    occurrence inside ordinary prose.
    """
    leaks = []
    for w in sorted(mapping["objects"]) + sorted(mapping["baskets"]):
        if w in text:
            leaks.append(w)
    for w in sorted(mapping["categories"]):
        if re.search(r"\b" + re.escape(w) + r"\b", text):
            leaks.append(w)
    return leaks


def assert_clean(messages, mapping):
    """Raise if any real name survives anywhere in the rendered prompt.

    This is the backstop for the whole rung, and it reads the artefact
    that actually reaches the model rather than the state it was built
    from. If the base prompt later gains an object name, or the state
    grows a field the walk did not expect, this is what stops the run
    instead of a reviewer.
    """
    text = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            text.append(c)
        elif isinstance(c, list):
            for b in c:
                if b.get("type") == "text":
                    text.append(b.get("text", ""))
    leaks = find_leaks("\n".join(text), mapping)
    if leaks:
        raise ValueError(
            f"L1 prompt still contains real object identity: {leaks}. The "
            f"rung measures what the model does WITHOUT the name, so a "
            f"single surviving name invalidates the trial.")
    return True


# ---------------------------------------------------------------------------
# Reply
# ---------------------------------------------------------------------------

def deanonymise_decision(decision, mapping):
    """(decision with a real basket name, info).

    info carries what the model actually said, so an unmappable basket is
    visible in the row rather than hidden:

        basket_alias   the value the model returned
        basket_mapped  True if it was a valid alias

    An unmappable value is passed through UNCHANGED so the validator
    rejects it as BASKET_MISSING. Repairing it here would turn a model
    error into a silent pass, and BASKET_MISSING counts at L1 are already
    not comparable to L3 because the naming scheme differs.
    """
    if decision is None:
        return None, {"basket_alias": None, "basket_mapped": None}
    out = dict(decision)
    alias = out.get("basket")
    if alias is None:
        return out, {"basket_alias": None, "basket_mapped": None}
    real = mapping["baskets_inv"].get(alias)
    info = {"basket_alias": alias, "basket_mapped": real is not None}
    if real is not None:
        out["basket"] = real
    return out, info
