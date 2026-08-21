"""audit_ex1: check the EX1 dataset and pipeline before spending on a run.

Every check here answers "what would this catch", and the ones worth the
most are the rung invariants, because a fault there does not crash. It
produces numbers that look fine and mean nothing.

WHAT IS CHECKED

Data
  every task names an object that exists
  every arm named in an object's carried_by exists, and the arm agrees
  reach_ok_arms on objects, baskets and pads agrees with the zonemap
  arm limits in the state agree with cell_config
  every task carries a destination

  The last one matters more than it looks. If a task had no destination
  the model would name a basket, the basket would fix the delivery point,
  and routing would then depend on a SEMANTIC sorting judgement. At an
  anonymised rung sorting collapses to index matching, so it gets easier,
  so spurious no_route rejections get rarer, so L1 would look better than
  L3 for a reason having nothing to do with capability. All 1021 tasks
  carry a destination, which is why that confound does not exist, and this
  check is what keeps it that way if the set is ever rebuilt.

Rungs
  L2 renders the SAME state as L3: it is a prompt-level rung only
  L4 differs from L3 only by eligible_arms and the reachability marker
  L3-nowidth differs from L3 only by grasp_m
  L1-nowidth differs from L3-nowidth only by names, categories and basket
    keys
  the alias map is a bijection and preserves grouping

  These are the spine's design claim expressed as assertions. "Each step
  removes exactly one kind of information" is either true of the states or
  the gaps measure something else.

Ground truth
  the validator returns an IDENTICAL verdict at every rung for the same
  decision

  This is the check that the ladder is one experiment rather than five.
  The coordinator is rebuilt from the ORIGINAL probe, so legality should
  not move when the prompt changes. If it ever did, the rendered state
  would have leaked into the scoring path and every gap would be a
  comparison between different questions.

Text
  every object's grasp_m appears in the L3 prompt and NONE appear in the
  L3-nowidth prompt

  The state-level diff proves the field was removed from the dict. This
  proves it was removed from what the model actually reads.

Reply
  a decision written in aliases validates identically to the same decision
  written in real names, over every legal pair in the set

  Previously tested only with a stub that always picked the first basket,
  which is the weakest possible case.

WHAT IS NOT CHECKED

Whether the prompts READ correctly. Use --dump and read them. No script
replaces looking at the thing you are about to send a model 810 times.

Usage:

    python3 analysis/ex1/ex1_audit_states.py --probes probes/ex1_v2.json
    python3 analysis/ex1/ex1_audit_states.py --probes probes/ex1_v2.json --limit 20
    python3 analysis/ex1/ex1_audit_states.py --probes probes/ex1_v2.json \\
        --dump 1 --dump-dir out/ex1_prompts
"""

import argparse
import copy
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.cell import cell_config as C                          # noqa: E402
from core.decision.vlm_allocator import validate_decision       # noqa: E402
from analysis.frozen_coord import from_record                   # noqa: E402
from analysis.probe_store import load, legal_options            # noqa: E402
from analysis import probe_replay as pr                         # noqa: E402
from experiments.ex1 import anonymise as A                      # noqa: E402

RUNGS = ("L4", "L3", "L3-nowidth", "L2", "L1-nowidth")
SPINE = ("L3", "L3-nowidth", "L1-nowidth")

fails = []
notes = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name
          + ("" if ok or not detail else "\n          " + str(detail)[:400]))
    if not ok:
        fails.append(name)


