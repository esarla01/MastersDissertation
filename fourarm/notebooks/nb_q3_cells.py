"""Cell sources for ex2_q3_remediation.ipynb, the Q3 notebook.

Only the cells Q3 does not share with Q1. The key paste, the block geometry
check and the capture inventory are Q1's strings, spliced in by
build_q3_nb.py; cell 1 is Q1's cell 1 with declared substitutions.

Q3 asks: which kind of instruction moves a model from following the text to
using the scene?
"""

MD1 = r"""# Experiment 2, Q3: Remediation

**Which kind of instruction moves a model from following the text to using the
scene?**

The six rungs are already defined in `prompts.RUNGS` and are not redefined
here. `N0` adds nothing, `N-A` directs attention, `N-C` states the derivation,
`N-order` changes the field order and nothing else, `N-D` forces the report
before the arm, and `N-CD` does C and D together.

**One repeat per rung**, against `N0` baselines collected at three. A rung's
per-position share is therefore 0 or 100, while the baseline's is one of four
values, so the second-order contrast is noisier than the first-order ones in
Q1 and Q2. That is a deliberate trade: five rungs across two conditions at
three repeats would be six thousand calls.

**The spend is staged and gated.** `N-D` runs first, in `dims`, three models,
one repeat. Everything after it is gated on what that shows, per model.

Cells 1 to 5 and 11 to 16 are free. Cells 6, 8, 9 and 10 spend."""


MD4 = r"""## Cell 4. The rung design

No model calls. The rungs come from `prompts.RUNGS`; this cell records what
each one adds, checks the factors are isolated, and prints the exact added
wording so the chapter quotes the prompt rather than a paraphrase of it."""

C4 = r'''# --- Cell 4. The rung design. No model calls. -------------------------------
# READ from the prompt module, never redefined. A rung list typed here would
# be a second source of truth for the thing the experiment manipulates.
LADDER = ("N0", "N-A", "N-C", "N-order", "N-D", "N-CD")
if set(LADDER) != set(P.PRE_REGISTERED_LADDER):
    raise SystemExit("the prompt module's pre-registered ladder is %s; this "
                     "notebook names %s"
                     % (sorted(P.PRE_REGISTERED_LADDER), sorted(LADDER)))

# THE CEILING, on the ladder but NOT pre-registered, and read from the module
# rather than typed: whatever LADDER_RUNGS holds beyond the six. It is kept
# out of LADDER on purpose. Cell 9d buys it and cell 9e reads it, so folding
# it in would widen cell 9's cost line and would put a rung added after the
# ladder was run into every table whose column says "factor". Naming it here
# is what stops it falling off the end of both lists and being swept by
# nothing, which the guard below then checks.
CEILING = tuple(r for r in P.LADDER_RUNGS if r not in LADDER)

# The off-ladder precedence directives, read from the module and never
# typed here. The second guard is what stops a variant being added to
# prompts.RUNGS and quietly reaching neither list: it would then be swept
# by nothing and checked by nothing, which is how a rung goes missing.
DIRECTIVES = tuple(P.DIRECTIVE_RUNGS)

# The Q3 repair treatments, read from the module for the same reason. They are
# a fourth category because prompts.py derives DIRECTIVE_RUNGS by exclusion
# from LADDER_RUNGS, so without REPAIR_RUNGS to name them they would land in
# it and be swept as precedence directives. This partition did not know they
# existed until 2026-09-10, and the guard below correctly refused to run.
REPAIR = tuple(P.REPAIR_RUNGS)

if (set(LADDER) | set(CEILING) | set(DIRECTIVES) | set(REPAIR)
        != set(P.RUNGS)):
    raise SystemExit("prompts.RUNGS holds %s, which is neither the ladder, "
                     "the ceiling, a declared directive, nor a repair rung"
                     % sorted(set(P.RUNGS) - set(LADDER) - set(CEILING)
                              - set(DIRECTIVES) - set(REPAIR)))

# WHICH DIRECTIVE CELL IS BOUGHT, IN STAGES, following the same discipline
# as GATE_RUNG below: a cheaper cell decides whether the rest is worth
# buying. Stage 2 exists only to INTERPRET stage 1 -- one control for "any
# extra sentence would have done it", one for "it merely heard the word
# image" -- so if stage 1 does not move there is nothing to control for and
# neither is bought.
DIRECTIVE_STAGE1 = (("conflict_face", "X-image"),)
DIRECTIVE_STAGE2 = (("congruent_face", "X-image"),
                    ("conflict_face", "X-state"))
DIRECTIVE_CELLS = DIRECTIVE_STAGE1 + DIRECTIVE_STAGE2

# THE GATE RUNG. N-D rather than N-CD, which is what the design document
# proposed. The pilot files from 2026-08-27 already show gemini going from
# 46.9 at N0 to a complete flip under N-D alone, with the face named
# correctly on every trial, and gpt not moving. So elicitation is the rung
# the evidence implicates, N-D minus N0 is the contrast that matters, and
# running the combined rung first would spend 204 calls confirming something
# a cheaper cell already indicates. N-CD becomes a sufficiency cell for a
# model N-D does not move.
GATE_RUNG = "N-D"
# Below this, at one repeat and 32 positions, an effect cannot be told from
# zero. Used to separate "not moved" from "not resolved", which are different
# findings and must not be reported as the same one.
GATE_MIN = 30.0

rung_rows = []
for rung in LADDER + CEILING:
    spec = P.RUNGS[rung]
    rung_rows.append([rung, ";".join(spec["factors"]) or "none",
                      spec["schema"],
                      len(spec["text"].strip().splitlines()),
                      spec["text"].strip().replace("\n", " ")[:60]
                      or "(nothing added)"])
show(["rung", "factors", "schema", "lines", "wording"], rung_rows)
write_csv("tab_ex2_q3_rungs.csv",
          ["rung", "factors", "schema", "added_lines", "added_wording"],
          [[r[0], r[1], r[2], r[3],
            P.RUNGS[r[0]]["text"].strip()] for r in rung_rows])

# The factors must be isolated, in every condition Q3 runs. These raise.
pp = []
for cond in CONDITIONS:
    try:
        P.assert_rungs_isolated(cond)
    except Exception as exc:
        pp.append("%s: %s" % (cond, exc))
try:
    P.assert_base_states_no_relation()
except Exception as exc:
    pp.append("base prompt: %s" % exc)
if pp:
    raise AssertionError("RUNG ISOLATION FAILED:\n  " + "\n  ".join(pp))
print()
print("PASS  every rung is N0 plus its own block at the same anchor, the")
print("      schema variants are as declared, and no rung leaks another's")
print("      wording. Checked in %s." % " and ".join(CONDITIONS))
print()
print("The table above is the LADDER and the CEILING. The directives are")
print("off it and are cell 4b: putting them in a table whose column says")
print("\"factor\" would present them as a fifth and sixth factor of a design")
print("that pre-registered four.")
if CEILING:
    print()
    print("NOT PRE-REGISTERED, and shown last: %s. It was added after the"
          % ", ".join(CEILING))
    print("ladder had been run, is bought by cell 9d and read by cell 9e, and")
    print("is deliberately not in LADDER: every cost line, every sweep and")
    print("every factor table here is the pre-registered six.")
print()
print("PRE-REGISTERED PREDICTIONS, from prompts.PREDICTIONS:")
for k, v in sorted(P.PREDICTIONS.items()):
    print("  %-16s %s" % (k, v))
print()
print("N-order exists because N-D moves the report ahead of the arm AND asks")
print("for the face, and a model generates left to right. Without the order")
print("control an N-D effect could not be attributed to either.")
print("N-CD is a sufficiency cell against N0. It is never an interaction")
print("test: this design is not powered for one and does not claim to be.")'''


MD4B = r"""## Cell 4b. The precedence directives, off the ladder

No model calls. The ladder scaffolds the derivation while staying silent about
provenance. A **directive** does the opposite: it names the stated resting face
and says the image can contradict it, which the boundary rule forbids `A`, `C`
and `D`. So it is not a seventh rung. It measures whether a model has an
arbitration step at all that a direct instruction can reach, and it is the
ceiling on instructed arbitration in the way `congruent_face` is the ceiling on
derivation.

This cell prints the exact wording so the chapter quotes the prompt rather than
a paraphrase, and shows that the cell which cannot be interpreted cannot be
rendered either."""

C4B = r'''# --- Cell 4b. The precedence directives. No model calls. --------------------
dir_rows = []
for rung in DIRECTIVES:
    spec = P.RUNGS[rung]
    added = spec["text"][len(P.A_ATTEND):].strip()
    dir_rows.append([rung, ";".join(spec["factors"]), spec["schema"], added])
show(["directive", "factors", "schema", "sentence added to N-A"], dir_rows)
write_csv("tab_ex2_q3_directives.csv",
          ["directive", "factors", "schema", "full_wording",
           "sentence_added_to_N_A"],
          [[r[0], r[1], r[2], P.RUNGS[r[0]]["text"].strip(), r[3]]
           for r in dir_rows])

print()
print("EACH IS N-A PLUS ONE SENTENCE. That is the whole attribution: N-A is")
print("already on disk in conflict_face at %d repeats, so X minus N-A is the"
      % REPEATS)
print("precedence sentence and nothing else, bought for nothing.")
print()
print("BOTH SENTENCES NAME THE IMAGE and differ in one word. X-state is what")
print("separates reading the instruction from reacting to image-talk: if the")
print("model moves toward the picture under BOTH, it is not arbitrating.")
print()
print("THE WORDING IS CONDITIONAL, never assertive. \"The image disagrees with")
print("the text\" would be a FALSE sentence in congruent_face, and")
print("congruent_face is the control that makes the result readable: the same")
print("prompt, the same sentence, an antecedent that is never satisfied.")
print()
print("THE SCHEMA STAYS base. A directive that also reordered the answer would")
print("confound precedence with the report order, which is what N-order is")
print("there to separate. It also means the arm is committed BEFORE the")
print("opening is written, so a failure to move cannot be told apart from")
print("obedience arriving too late in the generation. That is a limitation of")
print("this cell and belongs in the chapter, not a defect to patch by giving")
print("the directive the face-first schema.")
print()
print("WHERE A DIRECTIVE IS REFUSED, from prompts.RUNG_VACUOUS_IN:")
for rung in DIRECTIVES:
    print("  %-8s vacuous in %s" % (rung, ", ".join(P.RUNG_VACUOUS_IN[rung])))
for cond in sorted(set(CONDITIONS) | {c for c, _ in DIRECTIVE_CELLS}):
    offered = [r for r in DIRECTIVES if r in P.rungs_for(cond)]
    print("  %-15s offers %s" % (cond, ", ".join(offered) or "(none)"))
try:
    P.system_prompt("X-image", "dims")
    raise AssertionError("dims rendered a directive; it states no face")
except ValueError as exc:
    print()
    print("PASS  rendering X-image in dims raises rather than buying it:")
    print("      %s" % " ".join(str(exc).split())[:66])
print()
print("dims pops resting_face from the state and its glossary says so, so a")
print("sentence about \"the stated resting face\" would name a field the prompt")
print("has just withdrawn. That is a comprehension puzzle, not the question")
print("under test, so the cell is unrenderable rather than merely discouraged.")'''


