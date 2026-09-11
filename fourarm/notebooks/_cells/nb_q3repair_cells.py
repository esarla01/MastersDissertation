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
_seen = {}
for _s in CALL_SCENES:
    _body, _meta = T.transform({"state": _s["state"],
                                "positions_exact": _s["positions_exact"]}, "dims")
    _pos = _s["seq"].rsplit("_", 1)[0]
    _seen.setdefault(_pos, {})[_meta["true_pose"]] = P.candidate_faces_signature(_body)
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

MD_PROV = """## Provenance

No model calls. One row per input file, with its length, its SHA-256 and the
prompt version it was written under. This is the trail from a number in the
chapter back to the file it came from, and it is what lets a reader a month
later tell a file that was bought whole from one that was topped up."""

C_PROV = r'''# --- Provenance. No model calls. -------------------------------------------
today = datetime.date.today().isoformat()
prov = [provenance_row("captures", CAPTURES / "consults.jsonl", OUT,
                       today=today, default_version=P.EX2_PROMPT_VERSION)]
for (cond, rung, role), path in sorted(FILES.items()):
    prov.append(provenance_row("%s_%s_%s" % (role.replace(" ", ""), cond, rung),
                               path, OUT, today=today,
                               default_version=P.EX2_PROMPT_VERSION))

show(["role", "rows", "sha256", "prompt_version", "models"],
     [[r[0], r[2], (r[3] or "")[:12], r[4], r[5]] for r in prov])
write_csv("tab_ex2_q3_repair_provenance.csv",
          ["role", "path", "rows", "sha256", "prompt_version", "model_string",
           "run_date"], prov)
print()
print("A row reading MISSING is a cell that has not been bought. A row whose")
print("prompt_version is not %s was written under a different prompt and"
      % P.EX2_PROMPT_VERSION)
print("cannot be compared with the rest without saying so in the chapter.")'''

MD_CEILING = """## Ceiling cell

**Makes model calls,** three repeats, \\num{408} calls.

`N-ABCS` applies all four treatments at once: attention, the description in
the state, the derivation sentence, and the staged report. It is not
diagnostic and is not meant to be. Attribution comes from the four single
cells; this one answers what the combination reaches, which is the question
the singles cannot.

It supports no increment. `N-ABCS` minus `N-ACD` is not the description's
contribution, because it also swaps the elicitation block for the staged one
and so carries two changes. The only contrast it can be read in is against the
baseline, which differs from it by all four treatments together.

Note that derivation already takes conversion to 100 per cent, so the staged
report cannot contribute through step 2 here and can act only through reading
or the arm.

**Run this last**, after the four cells above, so that the prediction recorded
in `prompts.CEILING_PREDICTION` is read against numbers that already exist."""

C_CEILING = r'''# --- Ceiling cell. dims at N-ABCS. MAKES MODEL CALLS. -----------------------
CEIL_OUT = RUNS / "ex2_q3_dims_N-ABCS.jsonl"

print("THE PREDICTION, from prompts.CEILING_PREDICTION, recorded before this")
print("cell was called once:")
for _line in P.CEILING_PREDICTION.split(". "):
    print("   ", _line.strip().rstrip(".") + ".")
print()

n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
print("COST: %d scenes x %d models x %d repeats = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
print("      dims at N-ABCS, all four treatments at once. Read against the")
print("      N-D baseline; it differs from every other cell by more than one")
print("      change and attributes nothing.")

# The same pose-invariance guard the N-BCD cell applies, because N-ABCS also
# carries the description and the field must state no pose here either.
_seen = {}
for _s in CALL_SCENES:
    _body, _meta = T.transform({"state": _s["state"],
                                "positions_exact": _s["positions_exact"]}, "dims")
    _pos = _s["seq"].rsplit("_", 1)[0]
    _seen.setdefault(_pos, {})[_meta["true_pose"]] = P.candidate_faces_signature(_body)
_leaky = [q for q, v in _seen.items() if len(v) == 2 and len(set(v.values())) != 1]
assert not _leaky, (
    "candidate_faces_m differs between the two poses at %s" % _leaky)
assert "N-ABCS" in P.CANDIDATE_FACE_RUNGS, (
    "N-ABCS carries the description block but is not in CANDIDATE_FACE_RUNGS, "
    "so the gloss would name a field the state does not carry")
print("      candidate_faces_m checked at all %d positions." % len(_seen))

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, CEIL_OUT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", REPEATS))):
    S.run(str(CAPTURES), out_path=str(CEIL_OUT), models=MODELS,
          conditions=("dims",), preferences=(PREFERENCE,),
          rungs=("N-ABCS",), modalities=("V",), kind="pair", repeats=REPEATS)
    print("answered now:", answered(CEIL_OUT))'''

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
    ("dims",           "N-ACD", "baseline"):  RUNS / "ex2_q3_dims_N-ACD.jsonl",
    ("dims",           "N-ABCS", "ceiling"):  RUNS / "ex2_q3_dims_N-ABCS.jsonl",
}
TOL = 0.006

