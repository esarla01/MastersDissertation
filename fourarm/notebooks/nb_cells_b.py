MD5B = r"""### Cue validation results

Accuracy per face with Wilson intervals, and the `small_face` / `large_face`
confusion. A verdict, not a table to be interpreted later.

Two-way since 2026-08-27. The probe was three-way and its hard pair was
`edge` against `large_face`; that face was withdrawn because no model read
it. What that costs is printed with the verdict."""

C5B = r'''# --- Cell 5b. Cue validation results. No model calls. -----------------------
cue_rows = []
for model in MODELS:
    for rep in range(1, CUE_REPEATS + 1):
        f = RUNS / (CUE_FILE % (model, rep))
        if f.exists():
            for line in open(f):
                if line.strip():
                    r = json.loads(line)
                    r["model"], r["repeat"] = model, rep
                    cue_rows.append(r)

# Rows from a probe that offered a different set of answers are not the
# same measurement and must never be pooled with these. The retired
# three-way runs sit in the same directory under ex2_q1_cue_*.jsonl and
# would otherwise be read as if they answered this question: restricted to
# the two surviving faces they score 56 percent, because the model could
# still say "edge", and the gate below would read NOT SEPARABLE and shut
# the notebook for the wrong reason.
_foreign = [r for r in cue_rows
            if (r.get("true_face") or r.get("true_pose")) not in FACES
            or (r.get("answer") is not None and r["answer"] not in FACES)]
if _foreign:
    raise AssertionError(
        "%d of %d cue rows answer a different question (e.g. %r). They are "
        "evidence, not input: read them from their own files. %s holds "
        "only this probe's runs."
        % (len(_foreign), len(cue_rows),
           _foreign[0].get("answer") or _foreign[0].get("true_face"),
           CUE_FILE.replace("%s", "<model>").replace("%d", "<rep>")))

if not cue_rows:
    print("no cue files matching %s yet; run cell 5 first"
          % CUE_FILE.replace("%s", "<model>").replace("%d", "<rep>"))
else:
    CHANCE = 100.0 / len(FACES)
    acc_rows, conf_rows = [], []
    for model in MODELS:
        for face in FACES:
            sub = [r for r in cue_rows if r["model"] == model
                   and (r.get("true_face") or r["true_pose"]) == face
                   and r.get("answer") is not None]
            k = sum(1 for r in sub if r["correct"])
            lo, hi = wilson(k, len(sub))
            acc_rows.append([model, face, len({r["seq"] for r in sub}), k,
                             "%.1f" % (100.0 * k / len(sub)) if sub else "NA",
                             "%.1f" % lo if sub else "NA",
                             "%.1f" % hi if sub else "NA"])
        for tf in FACES:
            for pf in FACES:
                n = sum(1 for r in cue_rows if r["model"] == model
                        and (r.get("true_face") or r["true_pose"]) == tf
                        and r.get("answer") == pf)
                conf_rows.append([model, tf, pf, n])

    show(["model", "face", "images", "correct", "acc%", "lo", "hi"], acc_rows)
    print("\nchance is %.1f%% (%d-way forced choice)" % (CHANCE, len(FACES)))
    write_csv("tab_ex2_q1_cue.csv",
              ["model", "resting_face", "n_images", "correct_n",
               "accuracy_pct", "wilson_lo", "wilson_hi"], acc_rows)
    write_csv("tab_ex2_q1_cue_confusion.csv",
              ["model", "true_face", "predicted_face", "n"], conf_rows)

    # Until 2026-08-27 this block restricted the three-way probe to its
    # hard pair, edge against large_face. With two faces the probe IS that
    # pair, so the restriction is gone and the whole accuracy is the
    # verdict. The Wilson bound, not the point estimate, is what decides:
    # a lower bound above chance is the claim that survives a small n.
    print()
    print("=" * 70)
    print("THE DIAGNOSTIC: small_face against large_face")
    print("=" * 70)
    verdict_ok = True
    for model in MODELS:
        sub = [r for r in cue_rows if r["model"] == model
               and (r.get("true_face") or r["true_pose"]) in FACES
               and r.get("answer") is not None]
        k = sum(1 for r in sub
                if r["answer"] == (r.get("true_face") or r["true_pose"]))
        lo, hi = wilson(k, len(sub))
        ok = lo > CHANCE
        verdict_ok &= ok
        print("  %-8s %d/%d correct = %.1f%% [%.1f, %.1f]   %s"
              % (model, k, len(sub), 100.0 * k / len(sub) if sub else float("nan"),
                 lo, hi, "separable" if ok else "NOT SEPARABLE"))
    print()
    if verdict_ok:
        print("VERDICT  the two faces are separable above chance.")
        print("         Q1's contrast is measurable. Proceed.")
    else:
        print("VERDICT  the two faces are NOT separable.")
        print("         Q1's contrast is DEAD: a null on it would measure")
        print("         the render, not the model. Do not run cells 6 and 7.")
        print("         Report this as an instrument result.")
    print()
    print("  This probe cannot distinguish a model that derives the opening")
    print("  from geometry from one that reads posture and applies a rule:")
    print("  small_face stands and large_face lies, so posture alone scores")
    print("  here. The face that separated those readings was withdrawn on")
    print("  2026-08-27 because no model could see it. State this as a")
    print("  limitation wherever the Q1 verdict is reported.")'''