MD5 = r"""## Cell 5. What each rung actually adds

No model calls. The diff of every rung against `N0`, and the answer schema each
one asks for, so the wording and the field order are both on the record before
anything is bought."""

C5 = r'''# --- Cell 5. Rung prompts, diffed against N0. No model calls. ---------------
import difflib
for cond in CONDITIONS:
    print("=" * 70)
    print("CONDITION %s" % cond.upper())
    print("=" * 70)
    texts = P.rung_diff(cond)
    base = texts["N0"].splitlines()
    # rung_diff returns only the rungs coherent in this condition, so a
    # directive is simply absent where it is refused.
    for rung in LADDER + DIRECTIVES:
        if rung == "N0" or rung not in texts:
            continue
        added = [l[1:] for l in difflib.unified_diff(base,
                                                     texts[rung].splitlines(),
                                                     lineterm="", n=0)
                 if l.startswith("+") and not l.startswith("+++")]
        removed = [l[1:] for l in difflib.unified_diff(base,
                                                       texts[rung].splitlines(),
                                                       lineterm="", n=0)
                   if l.startswith("-") and not l.startswith("---")]
        print()
        print("%-8s schema %-12s +%d lines  -%d lines"
              % (rung, P.RUNGS[rung]["schema"], len(added), len(removed)))
        for l in added:
            if l.strip():
                print("   + " + l)
        for l in removed:
            if l.strip():
                print("   - " + l)
    print()

print("=" * 70)
print("THE ANSWER SCHEMA, per variant")
print("=" * 70)
for name in ("base", "report_first", "face_first"):
    used = [r for r in LADDER + DIRECTIVES if P.RUNGS[r]["schema"] == name]
    print()
    print("%-13s used by %s" % (name, ", ".join(used)))
    for line in P.schema_text(name).strip().splitlines():
        print("   " + line)
print()
print("resting_face is required ONLY by face_first. Asking for it at every")
print("rung would tell the model that the face matters, which is the thing")
print("factor D is there to manipulate.")'''


MD6 = r"""## Cell 6. The gate: N-D in dims

**Makes model calls.** 68 scenes, three models, one repeat. This is the rung
the 2026-08-27 pilots implicate, and everything after it is gated on what it
shows, per model."""

C6 = r'''# --- Cell 6. GATE: N-D in dims. MAKES MODEL CALLS. --------------------------
def rung_file(cond, rung):
    """One file per condition and rung. The rung is in solo's trial_id too,
    so this is belt and braces -- but a rung pointed at the wrong file would
    find every id present, skip the lot, and report itself complete having
    spent nothing."""
    return RUNS / ("ex2_q3_%s_%s.jsonl" % (cond, rung))

GATE_OUT = rung_file("dims", GATE_RUNG)

# SEEDED FROM THE PILOTS ALREADY ON DISK, before the cost is computed.
# Two files from 2026-08-27 hold exactly this cell for gpt_hi and gemini:
# same rung, same condition, same 68 scenes, same prompt version, one
# repeat, default face order and frame. They were written by solo.run, so
# their trial_ids are the ones this cell would generate, and copying them
# in means the runner resumes over them rather than buying them twice.
# That is 136 of the 204 calls.
#
# THE FILTER REBUILDS THE ID THIS CELL WOULD ASK FOR and takes only exact
# matches. That matters: the gemini file also holds a large_first arm,
# which is a different cell of a different factor, and its ids carry a
# suffix. Rebuilding rather than pattern-matching means a row from another
# arm cannot leak in, now or when another factor is added later.
PILOTS = (("runs/ex2_q1_dims_N-D_effort.jsonl", "gpt_hi"),
          ("runs/ex2_q1_dims_N-D_order.jsonl", "gemini"))

def seed_from_pilots(out_path, pilots, cond, rung):
    """Copy matching rows into out_path. Idempotent; returns what it added."""
    have = set()
    if pathlib.Path(out_path).exists():
        for line in open(out_path):
            if line.strip():
                have.add(json.loads(line).get("trial_id"))
    added, skipped = collections.Counter(), collections.Counter()
    with open(out_path, "a") as fh:
        for src, model in pilots:
            if not pathlib.Path(src).exists():
                skipped["source file missing"] += 1
                continue
            seen = {}
            for line in open(src):
                if line.strip():
                    r = json.loads(line)
                    seen[r.get("trial_id")] = r
            for r in seen.values():
                if r.get("model") != model or r.get("error"):
                    continue
                rep = r.get("repeat") or 1
                if rep > REPEATS:
                    skipped["beyond this cell's repeats"] += 1
                    continue
                want = "%s|%s|%s|%s|%s|V|r%d" % (r.get("seq"), cond, model,
                                                 PREFERENCE, rung, rep)
                if r.get("trial_id") != want:
                    skipped["a different factor arm"] += 1
                    continue
                if r.get("ex2_prompt_version") != P.EX2_PROMPT_VERSION:
                    skipped["older prompt version"] += 1
                    continue
                if want in have:
                    continue
                fh.write(json.dumps(r) + "\n")
                have.add(want)
                added[model] += 1
    return added, skipped

_added, _skipped = seed_from_pilots(GATE_OUT, PILOTS, "dims", GATE_RUNG)
if _added:
    print("seeded from the pilots: %s"
          % ", ".join("%s %d" % (m, n) for m, n in sorted(_added.items())))
    for _src, _m in PILOTS:
        print("   %s" % _src)
    print("   Not new observations: the same cell, already paid for, resumed")
    print("   rather than re-bought. Cell 16 records the provenance.")
if _skipped:
    print("   not seeded: %s"
          % ", ".join("%s %d" % (k, v) for k, v in sorted(_skipped.items())))

n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
print("COST: %d scenes x %d models x %d repeat = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
print("      rung %s, condition dims, against the N0 baseline already on disk"
      % GATE_RUNG)

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, GATE_OUT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", REPEATS))):
    S.run(str(CAPTURES), out_path=str(GATE_OUT), models=MODELS,
          conditions=("dims",), preferences=(PREFERENCE,),
          rungs=(GATE_RUNG,), modalities=("V",), kind="pair", repeats=REPEATS)
    print("answered now:", answered(GATE_OUT))'''


MD7 = r"""## Cell 7. Gate read-out

No model calls. Three outcomes per model, not two: **moved**, **not moved**, and
**unresolved**. At one repeat over 32 positions an effect below about 30 points
cannot be told from zero, and reporting that as a null would be reading a
finding out of an interval that never had the resolution to produce one."""

C7 = r'''# --- Cell 7. Gate read-out. No model calls. ---------------------------------
# Every N0 baseline on disk, not only the two the ladder runs in. The four
# face and number conditions are what the rung effects have to be read
# against -- a rung that lifts dims to +50 means one thing beside a
# congruent_face ceiling of +100 and another beside one of +6 -- so they
# belong in the inventory and in the contrast table even though no rung is
# planned in them.
N0_FILE = {"dims": RUNS / "ex2_q1_dims_N0.jsonl",
           "conflict": RUNS / "ex2_q2_conflict_N0.jsonl",
           "congruent": RUNS / "ex2_q1_congruent_N0.jsonl",
           "congruent_face": RUNS / "ex2_q1_congruent_face_N0.jsonl",
           "conflict_face": RUNS / "ex2_q2_conflict_face_N0.jsonl"}

# Shown at N0 only: they carry no ladder, so listing five missing rungs
# apiece would be ten rows of noise.
BASELINES = tuple(c for c in N0_FILE if c not in CONDITIONS)

def rung_rows_for(cond, rung):
    """Analysable rows for one condition and rung, from the right file."""
    path = N0_FILE[cond] if rung == "N0" else rung_file(cond, rung)
    rows, _ = load_run(path, cond, MODELS)
    rows = [r for r in rows if r.get("rung") == rung]
    return keep_analysable(rows, USABLE)

def contrast_pairs(cond, rung, model):
    rows = [r for r in rung_rows_for(cond, rung) if r["model"] == model]
    return paired_diffs(rows, USABLE, "small_face", "large_face")

GATE_VERDICT = {}
gate_rows = []
for model in MODELS:
    a = contrast_pairs("dims", GATE_RUNG, model)
    b = contrast_pairs("dims", "N0", model)
    m_r, _, _, n_r = paired_mean_ci([d for _, d in a])
    m_0, _, _, n_0 = paired_mean_ci([d for _, d in b])
    delta = paired_delta(a, b)
    mean, lo, hi, npos = paired_mean_ci([d for _, d in delta])

    if not npos:
        v = "NOT RUN"
    elif lo > 0:
        v = "MOVED"
    elif hi < 0:
        v = "MOVED BACKWARDS"
    elif hi < GATE_MIN:
        v = "NOT MOVED"
    else:
        v = "UNRESOLVED"
    GATE_VERDICT[model] = v
    gate_rows.append([model, fmt(m_0), fmt(m_r), npos, fmt(mean), fmt(lo),
                      fmt(hi), v])

show(["model", "N0", GATE_RUNG, "npos", "delta", "lo", "hi", "verdict"],
     gate_rows)
print()
print("delta is %s minus N0, paired within position at both levels." % GATE_RUNG)
print("A model reads UNRESOLVED when the interval still admits an effect of")
print("%.0f points or more. That is not a null: it is a cell that needs more" % GATE_MIN)
print("repeats before it can be called either way.")
print()
for model in MODELS:
    v = GATE_VERDICT[model]
    print("  %-9s %s" % (model, v))
    if v == "MOVED":
        print("             -> elicitation works for this model. Cell 8 tests")
        print("                whether it needs the picture; cell 9 asks")
        print("                which factor did it.")
    elif v == "NOT MOVED":
        print("             -> the strongest single instruction did nothing.")
        print("                Cell 9 runs N-CD for this model as the")
        print("                sufficiency cell; the intermediate rungs are")
        print("                very unlikely to move what N-D did not.")
    elif v == "UNRESOLVED":
        print("             -> more repeats on this cell before any further")
        print("                rung is bought for this model.")
    else:
        print("             -> cell 6 has not been run.")
# THE GATE NO LONGER NARROWS THE DESIGN. It was written to skip models the
# strongest rung did not move, on the grounds that a weaker one would buy a
# row of zeros. Two things killed that. It returned UNRESOLVED rather than
# NOT MOVED for two models of three, and excluding a model on an
# inconclusive verdict is not the same as excluding it on a null; and at one
# repeat the whole ladder is cheap enough that a complete factorial costs
# less than the argument about which cells to skip. So the verdicts above
# are read as INFORMATION, and every cell below asks every model.
PROCEED = list(MODELS)
print()
print("Every rung below is run for every model. The verdicts above are a")
print("read-out, not a filter: two of three came back UNRESOLVED, and a")
print("model dropped on an inconclusive gate would be missing from the")
print("chapter with no result of its own to show for it.")'''