def cells(path, cond):
    if not pathlib.Path(path).exists():
        return None
    rows, _ = load_run(path, cond, MODELS)
    return keep_analysable(rows, USABLE)

def summarise(rows, model):
    """Every quantity this design reads, for one cell of it.

    Conversion is measured ONLY on replies that named the face correctly.
    A model that reads the wrong face and then converts it faithfully has
    not failed step 2, and scoring it as though it had would move the two
    steps' numbers together and hide which one a treatment repaired. The
    denominator is therefore n_face_ok, which is reported beside it because
    it shrinks exactly where reading is worst and the rate is noisiest.
    """
    sub = [r for r in rows if r["model"] == model]
    if not sub:
        return None
    told = [r for r in sub if r.get("resting_face")]
    fok = [r for r in told if r["resting_face"] == r["face"]]
    conv = [r for r in fok if r.get("opening_needed_m") is not None
            and abs(r["opening_needed_m"] - FACTS[r["resting_face"]]["grasp_m"]) <= TOL]
    d = [x for _, x in paired_diffs(sub, USABLE, "small_face", "large_face")]
    mean, lo, hi, npos = paired_mean_ci(d)
    fk, fn = full_flip_count(d)
    flo, fhi = wilson(fk, fn)
    face_lo, face_hi = wilson(len(fok), len(told)) if told else (None, None)
    conv_lo, conv_hi = wilson(len(conv), len(fok)) if fok else (None, None)
    return dict(n=len(sub), n_told=len(told), n_face_ok=len(fok),
                face=pct(len(fok), len(told)) if told else None,
                face_lo=face_lo, face_hi=face_hi,
                conv=pct(len(conv), len(fok)) if fok else None,
                conv_lo=conv_lo, conv_hi=conv_hi,
                franka_small=share_at([r for r in sub
                                       if r["face"] == "small_face"]),
                franka_large=share_at([r for r in sub
                                       if r["face"] == "large_face"]),
                delta=mean, lo=lo, hi=hi, npos=npos,
                flips=fk, flips_n=fn, flips_lo=flo, flips_hi=fhi)

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
    print("  from one that moves neither.")

    # --- the ceiling, reported apart because it attributes nothing ---------
    _ceil = loaded[("dims", "N-ABCS", "ceiling")]
    if _ceil:
        print()
        print("=" * 72)
        print("CEILING CELL, all four treatments at once")
        print("=" * 72)
        print("  prediction: %s" % P.CEILING_PREDICTION)
        print()
        crow = []
        for m in MODELS:
            c = summarise(_ceil, m)
            b = summarise(loaded[("dims", "N-D", "baseline")], m)
            if c is None:
                continue
            crow.append([m, c["n"], fmt(c["face"]), fmt(c["face_lo"]),
                         fmt(c["face_hi"]), fmt(c["conv"]), fmt(c["delta"]),
                         fmt(c["lo"]), fmt(c["hi"]),
                         "%d/%d" % (c["flips"], c["flips_n"]),
                         fmt(b["delta"]) if b else "--"])
        show(["model", "n", "face%", "face lo", "face hi", "conv%",
              "delta", "lo", "hi", "flips", "baseline delta"], crow)
        print()
        print("  Read against the baseline column only. This cell differs")
        print("  from every other by more than one change, so it gives the")
        print("  height reached and attributes none of it.")