MD6 = r"""## Cells 6 and 7. The two conditions at N0

**Make model calls.** Both models, Franka preference, three repeats.
`solo.run` resumes into its output file and skips trials already answered, so
re-running a cell costs nothing and destroys nothing.

The scene count comes from `CALL_SCENES`, set in cell 3. By default that is
**every captured scene**, not just the usable positions: the excluded ones are
asked and then dropped in cell 8 at analysis time, which keeps the exclusion
visible in the data and shows it predates any accuracy result. With 34
captured positions and 32 usable that is 68 scenes rather than 64. Set
`RUN_ALL_POSITIONS = False` in cell 3 to pay only for the usable ones; the
analysis is identical either way.

The count was hardcoded as 90 until 2026-08-27 and had been wrong since the
capture set grew. It is derived now."""

C6 = r'''# --- Cell 6. Congruent, N0. MAKES MODEL CALLS. ------------------------------
CONGRUENT_OUT = RUNS / "ex2_q1_congruent_N0.jsonl"

# CALL_SCENES, not scenes: cell 3 decides which positions are paid for, so
# this cell and cell 7 cannot drift apart. The breakdown is printed because
# "68 scenes" against "32 usable positions" looks like a bug otherwise, and
# that question is worth answering before the money is spent, not after.
n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
_extra = len(CALL_SCENES) - len(USABLE) * len(FACES)
print("COST: %d scenes x %d models x %d repeats = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
print("      %d usable positions x %d faces = %d scenes%s"
      % (len(USABLE), len(FACES), len(USABLE) * len(FACES),
         ", plus %d at excluded positions, asked so the exclusion is "
         "visible in the data and dropped in cell 8" % _extra
         if _extra else ""))
have = answered(CONGRUENT_OUT)
print("already answered: %d of %d in %s"
      % (have, n_calls, CONGRUENT_OUT.name))
print("set CONFIRM_SPEND = %d in this cell to proceed" % n_calls)

CONFIRM_SPEND = None            # <-- set to the number above

if CONFIRM_SPEND != n_calls:
    print("\nnot confirmed; no calls made.")
elif have >= n_calls:
    print("\ncomplete already; nothing to do.")
else:
    S.run(str(CAPTURES), out_path=str(CONGRUENT_OUT), models=MODELS,
          conditions=("congruent",), preferences=(PREFERENCE,),
          rungs=(RUNG,), modalities=("V",), kind="pair", repeats=REPEATS)
    print("answered now:", answered(CONGRUENT_OUT))'''

C7 = r'''# --- Cell 7. Dims, N0. MAKES MODEL CALLS. -----------------------------------
DIMS_OUT = RUNS / "ex2_q1_dims_N0.jsonl"

# CALL_SCENES, not scenes: cell 3 decides which positions are paid for, so
# this cell and cell 7 cannot drift apart. The breakdown is printed because
# "68 scenes" against "32 usable positions" looks like a bug otherwise, and
# that question is worth answering before the money is spent, not after.
n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
_extra = len(CALL_SCENES) - len(USABLE) * len(FACES)
print("COST: %d scenes x %d models x %d repeats = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
print("      %d usable positions x %d faces = %d scenes%s"
      % (len(USABLE), len(FACES), len(USABLE) * len(FACES),
         ", plus %d at excluded positions, asked so the exclusion is "
         "visible in the data and dropped in cell 8" % _extra
         if _extra else ""))
have = answered(DIMS_OUT)
print("already answered: %d of %d in %s"
      % (have, n_calls, DIMS_OUT.name))
print("set CONFIRM_SPEND = %d in this cell to proceed" % n_calls)

CONFIRM_SPEND = None            # <-- set to the number above

if CONFIRM_SPEND != n_calls:
    print("\nnot confirmed; no calls made.")
elif have >= n_calls:
    print("\ncomplete already; nothing to do.")
else:
    S.run(str(CAPTURES), out_path=str(DIMS_OUT), models=MODELS,
          conditions=("dims",), preferences=(PREFERENCE,),
          rungs=(RUNG,), modalities=("V",), kind="pair", repeats=REPEATS)
    print("answered now:", answered(DIMS_OUT))'''