MD8 = r"""## Cell 8. The control: N-D with no image

**Makes model calls.** The rung that moves a model has to be shown to move it
*towards the scene*, not towards a better guess from the text.

Q1's ablation answers this at `N0`; it cannot answer it at `N-D`, because a
schema effect only shows under the schema. If a model scores here, where the
picture is absent, the face-first result is a text artefact and the rung is
withdrawn."""

C8 = r'''# --- Cell 8. CONTROL: N-D, dims, no image. MAKES MODEL CALLS. ---------------
CONTROL_OUT = RUNS / ("ex2_q3_dims_%s_noimage.jsonl" % GATE_RUNG)

# Only the models the gate moved. There is nothing to control for in a model
# that did not move.
CONTROL_MODELS = tuple(PROCEED)
n_calls = len(CALL_SCENES) * len(CONTROL_MODELS) * REPEATS
print("COST: %d scenes x %d models x %d repeat = %d calls"
      % (len(CALL_SCENES), len(CONTROL_MODELS), REPEATS, n_calls))
print("      models the gate moved: %s" % (", ".join(CONTROL_MODELS) or "none"))
print("      Under dims the two faces are indistinguishable in text, so this")
print("      must land at zero. If it does not, %s is a text artefact." % GATE_RUNG)

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if not CONTROL_MODELS:
    print("\nno model to control; nothing to do.")
elif spend_gate(n_calls, CONFIRM_SPEND, CONTROL_OUT,
                factors=(("scenes", len(CALL_SCENES)),
                         ("models", len(CONTROL_MODELS)),
                         ("repeats", REPEATS))):
    S.run(str(CAPTURES), out_path=str(CONTROL_OUT), models=CONTROL_MODELS,
          conditions=("dims",), preferences=(PREFERENCE,),
          rungs=(GATE_RUNG,), modalities=("A",), kind="pair", repeats=REPEATS)
    print("answered now:", answered(CONTROL_OUT))'''


MD9 = r"""## Cell 9. The rest of the dims ladder

**Makes model calls.** `N-A`, `N-C`, `N-order` and `N-CD` in `dims`, for every
model, one repeat. `N0` is Q1's and `N-D` is cell 6's.

No gating. The gate returned UNRESOLVED for two models of three, and dropping a
model on an inconclusive verdict would leave it missing from the chapter with
no result of its own. At one repeat the complete factorial is cheap enough that
the argument about which cells to skip costs more than the cells.

`solo.run` resumes, so the Gemini cells already collected are not re-bought."""


C9 = r'''# --- Cell 9. The rest of the dims ladder. MAKES MODEL CALLS. ----------------
# Every rung except N0 (Q1's) and N-D (cell 6's), for every model. One
# repeat. solo.run resumes, so the gemini cells already on disk are not
# re-bought and this asks only for what is missing.
DIMS_REST = tuple(r for r in LADDER if r not in ("N0", GATE_RUNG))

n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS * len(DIMS_REST)
print("COST: %d scenes x %d models x %d repeat x %d rungs = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, len(DIMS_REST), n_calls))
print("      rungs: %s" % ", ".join(DIMS_REST))
for rung in DIMS_REST:
    _f = rung_file("dims", rung)
    print("      %-8s %3d of %d answered" % (rung, answered(_f),
                                             len(CALL_SCENES) * len(MODELS)))

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", REPEATS), ("rungs", len(DIMS_REST)))):
    for rung in DIMS_REST:
        out = rung_file("dims", rung)
        print("\n--- dims %s ---" % rung)
        S.run(str(CAPTURES), out_path=str(out), models=MODELS,
              conditions=("dims",), preferences=(PREFERENCE,), rungs=(rung,),
              modalities=("V",), kind="pair", repeats=REPEATS)
    print("\ndims ladder complete")'''



MD9B = r"""## Cell 9b. The frame control: `dims` under `extents`

**Makes model calls.** The `dims` glossary states the extents "measured
**standing on its smallest face**". The block is 0.130 x 0.100 x 0.050, so its
smallest face is 0.100 x 0.050, and *standing on its smallest face* is the
`small_face` condition word for word.

That leaves two failures indistinguishable under the `named` frame: a model that
cannot read the pose from the image, and a model that read the orientation the
glossary stated and never treated it as a convention. Both predict `small_face`
on every trial. The frame is the only thing that separates them, because the
first predicts the wording makes no difference and the second predicts the
answer follows it.

`extents`, already in `prompts.DIMS_FRAMES`, renders the same three numbers as
"three extents largest first" and names no orientation. It **removes** step 1
rather than scaffolding it, which is what a control should do.

**Three rungs, not one.** `N0` is the baseline: what the frame is worth with no
instruction at all. `N-CD` is where the named ladder first moves. `N-ACD` is the
ceiling. Together they give the frame effect at three points on the instruction
axis, which is what the confound calls into question. `N-A`, `N-C`, `N-order`
and `N-D` are the factor-attribution cells and are not needed to show the
frame effect exists; cell 9b2 buys them under the same frame once cell 9c
says there is one.

**Matched repeats.** The named ladder is on disk at three repeats. A frame arm at
one repeat would widen every interval by about 1.6x and leave the clean arm
noisier than the confounded one it replaces, so the repeat count is read from
disk and asserted rather than taken from `REPEATS`."""

C9B = r'''# --- Cell 9b. FRAME CONTROL: dims under extents. MAKES MODEL CALLS. ---------
FRAME_ALT = "extents"
FRAME_RUNGS = ("N0", "N-CD", "N-ACD")     # baseline, partial, complete
FRAME_OUT = {g: RUNS / ("ex2_q3_dims_%s_%s.jsonl" % (g, FRAME_ALT))
             for g in FRAME_RUNGS}
FRAME_BASE = {g: (N0_FILE["dims"] if g == "N0" else rung_file("dims", g))
              for g in FRAME_RUNGS}

# The alternative frame is prompts' own, never a string invented here. If it
# is renamed this must fail rather than quietly re-buy the DEFAULT frame and
# report it as a control: a file compared with itself reads as a clean null
# and is the most expensive way to be wrong in this notebook.
if FRAME_ALT not in P.DIMS_FRAMES:
    raise AssertionError(
        "%r is not in prompts.DIMS_FRAMES (%s)."
        % (FRAME_ALT, ", ".join(P.DIMS_FRAMES)))

# WHAT THE FRAME ACTUALLY CHANGES, printed rather than described. The
# manipulation is only interpretable if it touches the glossary line and
# nothing else, and if it makes the SAME edit at every rung -- a frame that
# changed more under one instruction than another would confound the two.
import difflib
print("=" * 70)
print("THE FRAME EDIT: %s minus named, at every rung this cell buys" % FRAME_ALT)
print("=" * 70)
_edit = None
for g in FRAME_RUNGS:
    _a = P.system_prompt(g, "dims", dims_frame="named").splitlines()
    _b = P.system_prompt(g, "dims", dims_frame=FRAME_ALT).splitlines()
    _d = list(difflib.unified_diff(_a, _b, lineterm="", n=0))
    add = [l[1:] for l in _d if l.startswith("+") and not l.startswith("+++")]
    rem = [l[1:] for l in _d if l.startswith("-") and not l.startswith("---")]
    print()
    print("%-7s  -%d lines  +%d lines" % (g, len(rem), len(add)))
    for l in rem:
        if l.strip():
            print("   - " + l)
    for l in add:
        if l.strip():
            print("   + " + l)
    if _edit is None:
        _edit = (tuple(add), tuple(rem))
    elif (tuple(add), tuple(rem)) != _edit:
        raise AssertionError(
            "the %s edit differs between %s and %s. The frame contrast has "
            "to be the same manipulation at every rung, or the frame and the "
            "instruction cannot be told apart."
            % (FRAME_ALT, FRAME_RUNGS[0], g))
print()
print("PASS  the frame makes the same edit at all %d rungs, so a difference"
      % len(FRAME_RUNGS))
print("      between them is the instruction and not the wording.")
print()
print("The phrase that goes away is \"standing on its smallest face\". The")
print("block's smallest face IS the small_face condition, so under the named")
print("frame the glossary names one of the two answers.")
print()
print("=" * 70)
print("THE FULL PROMPT SENT, dims N0 under %s" % FRAME_ALT)
print("=" * 70)
print(P.system_prompt("N0", "dims", dims_frame=FRAME_ALT))
print("=" * 70)

# REPEATS IS READ FROM DISK, not from the cell-1 constant. Q3 declares one
# repeat; the dims ladder on disk carries three. Hard-coding either would let
# the frame arm drift out of match with the arm it is read against, and an
# unmatched control is worth less than no control.
def repeats_on_disk(path, rung):
    if not pathlib.Path(path).exists():
        return 0
    rows, _ = load_run(path, "dims", MODELS)
    return len({r.get("repeat") for r in rows if r.get("rung") == rung})

_named = {g: repeats_on_disk(FRAME_BASE[g], g) for g in FRAME_RUNGS}
if 0 in _named.values():
    print("The named-frame rungs this is read against are not all on disk:")
    for g in FRAME_RUNGS:
        print("  %-6s %-46s %s" % (g, rel(FRAME_BASE[g]),
                                   "%d repeats" % _named[g] if _named[g]
                                   else "MISSING"))
    print("Cells 9 and 9d buy them. Nothing to control against, nothing bought.")
elif len(set(_named.values())) != 1:
    raise AssertionError(
        "the named rungs carry different repeat counts (%s). The frame arm "
        "can only match one of them, and a control matched to some cells and "
        "not others cannot be read as one contrast." % _named)
else:
    FRAME_REPEATS = next(iter(_named.values()))
    n_calls = (len(CALL_SCENES) * len(MODELS) * FRAME_REPEATS
               * len(FRAME_RUNGS))
    print("COST: %d scenes x %d models x %d repeats x %d rungs = %d calls"
          % (len(CALL_SCENES), len(MODELS), FRAME_REPEATS, len(FRAME_RUNGS),
             n_calls))
    print("      repeats read from disk, matched to the named ladder.")
    print()
    _per = len(CALL_SCENES) * len(MODELS) * FRAME_REPEATS
    for g in FRAME_RUNGS:
        print("      %-6s %-40s %4d of %d answered"
              % (g, rel(FRAME_OUT[g]), answered(FRAME_OUT[g]), _per))
    print()
    print("      solo appends the frame to the trial_id when it is not the")
    print("      default, so these ids cannot collide with the named runs'")
    print("      even though scene, model, rung and repeat are identical.")
    print("      A part-run cell resumes: only the missing repeats are bought,")
    print("      and an unparseable reply is retried rather than skipped.")
    print()
    print("      EVERY MODEL, including gemini. Gemini reads the pose at 100%%")
    print("      under the named frame, so a frame effect in another model")
    print("      means nothing unless gemini stays put in the same run.")

    CONFIRM_SPEND = None        # <-- set to the number in the COST line

    if spend_gate(n_calls, CONFIRM_SPEND,
                  factors=(("scenes", len(CALL_SCENES)),
                           ("models", len(MODELS)),
                           ("repeats", FRAME_REPEATS),
                           ("rungs", len(FRAME_RUNGS)))):
        for g in FRAME_RUNGS:
            print("\n--- dims %s, %s frame ---" % (g, FRAME_ALT))
            S.run(str(CAPTURES), out_path=str(FRAME_OUT[g]), models=MODELS,
                  conditions=("dims",), preferences=(PREFERENCE,),
                  rungs=(g,), modalities=("V",), kind="pair",
                  repeats=FRAME_REPEATS, dims_frames=(FRAME_ALT,))
        print("\nframe control complete")'''


