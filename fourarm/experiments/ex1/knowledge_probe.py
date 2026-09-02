"""EX1 probe: what opening does the model think each object needs.

WHY THIS EXISTS, AND WHY IT IS THE CHEAPEST CELL IN THE PROJECT.

The chapter's central result is a null: with the declared opening withheld
and the object's name present, legality does not recover. From that we can
say the models do not USE the name to recover the opening. We cannot say
whether they COULD. Those are different claims, and only the second one is
about memorisation.

Experiment 2 already has this check. Its manipulation check asks the model
what it can see, with no allocation to perform, so that a low
image-following rate is attributable to cue weighting rather than to a
render nothing could read. Experiment 1 had no equivalent, and that was the
one genuine structural asymmetry between the two chapters. This closes it.

Asked outside the allocation task, per object rather than per state, it
costs eleven objects times three models times a few repeats: about a
hundred calls whatever the probe set size.

HOW THE ANSWER IS READ.

Three ways, reported together, because the object registry's own number is
not the only defensible target:

  exact       the absolute error against the registry's "grasp_m", the
              same number the validator compares against. This is the
              strict reading and will be poor for almost any model:
              nothing tells it the cell measures the minimum horizontal
              dimension, and two of the eleven objects carry an AUTHORED
              width rather than a measured one (the drill is grasped by
              its handle, the bowl by its rim), so no amount of product
              knowledge recovers those two.

  side        which side of the Franka aperture the answer falls, at
              0.080 m. THIS IS THE ENDPOINT THAT MATTERS. The allocation
              decision turns on one binary: does this object fit the
              narrow gripper. A model whose estimate is 20 mm out but on
              the right side of the aperture allocates correctly every
              time, and one whose estimate is 5 mm out across it does not.
              Reporting only the absolute error would call the first model
              worse than it is and the second better.

  band        the answer within a declared tolerance of the registry
              value. Reported because "side" is coarse: an object 30 mm
              from the aperture is on the right side of it by luck as
              easily as by knowledge, and the band says which.

WHAT THE QUESTION DOES AND DOES NOT SAY.

  It names the object and nothing else about it. No mass, no category, no
  dimensions. Supplying any of those would make this a derivation question,
  and the whole point is that it is a retrieval question.

  It states the grasp convention, because the cell's number is a
  convention and not a fact about the object: picked from directly above,
  gripper free to turn. Without it the model is being scored against a
  measurement protocol it was never told, and a wrong answer would be
  ambiguous between not knowing the object and not knowing the protocol.

  IT DOES NOT SAY WHICH DIMENSION. "The smaller of its two horizontal
  extents" is exactly the relation Experiment 2 manipulates as its
  derivation factor, and stating it here would hand over the relation
  under a probe that claims to measure knowledge of the object.

  It asks for a number, not a choice. A two-way "wider or narrower than
  0.080 m" would be isomorphic to the endpoint and could not show WHERE
  the estimate sits, which is what separates a model that is close and
  unlucky from one that is guessing.

  The AUTHORED widths are flagged on every row (grasp_authored), so the
  strict number can be reported with and without them. They are not
  dropped: what the model says about the drill is still evidence about the
  drill.

CAST. Defaults to the eleven-object cast Experiment 1 runs, in registry
order, so the probe covers exactly the objects the states contain. Cast B
is one flag away, and mixing them in one file is refused: the two casts are
disjoint and a pooled accuracy would describe neither.

Usage:
    python3 -m experiments.ex1.knowledge_probe --dry-run
    python3 -m experiments.ex1.knowledge_probe --model gpt --repeats 3 \\
        --out out/ex1_knowledge_gpt.jsonl
    python3 -m experiments.ex1.knowledge_probe --summarise \\
        out/ex1_knowledge_gpt.jsonl
"""

import argparse
import json
import os
import re
import statistics
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_ROOT, os.path.join(_ROOT, "ycb")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.decision.vlm_allocator import chat                      # noqa: E402
from core.cell import cell_config as C                            # noqa: E402

PROBE_VERSION = "2026-09-02a"