MD8 = r"""## Cell 8. Load and validate replies

No model calls. Nothing is silently dropped: every exclusion is counted and
named, and the rows are kept."""

C8 = r'''# --- Cell 8. Load and validate. No model calls. -----------------------------
def load_run(path, condition):
    if not pathlib.Path(path).exists():
        print("MISSING %s" % path)
        return []
    seen = {}
    for line in open(path):
        if line.strip():
            r = json.loads(line)
            seen[r.get("trial_id")] = r        # last write wins, as solo does
    rows = list(seen.values())
    for r in rows:
        r["condition"] = r.get("condition", condition)
        r["position"] = r["seq"].rsplit("_", 1)[0]
        r["face"] = r["true_pose"]
    return rows

ROWS = load_run(CONGRUENT_OUT, "congruent") + load_run(DIMS_OUT, "dims")
print("distinct trials loaded: %d" % len(ROWS))

flags = collections.Counter()
for r in ROWS:
    if r.get("error"):
        flags["transport error"] += 1
    if r.get("outcome") == "unparseable":
        flags["unparseable reply"] += 1
    if r.get("arm") and r["arm"] not in (r.get("legal_true") or []):
        flags["named an arm the validator rejects"] += 1
    if not r.get("arm"):
        flags["declined (no arm named)"] += 1
    op, arm = r.get("opening_needed_m"), r.get("arm")
    if op is not None and arm:
        cap = C.ARM_TYPES[C.ARMS[arm]["type"]]["max_grasp_m"] if arm in C.ARMS else None
        if cap is not None and op > cap + 1e-9:
            flags["reported an opening its own arm cannot span"] += 1
    if op is None and r.get("arm"):
        flags["named an arm but reported no opening"] += 1

show(["issue", "n"], [[k, v] for k, v in sorted(flags.items())] or [["none", 0]])
print()
print("Nothing above is dropped. The analysis excludes declines from the")
print("Franka-share denominator (cell 9) and reports them in cell 11; every")
print("other flag is carried through so it can be inspected.")

ANALYSED = [r for r in ROWS if not r.get("error")
            and r.get("outcome") != "unparseable"
            and r["position"] in USABLE]
print()
print("rows after removing errors and unparseables and restricting to the")
print("%d usable positions: %d" % (len(USABLE), len(ANALYSED)))
print("expected: %d positions x %d faces x %d conditions x %d models x %d reps"
      " = %d" % (len(USABLE), len(FACES), len(CONDITIONS), len(MODELS),
                 REPEATS, len(USABLE) * len(FACES) * len(CONDITIONS)
                 * len(MODELS) * REPEATS))'''

MD9 = r"""## Cell 9. Franka share by orientation

Table 2. Declines are excluded from both numerator and denominator; they are
reported separately in cell 11. Wilson bounds are on the proposal denominator."""

C9 = r'''# --- Cell 9. Franka share by orientation. No model calls. -------------------
def is_franka(arm):
    return bool(arm) and arm.startswith("franka")

share_rows = []
for cond in CONDITIONS:
    for model in MODELS:
        for face in FACES:
            sub = [r for r in ANALYSED if r["condition"] == cond
                   and r["model"] == model and r["face"] == face]
            proposals = [r for r in sub if r.get("arm")]
            k = sum(1 for r in proposals if is_franka(r["arm"]))
            n = len(proposals)
            lo, hi = wilson(k, n)
            share_rows.append([
                cond, model, face, len({r["position"] for r in sub}), n, k,
                "%.1f" % (100.0 * k / n) if n else "NA",
                "%.1f" % lo if n else "NA", "%.1f" % hi if n else "NA"])

show(["condition", "model", "face", "pos", "proposals", "franka", "share%",
      "lo", "hi"], share_rows)
print()
print("A deriving model reads HIGH on small_face and LOW on large_face.")
print("A model using a posture association reads HIGH, LOW, LOW: it separates")
print("standing from flat but not the two flat faces.")
write_csv("tab_ex2_q1_share.csv",
          ["condition", "model", "resting_face", "n_positions", "n_proposals",
           "franka_n", "franka_share_pct", "wilson_lo", "wilson_hi"],
          share_rows)'''