MD9B2 = r"""## Cell 9b2. The rest of the ladder under `extents`

**Makes model calls.** Cell 9b buys the frame at three points on the instruction
axis: no instruction, the pair, the complete procedure. This buys the four rungs
it left out -- `N-A`, `N-C`, `N-order` and `N-D` -- so the frame contrast exists
at **every** rung of the ladder.

**Why the four are worth buying.** They are the single-factor cells, and they are
what cells 12 and 13 read to say *which* instruction moved the model. Under the
`named` frame every one of those attributions carries the same confound the frame
control exists to test: a factor that "moves the model" may be moving it off a
glossary that already named the answer. Bought here, each attribution can be read
again under a glossary that names no orientation, and a factor that survives both
frames is a factor about grounding rather than about wording.

**Read cell 9c before buying this.** It is the expensive cell -- four rungs at the
matched three repeats, a third more calls than 9b -- and 9b plus 9c is what says
whether it is worth anything. If the anchor does not move at `N0`, `N-CD` and
`N-ACD`, the named ladder is not being read off the wording and this cell re-buys
a null four more times. If it does move, the ladder's own attribution is in
question and these four are how it gets settled.

**Nothing about the control is restated here.** The frame name, the file naming
and the repeat rule are cell 9b's, used as it left them, so the eight files are
one arm rather than two arms that happen to share a suffix. The cell asserts the
`extents` edit is the same at all seven rungs before it spends, and reads the
repeat count off the named ladder exactly as 9b does.

**It widens `FRAME_RUNGS`**, so cell 9c's table and `tab_ex2_q3_frame.csv` cover
the whole ladder instead of the three. Re-running 9b narrows it back to its own
three; re-run this cell afterwards if that happens."""


C9B2 = r'''# --- Cell 9b2. FRAME CONTROL, THE REST OF THE LADDER. MAKES MODEL CALLS. ----
# The four rungs cell 9b left on the named frame: the single-factor cells.
# They are what cells 12 and 13 read to attribute the movement to a factor,
# so leaving them on the named frame leaves every attribution resting on a
# glossary that names one of the two answers. This buys them under the same
# frame 9b bought, at the same repeats, so the eight files are one arm.
#
# READ CELL 9c FIRST. If the anchor does not move at N0, N-CD and N-ACD then
# the ladder is not being read off the wording, and this cell buys the same
# null four more times.

# CELL 9b DEFINES THE ARM; this only widens it. The frame name, the output
# naming and the repeat rule are stated once, in 9b, so that this cell
# cannot buy a differently-defined control and file it beside the first --
# two arms under one name is worse than one arm and a gap.
for _n in ("FRAME_ALT", "FRAME_RUNGS", "FRAME_OUT", "FRAME_BASE",
           "repeats_on_disk"):
    if _n not in globals():
        raise AssertionError(
            "%s is not defined, so cell 9b has not been run in this kernel. "
            "This cell extends 9b's arm rather than restating it." % _n)

# WHICH RUNGS ARE 9b's, remembered the first time this cell runs. FRAME_RUNGS
# is widened below so that cell 9c reads the whole ladder, which means it can
# no longer be the thing that answers "which rungs did 9b buy". Re-running
# this cell is meant to be harmless -- solo.run resumes -- and it stays
# harmless because FRAME_CORE is not recomputed once it exists.
FRAME_CORE = globals().get("FRAME_CORE") or tuple(FRAME_RUNGS)
FRAME_REST = tuple(g for g in P.LADDER_RUNGS if g not in FRAME_CORE)
if not FRAME_REST:
    raise AssertionError(
        "cell 9b already names every ladder rung (%s), so there is no rest "
        "of the ladder for this cell to buy." % ", ".join(FRAME_CORE))
if set(FRAME_CORE) - set(P.LADDER_RUNGS):
    raise AssertionError(
        "cell 9b names %s, which is not on the ladder. The frame arm is a "
        "control ON the ladder, and cell 9c reads its rungs into one table."
        % ", ".join(sorted(set(FRAME_CORE) - set(P.LADDER_RUNGS))))

# The same naming 9b uses, so the resume logic and cell 9c find these files
# without being told about them a second time.
FRAME_OUT.update({g: RUNS / ("ex2_q3_dims_%s_%s.jsonl" % (g, FRAME_ALT))
                  for g in FRAME_REST})
FRAME_BASE.update({g: rung_file("dims", g) for g in FRAME_REST})

# WIDENED FOR CELL 9c, whether or not this cell ends up spending. 9c loops
# over FRAME_RUNGS and skips a rung whose file is not on disk, so the
# read-out covers exactly what has been bought. Unconditional because a
# widening that depended on the spend gate would make the read-out's shape
# depend on the order the cells were run in.
FRAME_RUNGS = tuple(g for g in P.LADDER_RUNGS if g in FRAME_OUT)

# THE EDIT IS CHECKED AT EVERY RUNG, not only the four bought here. The four
# are read against 9b's three in one table, so the manipulation has to be
# the same at all seven or the frame and the instruction cannot be told
# apart -- which is the whole claim the control makes.
import difflib
print("=" * 70)
print("THE FRAME EDIT: %s minus named, at every rung of the ladder" % FRAME_ALT)
print("=" * 70)
_edits = {}
for g in P.LADDER_RUNGS:
    _a = P.system_prompt(g, "dims", dims_frame="named").splitlines()
    _b = P.system_prompt(g, "dims", dims_frame=FRAME_ALT).splitlines()
    _d = list(difflib.unified_diff(_a, _b, lineterm="", n=0))
    _edits[g] = (
        tuple(l[1:] for l in _d
              if l.startswith("+") and not l.startswith("+++")),
        tuple(l[1:] for l in _d
              if l.startswith("-") and not l.startswith("---")))
if len(set(_edits.values())) != 1:
    raise AssertionError(
        "the %s edit is not the same at every rung (%s differ). The frame "
        "contrast has to be one manipulation everywhere, or a difference "
        "between rungs is the wording and not the instruction."
        % (FRAME_ALT, ", ".join(sorted(g for g in P.LADDER_RUNGS
                                       if _edits[g] != _edits["N0"]))))
_add, _rem = _edits[FRAME_REST[0]]
for l in _rem:
    if l.strip():
        print("   - " + l)
for l in _add:
    if l.strip():
        print("   + " + l)
print()
print("PASS  one edit, identical at all %d rungs, so the %d bought here are"
      % (len(P.LADDER_RUNGS), len(FRAME_REST)))
print("      the same control cell 9b ran and belong in its table.")

# THE PROMPT SENT, at the gate rung. 9b prints N0's; this prints the rung
# the gate implicated, which is the one whose frame arm the chapter will be
# asked about first.
_show = GATE_RUNG if GATE_RUNG in FRAME_REST else FRAME_REST[0]
print()
print("=" * 70)
print("THE FULL PROMPT SENT, dims %s under %s" % (_show, FRAME_ALT))
print("=" * 70)
print(P.system_prompt(_show, "dims", dims_frame=FRAME_ALT))
print("=" * 70)

# ONE REPEAT COUNT FOR THE WHOLE ARM, read from disk exactly as 9b reads it.
# Checked across 9b's rungs as well as these four: if the four came in at a
# different count, the frame column in cell 9c would be three rungs at one
# precision and four at another and the delta column would not be one
# contrast.
_named = {g: repeats_on_disk(FRAME_BASE[g], g) for g in FRAME_RUNGS}
if 0 in _named.values():
    print()
    print("The named-frame rungs this is read against are not all on disk:")
    for g in FRAME_RUNGS:
        print("  %-8s %-44s %s" % (g, rel(FRAME_BASE[g]),
                                   "%d repeats" % _named[g] if _named[g]
                                   else "MISSING"))
    print("Cells 9 and 9d buy them. Nothing to control against, nothing bought.")
elif len(set(_named.values())) != 1:
    raise AssertionError(
        "the named rungs carry different repeat counts (%s). The frame arm "
        "can only match one of them, and a control matched to some rungs and "
        "not others cannot be read as one contrast." % _named)
else:
    FRAME_REPEATS = next(iter(_named.values()))
    n_calls = (len(CALL_SCENES) * len(MODELS) * FRAME_REPEATS
               * len(FRAME_REST))
    print()
    print("COST: %d scenes x %d models x %d repeats x %d rungs = %d calls"
          % (len(CALL_SCENES), len(MODELS), FRAME_REPEATS, len(FRAME_REST),
             n_calls))
    print("      rungs: %s" % ", ".join(FRAME_REST))
    print("      repeats read from disk, matched to the named ladder and to")
    print("      the three rungs cell 9b bought.")
    print()
    _per = len(CALL_SCENES) * len(MODELS) * FRAME_REPEATS
    for g in FRAME_REST:
        print("      %-8s %-40s %4d of %d answered"
              % (g, rel(FRAME_OUT[g]), answered(FRAME_OUT[g]), _per))
    print()
    print("      CELL 9b's, on disk already and costing nothing here:")
    for g in FRAME_CORE:
        print("      %-8s %-40s %4d of %d answered"
              % (g, rel(FRAME_OUT[g]), answered(FRAME_OUT[g]), _per))
    print()
    print("      solo appends the frame to the trial_id when it is not the")
    print("      default, so these ids cannot collide with the named runs'.")
    print("      A part-run cell resumes: only the missing repeats are")
    print("      bought, and an unparseable reply is retried rather than")
    print("      skipped.")
    print()
    print("      EVERY MODEL, for the reason 9b gives: gemini reads the pose")
    print("      at ceiling under the named frame, so a frame effect in")
    print("      another model means nothing unless gemini is in the same")
    print("      run and stays put.")

    CONFIRM_SPEND = None        # <-- set to the number in the COST line

    if spend_gate(n_calls, CONFIRM_SPEND,
                  factors=(("scenes", len(CALL_SCENES)),
                           ("models", len(MODELS)),
                           ("repeats", FRAME_REPEATS),
                           ("rungs", len(FRAME_REST)))):
        for g in FRAME_REST:
            print("\n--- dims %s, %s frame ---" % (g, FRAME_ALT))
            S.run(str(CAPTURES), out_path=str(FRAME_OUT[g]), models=MODELS,
                  conditions=("dims",), preferences=(PREFERENCE,),
                  rungs=(g,), modalities=("V",), kind="pair",
                  repeats=FRAME_REPEATS, dims_frames=(FRAME_ALT,))
        print("\nthe %s arm now covers every rung of the ladder" % FRAME_ALT)'''