# --- THE EXTRACT. One long-format row per cell, every quantity, always ------
# Written whatever has been run so far, with the missing cells absent rather
# than blank, so the file is a record of what exists rather than a shape that
# has to be filled in. Long format on purpose: the chapter's tables are not
# settled, and a wide file built for one of them has to be regenerated for
# the next, whereas any of them can be pivoted out of this.
COLS = ["condition", "rung", "role", "model", "n", "n_told", "n_face_ok",
        "face_pct", "face_lo", "face_hi", "conv_pct", "conv_lo", "conv_hi",
        "franka_small_pct", "franka_large_pct", "delta", "delta_lo",
        "delta_hi", "n_positions", "flips", "flips_of", "flips_lo",
        "flips_hi"]
long_rows = []
for (cond, rung, role), rows in sorted(loaded.items()):
    if rows is None:
        continue
    for m in MODELS:
        d = summarise(rows, m)
        if d is None:
            continue
        long_rows.append([cond, rung, role, m, d["n"], d["n_told"],
                          d["n_face_ok"], fmt(d["face"]), fmt(d["face_lo"]),
                          fmt(d["face_hi"]), fmt(d["conv"]), fmt(d["conv_lo"]),
                          fmt(d["conv_hi"]), fmt(d["franka_small"]),
                          fmt(d["franka_large"]), fmt(d["delta"]),
                          fmt(d["lo"]), fmt(d["hi"]), d["npos"], d["flips"],
                          d["flips_n"], fmt(d["flips_lo"]),
                          fmt(d["flips_hi"])])
print()
if long_rows:
    write_csv("tab_ex2_q3_repair_cells.csv", COLS, long_rows)
else:
    print("nothing run yet, so no extract written")'''


MDAUDIT = r"""---
## Audit: Tables 5.12, 5.13 and 5.14 against the thesis

The three E2-C tables, each cell checked against the number Chapter 5 prints.

Table 5.14 is assembled from **two** notebooks. Its `N-CD` baseline and
`+ description` rows come from this one; its `+ attention` row is `N-ACD`,
bought and read in `ex2_q3_remediation.ipynb` and written to
`tables/ex2_q3/`. Both are checked here so the split cannot hide a drift in
half a table.

One rung wears two labels. `N-CD` is "+ derivation" in Table 5.13 and the
baseline in Table 5.14 — the same rows read for two different questions, which
is correct and easy to misread.
"""

CAUDIT = r'''# --- Audit against the thesis. No model calls. ------------------------------
# PUBLISHED VALUES, transcribed from Chapter 5 and never computed here.

# Table 5.12, the two controls at one repeat: face %, conversion %, contrast.
THESIS_512 = {
    ("A", "congruent_face", "N-CD", "gpt_hi"):    (100.0, 96.9, 93.8),
    ("A", "congruent_face", "N-CD", "claude_md"): (100.0, 78.1, 56.2),
    ("B", "dims", "N-CD", "gpt_hi"):              (64.1, 97.6, 25.0),
    ("B", "dims", "N-CD", "claude_md"):           (43.8, 96.4, 0.0),
}

# Table 5.13, mapping a face to an opening: conversion, Franka share on each
# face, and the paired allocation contrast. All in dims.
THESIS_513 = {
    ("N-D", "gpt_hi"):     (65.1, 63.5, 60.4, 3.1),
    ("N-D", "claude_md"):  (68.0, 67.7, 67.7, 0.0),
    ("N-CD", "gpt_hi"):    (100.0, 100.0, 67.7, 32.3),
    ("N-CD", "claude_md"): (94.8, 100.0, 100.0, 0.0),
    ("N-S", "gpt_hi"):     (88.5, 88.5, 89.6, -1.0),
    ("N-S", "claude_md"):  (81.2, 82.3, 70.8, 11.5),
}

