"""Cells for ex2_q3_repair.ipynb -- the four runs of the Q3 Repair design.

WHAT THIS BUYS. Two steps, each addressed twice: once by supplying information
the model may be missing, once by rephrasing the question while supplying
nothing. Two of the four cells are already on disk from the ladder. This
notebook buys the other two, plus two controls.

    run           condition        rung     repeats   what it answers
    control A     congruent_face   N-CD     1         does the measurement still work
    control B     dims             N-CD     1         have the models drifted
    treatment 1   dims             N-S      3         staged report, step 2, rephrased
    treatment 2   dims             N-BCD    3         description, step 1, supplied

CONTROLS FIRST, AND THEY GATE. Cell 5 refuses to report the treatments until
both controls have landed and passed. A treatment measured against a baseline
the models no longer reproduce is not a measurement, and finding that out
after spending on 800 calls rather than before spending on 272 is the whole
reason the two controls exist.

GEMINI IS NOT RUN. It reaches 100.0 from N-D onward under dims and has nothing
left to repair. Claude is run as a negative control rather than as a
candidate: its step 2 fails even when the face is supplied, so neither
treatment should move it.

THE PREDICTIONS ARE NOT IN THIS FILE. They are in prompts.PREDICTIONS, which
was committed before either treatment had been called once, and cell 5 prints
them from there rather than restating them. A prediction a notebook can edit
after seeing the numbers is not a prediction.
"""

MD_CONTROLS = """## Controls. Run these first.

**Make model calls,** one repeat each, about \\num{272} calls in total.

Neither control is a treatment. Each is a configuration already characterised
by earlier work, re-bought now so that the treatments have something to be
measured against.

**Control A**, `congruent_face` at `N-CD`, supplies the face and the rule and
withholds only the opening. GPT reached a contrast of 89.6 on this condition at
`N0`; with the rule added it cannot do worse for a reason that is about the
models. A low value here means the instrument, not the model.

**Control B**, `dims` at `N-CD`, is the configuration both step-1 treatments are
read against. It must reproduce the 32.3 already reported for GPT and the 0.0
for Claude. A departure means the models have changed since those runs and that
no treatment below can be compared with them.

Both resume: `solo.run` appends and flushes each row as it lands and skips
every trial already answered, so interrupting a cell costs nothing."""

C_CTRL_A = r'''# --- Control A. congruent_face at N-CD. MAKES MODEL CALLS. ------------------
CTRL_A_OUT = RUNS / "ex2_q3_ctrlA_congruent_face_N-CD.jsonl"
CTRL_REPEATS = 1          # bound locally: a later cell rebinds REPEATS

n_calls = len(CALL_SCENES) * len(MODELS) * CTRL_REPEATS
print("COST: %d scenes x %d models x %d repeat = %d calls"
      % (len(CALL_SCENES), len(MODELS), CTRL_REPEATS, n_calls))
print("      congruent_face at N-CD. The face and the rule are both given,")
print("      so only the conversion is at stake. GPT read 89.6 on this")
print("      condition at N0; anything near zero here is the instrument.")

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, CTRL_A_OUT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", CTRL_REPEATS))):
    S.run(str(CAPTURES), out_path=str(CTRL_A_OUT), models=MODELS,
          conditions=("congruent_face",), preferences=(PREFERENCE,),
          rungs=("N-CD",), modalities=("V",), kind="pair",
          repeats=CTRL_REPEATS)
    print("answered now:", answered(CTRL_A_OUT))'''

C_CTRL_B = r'''# --- Control B. dims at N-CD. MAKES MODEL CALLS. ----------------------------
CTRL_B_OUT = RUNS / "ex2_q3_ctrlB_dims_N-CD.jsonl"
CTRL_REPEATS = 1

# ITS OWN FILE, not runs/ex2_q3_dims_N-CD.jsonl. The trial_id carries the
# rung and the repeat but not the date, so a fresh repeat 1 written into the
# old file would be skipped as already answered and this cell would report
# itself complete having made no calls. That is exactly the failure it
# exists to detect, and it would report a pass.
n_calls = len(CALL_SCENES) * len(MODELS) * CTRL_REPEATS
print("COST: %d scenes x %d models x %d repeat = %d calls"
      % (len(CALL_SCENES), len(MODELS), CTRL_REPEATS, n_calls))
print("      dims at N-CD, the baseline both step-1 treatments are read")
print("      from. Must reproduce GPT 32.3 [23.3, 41.3] and Claude 0.0.")

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, CTRL_B_OUT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", CTRL_REPEATS))):
    S.run(str(CAPTURES), out_path=str(CTRL_B_OUT), models=MODELS,
          conditions=("dims",), preferences=(PREFERENCE,),
          rungs=("N-CD",), modalities=("V",), kind="pair",
          repeats=CTRL_REPEATS)
    print("answered now:", answered(CTRL_B_OUT))'''