MD9C = r"""## Cell 9c. Frame read-out

No model calls. The contrast says where each model lands. The **anchor** says
where its answer sat: how often it named `small_face`, and how often it reported
the 0.050 m opening that follows from standing on the smallest face.

Read the anchor, not the accuracy. The two faces are balanced, so a model that
always answers `small_face` scores 50% correct and reads as a coin flip. What
separates seeing the pose from reading the wording is whether the anchor **moves
when the frame moves**.

`N0` uses the base schema and does not report `resting_face`, so its anchor is
the reported opening alone."""

C9C = r'''# --- Cell 9c. Frame read-out. No model calls. -------------------------------
TOL = 0.006                # grade.classify_width's tolerance, not a new one
SMALL_OPENING = 0.050      # the opening for a block on its SMALLEST face,
                           # which is the orientation the named frame states

def frame_rows(path, rung, model):
    if not pathlib.Path(path).exists():
        return []
    rows, _ = load_run(path, "dims", MODELS)
    rows = [r for r in rows if r.get("rung") == rung]
    return [r for r in keep_analysable(rows, USABLE) if r["model"] == model]

_have = [g for g in FRAME_RUNGS if pathlib.Path(FRAME_OUT[g]).exists()]
if not _have:
    print("Cell 9b has not been run, so there is no %s arm to read." % FRAME_ALT)
    print("Nothing here is a null; there is simply no control yet.")
else:
    contrast_out, anchor_out = [], []
    for g in _have:
        for model in MODELS:
            a = paired_diffs(frame_rows(FRAME_OUT[g], g, model), USABLE,
                             "small_face", "large_face")
            b = paired_diffs(frame_rows(FRAME_BASE[g], g, model), USABLE,
                             "small_face", "large_face")
            m_a, _, _, n_a = paired_mean_ci([d for _, d in a])
            m_b, _, _, n_b = paired_mean_ci([d for _, d in b])
            mean, lo, hi, npos = paired_mean_ci(
                [d for _, d in paired_delta(a, b)])
            if not npos:
                v = "NOT RUN"
            elif lo > 0 or hi < 0:
                v = "FRAME EFFECT"
            elif hi < GATE_MIN and lo > -GATE_MIN:
                v = "no frame effect"
            else:
                v = "UNRESOLVED"
            contrast_out.append([g, model, n_b, fmt(m_b), n_a, fmt(m_a),
                                 fmt(mean), fmt(lo), fmt(hi), v])

            for label, path in (("named", FRAME_BASE[g]),
                                (FRAME_ALT, FRAME_OUT[g])):
                rs = frame_rows(path, g, model)
                named = [r for r in rs if r.get("resting_face")]
                opened = [r for r in rs
                          if r.get("opening_needed_m") is not None]
                anchor_out.append([
                    g, model, label, len(rs),
                    fmt(pct(sum(1 for r in opened
                                if abs(r["opening_needed_m"] - SMALL_OPENING)
                                < TOL), len(opened))),
                    fmt(pct(sum(1 for r in named
                                if r["resting_face"] == "small_face"),
                            len(named))) if named else "not asked",
                    fmt(pct(sum(1 for r in named
                                if r["resting_face"] == r.get("true_pose")),
                            len(named))) if named else "not asked"])

    show(["rung", "model", "n", "named", "n", FRAME_ALT,
          "delta", "lo", "hi", "verdict"], contrast_out)
    print()
    print("delta is %s minus named, paired within position at both frames."
          % FRAME_ALT)
    print()
    show(["rung", "model", "frame", "n", "reports 0.050", "says small_face",
          "face correct"], anchor_out)
    write_csv("tab_ex2_q3_frame.csv",
              ["rung", "model", "frame", "n_trials",
               "reports_small_opening_pct", "says_small_face_pct",
               "face_correct_pct"], anchor_out)
    print()
    print("=" * 70)
    print("WHAT THE TWO OUTCOMES MEAN, stated before the numbers are read")
    print("=" * 70)
    print("  anchor STAYS PUT   step 1 was never the problem. The model")
    print("                     already treated the stated size as a")
    print("                     convention, and the dims ladder measured")
    print("                     what it claims to measure.")
    print()
    print("  anchor FOLLOWS     the answer tracked the wording rather than")
    print("  the frame          the picture, and every dims number for that")
    print("                     model is about the glossary, not grounding.")
    print()
    print("GEMINI IS THE INTERNAL CONTROL. It reads the pose at 100% under")
    print("named. If its anchor moves too, the frame changed something other")
    print("than step 1 and neither column is about grounding for any model.")
    print()
    print("READ N0 FIRST. If a model already scores well there under %s," % FRAME_ALT)
    print("the instruction ladder was compensating for the glossary rather")
    print("than for a failure to ground, and cell 12's contrasts are about")
    print("the prompt's own wording.")'''


MD9D = r"""## Cell 9d. The ceiling: the complete procedure in `dims`

**Makes model calls.** The ladder tests each factor alone and one pair. It never
tests the whole procedure. `N-ACD` is `A + C + D` together: look at the image,
here is how the opening follows from the resting face, and state the face and
the opening before you name an arm.

**Why it is needed.** Without it a model that stops short at `N-CD` cannot be
told apart from one that was never asked for every step. *Cannot derive* and
*was not instructed to derive* predict the same number. `N-ACD` bounds what
instruction can achieve, which is what EX1's `givenset` does for that
experiment's spine.

**It is not pre-registered.** The first six rungs are; this was added on
2026-09-01 after they had been run, and `prompts.PRE_REGISTERED_LADDER` is what
any table presenting the ladder as a pre-registered design must read.

`A_ATTEND` is used unchanged, so `N-ACD` minus `N-CD` is the attention sentence
and nothing else. A stronger sentence naming the resting face as visible would
be a new factor with no single-factor cell of its own, and it would cross into
telling the model where the answer is, which is the directives' job."""

C9D = r'''# --- Cell 9d. CEILING: dims N-ACD. MAKES MODEL CALLS. -----------------------
CEIL_RUNG = "N-ACD"
CEIL_OUT = rung_file("dims", CEIL_RUNG)
CEIL_BASE = rung_file("dims", "N-CD")       # the rung it is read against

# The ceiling is only interpretable as A on top of C and D. If the rung ever
# stops being exactly that, the contrast stops being the attention sentence
# and the cell measures something it does not claim to.
if P.RUNGS[CEIL_RUNG]["text"] != P.A_ATTEND + P.C_DERIVE + P.D_ELICIT:
    raise AssertionError(
        "%s is not A_ATTEND + C_DERIVE + D_ELICIT. Its whole attribution is "
        "that it is N-CD plus the attention sentence, so %s minus N-CD is "
        "that sentence and nothing else." % (CEIL_RUNG, CEIL_RUNG))
if CEIL_RUNG in P.DIRECTIVE_RUNGS:
    raise AssertionError(
        "%s is classified as a directive. Every table that splits the ladder "
        "from the directives would file the ceiling with X-image, which "
        "presents a scaffolding rung as a provenance instruction."
        % CEIL_RUNG)
if CEIL_RUNG in P.PRE_REGISTERED_LADDER:
    raise AssertionError(
        "%s is inside PRE_REGISTERED_LADDER. It was added after the ladder "
        "was run and must not be presented as pre-registered." % CEIL_RUNG)

if not pathlib.Path(CEIL_BASE).exists():
    print("N-CD in dims is not on disk:")
    print("  %s" % rel(CEIL_BASE))
    print("Cell 9 buys it. The ceiling is read against it, so nothing bought.")
else:
    n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
    print("COST: %d scenes x %d models x %d repeat = %d calls"
          % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
    print("      dims %s, one cell." % CEIL_RUNG)
    print("      %3d of %d already answered" % (answered(CEIL_OUT), n_calls))
    print()
    print("      READ AGAINST, already on disk and costing nothing:")
    for _r in ("N0", "N-CD"):
        _f = N0_FILE["dims"] if _r == "N0" else rung_file("dims", _r)
        print("        %-5s %-44s %3d answered"
              % (_r, rel(_f), answered(_f) if pathlib.Path(_f).exists() else 0))
    print()
    print("      dims ONLY. In conflict_face the same rung would confound the")
    print("      procedure with precedence, which is what X-image measures.")
    print("      Keeping them in separate questions keeps both attributable.")

    CONFIRM_SPEND = None        # <-- set to the number in the COST line

    if spend_gate(n_calls, CONFIRM_SPEND, CEIL_OUT,
                  factors=(("scenes", len(CALL_SCENES)),
                           ("models", len(MODELS)), ("repeats", REPEATS))):
        S.run(str(CAPTURES), out_path=str(CEIL_OUT), models=MODELS,
              conditions=("dims",), preferences=(PREFERENCE,),
              rungs=(CEIL_RUNG,), modalities=("V",), kind="pair",
              repeats=REPEATS)
        print("answered now:", answered(CEIL_OUT))'''


MD9E = r"""## Cell 9e. Ceiling read-out

No model calls. Three readings, and the third is the one the cell exists for.

The **contrast** is where instruction tops out. The **delta against `N-CD`** is
what the attention sentence adds once derivation and elicitation are already in
place. The **face accuracy** says whether a model that still fails is failing to
see the pose or failing to act on the pose it named, which the arm contrast on
its own cannot distinguish."""