def diff_paths(a, b, path=""):
    """Every path at which two nested structures differ."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            if k not in a:
                out.append(f"{path}/+{k}")
            elif k not in b:
                out.append(f"{path}/-{k}")
            else:
                out += diff_paths(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}[len {len(a)}!={len(b)}]")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += diff_paths(x, y, f"{path}[]")
    elif a != b:
        out.append(path)
    return sorted(set(out))


# ---------------------------------------------------------------------------

def audit_data(probes, zm):
    print("\n1. data integrity")
    bad_obj = bad_arm = bad_reach = bad_limits = no_dest = 0
    ex = {}
    for p in probes:
        st = p["state"]
        names = {o["name"] for o in st["objects"]}
        arms = {a["name"] for a in st["arms"]}
        holding = {a["name"]: a.get("holding") for a in st["arms"]}
        for t in st["tasks"]:
            if t.get("object") and t["object"] not in names:
                bad_obj += 1
                ex.setdefault("obj", t["object"])
            if t.get("dest_xy") is None:
                no_dest += 1
        for o in st["objects"]:
            cb = o.get("carried_by")
            if cb is not None:
                if cb not in arms:
                    bad_arm += 1
                    ex.setdefault("arm", (o["name"], cb))
                elif holding.get(cb) != o["name"]:
                    bad_arm += 1
                    ex.setdefault("hold", (cb, holding.get(cb), o["name"]))
            want = [a for a in arms if zm.reachable(a, *o["xy"])]
            if o.get("reach_ok_arms") is not None and \
                    sorted(o["reach_ok_arms"]) != sorted(want):
                bad_reach += 1
                ex.setdefault("reach", (o["name"], o["reach_ok_arms"], want))
        for blk in (st.get("baskets") or {}, st.get("exchange_pads") or {}):
            for nm, b in blk.items():
                want = [a for a in arms if zm.reachable(a, *b["xy"])]
                if b.get("reach_ok_arms") is not None and \
                        sorted(b["reach_ok_arms"]) != sorted(want):
                    bad_reach += 1
                    ex.setdefault("breach", (nm, b["reach_ok_arms"], want))
        for a in st["arms"]:
            spec = C.ARM_TYPES.get(a["type"], {})
            for f in ("max_grasp_m", "payload_kg", "delicate_ok"):
                if f in spec and a.get(f) != spec[f]:
                    bad_limits += 1
                    ex.setdefault("limit", (a["name"], f, a.get(f), spec[f]))

    check("every task names an object present in the state",
          bad_obj == 0, ex.get("obj"))
    check("carried_by and the arm's holding field agree",
          bad_arm == 0, ex.get("arm") or ex.get("hold"))
    check("reach_ok_arms agrees with the zonemap everywhere",
          bad_reach == 0, ex.get("reach") or ex.get("breach"))
    check("arm limits in the state agree with cell_config",
          bad_limits == 0, ex.get("limit"))
    check("every task carries a destination",
          no_dest == 0,
          f"{no_dest} dest-less tasks. The model would name a basket, "
          f"routing would depend on a semantic sorting judgement, and "
          f"sorting is EASIER at an anonymised rung, so L1 would gain an "
          f"advantage unrelated to capability.")


def audit_rungs(probes):
    print("\n2. rung construction")
    states = {}
    for p in probes:
        states[p["provenance"]["seq"]] = {
            r: pr.state_at_rung(p, r, return_map=True) for r in RUNGS}

    l2 = sum(1 for s in states.values()
             if diff_paths(s["L3"][0], s["L2"][0]))
    check("L2 renders the same state as L3 (prompt-level rung only)",
          l2 == 0, f"{l2} states differ")

    bad, ex = 0, None
    for s in states.values():
        d = diff_paths(s["L3"][0], s["L4"][0])
        if any(not (x.endswith("eligible_arms") or x.endswith("reachability")
                    or "+eligible_arms" in x) for x in d):
            bad += 1
            ex = ex or d
    check("L4 differs from L3 only by eligible_arms and reachability",
          bad == 0, ex)

    bad, ex = 0, None
    for s in states.values():
        d = diff_paths(s["L3"][0], s["L3-nowidth"][0])
        if any(not x.endswith("grasp_m") for x in d):
            bad += 1
            ex = ex or [x for x in d if not x.endswith("grasp_m")]
    check("L3-nowidth differs from L3 ONLY by grasp_m",
          bad == 0, ex)

    ok_fields = ("name", "category", "object", "holding")
    bad, ex = 0, None
    for s in states.values():
        d = diff_paths(s["L3-nowidth"][0], s["L1-nowidth"][0])
        odd = [x for x in d
               if not (x.rsplit("/", 1)[-1] in ok_fields
                       or "/baskets/" in x)]
        if odd:
            bad += 1
            ex = ex or odd
    check("L1-nowidth differs from L3-nowidth ONLY by names and baskets",
          bad == 0, ex)

    bad_bij = bad_grp = 0
    ex = {}
    for p in probes:
        _st, m = states[p["provenance"]["seq"]]["L1-nowidth"]
        if len(set(m["objects"].values())) != len(m["objects"]):
            bad_bij += 1
            ex.setdefault("bij", m["objects"])
        # Grouping lives in the CATEGORY field, not in the object name.
        # An object name that encoded its category would carry more
        # structure than a plain label, which is not what anonymised
        # should mean, and every task already has its destination so
        # nothing needs to sort.
        if any("Category" in a for a in m["objects"].values()):
            bad_grp += 1
            ex.setdefault("prefix", m["objects"])
        cat = {o["name"]: o["category"] for o in p["state"]["objects"]}
        seen = {}
        for real, c in cat.items():
            a = m["categories"][c]
            if seen.setdefault(a, c) != c:
                bad_grp += 1
                ex.setdefault("share", (a, c, seen[a]))
        if len(set(m["categories"].values())) != len(m["categories"]):
            bad_grp += 1
            ex.setdefault("catbij", m["categories"])
        # Baskets must line up with the categories they serve, or the
        # anonymised state would describe a cell that cannot be sorted
        # even in principle.
        if len(set(m["baskets"].values())) != len(m["baskets"]):
            bad_grp += 1
            ex.setdefault("baskbij", m["baskets"])
    check("every alias is unique within its state", bad_bij == 0,
          ex.get("bij"))
    check("grouping is carried by the category field, not the object name",
          bad_grp == 0,
          ex.get("prefix") or ex.get("share") or ex.get("catbij")
          or ex.get("baskbij"))
    return states


def audit_ground_truth(probes, states, zm, baskets):
    print("\n3. ground truth is invariant across rungs")
    moved, ex = 0, None
    for p in probes:
        legal, _pt = legal_options(p)[0], None
        pair = next(iter(sorted({(t, a) for t, a, _k in
                                 legal_options(p)[0]})), None)
        if pair is None:
            continue
        dec = {"task_id": pair[0], "arm": pair[1], "basket": None}
        seen = set()
        for r in RUNGS:
            coord = from_record(p)
            ok, _t, _s, why = validate_decision(dict(dec), coord, zm, baskets)
            seen.add((ok, why))
        if len(seen) != 1:
            moved += 1
            ex = ex or (p["provenance"]["seq"], seen)
    check("the validator returns one verdict per decision at every rung",
          moved == 0, ex)


def audit_text(probes, states):
    print("\n4. the prompt the model reads")
    miss = leak = 0
    ex = {}
    for p in probes:
        seq = p["provenance"]["seq"]
        t3 = "".join(m["content"] if isinstance(m["content"], str)
                     else m["content"][0]["text"]
                     for m in pr.render(p, "L3", "A")[0])
        tn = "".join(m["content"] if isinstance(m["content"], str)
                     else m["content"][0]["text"]
                     for m in pr.render(p, "L3-nowidth", "A")[0])
        widths = {o["grasp_m"] for o in p["state"]["objects"]
                  if o.get("grasp_m") is not None}
        for w in widths:
            if f"{w}" not in t3:
                miss += 1
                ex.setdefault("miss", (seq, w))
            if f'"grasp_m": {w}' in tn:
                leak += 1
                ex.setdefault("leak", (seq, w))
    check("every declared width appears in the L3 prompt",
          miss == 0, ex.get("miss"))
    check("no declared width survives into the L3-nowidth prompt",
          leak == 0, ex.get("leak"))


def audit_reply(probes, states, zm, baskets):
    print("\n5. the alias round trip, over every legal pair")
    n = bad = 0
    ex = None
    for p in probes:
        _st, m = states[p["provenance"]["seq"]]["L1-nowidth"]
        for tid, arm, _k in legal_options(p)[0]:
            for real, alias in list(m["baskets"].items()):
                dec_alias = {"task_id": tid, "arm": arm, "basket": alias}
                back, info = A.deanonymise_decision(dec_alias, m)
                dec_real = {"task_id": tid, "arm": arm, "basket": real}
                a = validate_decision(dict(back), from_record(p), zm, baskets)
                b = validate_decision(dict(dec_real), from_record(p), zm,
                                      baskets)
                n += 1
                if (a[0], a[3]) != (b[0], b[3]) or not info["basket_mapped"]:
                    bad += 1
                    ex = ex or (tid, arm, alias, a[3], b[3])
    check(f"an aliased decision validates as its real twin ({n} compared)",
          bad == 0, ex)


def dump(probes, seq, out_dir):
    p = next((q for q in probes if q["provenance"]["seq"] == seq), None)
    if p is None:
        raise SystemExit(f"no probe with seq {seq}")
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for r in ("recorded",) + RUNGS:
        msgs, _st = pr.render(p, r, "A")
        parts = []
        for m in msgs:
            c = m["content"]
            parts.append(f"===== {m['role'].upper()} =====\n" + (
                c if isinstance(c, str)
                else "\n".join(b.get("text", "") for b in c
                               if b.get("type") == "text")))
        path = os.path.join(out_dir, f"seq{seq}_{r}.txt")
        with open(path, "w") as f:
            f.write("\n\n".join(parts))
        written.append((r, path, sum(len(x) for x in parts)))
    print(f"\nDUMPED seq {seq}")
    for r, path, n in written:
        print(f"  {r:<12} {n:6d} chars  {path}")
    print("\n  Read these. Suggested diffs:")
    print(f"    diff {out_dir}/seq{seq}_L3.txt "
          f"{out_dir}/seq{seq}_L3-nowidth.txt")
    print(f"    diff {out_dir}/seq{seq}_L3-nowidth.txt "
          f"{out_dir}/seq{seq}_L1-nowidth.txt")
    print(f"    diff {out_dir}/seq{seq}_L3.txt {out_dir}/seq{seq}_L2.txt")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probes", required=True)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dump", type=int, metavar="SEQ")
    ap.add_argument("--dump-dir", default="out/ex1_prompts")
    args = ap.parse_args(argv)

    ps = load(args.probes)
    probes = ps["probes"][:args.limit] if args.limit else ps["probes"]
    print(f"{args.probes}")
    print(f"  hash {ps.get('hash', '')[:16]}  n {len(probes)}")

    if args.dump is not None:
        dump(probes, args.dump, args.dump_dir)
        return 0

    zm = pr.zonemap()
    baskets = pr._baskets()
    audit_data(probes, zm)
    states = audit_rungs(probes)
    audit_ground_truth(probes, states, zm, baskets)
    audit_text(probes, states)
    audit_reply(probes, states, zm, baskets)

    print("\nRESULT: " + ("ALL PASS" if not fails
                          else f"{len(fails)} FAILURE(S): {fails}"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