MD_TREAT = """## Treatments

**Make model calls,** three repeats each, about \\num{816} calls in total.

`N-S` is the staged report: the baseline instruction with one required field
between the face and the opening, and no relation stated. It is read against
`N-D`, already on disk.

`N-BCD` is the description: `candidate_faces_m` added to every object in the
state, and one sentence naming the field. It is read against `N-CD`, which
control B has just re-bought.

Do not run these until cell 5 says both controls passed."""

C_TREAT_S = r'''# --- Treatment 1. dims at N-S. MAKES MODEL CALLS. ---------------------------
TREAT_S_OUT = RUNS / "ex2_q3_dims_N-S.jsonl"

n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
print("COST: %d scenes x %d models x %d repeats = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
print("      dims at N-S, read against N-D. Conversion at N-D is 65.1%")
print("      for GPT on replies that named the face correctly.")

# The schema must carry the field the block asks for, checked here rather
# than discovered in the replies.
assert "horizontal_extents_m" in P.SCHEMAS[P.RUNGS["N-S"]["schema"]], (
    "N-S asks for an intermediate the answer schema gives it nowhere to put")

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, TREAT_S_OUT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", REPEATS))):
    S.run(str(CAPTURES), out_path=str(TREAT_S_OUT), models=MODELS,
          conditions=("dims",), preferences=(PREFERENCE,),
          rungs=("N-S",), modalities=("V",), kind="pair", repeats=REPEATS)
    print("answered now:", answered(TREAT_S_OUT))'''

C_TREAT_B = r'''# --- Treatment 2. dims at N-BCD. MAKES MODEL CALLS. -------------------------
TREAT_B_OUT = RUNS / "ex2_q3_dims_N-BCD.jsonl"

n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
print("COST: %d scenes x %d models x %d repeats = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
print("      dims at N-BCD, read against N-CD. Face accuracy at N-CD is")
print("      66.1% for GPT and 50.5% for Claude.")

# THE PROPERTY THE TREATMENT RESTS ON, re-checked at the point of spending.
# candidate_faces_m must be identical for the two poses at a position: if it
# is not, the state names the resting face and this cell measures obedience
# to a supplied answer. prompts asserts it over orderings; this asserts it
# over the scenes actually being bought.
def _faces_in(body):
    """Every candidate_faces_m value in a state, as a sorted signature.

    Read off the structure rather than sliced out of the rendered text: the
    rendered state also carries the positions and the idle arms, which differ
    between the two poses for reasons that have nothing to do with this
    field, so a text slice compares the wrong thing and always fails.
    """
    found = []
    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k == P.CANDIDATE_FACES_FIELD:
                    found.append(x)
                else:
                    walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(P.with_candidate_faces(body))
    return json.dumps(sorted(json.dumps(f) for f in found))

_seen = {}
for _s in CALL_SCENES:
    _body, _meta = T.transform({"state": _s["state"],
                                "positions_exact": _s["positions_exact"]}, "dims")
    _pos = _s["seq"].rsplit("_", 1)[0]
    _seen.setdefault(_pos, {})[_meta["true_pose"]] = _faces_in(_body)
_leaky = [p for p, v in _seen.items() if len(v) == 2 and len(set(v.values())) != 1]
assert not _leaky, (
    "candidate_faces_m differs between the two poses at %s, so the state "
    "states the resting face and this cell measures nothing." % _leaky)
print("      candidate_faces_m checked: identical across both poses at all")
print("      %d positions, so it carries no pose information." % len(_seen))

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, TREAT_B_OUT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", REPEATS))):
    S.run(str(CAPTURES), out_path=str(TREAT_B_OUT), models=MODELS,
          conditions=("dims",), preferences=(PREFERENCE,),
          rungs=("N-BCD",), modalities=("V",), kind="pair", repeats=REPEATS)
    print("answered now:", answered(TREAT_B_OUT))'''

MD_READ = """## Read-out

No model calls. Reads every file off disk, so it survives a kernel restart and
can be run part-way through a paid cell.

It prints the controls first and **refuses to report the treatments until both
pass**. It also prints the recorded predictions from `prompts.PREDICTIONS`
before any number, so that what was expected is on the page above what
happened."""