C9E = r'''# --- Cell 9e. Ceiling read-out. No model calls. -----------------------------
def ceil_rows(path, rung, model):
    if not pathlib.Path(path).exists():
        return []
    rows, _ = load_run(path, "dims", MODELS)
    rows = [r for r in rows if r.get("rung") == rung]
    return [r for r in keep_analysable(rows, USABLE) if r["model"] == model]

if not pathlib.Path(CEIL_OUT).exists():
    print("Cell 9d has not been run, so there is no ceiling to read.")
    print("This is not a null. There is simply no bound yet on what")
    print("instruction can achieve, and N-CD remains the highest rung.")
else:
    ceil_out, face_out = [], []
    for model in MODELS:
        a = paired_diffs(ceil_rows(CEIL_OUT, CEIL_RUNG, model), USABLE,
                         "small_face", "large_face")
        m_a, alo, ahi, n_a = paired_mean_ci([d for _, d in a])
        row = [model, fmt(m_a), fmt(alo), fmt(ahi), n_a]
        for base_rung, base_path in (("N-CD", CEIL_BASE),
                                     ("N0", N0_FILE["dims"])):
            b = paired_diffs(ceil_rows(base_path, base_rung, model), USABLE,
                             "small_face", "large_face")
            if not any(d is not None for _, d in b):
                row += ["NA", "NA", "NA"]
                continue
            mean, lo, hi, npos = paired_mean_ci(
                [d for _, d in paired_delta(a, b)])
            row += [fmt(mean), fmt(lo), fmt(hi)]
        ceil_out.append(row)

        # Did it name the face, and did it name it right? Only asked under
        # the face-first schema, which both N-ACD and N-CD use.
        for label, path, rung in ((CEIL_RUNG, CEIL_OUT, CEIL_RUNG),
                                  ("N-CD", CEIL_BASE, "N-CD")):
            rs = ceil_rows(path, rung, model)
            named = [r for r in rs if r.get("resting_face")]
            right = sum(1 for r in named
                        if r["resting_face"] == r.get("true_pose"))
            face_out.append([model, label, len(rs), len(named),
                             fmt(pct(right, len(named)))])

    show(["model", CEIL_RUNG, "lo", "hi", "npos",
          "vs N-CD", "lo", "hi", "vs N0", "lo", "hi"], ceil_out)
    print()
    print("vs N-CD is the ATTENTION SENTENCE, on top of derivation and")
    print("elicitation. vs N0 is everything instruction bought in dims.")
    print()
    show(["model", "rung", "n", "named", "face correct %"], face_out)
    write_csv("tab_ex2_q3_ceiling.csv",
              ["model", "rung", "n_trials", "n_named", "face_correct_pct"],
              face_out)
    print()
    print("=" * 70)
    print("HOW TO READ THE CEILING, stated before the numbers")
    print("=" * 70)
    print("A model still short of +100 here was told every step and did not")
    print("complete them. That bounds INSTRUCTION, not the model: a rung")
    print("cannot rule out that a differently worded procedure would do")
    print("better, and the chapter must say so rather than reading this as")
    print("a capability limit.")
    print()
    print("The face column separates the two ways of falling short:")
    print("  face right, contrast low   -> it saw the pose and did not act")
    print("                                on the pose it named")
    print("  face wrong, contrast low   -> it never had the pose to act on,")
    print("                                and no wording about DERIVING")
    print("                                from the pose can repair that")
    print()
    print("At %d positions and %d repeat an interval here is about %.0f points"
          % (len(USABLE), REPEATS, GATE_MIN))
    print("wide whatever the data, so read a small delta as unresolved.")'''


MD10 = r"""## Cell 10. The conflict-face ladder

**Makes model calls.** Every rung except `N0`, for every model, one repeat.

**Why `conflict_face` and not `conflict`.** Q3 asks which instruction moves a
model from following the text to using the scene. In `conflict` the state
supplies `opening_needed_m` and R3 names that field, so following the text is
**rule-compliant** and a rung effect there would answer a different question:
does the instruction make the model override a supplied value. In
`conflict_face` the number is withheld, R3 names nothing, and the only route to
an opening is a face -- one asserted by the text, one visible in the image. A
rung effect there is remediation of precedence, which is what Q3 asks about.

The baseline is Q2's `conflict_face` at N0, where GPT reads -89.6 and Gemini
-100.0 against ceilings of +87.5 and +100.0. Claude is a null in both and has
no source to prefer, so a rung that moves it would be teaching it to derive at
all rather than to prefer the scene."""

C10 = r'''# --- Cell 10. The conflict_face ladder. MAKES MODEL CALLS. ------------------
CONFLICT_RUNGS = tuple(r for r in LADDER if r != "N0")

if not pathlib.Path(N0_FILE["conflict_face"]).exists():
    print("Q2's conflict_face N0 file is not on disk:")
    print("  %s" % rel(N0_FILE["conflict_face"]))
    print("Every contrast here is against it, so this cannot be read until")
    print("Q2 cell 6b has been run. Nothing bought.")
else:
    n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS * len(CONFLICT_RUNGS)
    print("COST: %d scenes x %d models x %d repeat x %d rungs = %d calls"
          % (len(CALL_SCENES), len(MODELS), REPEATS, len(CONFLICT_RUNGS),
             n_calls))
    print("      rungs: %s" % ", ".join(CONFLICT_RUNGS))
    for rung in CONFLICT_RUNGS:
        _f = rung_file("conflict_face", rung)
        print("      %-8s %3d of %d answered"
              % (rung, answered(_f), len(CALL_SCENES) * len(MODELS)))

    CONFIRM_SPEND = None        # <-- set to the number in the COST line

    if spend_gate(n_calls, CONFIRM_SPEND,
                  factors=(("scenes", len(CALL_SCENES)),
                           ("models", len(MODELS)), ("repeats", REPEATS),
                           ("rungs", len(CONFLICT_RUNGS)))):
        for rung in CONFLICT_RUNGS:
            out = rung_file("conflict_face", rung)
            print("\n--- conflict_face %s ---" % rung)
            S.run(str(CAPTURES), out_path=str(out), models=MODELS,
                  conditions=("conflict_face",), preferences=(PREFERENCE,),
                  rungs=(rung,), modalities=("V",), kind="pair",
                  repeats=REPEATS)
        print("\nconflict_face ladder complete")'''


MD10B = r"""## Cell 10b. Stage 1: the precedence directive in `conflict_face`

**Makes model calls.** The run this notebook exists to add: does telling a model
*where the image and the stated resting face disagree, go by the image* move it
off the false stated face?

Read against two files already on disk. `N0` is the baseline. `N-A` is the more
informative one: it says "look at the image" without naming the face or admitting
a conflict, and `X-image` is literally that text plus one sentence, so
`X-image - N-A` is the precedence sentence and nothing else."""

C10B = r'''# --- Cell 10b. STAGE 1: X-image in conflict_face. MAKES MODEL CALLS. --------
DIRECTIVE_COND, DIRECTIVE = DIRECTIVE_STAGE1[0]
DIRECTIVE_OUT = rung_file(DIRECTIVE_COND, DIRECTIVE)

if not pathlib.Path(N0_FILE[DIRECTIVE_COND]).exists():
    print("Q2's %s N0 file is not on disk:" % DIRECTIVE_COND)
    print("  %s" % rel(N0_FILE[DIRECTIVE_COND]))
    print("The headline contrast is against it, so this cannot be read until")
    print("Q2 has been run. Nothing bought.")
else:
    n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
    print("COST: %d scenes x %d models x %d repeats = %d calls"
          % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
    print("      %s in %s, one cell." % (DIRECTIVE, DIRECTIVE_COND))
    print("      %3d of %d already answered"
          % (answered(DIRECTIVE_OUT), n_calls))
    print()
    print("      READ AGAINST, already on disk and costing nothing:")
    for _r in ("N0", "N-A"):
        _f = N0_FILE[DIRECTIVE_COND] if _r == "N0" else rung_file(
            DIRECTIVE_COND, _r)
        print("        %-4s %-46s %3d answered"
              % (_r, rel(_f), answered(_f) if pathlib.Path(_f).exists() else 0))
    print()
    print("      dims is NOT here and cannot be: it states no resting face,")
    print("      so the directive is vacuous there and solo refuses to render")
    print("      it before a single call is made.")

    CONFIRM_SPEND = None        # <-- set to the number in the COST line

    if spend_gate(n_calls, CONFIRM_SPEND, DIRECTIVE_OUT,
                  factors=(("scenes", len(CALL_SCENES)),
                           ("models", len(MODELS)), ("repeats", REPEATS))):
        S.run(str(CAPTURES), out_path=str(DIRECTIVE_OUT), models=MODELS,
              conditions=(DIRECTIVE_COND,), preferences=(PREFERENCE,),
              rungs=(DIRECTIVE,), modalities=("V",), kind="pair",
              repeats=REPEATS)
        print("answered now:", answered(DIRECTIVE_OUT))'''


MD10C = r"""## Cell 10c. Stage 1 read-out, and the gate on stage 2

No model calls. Three outcomes per model, as in cell 7: **moved**, **not
moved**, **unresolved**. The two controls in cell 10d exist only to interpret a
model that moved, so a model that did not move buys nothing further."""

C10C = r'''# --- Cell 10c. Directive read-out. No model calls. --------------------------
DIRECTIVE_VERDICT = {}
dir_read = []
for model in MODELS:
    a = contrast_pairs(DIRECTIVE_COND, DIRECTIVE, model)
    b = contrast_pairs(DIRECTIVE_COND, "N0", model)
    c = contrast_pairs(DIRECTIVE_COND, "N-A", model)
    m_0, _, _, _ = paired_mean_ci([d for _, d in b])
    m_a, _, _, _ = paired_mean_ci([d for _, d in c])
    m_x, _, _, _ = paired_mean_ci([d for _, d in a])
    mean, lo, hi, npos = paired_mean_ci([d for _, d in paired_delta(a, b)])
    _sent = paired_mean_ci([d for _, d in paired_delta(a, c)])
    if not npos:
        v = "NOT RUN"
    elif lo > 0:
        v = "MOVED"
    elif hi < 0:
        v = "MOVED BACKWARDS"
    elif hi < GATE_MIN:
        v = "NOT MOVED"
    else:
        v = "UNRESOLVED"
    DIRECTIVE_VERDICT[model] = v
    dir_read.append([model, fmt(m_0), fmt(m_a), fmt(m_x), npos, fmt(mean),
                     fmt(lo), fmt(hi), fmt(_sent[0]), v])

show(["model", "N0", "N-A", DIRECTIVE, "npos", "vs N0", "lo", "hi",
      "vs N-A", "verdict"], dir_read)
write_csv("tab_ex2_q3_directive_gate.csv",
          ["model", "n0", "n_a", "directive", "npos", "delta_vs_n0",
           "lo", "hi", "delta_vs_n_a", "verdict"], dir_read)
print()
print("\"vs N0\" is the total movement a direct instruction buys. \"vs N-A\"")
print("subtracts being told to look at the image, leaving the precedence")
print("sentence alone. Both are paired within position at each level.")
print()
print("A model reads UNRESOLVED when the interval still admits an effect of")
print("%.0f points or more. That is not a null." % GATE_MIN)
print()
DIRECTIVE_PROCEED = [m for m in MODELS
                     if DIRECTIVE_VERDICT[m] in ("MOVED", "MOVED BACKWARDS",
                                                 "UNRESOLVED")]
for model in MODELS:
    print("  %-9s %s" % (model, DIRECTIVE_VERDICT[model]))
if DIRECTIVE_PROCEED:
    print()
    print("STAGE 2 IS WORTH BUYING. %s did not come back a flat null, and a"
          % ", ".join(DIRECTIVE_PROCEED))
    print("number that moved is exactly the number the two controls are")
    print("needed to interpret:")
    print("  congruent_face @ X-image  rules out that ANY extra sentence")
    print("                            would have done it")
    print("  conflict_face  @ X-state  rules out that the model merely heard")
    print("                            the word \"image\"")
else:
    print()
    print("STAGE 2 BUYS NOTHING. No model moved, so there is no effect for")
    print("either control to explain away. Report the null and stop; cell 10d")
    print("will refuse on its own gate.")'''


