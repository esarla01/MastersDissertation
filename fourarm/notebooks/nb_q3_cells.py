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
if set(LADDER) != set(P.RUNGS):
    raise SystemExit("the prompt module defines %s; this notebook names %s"
                     % (sorted(P.RUNGS), sorted(LADDER)))

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
for rung in LADDER:
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
print("PRE-REGISTERED PREDICTIONS, from prompts.PREDICTIONS:")
for k, v in sorted(P.PREDICTIONS.items()):
    print("  %-12s %s" % (k, v))
print()
print("N-order exists because N-D moves the report ahead of the arm AND asks")
print("for the face, and a model generates left to right. Without the order")
print("control an N-D effect could not be attributed to either.")
print("N-CD is a sufficiency cell against N0. It is never an interaction")
print("test: this design is not powered for one and does not claim to be.")'''


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
    for rung in LADDER:
        if rung == "N0":
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
    used = [r for r in LADDER if P.RUNGS[r]["schema"] == name]
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


MD11 = r"""## Cell 11. What is on disk

No model calls. One row per condition and rung, with the row count, the models
present and whether the file's own `rung` field matches the file it is in.

That last check is not ceremony: a rung recorded under the wrong name is
exactly the failure `solo`'s `trial_id` scheme exists to prevent, and it would
show up as a rung that mysteriously did nothing."""

C11 = r'''# --- Cell 11. Rung inventory. No model calls. -------------------------------
inv, problems = [], []
AVAILABLE = []
_plan = ([(c, LADDER) for c in CONDITIONS]
         + [(c, ("N0",)) for c in BASELINES])
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
print("The N0 rows come from Q1 and Q2, at 3 repeats for the number")
print("conditions and 1 for the face ones.")
print("Every rung file here is at %d. A rung's per-position share is" % REPEATS)
print("therefore 0 or 100 while the baseline's is one of four values, so the")
print("second-order contrasts below are noisier than Q1's and Q2's. Say so")
print("beside any number quoted from them.")'''


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
print("2. Rungs run at %d repeat against N0 baselines at 3. The second-order"
      % REPEATS)
print("   contrasts are correspondingly noisier and an interval spanning")
print("   zero is the design's resolution, not evidence of no effect.")
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