MD10 = r"""## Cell 10. Paired contrasts

Table 3, and the by-position companion so the pairing is inspectable.

**On the interval.** The design document asks for Newcombe. Newcombe is an
interval on the difference of two *independent* proportions; these contrasts
are computed within position and then averaged, so the unit is the position and
the correct interval is a t interval over the 29 paired differences. Both are
emitted: `paired_lo`/`paired_hi` is the one to quote, `newcombe_lo`/
`newcombe_hi` is the unpaired comparison the spec named. They are reported side
by side rather than silently substituted."""

C10 = r'''# --- Cell 10. Paired contrasts. No model calls. -----------------------------
# ONE contrast. It was two until 2026-08-27, the second being
# edge_minus_large, which is what made the design diagnostic: edge and
# large_face are both flat, so a difference between them could only come
# from geometry. The middle face was withdrawn because no model read it,
# and this is where that loss lands.
CONTRASTS = (("small_minus_large", "small_face", "large_face"),)

def share_at(rows):
    props = [r for r in rows if r.get("arm")]
    if not props:
        return None
    return 100.0 * sum(1 for r in props if is_franka(r["arm"])) / len(props)

bypos_rows, contrast_rows = [], []
ratios = {}
for cond in CONDITIONS:
    for model in MODELS:
        base = [r for r in ANALYSED if r["condition"] == cond
                and r["model"] == model]
        for name, a, b in CONTRASTS:
            diffs = []
            for pos in USABLE:
                sa = share_at([r for r in base
                               if r["position"] == pos and r["face"] == a])
                sb = share_at([r for r in base
                               if r["position"] == pos and r["face"] == b])
                d = None if (sa is None or sb is None) else sa - sb
                diffs.append(d)
                bypos_rows.append([cond, model, pos, name,
                                   "NA" if d is None else "%.1f" % d])
            mean, plo, phi, npos = paired_mean_ci(diffs)

            # The unpaired comparison the spec asked for, pooled over proposals.
            pa = [r for r in base if r["face"] == a and r.get("arm")]
            pb = [r for r in base if r["face"] == b and r.get("arm")]
            nlo, nhi = newcombe(sum(1 for r in pa if is_franka(r["arm"])), len(pa),
                                sum(1 for r in pb if is_franka(r["arm"])), len(pb))
            contrast_rows.append([cond, model, name, npos,
                                  "%.1f" % mean if mean == mean else "NA",
                                  "%.1f" % nlo if nlo == nlo else "NA",
                                  "%.1f" % nhi if nhi == nhi else "NA",
                                  "%.1f" % plo if plo == plo else "NA",
                                  "%.1f" % phi if phi == phi else "NA",
                                  spans_zero(plo, phi), "NA"])
            ratios[(cond, model, name)] = mean

# dims / congruent, for the one remaining contrast.
for row in contrast_rows:
    cond, model, name = row[0], row[1], row[2]
    if cond == "dims" and name == "small_minus_large":
        num = ratios.get(("dims", model, name))
        den = ratios.get(("congruent", model, name))
        # index 10 is the ratio column; 9 is spans_zero. Counted, not guessed:
        # condition, model, contrast, npos, mean, newc_lo, newc_hi,
        # paired_lo, paired_hi, spans_zero, ratio_to_congruent.
        row[10] = ("%.2f" % (num / den)) if (den is not None and den == den
                                             and abs(den) > 1e-9
                                             and num is not None and num == num
                                             ) else "NA"

show(["condition", "model", "contrast", "npos", "mean", "newc_lo", "newc_hi",
      "paired_lo", "paired_hi", "spans0", "ratio"], contrast_rows)
write_csv("tab_ex2_q1_contrasts.csv",
          ["condition", "model", "contrast", "n_positions", "mean_diff_pts",
           "newcombe_lo", "newcombe_hi", "paired_lo", "paired_hi",
           "spans_zero", "ratio_to_congruent"], contrast_rows)
write_csv("tab_ex2_q1_contrasts_bypos.csv",
          ["condition", "model", "position_id", "contrast", "diff_pts"],
          bypos_rows)

# --- the verdict, against the four patterns in the design document ----------
print()
print("=" * 70)
print("READING, per model, in DIMS")
print("=" * 70)
# THREE patterns, not four. The fourth read "separates standing from flat
# but not the two flat faces: a coarse association, not a derivation", and
# it was the one the design existed to detect. It needed edge_minus_large,
# and the middle face was withdrawn on 2026-08-27 because no model could
# see it. That pattern is now UNTESTABLE, not absent: a model matching it
# reads here as "obtains the opening from the geometry", which is the
# reading it was built to rule out.
#
# Do not let that sit implicitly in the code. It is printed below every
# verdict and belongs in the Limitations section, with runs/ex2_q1_cue_*
# as the evidence that the pattern was real.
for model in MODELS:
    d_sm = ratios.get(("dims", model, "small_minus_large"))
    row = [r for r in contrast_rows if r[0] == "dims" and r[1] == model]
    sm_zero = [r for r in row if r[2] == "small_minus_large"][0][9]
    crow = [r for r in contrast_rows if r[0] == "congruent" and r[1] == model]
    c_zero = [r for r in crow if r[2] == "small_minus_large"][0][9]

    if not sm_zero:
        v = "obtains the opening from the geometry in the scene"
    elif not c_zero:
        v = ("applies the rule when given the opening but cannot obtain it "
             "from the scene")
    else:
        v = ("cannot apply the rule even when given the opening; every later "
             "result for this model is uninterpretable")
    print("  %-8s small-large %s" %
          (model, "NA" if d_sm != d_sm else "%+.1f" % d_sm))
    print("           -> %s" % v)
    if not sm_zero:
        print("              CANNOT BE DISTINGUISHED from a model that reads")
        print("              posture and applies a rule. small_face stands")
        print("              and large_face lies, so posture alone produces")
        print("              this result. The contrast that separated the")
        print("              two readings needed a third resting face and")
        print("              was withdrawn: see runs/ex2_q1_cue_*.jsonl.")
        print("              The prompt gives posture a SECOND route to the")
        print("              same answer, independent of the withdrawn face:")
        print("              \"size_upright_m\" names the frame its numbers")
        print("              were taken in, so standing-or-flat fixes the")
        print("              opening and the model never has to work out")
        print("              which two extents are horizontal. Both routes")
        print("              are unavoidable with two faces. Read this")
        print("              verdict as posture-plus-lookup, which geometric")
        print("              derivation would also produce.")'''