# The aperture the allocation decision turns on. Read from the registry
# rather than written here, so a change to the arm tables moves the
# endpoint with it instead of leaving this file quietly wrong.
FRANKA_APERTURE = C.ARM_TYPES["franka"]["max_grasp_m"]
UR_APERTURE = C.ARM_TYPES["ur10"]["max_grasp_m"]

# The "band" reading's tolerance, in metres. Declared here and recorded on
# every row, because a tolerance chosen after seeing the answers is not a
# measurement.
DEFAULT_BAND_M = 0.015


def cast_names(cast="A", n=11):
    """The object cast, in registry order.

    Imported from the registry rather than listed, so the probe and the
    episodes can never disagree about which objects the experiment uses.
    """
    from ycb_objects import YCB
    from layouts import LAYOUT_CASTS
    if cast == "A":
        return list(YCB)[:n]
    if cast == "B":
        for key, names in LAYOUT_CASTS.items():
            if "set_b" in key or "setb" in key:
                return list(names)
        raise ValueError(
            "cast B is not in LAYOUT_CASTS under a name containing 'set_b'. "
            "Guessing which entry is the second cast would probe the wrong "
            "objects, so this fails instead.")
    raise ValueError(f"unknown cast {cast!r}; expected A or B")


def display_name(obj):
    """The object as the state names it, minus the scene prefix.

    The state renders objects as "ycb_soup_can" and the model is asked
    about "soup can". The underscore form is what a state carries and the
    spaced form is what a question asks; using one where the other belongs
    would test tokenisation rather than knowledge.
    """
    stem = obj[4:] if obj.startswith("ycb_") else obj
    return stem.replace("_", " ")


QUESTION = (
    "A robot gripper will pick up a {name} from directly above. The gripper "
    "approaches straight down and is free to turn to whichever horizontal "
    "direction suits before it closes. How wide must the gripper open, in "
    "metres, to grasp the object? Answer with a single number to three "
    "decimals and nothing else.")


def build_messages(obj):
    """The probe for one object. No state, no rules, no allocation."""
    return [
        {"role": "system", "content": "Answer with one number and nothing "
                                      "else."},
        {"role": "user", "content": QUESTION.format(name=display_name(obj))},
    ]


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def parse_metres(reply):
    """The first number in the reply, in metres, or None.

    A reply in millimetres is a real risk on a question that asks for
    metres, and reading "85" as 85 m would produce a nonsense error rather
    than a visible unit mistake. Anything above 1.0 is therefore read as
    millimetres and converted, and the conversion is recorded on the row so
    it can be excluded rather than discovered later.
    """
    if not reply:
        return None, None
    m = _NUM.search(reply.replace(",", ""))
    if not m:
        return None, None
    v = float(m.group(0))
    if v <= 0:
        return None, None
    if v > 1.0:                     # plainly not metres for a YCB object
        return v / 1000.0, "mm"
    return v, None


def truth(obj):
    """The registry's numbers for one object."""
    from ycb_objects import YCB
    stem = obj[4:] if obj.startswith("ycb_") else obj
    spec = YCB[stem]
    return {"grasp_m": spec["grasp_m"],
            "grasp_authored": bool(spec.get("grasp_authored", False)),
            "category": spec.get("category"),
            "delicate": bool(spec.get("delicate", False))}


def score(answer_m, true_m, band_m=DEFAULT_BAND_M):
    """The three readings for one answer. All None when nothing parsed."""
    if answer_m is None:
        return {"abs_error_m": None, "signed_error_m": None,
                "within_band": None, "side_correct": None,
                "fits_franka_said": None, "fits_franka_true": None}
    fits_said = answer_m <= FRANKA_APERTURE
    fits_true = true_m <= FRANKA_APERTURE
    return {
        "abs_error_m": round(abs(answer_m - true_m), 4),
        "signed_error_m": round(answer_m - true_m, 4),
        "within_band": abs(answer_m - true_m) <= band_m,
        # THE ENDPOINT. Whether the answer puts the object on the same side
        # of the Franka aperture as the truth does, which is the only thing
        # the allocation decision reads.
        "side_correct": fits_said == fits_true,
        "fits_franka_said": fits_said,
        "fits_franka_true": fits_true,
    }