# Table 5.14, reading the face: face accuracy, both Franka shares, contrast
# and its paired interval. N-ACD comes from the remediation notebook.
THESIS_514 = {
    ("N-CD", "gpt_hi"):     (66.1, 100.0, 67.7, 32.3, 23.3, 41.3),
    ("N-CD", "claude_md"):  (50.5, 100.0, 100.0, 0.0, 0.0, 0.0),
    ("N-BCD", "gpt_hi"):    (75.0, 100.0, 50.0, 50.0, 39.8, 60.2),
    ("N-BCD", "claude_md"): (50.0, 40.6, 38.5, 2.1, -12.6, 16.7),
    ("N-ACD", "gpt_hi"):    (76.6, 100.0, 46.9, 53.1, 42.6, 63.6),
    ("N-ACD", "claude_md"): (50.0, 100.0, 100.0, 0.0, 0.0, 0.0),
}

EPS = 0.06
problems = []


def agrees(label, got, want, eps=EPS):
    if want is None:
        return
    if got is None or abs(got - want) > eps:
        problems.append("%s: computed %s, thesis prints %s" % (label, got, want))


def read_csv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def num(row, field):
    v = row.get(field, "")
    return float(v) if v not in ("", "NA", None) else None


cells = read_csv(TABLES / "tab_ex2_q3_repair_cells.csv")
by = {(r["condition"], r["rung"], r["model"], r["role"]): r for r in cells}


def pick(cond, rung, model, roles):
    for role in roles:
        if (cond, rung, model, role) in by:
            return by[(cond, rung, model, role)]
    return None


# --- Table 5.12 ------------------------------------------------------------
for (ctrl, cond, rung, model), (face, conv, d) in sorted(THESIS_512.items()):
    row = pick(cond, rung, model, ("control A", "control B"))
    tag = "5.12 control %s %s %s" % (ctrl, cond, model)
    if row is None:
        problems.append("%s: no row in tab_ex2_q3_repair_cells.csv" % tag)
        continue
    agrees(tag + " face", num(row, "face_pct"), face)
    agrees(tag + " conversion", num(row, "conv_pct"), conv)
    agrees(tag + " contrast", num(row, "delta"), d)

# --- Table 5.13 ------------------------------------------------------------
for (rung, model), (conv, fs, fl, d) in sorted(THESIS_513.items()):
    row = pick("dims", rung, model, ("baseline", "treatment"))
    tag = "5.13 %s %s" % (rung, model)
    if row is None:
        problems.append("%s: no row" % tag)
        continue
    agrees(tag + " conversion", num(row, "conv_pct"), conv)
    agrees(tag + " franka small", num(row, "franka_small_pct"), fs)
    agrees(tag + " franka large", num(row, "franka_large_pct"), fl)
    agrees(tag + " contrast", num(row, "delta"), d)

# --- Table 5.14, including the half this notebook does not produce ---------
# N-ACD lives in tables/ex2_q3/, written by the remediation notebook: its face
# accuracy in the ceiling table and its contrast in the ceiling-contrast one.
Q3 = TABLES.parent / "ex2_q3"
ceiling = {(r["model"], r["rung"]): r
           for r in read_csv(Q3 / "tab_ex2_q3_ceiling.csv")}
ceil_con = {(r["model"], r["rung"]): r
            for r in read_csv(Q3 / "tab_ex2_q3_ceiling_contrast.csv")}