MD11 = r"""## Cell 11. Wait rate by orientation

Table 4. The denominator here is **all replies including declines**, unlike the
share table. The two differ on purpose.

Picking a UR on `large_face` is a judgement that the object is too wide.
Declining is a judgement that the model cannot tell. Both matter and they are
not the same."""

C11 = r'''# --- Cell 11. Wait rate by orientation. No model calls. ---------------------
WAIT_THRESHOLD = 5.0        # percent, below which the table is a sentence

wait_rows = []
for cond in CONDITIONS:
    for model in MODELS:
        for face in FACES:
            sub = [r for r in ANALYSED if r["condition"] == cond
                   and r["model"] == model and r["face"] == face]
            k = sum(1 for r in sub if not r.get("arm"))
            lo, hi = wilson(k, len(sub))
            wait_rows.append([cond, model, face, len(sub), k,
                              "%.1f" % (100.0 * k / len(sub)) if sub else "NA",
                              "%.1f" % lo if sub else "NA",
                              "%.1f" % hi if sub else "NA"])

show(["condition", "model", "face", "trials", "declines", "rate%", "lo", "hi"],
     wait_rows)
write_csv("tab_ex2_q1_waits.csv",
          ["condition", "model", "resting_face", "n_trials", "declines_n",
           "decline_rate_pct", "wilson_lo", "wilson_hi"], wait_rows)

rates = [float(r[5]) for r in wait_rows if r[5] != "NA"]
print()
if rates and max(rates) < WAIT_THRESHOLD:
    print("ALL CELLS BELOW %.0f%%. Replace the table with one sentence:" % WAIT_THRESHOLD)
    print('  "Declines were rare throughout, at most %.1f%% in any cell, so'
          % max(rates))
    print('   Franka share reads at face value."')
else:
    print("Waiting is not background. Read the table: a rate rising on")
    print("large_face means the model registers a problem without resolving")
    print("it; a rate rising across dims means it registered the missing")
    print("fields, which is the calibrated response.")'''

MD12 = r"""## Cell 12. Reported opening

Inline, no table file. `opening_needed_m` is a self-report and never a scored
endpoint on its own, but it localises the failure: a wrong face with a correct
derivation from it is a different failure from a correct face with a wrong
derivation."""