def ask(obj, model, repeat, model_fn=chat, timeout=60.0, band_m=DEFAULT_BAND_M,
        retry_errors=True):
    """One call. Returns a row whether or not the call succeeded."""
    messages = build_messages(obj)
    t = truth(obj)

    reply, error = None, None
    t0 = time.time()
    for attempt in (1, 2):
        try:
            reply = model_fn(messages, timeout=timeout, alias=model)
            error = None
            break
        except Exception as exc:                        # noqa: BLE001
            error = "%s: %s" % (type(exc).__name__, exc)
            if not retry_errors or attempt == 2:
                break
            time.sleep(2.0)

    answer_m, unit_fix = parse_metres(reply)
    row = {
        "probe_version": PROBE_VERSION,
        "probe_id": f"{model}:{obj}:{repeat}",
        "object": obj,
        "name_asked": display_name(obj),
        "model_alias": model,
        "repeat": repeat,
        "band_m": band_m,
        "franka_aperture_m": FRANKA_APERTURE,
        "ur_aperture_m": UR_APERTURE,
        "reply": reply,
        "answer_m": answer_m,
        "unit_fix": unit_fix,
        "latency_ms": round((time.time() - t0) * 1000.0, 1),
        "error": error,
    }
    row.update({"true_" + k: v for k, v in t.items()})
    row.update(score(answer_m, t["grasp_m"], band_m))
    return row


def _done_ids(path):
    """probe_ids already answered in an output file, for resuming.

    An errored row with no answer does not count as done, matching the
    summariser's own definition of a row, so a rerun retries exactly the
    calls that failed.
    """
    seen = set()
    if not path or not os.path.exists(path):
        return seen
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not rec.get("probe_id"):
                continue
            if rec.get("error") and rec.get("answer_m") is None:
                continue
            seen.add(rec["probe_id"])
    return seen


def run(objects, models, repeats=3, out=None, model_fn=chat, timeout=60.0,
        band_m=DEFAULT_BAND_M, resume=True):
    """Every (object, model, repeat) cell, appended as it completes."""
    done = _done_ids(out) if resume else set()
    rows = []
    if out:
        d = os.path.dirname(os.path.abspath(out))
        if d:
            os.makedirs(d, exist_ok=True)
    for model in models:
        for obj in objects:
            for r in range(1, repeats + 1):
                pid = f"{model}:{obj}:{r}"
                if pid in done:
                    continue
                row = ask(obj, model, r, model_fn=model_fn, timeout=timeout,
                          band_m=band_m)
                rows.append(row)
                if out:
                    with open(out, "a") as f:
                        f.write(json.dumps(row) + "\n")
                print(f"  {model:8s} {obj:16s} r{r}  "
                      f"said {row['answer_m']}  true {row['true_grasp_m']}  "
                      f"side {row['side_correct']}", flush=True)
    return rows


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarise(rows):
    """Per model: the three readings, with and without the authored widths.

    Authored widths are separated rather than dropped. The drill's 0.050 m
    is the handle and the bowl's 0.030 m is the rim, neither of which any
    amount of product knowledge recovers, so a strict accuracy that
    includes them measures the authoring as much as the model. The side
    reading is reported on both, because the authored numbers are what the
    validator uses and the allocation endpoint has to face them.
    """
    out = {}
    models = sorted({r["model_alias"] for r in rows})
    for m in models:
        mine = [r for r in rows if r["model_alias"] == m
                and r.get("answer_m") is not None]
        measured = [r for r in mine if not r["true_grasp_authored"]]
        block = {"n_answered": len(mine),
                 "n_unparseable": sum(1 for r in rows
                                      if r["model_alias"] == m
                                      and r.get("answer_m") is None)}
        for label, subset in (("all", mine), ("measured_only", measured)):
            if not subset:
                block[label] = None
                continue
            errs = [r["abs_error_m"] for r in subset]
            block[label] = {
                "n": len(subset),
                "side_correct": sum(1 for r in subset if r["side_correct"])
                                / len(subset),
                "within_band": sum(1 for r in subset if r["within_band"])
                               / len(subset),
                "median_abs_error_m": round(statistics.median(errs), 4),
                "mean_signed_error_m": round(
                    statistics.mean(r["signed_error_m"] for r in subset), 4),
            }
        # Per object, because one object can carry a whole model's error and
        # a pooled number would hide it.
        block["by_object"] = {}
        for obj in sorted({r["object"] for r in mine}):
            sub = [r for r in mine if r["object"] == obj]
            block["by_object"][obj] = {
                "n": len(sub),
                "true_m": sub[0]["true_grasp_m"],
                "authored": sub[0]["true_grasp_authored"],
                "median_said_m": round(
                    statistics.median(r["answer_m"] for r in sub), 4),
                "side_correct": sum(1 for r in sub if r["side_correct"])
                                / len(sub),
            }
        out[m] = block
    return out