MD10D = r"""## Cell 10d. Stage 2: the two controls

**Makes model calls.** Bought only if cell 10c says a model moved. Each control
rules out one competing explanation for that movement, and neither is worth
buying against a flat null."""

C10D = r'''# --- Cell 10d. STAGE 2: the directive controls. MAKES MODEL CALLS. ----------
if not DIRECTIVE_PROCEED:
    print("Cell 10c reports no movement in any model, so neither control has")
    print("anything to control for. Nothing bought.")
else:
    n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS * len(DIRECTIVE_STAGE2)
    print("COST: %d scenes x %d models x %d repeats x %d cells = %d calls"
          % (len(CALL_SCENES), len(MODELS), REPEATS, len(DIRECTIVE_STAGE2),
             n_calls))
    for _c, _r in DIRECTIVE_STAGE2:
        print("      %-15s %-8s %3d of %d answered"
              % (_c, _r, answered(rung_file(_c, _r)),
                 len(CALL_SCENES) * len(MODELS) * REPEATS))

    CONFIRM_SPEND = None        # <-- set to the number in the COST line

    if spend_gate(n_calls, CONFIRM_SPEND,
                  factors=(("scenes", len(CALL_SCENES)),
                           ("models", len(MODELS)), ("repeats", REPEATS),
                           ("cells", len(DIRECTIVE_STAGE2)))):
        for _c, _r in DIRECTIVE_STAGE2:
            out = rung_file(_c, _r)
            print("\n--- %s %s ---" % (_c, _r))
            S.run(str(CAPTURES), out_path=str(out), models=MODELS,
                  conditions=(_c,), preferences=(PREFERENCE,), rungs=(_r,),
                  modalities=("V",), kind="pair", repeats=REPEATS)
        print("\ndirective controls complete")'''


MD11 = r"""## Cell 11. What is on disk

No model calls. One row per condition and rung, with the row count, the models
present and whether the file's own `rung` field matches the file it is in.

That last check is not ceremony: a rung recorded under the wrong name is
exactly the failure `solo`'s `trial_id` scheme exists to prevent, and it would
show up as a rung that mysteriously did nothing."""

C11 = r'''# --- Cell 11. Rung inventory. No model calls. -------------------------------
inv, problems = [], []
AVAILABLE = []
# The directive cells go in as their own (condition, rung) entries rather
# than being folded into LADDER: conflict_face then appears twice, once for
# the ladder and once for its directives, and congruent_face gains a rung
# without becoming a ladder condition. Everything downstream reads
# AVAILABLE, so cells 12 and 14 pick them up for free.
_plan = ([(c, LADDER) for c in CONDITIONS]
         + [(c, ("N0",)) for c in BASELINES]
         + [(c, (r,)) for c, r in DIRECTIVE_CELLS])
for cond, _rungs in _plan:
    for rung in _rungs:
        path = N0_FILE[cond] if rung == "N0" else rung_file(cond, rung)
        if not pathlib.Path(path).exists():
            inv.append([cond, rung, rel(path), 0, "", "-", "missing"])
            continue
        rows, _ = load_run(path, cond, MODELS)
        wrong = sorted({r.get("rung") for r in rows} - {rung})
        if wrong:
            problems.append("%s holds rungs %s, expected %s only"
                            % (rel(path), wrong, rung))
        rows = [r for r in rows if r.get("rung") == rung]
        keep = keep_analysable(rows, USABLE)
        mods = sorted({r["model"] for r in keep})
        inv.append([cond, rung, rel(path), len(rows), ";".join(mods),
                    "%d" % len(keep),
                    "ok" if keep else "empty"])
        if keep:
            AVAILABLE.append((cond, rung, mods))

show(["condition", "rung", "file", "rows", "models", "analysable", "state"],
     inv)
if problems:
    raise AssertionError("RUNG LABEL MISMATCH:\n  " + "\n  ".join(problems))
print()
print("PASS  every file on disk carries only the rung its name claims.")
print()
print("BASELINES, at N0 only: %s. No rung is planned in them; they are"
      % ", ".join(BASELINES))
print("here because a rung effect is only readable against the ceiling for")
print("its own condition. congruent_face is the ceiling for conflict_face,")
print("and both are the ceiling for anything the ladder does to dims.")
print()
print("The N0 rows come from Q1 and Q2. Every file here, baseline and rung")
print("alike, holds 612 distinct trials at %d repeats, so the second-order"
      % REPEATS)
print("contrasts below are read at the same resolution as Q1's and Q2's.")
print()
print("The X- rows are the off-ladder precedence directives, not rungs. They")
print("are read in cell 12b, against N0 and against N-A.")'''


MD12 = r"""## Cell 12. Each rung against N0

No model calls. The contrast at each rung, and the change from `N0`, computed
**within condition** and never pooled across conditions: `C` supplies a missing
fact in `dims` and has to override a supplied one in `conflict`, so the two are
different manipulations wearing the same name."""

C12 = r'''# --- Cell 12. Rung contrasts against N0. No model calls. --------------------
contrast_rows = []
for cond, rung, mods in AVAILABLE:
    for model in mods:
        a = contrast_pairs(cond, rung, model)
        m_r, rlo, rhi, n_r = paired_mean_ci([d for _, d in a])
        if rung == "N0":
            contrast_rows.append([cond, model, rung, n_r, fmt(m_r), fmt(rlo),
                                  fmt(rhi), "-", "-", "-", "-"])
            continue
        b = contrast_pairs(cond, "N0", model)
        delta = paired_delta(a, b)
        mean, lo, hi, npos = paired_mean_ci([d for _, d in delta])
        contrast_rows.append([cond, model, rung, n_r, fmt(m_r), fmt(rlo),
                              fmt(rhi), npos, fmt(mean), fmt(lo), fmt(hi)])

show(["condition", "model", "rung", "npos", "contrast", "c_lo", "c_hi",
      "n_delta", "delta_vs_N0", "d_lo", "d_hi"], contrast_rows)
write_csv("tab_ex2_q3_contrasts.csv",
          ["condition", "model", "rung", "n_positions", "contrast_pts",
           "contrast_lo", "contrast_hi", "n_positions_delta",
           "delta_vs_N0_pts", "delta_lo", "delta_hi"], contrast_rows)
print()
print("contrast is the same small_minus_large Q1 and Q2 report, at that rung.")
print("delta_vs_N0 is how far the rung moved it, paired within position at")
print("both levels. A saturated rung has no useful interval on the contrast")
print("itself; read the delta.")'''


MD12B = r"""## Cell 12b. The precedence directives, read

No model calls. The headline and its two controls in one table, with the
`congruent_face` `N0` ceiling beside them so the movement is read against how
far there was to move.

Each row is a paired within-position difference of the small-face against
large-face contrast, then differenced again against the comparison level."""

C12B = r'''# --- Cell 12b. The directive read-out. No model calls. ----------------------
DIRECTIVE_READS = (
    ("headline", "conflict_face", "X-image", "N0",
     "does the instruction move the model off the false stated face"),
    ("sentence only", "conflict_face", "X-image", "N-A",
     "subtracts being told to look; leaves the precedence sentence alone"),
    ("control: wording", "congruent_face", "X-image", "N0",
     "same prompt, antecedent never satisfied; movement here is not obedience"),
    ("control: symmetry", "conflict_face", "X-state", "N0",
     "one word different, still names the image; movement toward the picture "
     "here means the model is not reading which source was named"),
)

dir_rows = []
for label, cond, rung, against, why in DIRECTIVE_READS:
    for model in MODELS:
        a = contrast_pairs(cond, rung, model)
        b = contrast_pairs(cond, against, model)
        if not a or not b:
            dir_rows.append([label, cond, rung, against, model, 0, "-", "-",
                             "-", "not run"])
            continue
        mean, lo, hi, npos = paired_mean_ci([d for _, d in paired_delta(a, b)])
        # Keyed on npos first. An empty cell yields nan bounds, and
        # spans_zero counts nan as spanning, so a cell that was never run
        # would otherwise be reported as an interval consistent with no
        # effect -- a null read out of a file that does not exist.
        if not npos:
            interval = "not run"
        else:
            interval = "spans zero" if spans_zero(lo, hi) else "excludes zero"
        dir_rows.append([label, cond, rung, against, model, npos, fmt(mean),
                         fmt(lo), fmt(hi), interval])

show(["read", "condition", "rung", "vs", "model", "npos", "delta", "lo", "hi",
      "interval"], dir_rows)
write_csv("tab_ex2_q3_directive.csv",
          ["read", "condition", "rung", "against", "model", "npos", "delta",
           "lo", "hi", "interval"], dir_rows)

print()
print("THE CEILING, for scale. congruent_face at N0 is how far there was to")
print("move: the same prompt with a TRUE stated face, where no arbitration is")
print("required of the model at all.")
for model in MODELS:
    _c = contrast_pairs("congruent_face", "N0", model)
    m, lo, hi, n = paired_mean_ci([d for _, d in _c])
    print("  %-9s %s  [%s, %s]  over %d positions"
          % (model, fmt(m), fmt(lo), fmt(hi), n))
print()
for label, cond, rung, against, why in DIRECTIVE_READS:
    print("%-18s %s" % (label + ":", why))
print()
print("HOW TO READ THIS. The headline is only obedience if BOTH controls are")
print("flat. A wording control that moves says the model responded to having")
print("an extra sentence. A symmetry control that moves the same way says it")
print("responded to the word \"image\" rather than to which source was named.")
print()
print("LIMITATION, stated wherever this table is quoted. X uses the base")
print("schema, so the arm is committed before the opening is written. A model")
print("that did not move cannot be told apart from one that obeyed too late")
print("in the generation. Giving the directive the face-first schema would")
print("fix that and confound precedence with factor D, so it is not done.")'''


MD13 = r"""## Cell 13. Attribution

No model calls.

**State this before reading the table.** These are differences of paired
differences. At 32 positions and one repeat the interval on one of them is
roughly 30 points whatever the data, so **small ladder effects are not
resolvable by this design**. A wide interval here is the design's resolution
showing, not evidence of no effect, and it must not be reported as a null.

- `N-D` minus `N-C` — does elicitation supply a missing fact, or force the
  application of one the model already held?
- `N-D` minus `N-order` — is `N-D`'s effect the instruction, or the field order
  it also changes?"""