C12 = r'''# --- Cell 12. Reported opening. No model calls. -----------------------------
TOL = 1e-9
for cond in CONDITIONS:
    print("=" * 70)
    print(cond.upper())
    for model in MODELS:
        for face in FACES:
            sub = [r for r in ANALYSED if r["condition"] == cond
                   and r["model"] == model and r["face"] == face]
            true_open = FACTS[face]["grasp_m"]
            stated = [r for r in sub if r.get("opening_needed_m") is not None]
            right = [r for r in stated
                     if abs(r["opening_needed_m"] - true_open) <= 0.006]
            # A wrong number that nevertheless licenses the arm chosen: the
            # model's action follows its own report even though the report is
            # wrong, which is a different failure from acting against it.
            consistent = 0
            for r in stated:
                arm = r.get("arm")
                if not arm or arm not in C.ARMS:
                    continue
                cap = C.ARM_TYPES[C.ARMS[arm]["type"]]["max_grasp_m"]
                if r["opening_needed_m"] <= cap + 1e-9:
                    consistent += 1
            print("  %-8s %-11s stated %2d/%-2d   correct %2d   "
                  "arm consistent with own report %2d"
                  % (model, face, len(stated), len(sub), len(right), consistent))

# One figure: does the arm follow the reported opening, whatever the truth?
print()
print("=" * 70)
print("COUPLING between the reported opening and the arm chosen")
print("=" * 70)
for cond in CONDITIONS:
    for model in MODELS:
        sub = [r for r in ANALYSED if r["condition"] == cond
               and r["model"] == model and r.get("arm") in C.ARMS
               and r.get("opening_needed_m") is not None]
        agree = sum(1 for r in sub
                    if (r["opening_needed_m"]
                        <= C.ARM_TYPES[C.ARMS[r["arm"]]["type"]]["max_grasp_m"] + 1e-9))
        print("  %-10s %-8s %d of %d replies name an arm that can span the"
              " opening they reported (%.1f%%)"
              % (cond, model, agree, len(sub),
                 100.0 * agree / len(sub) if sub else float("nan")))
print()
print("A model whose arm follows its own reported opening is applying the")
print("rule; where it fails, the failure is in obtaining the opening. A model")
print("whose arm contradicts its own report has reasoning and action coming")
print("apart, which is a different finding.")'''

MD13 = r"""## Cell 13. Figure

Franka share by orientation, both conditions, both models, with intervals and
a reference line at the level a model indifferent between arm types would
produce.

Written as plotted values plus a self-contained TikZ picture: matplotlib is not
installed in this project's environments, and a TikZ figure stays editable in
the thesis rather than arriving as a raster. The colours are declared at the
top of the `.tex` so they can be swapped for the thesis `includes.tex` names."""