C_READ = r'''# --- Read-out. No model calls. ---------------------------------------------
FILES = {
    ("congruent_face", "N-CD",  "control A"): RUNS / "ex2_q3_ctrlA_congruent_face_N-CD.jsonl",
    ("dims",           "N-CD",  "control B"): RUNS / "ex2_q3_ctrlB_dims_N-CD.jsonl",
    ("dims",           "N-D",   "baseline"):  RUNS / "ex2_q3_dims_N-D.jsonl",
    ("dims",           "N-CD",  "baseline"):  RUNS / "ex2_q3_dims_N-CD.jsonl",
    ("dims",           "N-S",   "treatment"): RUNS / "ex2_q3_dims_N-S.jsonl",
    ("dims",           "N-BCD", "treatment"): RUNS / "ex2_q3_dims_N-BCD.jsonl",
}
TOL = 0.006

def cells(path, cond):
    if not pathlib.Path(path).exists():
        return None
    rows, _ = load_run(path, cond, MODELS)
    return keep_analysable(rows, USABLE)

def summarise(rows, model):
    """(n, face accuracy, conversion on correct faces, delta, lo, hi)."""
    sub = [r for r in rows if r["model"] == model]
    if not sub:
        return None
    told = [r for r in sub if r.get("resting_face")]
    fok = [r for r in told if r["resting_face"] == r["face"]]
    conv = [r for r in fok if r.get("opening_needed_m") is not None
            and abs(r["opening_needed_m"] - FACTS[r["resting_face"]]["grasp_m"]) <= TOL]
    d = [x for _, x in paired_diffs(sub, USABLE, "small_face", "large_face")]
    mean, lo, hi, npos = paired_mean_ci(d)
    return dict(n=len(sub),
                face=pct(len(fok), len(told)) if told else None,
                conv=pct(len(conv), len(fok)) if fok else None,
                delta=mean, lo=lo, hi=hi)

loaded = {k: cells(v, k[0]) for k, v in FILES.items()}

print("=" * 72)
print("RECORDED PREDICTIONS, from prompts.PREDICTIONS, committed before the")
print("first call of either treatment")
print("=" * 72)
for _f in ("staged", "description"):
    print("  %-12s %s" % (_f, P.PREDICTIONS[_f]))
print()

# --- the controls, and the gate --------------------------------------------
print("=" * 72)
print("CONTROLS")
print("=" * 72)
ctrl_rows, ctrl_ok = [], True
for key, label, test in (
        (("congruent_face", "N-CD", "control A"), "A  congruent_face N-CD",
         lambda s: s["delta"] is not None and s["delta"] >= 80.0),
        (("dims", "N-CD", "control B"), "B  dims N-CD",
         lambda s: s["delta"] is not None and s["delta"] == s["delta"])):
    rows = loaded[key]
    if rows is None:
        print("  %-24s NOT RUN" % label); ctrl_ok = False; continue
    for m in MODELS:
        s = summarise(rows, m)
        if s is None:
            print("  %-24s %-10s no rows" % (label, m)); ctrl_ok = False; continue
        ctrl_rows.append([label, m, s["n"], fmt(s["face"]), fmt(s["conv"]),
                          fmt(s["delta"]), fmt(s["lo"]), fmt(s["hi"])])
show(["control", "model", "n", "face%", "conv%", "delta", "lo", "hi"], ctrl_rows)
print()
print("  Control A passes if GPT's contrast is high: the face and the rule")
print("  are both given, and it read 89.6 on this condition at N0 without")
print("  the rule. Control B passes if GPT reproduces 32.3 [23.3, 41.3] and")
print("  Claude stays at zero. One repeat gives a wider interval than the")
print("  three-repeat runs these are compared with, so read overlap rather")
print("  than equality.")
print()

# --- the treatments, gated -------------------------------------------------
_have_treat = any(loaded[k] for k in loaded if k[2] == "treatment")
if not ctrl_ok:
    print("=" * 72)
    print("TREATMENTS NOT REPORTED: a control has not been run or returned no")
    print("rows. A treatment measured against a baseline the models no longer")
    print("reproduce is not a measurement. Run the control cells first.")
    print("=" * 72)
elif not _have_treat:
    print("Controls are in. Neither treatment has been run yet.")
else:
    print("=" * 72)
    print("TREATMENTS, each against the configuration it is read from")
    print("=" * 72)
    out = []
    for key, ref, step in (
            (("dims", "N-S", "treatment"), ("dims", "N-D", "baseline"),
             "2, conversion"),
            (("dims", "N-BCD", "treatment"), ("dims", "N-CD", "baseline"),
             "1, face reading")):
        rows, base = loaded[key], loaded[ref]
        for m in MODELS:
            s = summarise(rows, m) if rows else None
            b = summarise(base, m) if base else None
            f = lambda d, k: "--" if not d else fmt(d[k])
            out.append([key[1], m, step, f(b, "face"), f(s, "face"),
                        f(b, "conv"), f(s, "conv"),
                        f(b, "delta"), f(s, "delta")])
    show(["rung", "model", "step", "face% from", "face% to",
          "conv% from", "conv% to", "delta from", "delta to"], out)
    print()
    print("  N-S is read on the conversion column, N-BCD on the face column.")
    print("  The delta columns are carried for both because a treatment that")
    print("  moves its own step and not the allocation is a different finding")
    print("  from one that moves neither.")'''