C13 = r'''# --- Cell 13. Attribution. No model calls. ----------------------------------
print("=" * 70)
print("RESOLUTION, stated before the numbers")
print("=" * 70)
print("These are differences of PAIRED DIFFERENCES. At %d positions and %d"
      % (len(USABLE), REPEATS))
print("repeat the interval on one is roughly %.0f points whatever the data." % GATE_MIN)
print("An interval that spans zero here means THE DESIGN CANNOT RESOLVE IT.")
print("It is not evidence of no effect and must not be written as one.")
print()

ATTRIB = (("N-D_minus_N-C", "N-D", "N-C",
           "does elicitation supply a missing fact, or force the "
           "application of one already held"),
          ("N-D_minus_N-order", "N-D", "N-order",
           "is N-D's effect the instruction, or the field order"))

have = {(c, r) for c, r, _ in AVAILABLE}
attrib_rows = []
for name, ra, rb, _q in ATTRIB:
    for cond in CONDITIONS:
        if (cond, ra) not in have or (cond, rb) not in have:
            continue
        for model in MODELS:
            a = contrast_pairs(cond, ra, model)
            b = contrast_pairs(cond, rb, model)
            if not any(d is not None for _, d in a) or \
               not any(d is not None for _, d in b):
                continue
            delta = paired_delta(a, b)
            mean, lo, hi, npos = paired_mean_ci([d for _, d in delta])
            verdict = ("NOT RESOLVABLE" if npos and hi - lo > 2 * GATE_MIN
                       and spans_zero(lo, hi)
                       else "positive" if lo > 0
                       else "negative" if hi < 0
                       else "spans zero")
            attrib_rows.append([cond, model, name, npos, fmt(mean), fmt(lo),
                                fmt(hi), verdict])

if not attrib_rows:
    print("Neither rung pair is on disk yet, so there is nothing to")
    print("attribute. Cell 9 buys N-C and N-order.")
else:
    show(["condition", "model", "contrast", "npos", "mean", "lo", "hi",
          "reading"], attrib_rows)
    write_csv("tab_ex2_q3_attribution.csv",
              ["condition", "model", "contrast", "n_positions", "mean_pts",
               "paired_lo", "paired_hi", "reading"], attrib_rows)
    print()
    for name, ra, rb, q in ATTRIB:
        print("  %-18s %s" % (name, q))'''


MD14 = r"""## Cell 14. Does the reported opening improve with rung

No model calls. `opening_needed_m` is a self-report and never a scored endpoint
on its own, but it localises the failure: a rung that fixes the arm without
fixing the reported opening is doing something other than what it claims."""

C14 = r'''# --- Cell 14. Reported opening by rung. No model calls. ---------------------
TOL = 0.006          # grade.classify_width's tolerance, not a new one
rep_rows = []
for cond, rung, mods in AVAILABLE:
    for model in mods:
        for face in FACES:
            sub = [r for r in rung_rows_for(cond, rung)
                   if r["model"] == model and r["face"] == face]
            stated = [r for r in sub if r.get("opening_needed_m") is not None]
            true_open = FACTS[face]["grasp_m"]
            right = sum(1 for r in stated
                        if abs(r["opening_needed_m"] - true_open) <= TOL)
            lo, hi = wilson(right, len(stated))
            rep_rows.append([cond, model, rung, face, len(sub), len(stated),
                             right, fmt(pct(right, len(stated))), fmt(lo),
                             fmt(hi)])

show(["condition", "model", "rung", "face", "trials", "stated", "correct",
      "pct", "lo", "hi"], rep_rows)
write_csv("tab_ex2_q3_reported.csv",
          ["condition", "model", "rung", "resting_face", "n_trials",
           "n_stated", "n_correct", "correct_pct", "wilson_lo", "wilson_hi"],
          rep_rows)
print()
print("In CONFLICT the true opening is not the declared one, so a low score")
print("here is a model believing the text, not a model failing to derive.")
print("Cross-read it with Q2's tab_ex2_q2_source.csv before calling it an")
print("error.")'''


MD15 = r"""## Cell 15. The face the model names

No model calls, and **only `N-D` and `N-CD` ask for it**, because those are the
rungs whose schema is `face_first`.

Reported separately from the opening, because a model that names the face
correctly and still gives the wrong opening has failed at the derivation, while
one that names it wrongly has failed at the perception. Q1 could not see this
distinction: no rung it ran required the face."""

C15 = r'''# --- Cell 15. Face-report accuracy. No model calls. -------------------------
FACE_RUNGS = tuple(r for r in LADDER
                   if P.RUNGS[r]["schema"] == "face_first")
print("rungs whose schema asks for the face: %s" % ", ".join(FACE_RUNGS))
print()
face_rows = []
for cond, rung, mods in AVAILABLE:
    if rung not in FACE_RUNGS:
        continue
    for model in mods:
        sub = [r for r in rung_rows_for(cond, rung) if r["model"] == model]
        named = [r for r in sub if r.get("resting_face")]
        right = sum(1 for r in named if r["resting_face"] == r["true_pose"])
        lo, hi = wilson(right, len(named))
        # The cell that matters: face right, opening wrong.
        split = sum(1 for r in named
                    if r["resting_face"] == r["true_pose"]
                    and r.get("opening_needed_m") is not None
                    and abs(r["opening_needed_m"]
                            - FACTS[r["true_pose"]]["grasp_m"]) > 0.006)
        face_rows.append([cond, model, rung, len(sub), len(named), right,
                          fmt(pct(right, len(named))), fmt(lo), fmt(hi),
                          split])

if not face_rows:
    print("No face_first rung is on disk yet. Cell 6 buys %s." % GATE_RUNG)
else:
    show(["condition", "model", "rung", "trials", "named", "correct", "pct",
          "lo", "hi", "face_right_open_wrong"], face_rows)
    write_csv("tab_ex2_q3_face.csv",
              ["condition", "model", "rung", "n_trials", "n_named",
               "n_correct", "correct_pct", "wilson_lo", "wilson_hi",
               "n_face_right_opening_wrong"], face_rows)
    print()
    print("face_right_open_wrong is the diagnostic cell. A model there SAW")
    print("the orientation and still could not turn it into an opening,")
    print("which is a derivation failure. A low correct_pct instead is a")
    print("perception failure, and the two want different remedies.")'''


MD16 = r"""## Cell 16. Provenance

No model calls. Every file this notebook read, with its row count and hash, the
prompt version, the models and the date."""

C16 = r'''# --- Cell 16. Provenance. No model calls. -----------------------------------
prov = []
today = datetime.date.today().isoformat()
prov.append(provenance_row("captures", CAPTURES / "consults.jsonl", OUT,
                           today=today,
                           default_version=P.EX2_PROMPT_VERSION))
for cond in CONDITIONS:
    for rung in LADDER:
        path = N0_FILE[cond] if rung == "N0" else rung_file(cond, rung)
        if pathlib.Path(path).exists():
            prov.append(provenance_row("%s_%s" % (cond, rung), path, OUT,
                                       today=today,
                                       default_version=P.EX2_PROMPT_VERSION))
for cond, rung in DIRECTIVE_CELLS:
    path = rung_file(cond, rung)
    if pathlib.Path(path).exists():
        prov.append(provenance_row("%s_%s" % (cond, rung), path, OUT,
                                   today=today,
                                   default_version=P.EX2_PROMPT_VERSION))
if pathlib.Path(CONTROL_OUT).exists():
    prov.append(provenance_row("dims_%s_noimage" % GATE_RUNG, CONTROL_OUT,
                               OUT, today=today,
                               default_version=P.EX2_PROMPT_VERSION))

show(["role", "rows", "sha256", "prompt_version", "models"],
     [[r[0], r[2], (r[3] or "")[:12], r[4], r[5]] for r in prov])
write_csv("tab_ex2_q3_provenance.csv",
          ["role", "path", "rows", "sha256", "prompt_version", "model_string",
           "run_date"], prov)

print()
print("DESIGN FACTS THAT MUST BE DISCLOSED IN THE CHAPTER")
print("-" * 70)
print("1. The gate rung is %s, not N-CD. The 2026-08-27 pilots already showed"
      % GATE_RUNG)
print("   gemini going from 46.9 at N0 to a complete flip under N-D alone,")
print("   with the face named correctly on every trial, and gpt not moving,")
print("   so elicitation is the rung the evidence implicates. N-CD is a")
print("   sufficiency cell for a model N-D does not move, never an")
print("   interaction test: this design is not powered for one.")
print("2. Rungs and baselines alike run at %d repeats over 612 trials, so an"
      % REPEATS)
print("   interval spanning zero is the design's resolution, not evidence")
print("   of no effect.")
print("3. X-image and X-state are NOT rungs. They break the boundary rule the")
print("   four factors are held to -- they name the stated resting face and")
print("   say the image can contradict it -- so they are off the ladder, they")
print("   are refused in dims, and they answer a different question: whether")
print("   a model has an arbitration step an instruction can reach at all.")
print("   Cell 4b prints their wording; cell 12b reads them.")
print("3. Contrasts are computed WITHIN condition and never pooled across")
print("   them: C supplies a missing fact in dims and overrides a supplied")
print("   one in conflict, so it is two manipulations under one name.")
print("4. N-order is the control for N-D. N-D changes the wording AND the")
print("   field order, and a model generates left to right, so without the")
print("   order control an N-D effect could not be attributed to either.")
print("5. resting_face is asked for only at %s. Asking at every rung would"
      % ", ".join(FACE_RUNGS))
print("   tell the model the face matters, which is what factor D")
print("   manipulates.")
print("6. The dims gate file is SEEDED from two 2026-08-27 pilot files,")
print("   runs/ex2_q1_dims_N-D_effort.jsonl and ..._N-D_order.jsonl, which")
print("   hold this exact cell for gpt_hi and gemini at the same prompt")
print("   version. Those rows were collected on 2026-08-27, not in this")
print("   sweep, and the seeding filter rebuilds the trial_id this cell")
print("   would ask for so that no other factor arm can enter. The row")
print("   count above therefore mixes two collection dates, which is what")
print("   resuming a run always does and is why the hash is recorded.")
print("7. Stage 3 is a PROBE plus a gated expansion, not the full ladder.")
print("   N-CD runs in conflict for all three models; the other four rungs")
print("   are bought only for models it moved. Buying all five for all")
print("   three would have been 1,020 calls, 65 percent of the notebook,")
print("   spent before knowing whether any instruction moves anything in a")
print("   condition Q2 measured at -100 points unanimously.")
print("8. Prompt version %s. Preference %s. %d usable positions."
      % (P.EX2_PROMPT_VERSION, PREFERENCE, len(USABLE)))'''