for (rung, model), (face, fs, fl, d, lo, hi) in sorted(THESIS_514.items()):
    tag = "5.14 %s %s" % (rung, model)
    if rung == "N-ACD":
        c, cc = ceiling.get((model, rung)), ceil_con.get((model, rung))
        if not c or not cc:
            problems.append("%s: missing from the remediation notebook's tables" % tag)
            continue
        agrees(tag + " face", num(c, "face_correct_pct"), face)
        agrees(tag + " contrast", num(cc, "contrast_pts"), d)
        agrees(tag + " paired lo", num(cc, "contrast_lo"), lo)
        agrees(tag + " paired hi", num(cc, "contrast_hi"), hi)
        # The shares are not tabled anywhere; the contrast is their difference,
        # so checking both against it is the strongest available statement.
        agrees(tag + " shares agree with the contrast", round(fs - fl, 1), d)
        continue
    row = pick("dims", rung, model, ("baseline", "treatment"))
    if row is None:
        problems.append("%s: no row" % tag)
        continue
    agrees(tag + " face", num(row, "face_pct"), face)
    agrees(tag + " franka small", num(row, "franka_small_pct"), fs)
    agrees(tag + " franka large", num(row, "franka_large_pct"), fl)
    agrees(tag + " contrast", num(row, "delta"), d)
    agrees(tag + " paired lo", num(row, "delta_lo"), lo)
    agrees(tag + " paired hi", num(row, "delta_hi"), hi)

# --- The transcribed constants, against the thesis itself ------------------
# The constants above are typed from the chapter. On their own a
# mis-transcription would pass and a change to the chapter would go unnoticed.
import thesis_check as _TC

_CK = _TC.Checker(os.path.join(TABLES.parent.parent, "notebooks", "ex2",
                               "thesis_expected_q3.json"))
_covered = []

# 5.12: face, conversion, contrast, per control then model. Gemini's rows are
# in the thesis and not in this notebook's CSV -- the repair run drops Gemini,
# which is at ceiling from N-D onward -- so they are skipped over here rather
# than pinned, and the coverage line says so.
_seq = []
for _ctrl, _cond in (("A", "congruent_face"), ("B", "dims")):
    for _m in ("gpt_hi", "claude_md"):
        _seq += list(THESIS_512[(_ctrl, _cond, "N-CD", _m)])
_covered.append(("5.12", "tab:ex2:q3:repair:controls")
                + _CK.check_subsequence("tab:ex2:q3:repair:controls", _seq))

# 5.13: conversion, both Franka shares, the allocation contrast.
_seq = [v for _r in ("N-D", "N-CD", "N-S") for _m in ("gpt_hi", "claude_md")
        for v in THESIS_513[(_r, _m)]]
_covered.append(("5.13", "tab:ex2:q3")
                + _CK.check_subsequence("tab:ex2:q3", _seq))

# 5.14: face accuracy, both shares, the contrast and its interval.
_seq = [v for _r in ("N-CD", "N-BCD", "N-ACD") for _m in ("gpt_hi", "claude_md")
        for v in THESIS_514[(_r, _m)]]
_covered.append(("5.14", "tab:ex2:q3:step1")
                + _CK.check_subsequence("tab:ex2:q3:step1", _seq))

print()
for _num, _lab, _got, _tot in _covered:
    print("  %-5s %-28s %d of %d thesis cells pinned%s"
          % (_num, _lab, _got, _tot,
             "" if _got == _tot else "   <-- the rest are not checked here"))
print(_CK.refresh())
print()

n_checks = len(THESIS_512) * 3 + len(THESIS_513) * 4 + len(THESIS_514) * 5
print("Experiment 2, Q3: tables checked against the thesis")
show(["Table", "Reports", "Source"],
     [["5.12", "the two controls", "tab_ex2_q3_repair_cells.csv"],
      ["5.13", "step 2, mapping a face to an opening", "tab_ex2_q3_repair_cells.csv"],
      ["5.14", "step 1, reading the face",
       "repair_cells.csv + ex2_q3/ceiling*.csv"]])
print()
for p in problems:
    print("  MISMATCH  %s" % p)
print("%d checks against Chapter 5, %d disagreed" % (n_checks, len(problems)))
assert not problems, "Q3 no longer reproduces the thesis: %s" % problems[:5]
print("every Q3 table still matches what Chapter 5 prints")
'''