def _print_summary(summary):
    for model, b in summary.items():
        print(f"\n{model}   answered {b['n_answered']}  "
              f"unparseable {b['n_unparseable']}")
        for label in ("all", "measured_only"):
            s = b.get(label)
            if not s:
                continue
            print(f"  {label:14s} n {s['n']:4d}   "
                  f"side {100 * s['side_correct']:5.1f}%   "
                  f"band {100 * s['within_band']:5.1f}%   "
                  f"median |err| {1000 * s['median_abs_error_m']:5.1f} mm   "
                  f"bias {1000 * s['mean_signed_error_m']:+6.1f} mm")
        print(f"  {'object':16s} {'true':>7s} {'said':>7s} {'side':>6s}")
        for obj, o in b["by_object"].items():
            print(f"  {obj:16s} {o['true_m']:7.3f} {o['median_said_m']:7.3f} "
                  f"{100 * o['side_correct']:5.0f}%"
                  + ("  (authored)" if o["authored"] else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", action="append", dest="models", default=None,
                    help="registry alias, repeatable. Default: gpt")
    ap.add_argument("--cast", default="A", choices=["A", "B"])
    ap.add_argument("--objects", type=int, default=11,
                    help="how many of the cast, in registry order")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--band", type=float, default=DEFAULT_BAND_M,
                    help="tolerance in metres for the 'within band' reading. "
                         "Declared before the run and recorded on every row")
    ap.add_argument("--out", default=None, help="append rows here as JSONL")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the question for every object and stop")
    ap.add_argument("--summarise", metavar="PATH", default=None,
                    help="summarise an existing output file and stop")
    args = ap.parse_args(argv)

    if args.summarise:
        rows = [json.loads(l) for l in open(args.summarise) if l.strip()]
        _print_summary(summarise(rows))
        return 0

    objects = cast_names(args.cast, args.objects)
    if args.dry_run:
        print(f"EX1 knowledge probe {PROBE_VERSION}, cast {args.cast}, "
              f"{len(objects)} objects, Franka aperture {FRANKA_APERTURE}\n")
        for obj in objects:
            t = truth(obj)
            print(f"{obj:16s} true {t['grasp_m']:.3f}"
                  + ("  (authored)" if t["grasp_authored"] else ""))
        print("\nSYSTEM: Answer with one number and nothing else.")
        print("USER:   " + QUESTION.format(name=display_name(objects[0])))
        print(f"\n{len(objects)} objects x {len(args.models or ['gpt'])} "
              f"models x {args.repeats} repeats = "
              f"{len(objects) * len(args.models or ['gpt']) * args.repeats} "
              f"calls")
        return 0

    models = args.models or ["gpt"]
    rows = run(objects, models, repeats=args.repeats, out=args.out,
               timeout=args.timeout, band_m=args.band,
               resume=not args.no_resume)
    if args.out and os.path.exists(args.out):
        rows = [json.loads(l) for l in open(args.out) if l.strip()]
    _print_summary(summarise(rows))
    if args.out:
        print(f"\nWROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