C13 = r'''# --- Cell 13. Figure. No model calls. ---------------------------------------
plot_rows = []
for cond in CONDITIONS:
    for model in MODELS:
        for face in FACES:
            m = [r for r in share_rows if r[0] == cond and r[1] == model
                 and r[2] == face]
            if m and m[0][6] != "NA":
                plot_rows.append([cond, model, face, float(m[0][6]),
                                  float(m[0][7]), float(m[0][8])])

fig_csv = FIGURES / "fig_ex2_q1_share.csv"
with open(fig_csv, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["condition", "model", "resting_face", "share_pct",
                "wilson_lo", "wilson_hi"])
    for r in plot_rows:
        w.writerow([r[0], r[1], r[2], "%.1f" % r[3], "%.1f" % r[4], "%.1f" % r[5]])
print("wrote", rel(fig_csv))

# --- TikZ, self-contained, no pgfplots --------------------------------------
PANEL_W, PANEL_H, GAP = 5.2, 4.2, 1.4
BAR_W, GROUP_GAP = 0.42, 0.30
COLOURS = {"gemini": "q1blue", "gpt": "q1teal"}

def y(pct):
    return PANEL_H * pct / 100.0

lines = [
    "% Experiment 2, Q1. Franka share by resting face.",
    "% Generated by notebooks/ex2_q1_derivation.ipynb -- do not hand-edit.",
    "% Swap the three colour definitions for the thesis includes.tex names.",
    "\\begin{tikzpicture}[x=1cm,y=1cm,font=\\small]",
    "\\definecolor{q1blue}{RGB}{59,110,165}",
    "\\definecolor{q1teal}{RGB}{62,150,146}",
    "\\definecolor{q1rule}{RGB}{140,140,140}",
]
for pi, cond in enumerate(CONDITIONS):
    x0 = pi * (PANEL_W + GAP)
    lines += [
        "%% --- panel: %s" % cond,
        "\\draw[q1rule] (%.2f,0) -- (%.2f,0);" % (x0, x0 + PANEL_W),
        "\\draw[q1rule] (%.2f,0) -- (%.2f,%.2f);" % (x0, x0, PANEL_H),
        "\\node[anchor=south] at (%.2f,%.2f) {\\textbf{%s}};"
        % (x0 + PANEL_W / 2.0, PANEL_H + 0.15, cond),
    ]
    for gy in (0, 25, 50, 75, 100):
        lines.append("\\draw[q1rule!35] (%.2f,%.2f) -- (%.2f,%.2f);"
                     % (x0, y(gy), x0 + PANEL_W, y(gy)))
        if pi == 0:
            lines.append("\\node[anchor=east,q1rule] at (%.2f,%.2f) {%d};"
                         % (x0 - 0.1, y(gy), gy))
    # a model indifferent between the two arm types names a Franka half the time
    lines.append("\\draw[q1rule,dashed] (%.2f,%.2f) -- (%.2f,%.2f);"
                 % (x0, y(50), x0 + PANEL_W, y(50)))
    for fi, face in enumerate(FACES):
        cx = x0 + PANEL_W * (fi + 0.5) / len(FACES)
        lines.append("\\node[anchor=north,align=center] at (%.2f,-0.12) "
                     "{\\texttt{%s}};" % (cx, face.replace("_", "\\_")))
        for mi, model in enumerate(MODELS):
            m = [r for r in plot_rows if r[0] == cond and r[1] == model
                 and r[2] == face]
            if not m:
                continue
            share, lo, hi = m[0][3], m[0][4], m[0][5]
            bx = cx + (mi - (len(MODELS) - 1) / 2.0) * (BAR_W + 0.06)
            col = COLOURS.get(model, "q1blue")
            lines.append("\\fill[%s] (%.2f,0) rectangle (%.2f,%.2f);"
                         % (col, bx - BAR_W / 2, bx + BAR_W / 2, y(share)))
            lines.append("\\draw[q1rule,thick] (%.2f,%.2f) -- (%.2f,%.2f);"
                         % (bx, y(lo), bx, y(hi)))
            lines.append("\\draw[q1rule] (%.2f,%.2f) -- (%.2f,%.2f);"
                         % (bx - 0.08, y(lo), bx + 0.08, y(lo)))
            lines.append("\\draw[q1rule] (%.2f,%.2f) -- (%.2f,%.2f);"
                         % (bx - 0.08, y(hi), bx + 0.08, y(hi)))

legx = (len(CONDITIONS) - 1) * (PANEL_W + GAP) + PANEL_W + 0.35
for mi, model in enumerate(MODELS):
    ly = PANEL_H - 0.4 * mi
    lines.append("\\fill[%s] (%.2f,%.2f) rectangle (%.2f,%.2f);"
                 % (COLOURS.get(model, "q1blue"), legx, ly, legx + 0.3, ly + 0.22))
    lines.append("\\node[anchor=west] at (%.2f,%.2f) {%s};"
                 % (legx + 0.38, ly + 0.11, model))
lines.append("\\node[anchor=west,q1rule] at (%.2f,%.2f) "
             "{\\footnotesize indifferent};" % (legx, y(50)))
lines.append("\\node[rotate=90,anchor=south] at (-0.85,%.2f) "
             "{Franka share (\\%%)};" % (PANEL_H / 2.0))
lines.append("\\end{tikzpicture}")

fig_tex = FIGURES / "fig_ex2_q1_share.tex"
fig_tex.write_text("\n".join(lines) + "\n")
print("wrote", rel(fig_tex), "(%d lines)" % len(lines))
print()
print("Compile inside the thesis with \\input{}. It needs only tikz; the three")
print("\\definecolor lines are local so the picture stands alone, and should be")
print("deleted once includes.tex supplies the palette.")'''

MD14 = r"""## Cell 14. Provenance

Every input file with its row count and hash, the prompt version, the model
strings and the date, written beside the tables so any number in the chapter
can be traced back."""

C14 = r'''# --- Cell 14. Provenance. No model calls. -----------------------------------
prov = []
today = datetime.date.today().isoformat()

def run_meta(path):
    if not pathlib.Path(path).exists():
        return 0, "", ""
    rows = [json.loads(l) for l in open(path) if l.strip()]
    vers = sorted({r.get("ex2_prompt_version") for r in rows if r.get("ex2_prompt_version")})
    mods = sorted({r.get("model") for r in rows if r.get("model")})
    return len(rows), ";".join(vers), ";".join(mods)

for role, path in (("captures", CAPTURES / "consults.jsonl"),
                   ("congruent", CONGRUENT_OUT),
                   ("dims", DIMS_OUT)):
    if not pathlib.Path(path).exists():
        prov.append([role, rel(path), 0, "MISSING", "", "", today])
        continue
    n, vers, mods = run_meta(path)
    if role == "captures":
        n = sum(1 for l in open(path) if l.strip())
    prov.append([role, rel(path), n, sha256(path),
                 vers or P.EX2_PROMPT_VERSION, mods, today])

for model in MODELS:
    for rep in range(1, CUE_REPEATS + 1):
        f = RUNS / (CUE_FILE % (model, rep))
        if f.exists():
            prov.append(["cue_%s_r%d" % (model, rep), rel(f),
                         sum(1 for l in open(f) if l.strip()), sha256(f),
                         P.EX2_PROMPT_VERSION, model, today])

show(["role", "rows", "sha256", "prompt_version", "models"],
     [[r[0], r[2], (r[3] or "")[:12], r[4], r[5]] for r in prov])
write_csv("tab_ex2_q1_provenance.csv",
          ["role", "path", "rows", "sha256", "prompt_version", "model_string",
           "run_date"], prov)

print()
print("DESIGN FACTS THAT MUST BE DISCLOSED IN THE CHAPTER")
print("-" * 70)
print("1. The idle UR is chosen per position, as the one that can reach the")
print("   object. Every capture was written with ur_w idle, which is right")
print("   for the west positions and wrong for the east: there the object is")
print("   reached by ur_e, so idle-and-reachable collapsed to franka_n alone")
print("   and large_face had NO legal arm. The arm states are set after the")
print("   frames are rendered and no arm is ever commanded to move, so this")
print("   is a text-layer choice that contradicts nothing in the image.")
print("2. %d positions carry the contrast and show the block. %s excluded"
      % (len(USABLE), ", ".join(sorted(excluded)) or "none"))
print("   for legality: the franka cannot reach, so there is no arm choice.")
print("   %s excluded for occlusion: the block is not visible enough to"
      % (", ".join(sorted(OCCLUDED)) or "none"))
print("   judge, measured from pixels alone and blind to any model reply.")
print("3. Only ex2_cam was captured, so there is no viewpoint control.")
print("4. The design used THREE resting faces until 2026-08-27. The third,")
print("   the middle face, gave the only contrast between two orientations")
print("   that were both flat, and so the only test that separated deriving")
print("   the opening from geometry from reading posture and applying a")
print("   rule. It was withdrawn because no model could see it: GPT scored")
print("   58%% on that pair, Fisher p = 0.76, over 81 answered trials, while")
print("   answering a plain standing-or-flat question 18 times out of 18.")
print("   Evidence: runs/ex2_q1_cue_*.jsonl, retained. CONSEQUENCE: every")
print("   'obtains the opening from the geometry' verdict in this notebook")
print("   is consistent with posture-plus-rule and does not exclude it.")
print("5. Posture reaches the same answer by a SECOND route, which retiring")
print("   the third face did not create and no prompt wording removes.")
print("   'size_upright_m' states the frame its three numbers were taken")
print("   in -- standing on the smallest face -- so with two captured")
print("   faces the object is either in that frame or flat, and a two-way")
print("   posture judgement fixes the opening. The model never has to")
print("   work out which two extents are horizontal.")
print("   NOT PATCHED, deliberately. The extents reach the model as an")
print("   unordered set whatever the field is called, so dropping the")
print("   frame from the gloss would not restore a step; it would add an")
print("   ambiguity, since the numbers could then be read as the extents")
print("   AS PLACED and give min(0.100, 0.050) = 0.050 on large_face --")
print("   the wrong opening on the correct condition, which is")
print("   measurement error rather than a harder task.")
print("   Q1 therefore measures posture-plus-lookup and cannot separate")
print("   it from geometric derivation. State that in Limitations.")
print("6. Contrasts are paired within position; the quoted interval is the")
print("   t interval over positions, not Newcombe. Both are in the CSV.")
print("7. Prompt version %s. Rung %s only." % (P.EX2_PROMPT_VERSION, RUNG))'''
