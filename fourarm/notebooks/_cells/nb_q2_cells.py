"""Cell sources for ex2_q2_precedence.ipynb, the Q2 notebook.

Only the cells Q2 does not share with Q1 are here. Cells 0, 2 and 3 -- the
key paste, the block geometry check and the capture inventory -- are Q1's
own strings, spliced in by build_q2_nb.py, and cell 1 is Q1's cell 1 with
three declared substitutions applied there. There is one copy of each, so a
fix to the inventory reaches both notebooks.

Q2 asks: when the text states the capability-relevant quantity and the scene
contradicts it, which source governs the decision?
"""

MD4 = r"""## Cell 4. Conflict design check

No model calls. The `conflict` transform declares each face as the other, so
both the resting face and the opening in the text are false and every trial
crosses the Franka aperture.

This sits **after** the inventory rather than before it, because two of its
three assertions are about every scene and the scenes are loaded in cell 3.

**On the direction names.** `transforms.py` records `permissive` when the *true*
face is the all-arms one, so the text under-states the arms and forbids the
Franka. A reader reasonably expects `permissive` to mean the opposite, and it
has been read both ways already. Every table below names what the text does
instead."""

C4 = r'''# --- Cell 4. Conflict design check. No model calls. -------------------------
# THE DIRECTION NAMES. transforms.py sets direction = "permissive" when the
# TRUE face is the all-arms one, i.e. when the TEXT under-states the arms and
# forbids a Franka that would in fact fit. That is the opposite of what the
# word suggests, harness/h_ex2_transforms.py pins the stored sense, and
# run.py has been writing it into rows since the condition existed. So the
# field is left exactly alone and the tables print what the text DOES:
DIRECTION_NAME = {"restrictive": "text_permits_franka",
                  "permissive":  "text_forbids_franka"}

def direction_of(row_or_meta):
    """The display name for a conflict row's direction.

    Falls back to the geometry for rows written before solo.py recorded the
    field, which is the same rule transforms.py applies: the direction is a
    property of the TRUE opening, not of a pose word.
    """
    d = row_or_meta.get("direction")
    if d is None:
        w = row_or_meta.get("true_grasp_m")
        if w is None:
            return None
        d = "permissive" if w <= FRANKA_MAX else "restrictive"
    return DIRECTION_NAME.get(d, d)

q2_problems = []

# 1. The conflict map is a strict involution and every trial crosses the
#    aperture. Read off transforms, not asserted against a literal.
for face in FACES:
    other = T.OTHER_POSE_BY_LABEL[LABEL][face]
    if T.OTHER_POSE_BY_LABEL[LABEL][other] != face:
        q2_problems.append("%s -> %s is not an involution" % (face, other))
    if (FACTS[face]["grasp_m"] <= FRANKA_MAX) == (FACTS[other]["grasp_m"] <= FRANKA_MAX):
        q2_problems.append(
            "%s and %s fall the same side of the franka aperture, so "
            "declaring one as the other is not a capability flip"
            % (face, other))

# 2. Every scene: the declared face is the other one, the legal sets differ,
#    and the direction is recorded. The legal sets are computed by the REAL
#    validator, twice, exactly as solo.one_trial computes them.
design_seen, n_checked = {}, 0
for pos in USABLE:
    for face in FACES:
        s = by_pos[pos][face]
        st, meta = T.transform({"state": s["state"],
                                "positions_exact": s["positions_exact"]},
                               "conflict")
        # conflict_face declares the SAME face; it only withholds the
        # number. Checked here so the two cannot drift apart, because the
        # whole point of the pair is that their contrasts are comparable.
        _, meta_f = T.transform({"state": s["state"],
                                 "positions_exact": s["positions_exact"]},
                                "conflict_face")
        if meta_f["declared_pose"] != meta["declared_pose"]:
            q2_problems.append("%s_%s: conflict and conflict_face declare "
                               "different faces" % (pos, face))
        tid = R.flip_task_id(s["state"], meta["flip_prim"])
        lt = set(R.legal_arms(s, meta["flip_prim"], tid))
        ld = set(R.legal_arms(s, L.pose_prim(meta["flip_label"],
                                             meta["declared_pose"]), tid))
        n_checked += 1
        if meta["declared_pose"] != T.OTHER_POSE_BY_LABEL[LABEL][face]:
            q2_problems.append("%s_%s declares %r, expected the other face"
                               % (pos, face, meta["declared_pose"]))
        if lt == ld:
            q2_problems.append(
                "%s_%s: the true and declared legal sets are identical (%s), "
                "so the arm named cannot say which source was followed"
                % (pos, face, sorted(lt)))
        if meta["direction"] is None:
            q2_problems.append("%s_%s has no direction recorded" % (pos, face))
        # The text must also be internally consistent: a state that declared
        # the face but kept the true opening would be a different experiment.
        declared_open = [o for o in st["objects"]
                         if o["name"] == meta["flip_label"]][0]["grasp_m"]
        if abs(declared_open - FACTS[meta["declared_pose"]]["grasp_m"]) > 1e-9:
            q2_problems.append("%s_%s: declared face and declared opening "
                               "disagree" % (pos, face))
        design_seen.setdefault(face, (meta, sorted(lt), sorted(ld)))

# 3. The two-row design table, one row per direction.
design_rows = []
for face in FACES:
    meta, lt, ld = design_seen[face]
    design_rows.append([
        direction_of(meta), face, "%.3f" % FACTS[face]["grasp_m"],
        meta["declared_pose"], "%.3f" % FACTS[meta["declared_pose"]]["grasp_m"],
        any(a.startswith("franka") for a in lt),
        any(a.startswith("franka") for a in ld),
        ";".join(lt), ";".join(ld)])

show(["direction", "true_face", "true_open", "declared_face", "declared_open",
      "franka_true", "franka_declared", "legal_true", "legal_declared"],
     design_rows)
print()
if q2_problems:
    raise AssertionError("CONFLICT DESIGN CHECK FAILED:\n  "
                         + "\n  ".join(q2_problems[:12]))
print("PASS  %d scenes checked. Each face declares the other, the declared" % n_checked)
print("      opening follows the declared face, and the true and declared")
print("      legal sets differ on every one, so the arm named always says")
print("      which source was followed.")
print()
print("  text_permits_franka   the block lies on its large face, needs 0.100,")
print("                        and the text calls it the small face. Following")
print("                        the text names a Franka that cannot close.")
print("  text_forbids_franka   the block stands on its small face, needs 0.050,")
print("                        and the text calls it the large face. Following")
print("                        the text passes over a Franka that would fit.")
print()
print("BOTH directions are required. A model that simply avoids the Franka")
print("scores correctly in the first without consulting the image; the second")
print("is where that model is caught.")

write_csv("tab_ex2_q2_design.csv",
          ["direction", "true_face", "true_opening_m", "declared_face",
           "declared_opening_m", "franka_legal_true", "franka_legal_declared",
           "legal_true", "legal_declared"], design_rows)'''


MD5 = r"""## Cell 5. Prompt inspection

No model calls. `congruent` and `conflict` render **byte-identical system
prompts**: `prompts.CONDITIONS` maps both to the full glossary and the full R3,
and `system_prompt` branches on nothing else. The entire manipulation lives in
the state JSON.

That is a design strength and it belongs in the chapter, not only in an
assertion here: because the instructions are identical, no prompt difference
can explain the contrast between the two conditions."""

C5 = r'''# --- Cell 5. Prompt inspection. No model calls. -----------------------------
probe_scene = by_pos[USABLE[0]]["large_face"]
rendered = {}
for cond in CONDITIONS:
    rendered[cond] = S.render(probe_scene, cond, PREFERENCE, RUNG, "V")

# 1. The system prompts of congruent and conflict must be IDENTICAL. Asserted
#    rather than diffed: a diff that finds nothing looks like a diff that was
#    not run.
sys_con = rendered["congruent"][0][0]["content"]
sys_cfl = rendered["conflict"][0][0]["content"]
if sys_con != sys_cfl:
    raise AssertionError(
        "congruent and conflict render different instructions, so a contrast "
        "between them could come from the wording rather than from the state.")
print("PASS  congruent and conflict send byte-identical instructions")
print("      (%d characters). The whole manipulation is in the state, so no"
      % len(sys_con))
print("      prompt difference can explain the contrast. Say so in the chapter.")
print()

# 2. dims must still differ, or the glossary check below means nothing.
if rendered["dims"][0][0]["content"] == sys_con:
    raise AssertionError("dims renders the same instructions as congruent; "
                         "it must withhold the opening and the face")
print("PASS  dims still differs, so the comparison above is a real one")
print()

# 3. The state the model reads: the declared face must NOT be the true one.
import difflib
state_con = rendered["congruent"][0][1]["content"][-1]["text"]
state_cfl = rendered["conflict"][0][1]["content"][-1]["text"]
meta_cfl = rendered["conflict"][1]
if meta_cfl["declared_pose"] == meta_cfl["true_pose"]:
    raise AssertionError("the conflict state declares the true face")
print("scene %s: capture rests on %s, conflict text declares %s (%s)"
      % (probe_scene["seq"], meta_cfl["true_pose"], meta_cfl["declared_pose"],
         direction_of(meta_cfl)))
print()
print("=" * 70)
print("WHAT CHANGES IN THE STATE, congruent -> conflict")
print("=" * 70)
for line in difflib.unified_diff(state_con.splitlines(),
                                 state_cfl.splitlines(),
                                 lineterm="", n=1):
    if line.startswith(("---", "+++", "@@")):
        continue
    print("  " + line)
print()

# 4. The prompt module's own preflight checks, over every condition. They
#    raise; collected rather than raised one at a time so a run reports all
#    of them at once.
pp = []
for cond in CONDITIONS:
    for fn in (P.assert_glossary_matches_state, P.assert_r3_matches_state):
        try:
            fn(cond)
        except Exception as exc:
            pp.append("%s %s: %s" % (cond, fn.__name__, exc))
try:
    P.assert_base_states_no_relation()
except Exception as exc:
    pp.append("assert_base_states_no_relation: %s" % exc)
if pp:
    raise AssertionError("PROMPT CHECKS FAILED:\n  " + "\n  ".join(pp))
print("PASS  the glossary matches the state and R3 matches the state, in")
print("      every condition including conflict, and the base prompt states")
print("      no face-to-geometry relation.")
print()
print("=" * 70)
print("THE FULL CONFLICT PROMPT AT %s" % RUNG)
print("=" * 70)
print(sys_cfl)
print()
print("--- state ---")
print(state_cfl)'''


MD6 = r"""## Cell 6. Conflict at N0

**Makes model calls.** The same scenes, models, preference and repeat count as
Q1's two conditions, in the one condition Q1 did not run. Gated on
`CONFIRM_SPEND`; `solo.run` resumes, so re-running costs nothing."""

C6 = r'''# --- Cell 6. Conflict, N0. MAKES MODEL CALLS. -------------------------------
CONFLICT_OUT = RUNS / "ex2_q2_conflict_N0.jsonl"

# CALL_SCENES, from cell 3, so this asks about exactly the scenes Q1 paid for
# and the three conditions are one sample rather than three.
n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
print("COST: %d scenes x %d models x %d repeats = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
print("      %d usable positions x %d faces = %d scenes, plus the excluded"
      % (len(USABLE), len(FACES), len(USABLE) * len(FACES)))
print("      ones, asked so the exclusion stays visible in the data.")

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, CONFLICT_OUT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", REPEATS))):
    S.run(str(CAPTURES), out_path=str(CONFLICT_OUT), models=MODELS,
          conditions=("conflict",), preferences=(PREFERENCE,),
          rungs=(RUNG,), modalities=("V",), kind="pair", repeats=REPEATS)
    print("answered now:", answered(CONFLICT_OUT))'''


MD7 = r"""## Cell 7. Load and validate

No model calls. Reads Q2's conflict file alongside Q1's two, so every contrast
below is against a condition collected on the same scenes with the same
runner."""

C7 = r'''# --- Cell 7. Load and validate. No model calls. -----------------------------
# Q1's two files, by their own names. Q2 adds a condition; it does not re-run
# the two that already exist, and nothing here writes to them.
CONGRUENT_OUT = RUNS / "ex2_q1_congruent_N0.jsonl"
DIMS_OUT      = RUNS / "ex2_q1_dims_N0.jsonl"

ROWS, SKIPPED_MODELS = [], collections.Counter()
for path, cond in ((CONGRUENT_OUT, "congruent"), (CONFLICT_OUT, "conflict"),
                   (CONFLICT_FACE_OUT, "conflict_face"),
                   (CONGRUENT_FACE_OUT, "congruent_face"),
                   (DIMS_OUT, "dims")):
    _r, _s = load_run(path, cond, MODELS)
    ROWS += _r
    SKIPPED_MODELS += _s
print("distinct trials loaded: %d  (models %s)" % (len(ROWS), ", ".join(MODELS)))
if SKIPPED_MODELS:
    print("not in the design, left in the files and not counted below: %s"
          % ", ".join("%s %d" % (m, n) for m, n in sorted(SKIPPED_MODELS.items())))

flags = collections.Counter()
for r in ROWS:
    if r.get("error"):
        flags["transport error"] += 1
    if r.get("outcome") == "unparseable":
        flags["unparseable reply"] += 1
    if not r.get("arm"):
        flags["declined (no arm named)"] += 1
    if r.get("self_contradicted"):
        flags["reported an opening its own arm cannot span"] += 1
show(["issue", "n"], [[k, v] for k, v in sorted(flags.items())] or [["none", 0]])

ANALYSED = keep_analysable(ROWS, USABLE)
print()
print("rows after removing errors and unparseables and restricting to the")
print("%d usable positions: %d" % (len(USABLE), len(ANALYSED)))
print("expected: %d positions x %d faces x %d conditions x %d models x %d reps"
      " = %d" % (len(USABLE), len(FACES), len(CONDITIONS), len(MODELS), REPEATS,
                 len(USABLE) * len(FACES) * len(CONDITIONS) * len(MODELS)
                 * REPEATS))
print()

# Every conflict row must carry a direction, one way or the other.
_cfl = [r for r in ANALYSED if r["condition"] == "conflict"]
_nodir = [r for r in _cfl if direction_of(r) is None]
if _nodir:
    raise AssertionError("%d conflict rows carry no direction and none can "
                         "be derived" % len(_nodir))
print("conflict rows by direction: %s"
      % dict(collections.Counter(direction_of(r) for r in _cfl)))
print("  (from the row's own field where solo recorded it, else derived from")
print("   true_grasp_m by the same rule transforms.py uses)")

# THE COUPLING, both ways. See analysis/ex2/ex2_q_common.py for why the
# one-directional version this replaces read 100 percent everywhere.
print()
print("=" * 70)
print("COUPLING between the reported opening and the arm chosen")
print("=" * 70)
couple_rows = []
for cond in CONDITIONS:
    for model in MODELS:
        sub = [r for r in ANALYSED if r["condition"] == cond
               and r["model"] == model]
        agree, n, over_reach, over_cautious = coupling(sub, FRANKA_MAX)
        lo, hi = wilson(agree, n)
        couple_rows.append([cond, model, n, agree, fmt(pct(agree, n)),
                            fmt(lo), fmt(hi), over_reach, over_cautious])
show(["condition", "model", "coupled", "agree", "agree%", "lo", "hi",
      "said_wide_chose_franka", "said_narrow_chose_ur"], couple_rows)
print()
print("In CONFLICT this is the sharpest of the three. A model that follows")
print("the text reports the declared opening and names the arm that fits it,")
print("so it stays internally coupled while being wrong about the world.")
print("Coupling is a measure of self-consistency, never of correctness.")'''


MD8 = r"""## Cell 8. Franka share by resting face

No model calls. **Always anchored to the image**: the face named is the one the
capture actually shows, never the one the text declares. Declines are excluded
from numerator and denominator and reported in cell 11."""

C8 = r'''# --- Cell 8. Franka share by resting face. No model calls. ------------------
# share_rows carries all three conditions in Q1's column order, because the
# figure cell reads it and because the three-condition block is what a reader
# compares. The CSV the design document asks for is the conflict slice with
# the other two as reference columns, written below it.
share_rows = []
for cond in CONDITIONS:
    for model in MODELS:
        for face in FACES:
            sub = [r for r in ANALYSED if r["condition"] == cond
                   and r["model"] == model and r["face"] == face]
            k, n = share_counts(sub)
            lo, hi = wilson(k, n)
            share_rows.append([
                cond, model, face, len({r["position"] for r in sub}), n, k,
                fmt(pct(k, n)), fmt(lo), fmt(hi)])

show(["condition", "model", "face", "pos", "proposals", "franka", "share%",
      "lo", "hi"], share_rows)
print()
print("Read the conflict block against the congruent one directly above it.")
print("Congruent is the ceiling: the same scene, the same model, with the")
print("text telling the truth. Conflict differs from it only in what the")
print("text says.")

_by = {(r[0], r[1], r[2]): r for r in share_rows}
q2_share = []
for model in MODELS:
    for face in FACES:
        c = _by[("conflict", model, face)]
        q2_share.append(c[1:3] + c[3:9]
                        + [_by[("congruent", model, face)][6],
                           _by[("dims", model, face)][6]])
write_csv("tab_ex2_q2_share.csv",
          ["model", "resting_face", "n_positions", "n_proposals", "franka_n",
           "franka_share_pct", "wilson_lo", "wilson_hi",
           "congruent_share_pct", "dims_share_pct"], q2_share)'''


MD9 = r"""## Cell 9. Paired contrasts

No model calls. `small_minus_large`, paired within position, on the face the
**image** shows.

| Sign | Reading |
|---|---|
| Positive | tracking the scene |
| **Negative** | **tracking the text** |
| Near zero | tracking neither |

Q1 is the only condition where zero is the null. In conflict the text points
somewhere specific and wrong, so a text-follower goes negative."""

C9 = r'''# --- Cell 9. Paired contrasts. No model calls. ------------------------------
CONTRASTS = (("small_minus_large", "small_face", "large_face"),)
GATE_ZERO = 5.0        # below this a dims contrast is reported as none

bypos_rows, contrast_rows, ratios = [], [], {}
for cond in CONDITIONS:
    for model in MODELS:
        base = [r for r in ANALYSED if r["condition"] == cond
                and r["model"] == model]
        for name, a, b in CONTRASTS:
            pairs = paired_diffs(base, USABLE, a, b)
            diffs = [d for _, d in pairs]
            if cond == "conflict":
                bypos_rows += [[cond, model, pos, name, fmt(d)]
                               for pos, d in pairs]
            mean, plo, phi, npos = paired_mean_ci(diffs)
            ka, na = share_counts([r for r in base if r["face"] == a])
            kb, nb = share_counts([r for r in base if r["face"] == b])
            nlo, nhi = newcombe(ka, na, kb, nb)
            k_flip, n_flip = full_flip_count(diffs)
            # THE SIGN IS ONLY DIAGNOSTIC IN CONFLICT. In congruent the
            # text and the scene agree, so +100 is consistent with reading
            # either one and says nothing about which governed; in dims
            # there is no text to compete with. Labelling congruent
            # "tracks the scene" is the same error grade.classify_width's
            # "tie" label exists to prevent -- calling agreement grounding
            # inflates it -- so it is not labelled at all.
            if mean != mean:
                sign = "NA"
            elif cond in ("congruent", "congruent_face"):
                sign = "not diagnostic: sources agree"
            elif cond == "dims":
                sign = ("uses the scene" if plo > 0
                        else "no contrast" if phi < GATE_ZERO else "neither")
            elif cond == "conflict":
                # Caveated: R3 names opening_needed_m and the state supplies
                # it, so following the text here is rule-compliant and the
                # sign cannot separate preference from compliance.
                sign = ("scene, over a compliant reading" if plo > 0 else
                        "text (or R3 compliance)" if phi < 0 else "neither")
            else:                                   # conflict_face
                sign = ("TRACKS THE SCENE" if plo > 0 else
                        "TRACKS THE TEXT" if phi < 0 else "tracks neither")
            contrast_rows.append([cond, model, name, npos, fmt(mean),
                                  fmt(nlo), fmt(nhi), fmt(plo), fmt(phi),
                                  spans_zero(plo, phi), sign,
                                  "%d/%d" % (k_flip, n_flip), "NA"])
            ratios[(cond, model, name)] = mean

for r in contrast_rows:
    if r[0] == "conflict" and r[2] == "small_minus_large":
        num = ratios.get(("conflict", r[1], r[2]))
        den = ratios.get(("congruent", r[1], r[2]))
        r[12] = ("%.2f" % (num / den)) if (den is not None and den == den
                                          and abs(den) > 1e-9 and num is not None
                                          and num == num) else "NA"

show(["condition", "model", "contrast", "npos", "mean", "newc_lo", "newc_hi",
      "paired_lo", "paired_hi", "spans0", "reading", "full_flip", "ratio"],
     contrast_rows)
print()
print("full_flip is how many positions moved the whole way. A cell where all")
print("of them did has zero variance, so its t interval collapses to zero")
print("width and reads as a precision no sample of %d supports: quote the" % len(USABLE))
print("count and a Wilson interval on it instead.")
for r in contrast_rows:
    k, n = (int(x) for x in r[11].split("/"))
    if n and k == n:
        lo, hi = wilson(k, n)
        print("   %-10s %-9s saturated: %d of %d, Wilson [%.1f, %.1f]"
              % (r[0], r[1], k, n, lo, hi))

write_csv("tab_ex2_q2_contrasts.csv",
          ["condition", "model", "contrast", "n_positions", "mean_diff_pts",
           "newcombe_lo", "newcombe_hi", "paired_lo", "paired_hi",
           "spans_zero", "reading", "positions_full_flip",
           "ratio_to_congruent"],
          [r for r in contrast_rows if r[0] == "conflict"])
write_csv("tab_ex2_q2_contrasts_bypos.csv",
          ["condition", "model", "position_id", "contrast", "diff_pts"],
          bypos_rows)

print()
print("=" * 70)
print("READING, per model, in CONFLICT")
print("=" * 70)
for model in MODELS:
    r = [x for x in contrast_rows if x[0] == "conflict" and x[1] == model][0]
    c = [x for x in contrast_rows if x[0] == "congruent" and x[1] == model][0]
    print("  %-9s conflict %s   congruent %s   ratio %s"
          % (model, r[4], c[4], r[12]))
    if not r[3]:
        print("           -> NOT RUN. No position carries this contrast.")
    elif r[10] == "TRACKS THE TEXT":
        print("           -> the TEXT governs. The model names the arm the")
        print("              declared face implies, against the scene.")
        print("              READ THIS WITH THE LIMITATION. R3 names")
        print("              \"opening_needed_m\" and the state supplies it,")
        print("              so following the text is RULE-COMPLIANT here;")
        print("              no rule mentions resting_face at all. This")
        print("              result shows the models do not audit a supplied")
        print("              capability field against the scene. It cannot")
        print("              separate that from a preference for text over")
        print("              vision, because the prompt never asks them to")
        print("              prefer the scene. A face-only conflict, which")
        print("              withholds the number, is what would.")
    elif r[10] == "tracks the scene":
        print("           -> the SCENE governs, against a text that says")
        print("              otherwise. The strongest form of grounding this")
        print("              instrument can show.")
    else:
        print("           -> neither source governs. The arm does not move")
        print("              with the face, either the true one or the")
        print("              declared one, so this model is not reading the")
        print("              capability question at all here.")'''


MD10 = r"""## Cell 10. Which source the reported opening came from

No model calls, and **meaningful in `conflict` only**: in congruent and dims the
true and declared openings are the same number, so `grade.classify_width`
returns `tie` by design and the question does not arise.

This is the diagnostic that separates a model following the text from one that
is indifferent to both. Reported per direction."""

C10 = r'''# --- Cell 10. Reported opening: image, text or neither. No model calls. -----
# The stored width_belief is the PRIMARY reading. It is computed by
# grade.classify_width at trial time with a 6 mm tolerance, and it is
# cross-checked here against analyse_conflict.classify, which is a separate
# implementation using exact equality. The count is printed EVEN WHEN IT IS
# ZERO, so a reader knows the check ran rather than inferring it from silence.
from experiments.ex2 import analyse_conflict as AC

SOURCE_NAME = {"image": "matches image", "state": "matches text"}

cfl = [r for r in ANALYSED if r["condition"] == "conflict"]
disagree = 0
for r in cfl:
    theirs = AC.classify(r.get("believed_width_m"), r.get("true_grasp_m"),
                         r.get("declared_grasp_m"))
    if theirs != r.get("width_belief"):
        disagree += 1
print("width_belief cross-check against analyse_conflict.classify: "
      "%d disagreement(s) in %d rows" % (disagree, len(cfl)))
print("  (the two use different tolerances on purpose, 6 mm against exact,")
print("   so a disagreement is a rounded reply rather than a fault)")
print()

source_rows = []
for model in MODELS:
    for dname in ("text_permits_franka", "text_forbids_franka"):
        sub = [r for r in cfl if r["model"] == model
               and direction_of(r) == dname]
        counts = collections.Counter(
            SOURCE_NAME.get(r.get("width_belief"), "neither") for r in sub)
        for src in ("matches image", "matches text", "neither"):
            k = counts.get(src, 0)
            lo, hi = wilson(k, len(sub))
            source_rows.append([model, dname, src, len(sub), k,
                                fmt(pct(k, len(sub))), fmt(lo), fmt(hi)])

show(["model", "direction", "source", "n", "k", "pct", "lo", "hi"], source_rows)
write_csv("tab_ex2_q2_source.csv",
          ["model", "direction", "opening_source", "n_trials", "n", "pct",
           "wilson_lo", "wilson_hi"], source_rows)
print()
print("A model reporting the DECLARED opening has read the text and believed")
print("it. One reporting the TRUE opening has read the scene and overridden")
print("the text. One reporting NEITHER has derived a third number, which can")
print("only come from looking and misreading -- not from never looking.")
print()
print("Read this beside the arm in cell 9. Belief and action can come apart,")
print("and where they do the trial says something different about the model")
print("than either column says alone.")'''


MD11 = r"""## Cell 11. Declines by direction

No model calls. A model that recognises the contradiction may decline rather
than choose, and that is neither source. The denominator here is all replies
including declines, unlike the share table."""

C11 = r'''# --- Cell 11. Declines by direction. No model calls. ------------------------
wait_rows = []
for cond in CONDITIONS:
    for model in MODELS:
        subs = ([("all", [r for r in ANALYSED if r["condition"] == cond
                          and r["model"] == model])]
                if cond != "conflict" else
                [(d, [r for r in ANALYSED if r["condition"] == cond
                      and r["model"] == model and direction_of(r) == d])
                 for d in ("text_permits_franka", "text_forbids_franka")])
        for dname, sub in subs:
            k = sum(1 for r in sub if not r.get("arm"))
            lo, hi = wilson(k, len(sub))
            wait_rows.append([cond, model, dname, len(sub), k,
                              fmt(pct(k, len(sub))), fmt(lo), fmt(hi)])

show(["condition", "model", "direction", "trials", "declines", "rate%",
      "lo", "hi"], wait_rows)
write_csv("tab_ex2_q2_waits.csv",
          ["condition", "model", "direction", "n_trials", "declines_n",
           "decline_rate_pct", "wilson_lo", "wilson_hi"], wait_rows)

rates = [float(r[5]) for r in wait_rows if r[5] != "NA"]
print()
if rates and max(rates) < 5.0:
    print("ALL CELLS BELOW 5%%. Declines are not how these models handle a")
    print("contradiction: at most %.1f%% in any cell. They choose an arm and" % max(rates))
    print("the choice is the finding. Note this against the calibration")
    print("claim: a model that never declines never signals the conflict.")
else:
    print("Declining is not background here. A rate rising in one direction")
    print("and not the other is a model that notices the contradiction only")
    print("when following the text would break a rule, which is a weaker")
    print("form of noticing than declining in both.")'''


MD13 = r"""## Cell 13. Provenance

No model calls. Every input file with its row count and hash, the prompt
version, the model strings and the date, written beside the tables so any
number in the chapter can be traced back to the file it came from."""

C13 = r'''# --- Cell 13. Provenance. No model calls. -----------------------------------
prov = []
today = datetime.date.today().isoformat()
for role, path in (("captures", CAPTURES / "consults.jsonl"),
                   ("congruent", CONGRUENT_OUT),
                   ("congruent_face", CONGRUENT_FACE_OUT),
                   ("conflict", CONFLICT_OUT),
                   ("conflict_face", CONFLICT_FACE_OUT),
                   ("dims", DIMS_OUT),
                   # The frame arm cells 6d and 6e buy. The sha and the row
                   # count are how a reader tells a frame file bought whole
                   # from one still part-way through. Both cells define
                   # their path before they spend, so running them with
                   # CONFIRM_SPEND unset is enough to make these rows
                   # appear.
                   ("conflict_%s" % FRAME_ALT, FRAME_OUT["conflict"]),
                   ("conflict_face_%s" % FRAME_ALT,
                    FRAME_OUT["conflict_face"])):
    prov.append(provenance_row(role, path, OUT, today=today,
                               default_version=P.EX2_PROMPT_VERSION))

show(["role", "rows", "sha256", "prompt_version", "models"],
     [[r[0], r[2], (r[3] or "")[:12], r[4], r[5]] for r in prov])
write_csv("tab_ex2_q2_provenance.csv",
          ["role", "path", "rows", "sha256", "prompt_version", "model_string",
           "run_date"], prov)

print()
print("DESIGN FACTS THAT MUST BE DISCLOSED IN THE CHAPTER")
print("-" * 70)
print("1. congruent and conflict send BYTE-IDENTICAL instructions. The")
print("   glossary and R3 are the full ones in both, because the fields are")
print("   present and merely wrong. The entire manipulation is in the state,")
print("   so no prompt difference can explain the contrast. This is the same")
print("   argument Experiment 1 makes about the deployed prompt being")
print("   byte-identical at Full Information.")
print("2. The direction names are text_permits_franka and text_forbids_franka.")
print("   transforms.py stores them as 'restrictive' and 'permissive', in the")
print("   opposite sense to the one a reader expects, so the stored field is")
print("   left alone and the tables name what the text does.")
print("3. Both directions are required. A model that simply avoids the Franka")
print("   scores correctly where the text permits it, without consulting the")
print("   image; the other direction is where that model is caught.")
print("4. The contrast is always anchored to the IMAGE: the face named is the")
print("   one the capture shows, never the one the text declares. A negative")
print("   contrast therefore means the text governed.")
print("5. Contrasts are paired within position, and the same positions carry")
print("   every condition, so the three conditions are paired with each other")
print("   too and must not be read as independent samples.")
print("6. %d positions carry the contrast; e02 is excluded for legality and" % len(USABLE))
print("   e10 for occlusion, both decided in cell 3 before any model reply.")
print("7. Prompt version %s. Rung %s only. Preference %s."
      % (P.EX2_PROMPT_VERSION, RUNG, PREFERENCE))'''


MD1 = r"""# Experiment 2, Q2: Precedence

**When the text states the capability-relevant quantity and the scene
contradicts it, which source governs the decision?**

Rung `N0`, preference `franka`, three models, three repeats, on the same 34
captures and the same 32 usable positions as Q1.

Q1 established that rule application is not in doubt for any model: all three
score 100% on `small_face` and 0% on `large_face` when the text tells the
truth. So Q2 does not depend on derivation. A model that follows a supplied
field never needs to read the scene, and all three participate on equal terms.

The measure is Q1's, unchanged and **always anchored to the image**: Franka
share on the `small_face` scene minus Franka share on the `large_face` scene,
paired within position. Positive means the scene governed, negative means the
text did, near zero means neither. Negative is the expected result and is the
finding.

Cells 1 to 3 and 7 to 13 are free. Only cell 6 spends."""


MD6B = r"""## Cell 6b. Conflict-face at N0

**Makes model calls.** The same false face as cell 6, with `opening_needed_m`
**withheld**.

**Why this cell exists.** In `conflict` the state supplies `opening_needed_m`
and R3 names that field verbatim: *"the arm is capable only when its
`opening_max_m` is at least the object's `opening_needed_m`."* A model that
reads the stated number and applies R3 has broken no rule. So a text-following
result there cannot be told apart from **rule-compliance** — and no rule
mentions `resting_face` at all, so the false face in `conflict` is inert:
nothing asks the model to consult it, so nothing has to be overcome.

Withholding the number puts R3 into the form that names no field and says the
opening is not stated. The model must then derive an opening from a face, the
false face in the text competes with the true face in the image, and **neither
source is privileged by a rule**. Only here does the sign of the contrast mean
what `conflict`'s sign was taken to mean.

One repeat first. `conflict` came back saturated at -100.0 on 32 of 32
positions, so if this behaves the same way one repeat settles it; if it lands
somewhere intermediate, top up to three."""

C6B = r'''# --- Cell 6b. Conflict-face, N0. MAKES MODEL CALLS. -------------------------
CONFLICT_FACE_OUT = RUNS / "ex2_q2_conflict_face_N0.jsonl"
FACE_REPEATS = 1        # bound here, not REPEATS: see the markdown above

n_calls = len(CALL_SCENES) * len(MODELS) * FACE_REPEATS
print("COST: %d scenes x %d models x %d repeat = %d calls"
      % (len(CALL_SCENES), len(MODELS), FACE_REPEATS, n_calls))
print("      Same false face as cell 6, with opening_needed_m withheld, so")
print("      R3 names no field and following the text is not compliance.")

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, CONFLICT_FACE_OUT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", FACE_REPEATS))):
    S.run(str(CAPTURES), out_path=str(CONFLICT_FACE_OUT), models=MODELS,
          conditions=("conflict_face",), preferences=(PREFERENCE,),
          rungs=(RUNG,), modalities=("V",), kind="pair", repeats=FACE_REPEATS)
    print("answered now:", answered(CONFLICT_FACE_OUT))'''


MD6C = r"""## Cell 6c. Congruent-face at N0, the matched ceiling

**Makes model calls.** The **true** face stated, `opening_needed_m` withheld.
Byte-identical prompt to cell 6b, differing only in whether the stated face is
true.

Without this cell, `conflict_face` would have to be read against `congruent`,
which differs from it in **two** ways at once — the face is false *and* the
number is gone — so its contrast would confound *the text lied* with *the model
had to derive*. This removes the second difference. The pair isolates
precedence."""

C6C = r'''# --- Cell 6c. Congruent-face, N0. MAKES MODEL CALLS. ------------------------
# Q1's notebook writes this same file. If it has already been run there,
# spend_gate reports it complete and this cell costs nothing: one condition,
# one file, whichever notebook reaches it first.
CONGRUENT_FACE_OUT = RUNS / "ex2_q1_congruent_face_N0.jsonl"

n_calls = len(CALL_SCENES) * len(MODELS) * FACE_REPEATS
print("COST: %d scenes x %d models x %d repeat = %d calls"
      % (len(CALL_SCENES), len(MODELS), FACE_REPEATS, n_calls))
print("      True face, opening withheld: the matched ceiling for cell 6b.")

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, CONGRUENT_FACE_OUT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", FACE_REPEATS))):
    S.run(str(CAPTURES), out_path=str(CONGRUENT_FACE_OUT), models=MODELS,
          conditions=("congruent_face",), preferences=(PREFERENCE,),
          rungs=(RUNG,), modalities=("V",), kind="pair", repeats=FACE_REPEATS)
    print("answered now:", answered(CONGRUENT_FACE_OUT))'''


MD6A = r"""## Cell 6a. Prompt inspection: the withheld-number row

No model calls. The prompt cells 6b and 6c actually send, printed in full
before either of them spends.

Cell 5 inspected the row where the number is supplied. This is the other row of
the 2x2, and the two rows differ in the one way that matters: with
`opening_needed_m` withheld, R3 renders in the form that **names no field** and
says the opening is not stated. So a model cannot satisfy R3 by reading a
number, and following the text stops being rule-compliance.

`congruent_face` and `conflict_face` must render **byte-identical** prompts, or
they are not a matched pair and the contrast between them would confound the
false face with something in the wording."""

C6A = r'''# --- Cell 6a. The withheld-number prompt. No model calls. -------------------
face_probe = by_pos[USABLE[0]]["large_face"]
face_rendered = {c: S.render(face_probe, c, PREFERENCE, RUNG, "V")
                 for c in ("congruent", "conflict",
                           "congruent_face", "conflict_face")}

def object_row(msgs):
    body = msgs[1]["content"][-1]["text"]
    body = body.split("Cell state:\n")[1].rsplit("\nIdle arms", 1)[0]
    return [o for o in json.loads(body)["objects"]
            if o["name"] == LABEL][0]

# 1. The matched pair must be byte-identical, and must differ from the row
#    where the number is supplied.
sys_cf = face_rendered["conflict_face"][0][0]["content"]
sys_gf = face_rendered["congruent_face"][0][0]["content"]
if sys_cf != sys_gf:
    raise AssertionError(
        "congruent_face and conflict_face render different instructions, so "
        "a contrast between them could come from the wording rather than "
        "from whether the stated face is true.")
if sys_cf == face_rendered["conflict"][0][0]["content"]:
    raise AssertionError(
        "the withheld-number row renders the same prompt as the supplied "
        "row; R3 has not changed form and the whole point is lost.")
print("PASS  congruent_face and conflict_face send byte-identical")
print("      instructions (%d characters), and both differ from the" % len(sys_cf))
print("      supplied-number row. The pair isolates the false face.")
print()

# 2. The 2x2, as the model receives it.
print("=" * 70)
print("WHAT THE STATE SAYS ABOUT THE BLOCK, in each condition")
print("=" * 70)
print("the capture truly rests on %s, which needs %.3f m"
      % (face_rendered["congruent"][1]["true_pose"],
         face_rendered["congruent"][1]["true_grasp_m"]))
grid = []
for cond in ("congruent", "conflict", "congruent_face", "conflict_face"):
    o = object_row(face_rendered[cond][0])
    meta = face_rendered[cond][1]
    stated = o.get(P.FIELD_ALIASES.get("pose", "resting_face"))
    grid.append([cond,
                 "-" if stated is None else
                 ("%s (true)" % stated if stated == meta["true_pose"]
                  else "%s (FALSE)" % stated),
                 "%.3f" % o["opening_needed_m"]
                 if "opening_needed_m" in o else "withheld",
                 "yes" if '"opening_needed_m"' in
                 face_rendered[cond][0][0]["content"][
                     face_rendered[cond][0][0]["content"].index("R3  Gripper"):
                     face_rendered[cond][0][0]["content"].index("R4  Load")]
                 else "no"])
show(["condition", "resting_face in the text", "opening in the text",
      "R3 names a field"], grid)
print()
print("Read the last two columns together. Where R3 names a field and the")
print("state supplies it, a model that reads the number and applies the rule")
print("has broken nothing: following the text is COMPLIANCE. Where the")
print("number is withheld, R3 names nothing, and the only route to an")
print("opening is a face -- one asserted by the text, one visible in the")
print("image. That is the only place the sign of the contrast means the")
print("text won.")
print()
print("=" * 70)
print("THE FULL PROMPT cells 6b and 6c SEND (rung %s)" % RUNG)
print("=" * 70)
print(sys_cf)
print()
print("--- user message: image (1024x1024 PNG), then this text ---")
print()
print(face_rendered["conflict_face"][0][1]["content"][-1]["text"])'''


# ---------------------------------------------------------------------------
# Cells 6d and 6e. The frame control for the two conflict conditions
# ---------------------------------------------------------------------------

MD6D = r"""## Cells 6d and 6e. The same two conditions under the `extents` frame

**Make model calls.** The `named` object-field gloss says the extents were
*"measured standing on its smallest face"*. The block is 0.130 x 0.100 x 0.050,
so its smallest face **is** `small_face`, and that phrase is a claim about how
the object is sitting.

**Why that matters more here than anywhere else in the thesis.** Cell 13 states
that `congruent` and `conflict` send byte-identical instructions and that the
entire manipulation is in the state, so no prompt difference can explain the
contrast. That is true, and it is not the whole picture. Under the `named`
frame the prompt carries **two** claims about the object's pose: the declared
`resting_face`, which conflict makes false, and the glossary phrase, which
always points at `small_face`. The design is described throughout as the text
against the image. Under `named` it is the declared face against the image
against a third statement that agrees with neither on half the trials.

**What the frame does about it.** `extents` renders the same three numbers as
*"three extents largest first"* and names no orientation, so the only pose claim
left in the text is the declared face -- the one the design is about. Nothing
else changes: the state, the scenes, the models, the rung and the repeat count
all come from the cells above.

**Where it could change the answer.** Cell 9 reads `conflict` as *text (or R3
compliance)* and `conflict_face` as **TRACKS THE TEXT**. A model reporting 0.050
because the glossary told it the object stands on its smallest face gives the
same answer as one following the declared face on every trial where the declared
face is `small_face`. Those two are indistinguishable under `named` and separate
under `extents`. If the verdict survives the frame, precedence is about the
declared face; if it weakens, part of what was read as text-following was the
glossary.

**Matched repeats, read off disk.** Both conflict files are on disk at three
repeats -- cell 6b's `FACE_REPEATS = 1` was topped up -- so each cell here buys
three, read from its own named twin and asserted rather than taken from
`REPEATS` or `FACE_REPEATS`. That is 612 calls per cell.

**Cell 6d defines the arm; 6e only extends it.** The read-out is cell 14, at the
end, so it can reuse cell 7's loader and cell 9's contrast and reading rule
rather than keeping a second copy that could drift from them."""

C6D = r'''# --- Cell 6d. Conflict at N0, EXTENTS frame. MAKES MODEL CALLS. -------------
import difflib

# THE FRAME IS PROMPTS' OWN NAME FOR IT, never a string invented here. If it
# is renamed there this must fail rather than quietly re-buy the DEFAULT
# frame and file it as a control: a file compared with itself reads as a
# clean null, and that is the most expensive way to be wrong in this
# notebook.
FRAME_ALT = "extents"
if FRAME_ALT not in P.DIMS_FRAMES:
    raise AssertionError(
        "%r is not in prompts.DIMS_FRAMES (%s)."
        % (FRAME_ALT, ", ".join(P.DIMS_FRAMES)))

FRAME_CONDS = ("conflict", "conflict_face")

def frame_file(cond):
    """One file per condition, with the frame in the name.

    The frame is in solo's trial_id too, so this is belt and braces -- but a
    frame arm pointed at the named file would find every id present, skip
    the lot, and report itself complete having spent nothing.
    """
    return RUNS / ("ex2_q2_%s_%s_%s.jsonl" % (cond, RUNG, FRAME_ALT))

FRAME_OUT = {c: frame_file(c) for c in FRAME_CONDS}
# The named twin each frame file is read against, named here rather than
# rebuilt in cell 14, so the read-out cannot pair a frame arm with the
# wrong baseline.
FRAME_NAMED = {"conflict": CONFLICT_OUT,
               "conflict_face": CONFLICT_FACE_OUT}

def show_frame_edit(cond):
    """Print what the frame changes in the prompt, and check it is that.

    The manipulation is only interpretable if it touches the glossary line
    and nothing else. Two things are asserted rather than described. The
    phrase this control exists to remove must be gone, or the cell is
    buying the confound again under a different file name. And the extents
    gloss must withhold exactly what the named gloss withholds, or the
    frame has changed the CONDITION as well as the wording -- which in a
    conflict condition would be catastrophic, since withholding the opening
    is the whole difference between cell 6 and cell 6b.
    """
    a = P.system_prompt(RUNG, cond, dims_frame="named").splitlines()
    b = P.system_prompt(RUNG, cond, dims_frame=FRAME_ALT).splitlines()
    d = list(difflib.unified_diff(a, b, lineterm="", n=0))
    add = [l[1:] for l in d if l.startswith("+") and not l.startswith("+++")]
    rem = [l[1:] for l in d if l.startswith("-") and not l.startswith("---")]
    if not add and not rem:
        raise AssertionError(
            "the %s prompt for %s is identical to the named one. There is "
            "no contrast to buy." % (FRAME_ALT, cond))
    for l in rem:
        if l.strip():
            print("   - " + l)
    for l in add:
        if l.strip():
            print("   + " + l)

    named_gloss = P._object_fields(cond, "named")
    alt_gloss = P._object_fields(cond, FRAME_ALT)
    # WHITESPACE COLLAPSED BEFORE SEARCHING. The gloss is wrapped to the
    # prompt's width and "standing on its smallest face" falls across a line
    # break in every condition, so a plain substring test finds the phrase
    # absent from the NAMED gloss and reports the control as unnecessary.
    # Checked on the flattened text; printed as it is sent.
    flat = lambda t: " ".join(t.split())
    PHRASE = "smallest face"
    if PHRASE in flat(alt_gloss):
        raise AssertionError(
            "the %s gloss for %s still contains the phrase this control "
            "exists to remove:\n%s" % (FRAME_ALT, cond, alt_gloss))
    if PHRASE not in flat(named_gloss):
        raise AssertionError(
            "the NAMED gloss for %s no longer contains \"%s\", so this cell "
            "is a control against nothing:\n%s" % (cond, PHRASE, named_gloss))
    # WITHHELD THE SAME WAY IN BOTH FRAMES. conflict_face withholds the
    # opening and says so; until 2026-09-03 _object_fields dispatched on
    # `condition == "dims"` and handed it the FULL extents gloss, which
    # announces an "opening_needed_m" the state does not carry. That would
    # have turned cell 6e into cell 6d with different wording.
    for field in ("opening_needed_m", "resting_face"):
        if (field in named_gloss) != (field in alt_gloss):
            raise AssertionError(
                "%s names %r in one frame and not the other, so the frame "
                "changes what the condition WITHHOLDS and not only how it "
                "is worded:\n\nnamed:\n%s\n\n%s:\n%s"
                % (cond, field, named_gloss, FRAME_ALT, alt_gloss))
    print()
    print("   PASS  the phrase is gone, and %s withholds the same fields in"
          % cond)
    print("         both frames, so the only difference is the wording.")

def frame_repeats(cond, path=None):
    """The named twin's repeat count, read off disk.

    NOT `REPEATS`, and NOT `FACE_REPEATS`. Cell 6 declares three and cell 6b
    declares one, and the conflict_face file was topped up to three after
    the fact, so neither constant describes what is on disk. A frame arm at
    one repeat would widen every interval by about 1.6x and leave the clean
    arm noisier than the confounded one it is read against, and an unmatched
    control is worth less than no control.
    """
    # `path` defaults to this arm's own twin. Cell 14 passes one in for the
    # matched ceiling, whose named file belongs to cell 6c rather than to
    # this arm, so the repeat rule is stated once and applied everywhere
    # rather than half-copied into the read-out.
    path = FRAME_NAMED[cond] if path is None else path
    rows, _ = load_run(path, cond, MODELS)
    frames = {r.get("dims_frame") or "named" for r in rows}
    if frames - {"named"}:
        raise AssertionError(
            "%s holds %s rows, so it is not the named twin this control is "
            "read against. The two frames must not share a file."
            % (path.name, ", ".join(sorted(frames - {"named"}))))
    return len({r.get("repeat") for r in rows if r.get("rung") == RUNG})

# --- conflict ---------------------------------------------------------------
COND = "conflict"
print("=" * 70)
print("THE FRAME EDIT: %s minus named, in %s" % (FRAME_ALT, COND))
print("=" * 70)
show_frame_edit(COND)
print()
print("   The phrase that goes away describes small_face. Under named this")
print("   condition therefore carries TWO claims about the pose -- the")
print("   declared resting_face, which is false here, and the glossary --")
print("   and they disagree with each other on the trials where the")
print("   declared face is large_face. Under extents only the declared")
print("   face remains, which is the contrast cell 9 reports.")
print()
print("=" * 70)
print("THE FULL PROMPT SENT, %s %s under %s" % (COND, RUNG, FRAME_ALT))
print("=" * 70)
print(P.system_prompt(RUNG, COND, dims_frame=FRAME_ALT))
print("=" * 70)
print()

FRAME_REPEATS = frame_repeats(COND)
n_calls = len(CALL_SCENES) * len(MODELS) * FRAME_REPEATS
if not FRAME_REPEATS:
    print("The named twin this is read against is not on disk:")
    print("  %s" % rel(FRAME_NAMED[COND]))
    print("Cell 6 buys it. Nothing to control against, nothing bought.")
else:
    print("COST: %d scenes x %d models x %d repeats = %d calls"
          % (len(CALL_SCENES), len(MODELS), FRAME_REPEATS, n_calls))
    print("      condition %s, rung %s, dims frame %s"
          % (COND, RUNG, FRAME_ALT.upper()))
    print("      repeats read from %s, matched to the arm this is read"
          % rel(FRAME_NAMED[COND]))
    print("      against rather than taken from REPEATS or FACE_REPEATS.")

# AT COLUMN 0, DELIBERATELY. This is the one line in the cell that exists to
# be typed into, and it used to sit inside the else: above -- where swapping
# None for a number is one stray space away from an IndentationError, and
# where a line pasted at the wrong depth leaves the gate reading a value the
# cell never set. Nothing below is nested under a branch either, so the line
# can be edited without having to work out what encloses it.
CONFIRM_SPEND = None            # <-- set to the number in the COST line

# FRAME_REPEATS AND ..., so a missing named twin never reaches the gate: it
# would be asked to confirm zero calls, which prints an instruction to type
# a number that would buy nothing.
#
# factors= is the guard against a later cell rebinding FRAME_REPEATS: the
# gate refuses when the counts stop multiplying to the number being
# confirmed, rather than the run quietly coming out a third of the size.
if FRAME_REPEATS and spend_gate(n_calls, CONFIRM_SPEND, FRAME_OUT[COND],
                                factors=(("scenes", len(CALL_SCENES)),
                                         ("models", len(MODELS)),
                                         ("repeats", FRAME_REPEATS))):
    # dims_frames is the ONE thing that differs from the run that produced
    # the named twin. Scenes, models, preference, rung, modality and kind
    # are read from cells 1 and 3, so the two runs cannot come apart on
    # anything the comparison is not about.
    S.run(str(CAPTURES), out_path=str(FRAME_OUT[COND]), models=MODELS,
          conditions=(COND,), preferences=(PREFERENCE,), rungs=(RUNG,),
          modalities=("V",), kind="pair", repeats=FRAME_REPEATS,
          dims_frames=(FRAME_ALT,))
    print("answered now:", answered(FRAME_OUT[COND]))'''


MD6E = r"""## Cell 6e. Conflict-face at N0, under `extents`

**Makes model calls.** The endpoint of Q2, under a gloss that names no
orientation. This is the cell the frame question actually bites on.

`conflict` supplies `opening_needed_m` and R3 names that field, so following
the text there is rule-compliant and cell 9 caveats the sign accordingly. Here
the number is withheld, R3 names no field, and the model has to derive an
opening from a face -- so the sign is diagnostic and the chapter reads it as
**TRACKS THE TEXT**.

Under `named` that verdict has a competitor. A model that reports 0.050 because
the glossary said the object stands on its smallest face produces exactly the
answer a text-follower produces, on every trial where the declared face is
`small_face`. The two are one number under `named` and two under `extents`.
The anchor column in cell 14 is where they come apart: correctness and the
0.050 anchor differ only where the **true** face is `large_face`.

**Nothing about the control is restated here.** The frame name, the file naming
and the repeat rule are cell 6d's, used as it left them, so the two files are
one arm rather than two that share a suffix."""

C6E = r'''# --- Cell 6e. Conflict-face at N0, EXTENTS frame. MAKES MODEL CALLS. --------
# CELL 6d DEFINES THE ARM; this only extends it to the second condition. The
# frame name, the output naming and the repeat rule are stated once, in 6d,
# so that this cell cannot buy a differently-defined control and file it
# beside the first. Two arms under one name is worse than one arm and a gap.
for _n in ("FRAME_ALT", "FRAME_OUT", "FRAME_NAMED", "frame_repeats",
           "show_frame_edit"):
    if _n not in globals():
        raise AssertionError(
            "%s is not defined, so cell 6d has not been run in this kernel. "
            "This cell extends 6d's arm rather than restating it." % _n)

COND = "conflict_face"
print("=" * 70)
print("THE FRAME EDIT: %s minus named, in %s" % (FRAME_ALT, COND))
print("=" * 70)
show_frame_edit(COND)
print()
print("   The opening is withheld in BOTH frames -- checked above, not")
print("   assumed -- so this stays cell 6b's condition and the only thing")
print("   that moved is the phrase that named an orientation.")
print()
print("=" * 70)
print("THE FULL PROMPT SENT, %s %s under %s" % (COND, RUNG, FRAME_ALT))
print("=" * 70)
print(P.system_prompt(RUNG, COND, dims_frame=FRAME_ALT))
print("=" * 70)
print()

# REPEATS READ FOR THIS CONDITION, not carried over from 6d. The two named
# files were bought by cells that declare different repeat counts, and they
# agree on disk today only because 6b was topped up. Reading again is what
# keeps each frame arm matched to its own twin.
FRAME_REPEATS = frame_repeats(COND)
n_calls = len(CALL_SCENES) * len(MODELS) * FRAME_REPEATS
if not FRAME_REPEATS:
    print("The named twin this is read against is not on disk:")
    print("  %s" % rel(FRAME_NAMED[COND]))
    print("Cell 6b buys it. Nothing to control against, nothing bought.")
else:
    print("COST: %d scenes x %d models x %d repeats = %d calls"
          % (len(CALL_SCENES), len(MODELS), FRAME_REPEATS, n_calls))
    print("      condition %s, rung %s, dims frame %s"
          % (COND, RUNG, FRAME_ALT.upper()))
    print("      False face declared, opening withheld, and now no")
    print("      orientation named anywhere in the prompt. This is the cell")
    print("      the frame question bites on.")

# AT COLUMN 0, for the reason cell 6d gives: this is the line that is meant
# to be typed into, so it is not nested inside anything.
CONFIRM_SPEND = None            # <-- set to the number in the COST line

if FRAME_REPEATS and spend_gate(n_calls, CONFIRM_SPEND, FRAME_OUT[COND],
                                factors=(("scenes", len(CALL_SCENES)),
                                         ("models", len(MODELS)),
                                         ("repeats", FRAME_REPEATS))):
    S.run(str(CAPTURES), out_path=str(FRAME_OUT[COND]), models=MODELS,
          conditions=(COND,), preferences=(PREFERENCE,), rungs=(RUNG,),
          modalities=("V",), kind="pair", repeats=FRAME_REPEATS,
          dims_frames=(FRAME_ALT,))
    print("answered now:", answered(FRAME_OUT[COND]))'''


# ---------------------------------------------------------------------------
# Cell 14. The frame read-out
# ---------------------------------------------------------------------------

MD14 = r"""## Cell 14. The frame control read-out

No model calls. Reads cells 6d and 6e off disk and puts them beside the named
runs cells 8, 9 and 10 report, using the same loader, the same share
definition, the same paired contrast and the same reading rule, so the `named`
column here reproduces the numbers already in the Q2 tables rather than being a
second, differently-computed version of them. It checks that it has: a named
delta or a named reading that disagrees with cell 9's stops the cell.

**Safe to run part-way through a paid cell.** It reads files, not a live
handle, so it survives a kernel restart, and a run still in progress shows a
fractional repeats-worth rather than being silently reported as a null.

**The matched ceiling comes along if it is there.** `congruent_face` under
`extents` is bought by Q1's cell 7d, into `ex2_q1_congruent_face_N0_extents.jsonl`.
Cell 6c already treats the named version as one file for whichever notebook
reaches it first, and the same applies here: if Q1 has bought it, this cell
reports it, labelled as Q1's, so `conflict_face` under `extents` can be read
against its ceiling under `extents` rather than against a ceiling from the
other frame. Nothing here writes to that file.

**What to read.** Not the delta on its own -- the **reading**. Cell 9's verdict
for `conflict_face` is TRACKS THE TEXT, and the question this cell answers is
whether that verdict is about the declared face or partly about a glossary
phrase that named an orientation. The last table prints the verdict under both
frames side by side, which is the form the chapter needs.

**No interval on the frame effect**, on purpose. It is a difference of paired
differences across two runs, and a t interval on it would report a precision the
design does not have. Under `dims` the same quantity moved by roughly 45 points
on Gemini at N0 and 30 to 48 on GPT at the treated rungs. Something of that
order is what is being looked for; a handful of points is not resolvable here
and must not be written up as one."""

C14 = r'''# --- Cell 14. The frame control read-out. No model calls. -------------------
# CELLS 6d AND 6e DEFINE THE ARM. This reads it, and names nothing of its
# own: the frame, the two conditions, the files and the repeat rule all come
# from there, so the read-out cannot end up describing a differently-defined
# control than the one that was bought.
for _n in ("FRAME_ALT", "FRAME_CONDS", "FRAME_OUT", "FRAME_NAMED",
           "frame_repeats"):
    if _n not in globals():
        raise AssertionError(
            "%s is not defined, so cell 6d has not been run in this kernel. "
            "Run 6d and 6e -- with CONFIRM_SPEND unset they make no calls "
            "and only define the arm -- then run this." % _n)

# Every helper here is the one cells 7, 8, 9 and 10 use. A control computed
# by a different rule than the number it controls is not a control, and that
# is enforced by there being one definition rather than a comment promising
# there are two.
OPEN_TOL = 0.006                  # the tolerance cell 10 grades openings on
SMALL_OPEN = FACTS["small_face"]["grasp_m"]

# THE MATCHED CEILING, if Q1 has bought it. conflict_face is read against
# congruent_face throughout this notebook -- that is what cell 6c exists for
# -- and a ceiling measured under the other frame is not a ceiling for this
# arm. Q1's cell 7d owns that file; this cell reports it and never writes to
# it, exactly as cell 7 treats Q1's named runs.
READ_CONDS = list(FRAME_CONDS)
READ_FILE = dict(FRAME_OUT)
READ_NAMED = dict(FRAME_NAMED)
READ_OWNER = {c: "cells 6d/6e" for c in FRAME_CONDS}
CEIL_EXT = RUNS / ("ex2_q1_congruent_face_%s_%s.jsonl" % (RUNG, FRAME_ALT))
if CEIL_EXT.exists():
    READ_CONDS.append("congruent_face")
    READ_FILE["congruent_face"] = CEIL_EXT
    READ_NAMED["congruent_face"] = CONGRUENT_FACE_OUT
    READ_OWNER["congruent_face"] = "Q1 cell 7d"
else:
    print("The matched ceiling under %s is not on disk:" % FRAME_ALT)
    print("  %s" % rel(CEIL_EXT))
    print("Q1's cell 7d buys it. conflict_face is reported below against its")
    print("NAMED ceiling only, which is a weaker comparison: read the")
    print("conflict_face rows knowing the ceiling has not moved with them.")
    print()

# --- what is on disk, reported rather than assumed --------------------------
# A file that is missing or part-written is REPORTED, not silently rendered
# as a blank row. Reading part-way through a paid cell is a normal thing to
# do here, and "the frame arm has not been bought yet" and "it was bought
# and moved nothing" must never look the same.
FRAME_ROWS, frame_status = {}, []
for cond in READ_CONDS:
    path = READ_FILE[cond]
    per_rep = len(USABLE) * len(FACES) * len(MODELS)
    named_reps = frame_repeats(cond, READ_NAMED[cond])
    if not pathlib.Path(path).exists():
        FRAME_ROWS[cond] = []
        frame_status.append([cond, READ_OWNER[cond], path.name, 0, per_rep,
                             "MISSING", "-", named_reps])
        continue
    rows, skipped = load_run(path, cond, MODELS)
    # trial_id carries the frame, so a file can only hold the frame it was
    # written for -- but check rather than assume: an out_path typo would
    # otherwise pool named rows into the frame column and read as a null.
    frames = sorted({r.get("dims_frame") or "named" for r in rows})
    if frames not in ([FRAME_ALT], []):
        raise AssertionError(
            "%s holds dims_frame %s, expected %r. The two frames must not "
            "share a file." % (path.name, frames, FRAME_ALT))
    keep = keep_analysable(rows, USABLE)
    reps = sorted(r for r in {x.get("repeat") for x in keep} if r is not None)
    FRAME_ROWS[cond] = keep
    # A RATIO rather than a complete/partial flag: each arm is bought at its
    # own twin's repeat count, so a flat flag would call a finished arm short
    # whenever that count is more than one.
    frame_status.append([cond, READ_OWNER[cond], path.name, len(keep),
                         per_rep, "%.2f" % (len(keep) / float(per_rep)),
                         ",".join("r%s" % r for r in reps) or "-", named_reps])
    if skipped:
        print("  %s: %d rows from models outside MODELS, not counted"
              % (path.name, sum(skipped.values())))

show(["condition", "bought by", "file", "analysable", "per repeat",
      "repeats worth", "repeats present", "named repeats"], frame_status)
print()
print("analysable = no transport error, reply parsed, and the position is one")
print("of the %d that carry the contrast and show the block. A run still in"
      % len(USABLE))
print("progress shows a fractional repeats-worth and fewer repeats than its")
print("named twin; the tables below are still readable, just noisier.")
print()

# --- the reading rule, cell 9's, applied to both frames ---------------------
def reading_of(cond, mean, plo, phi):
    """Cell 9's verdict rule, so the frame column is labelled as the named
    column is. Written out rather than imported because it is a DECISION and
    lives in the cell that makes it -- and checked below against the labels
    cell 9 actually produced, so the two copies cannot drift in silence.
    """
    if mean != mean:
        return "NA"
    if cond in ("congruent", "congruent_face"):
        return "not diagnostic: sources agree"
    if cond == "dims":
        return ("uses the scene" if plo > 0
                else "no contrast" if phi < GATE_ZERO else "neither")
    if cond == "conflict":
        return ("scene, over a compliant reading" if plo > 0 else
                "text (or R3 compliance)" if phi < 0 else "neither")
    return ("TRACKS THE SCENE" if plo > 0 else
            "TRACKS THE TEXT" if phi < 0 else "tracks neither")

def opening_stats(rows):
    """(n stated, % correct for the face SHOWN, % reporting 0.050).

    The third column is the ANCHOR, and it is what the frame moved under
    dims: the named gloss names small_face, so a model reading that phrase
    as a pose claim reports that face's opening whatever the picture shows
    and whatever the text declares. Correctness and the anchor come apart
    only where the true face is large_face, which is half these rows.
    """
    stated = [r for r in rows if r.get("opening_needed_m") is not None]
    if not stated:
        return 0, None, None
    ok = sum(1 for r in stated
             if abs(r["opening_needed_m"] - FACTS[r["face"]]["grasp_m"])
             <= OPEN_TOL)
    anchored = sum(1 for r in stated
                   if abs(r["opening_needed_m"] - SMALL_OPEN) <= OPEN_TOL)
    return len(stated), pct(ok, len(stated)), pct(anchored, len(stated))

frame_rows, frame_delta, frame_read = [], {}, {}
for cond in READ_CONDS:
    for model in MODELS:
        for frame in ("named", FRAME_ALT):
            sub = [r for r in (ANALYSED if frame == "named"
                               else FRAME_ROWS[cond])
                   if r["condition"] == cond and r["model"] == model]
            n_open, ok, anchor = opening_stats(sub)
            # THE SAME quantity cell 9 reports, anchored to the IMAGE: the
            # face named is the one the capture shows, never the one the
            # text declares, so a negative contrast means the text governed.
            diffs = [d for _, d in paired_diffs(sub, USABLE,
                                                "small_face", "large_face")]
            mean, lo, hi, npos = paired_mean_ci(diffs)
            fk, fn = full_flip_count(diffs)
            label = reading_of(cond, mean, lo, hi)
            frame_delta[(cond, model, frame)] = mean
            frame_read[(cond, model, frame)] = label
            frame_rows.append([cond, model, frame, len(sub), n_open, fmt(ok),
                               fmt(anchor),
                               fmt(share_at([r for r in sub
                                             if r["face"] == "small_face"])),
                               fmt(share_at([r for r in sub
                                             if r["face"] == "large_face"])),
                               npos, fmt(mean), fmt(lo), fmt(hi),
                               "%d/%d" % (fk, fn), label])

# THE NAMED COLUMN MUST BE CELL 9'S. Both the number and the verdict are
# recomputed here from ANALYSED with the same helpers rather than read out
# of cell 9's tables, so this comparison is a real check on both and not a
# restatement of one of them. A disagreement means the two cells are no
# longer measuring the same thing, or reading it by different rules, which
# would make every frame effect below uninterpretable.
for cond in READ_CONDS:
    for model in MODELS:
        row = [x for x in contrast_rows if x[0] == cond and x[1] == model
               and x[2] == "small_minus_large"]
        if not row:
            continue
        a, b = frame_delta[(cond, model, "named")], row[0][4]
        if fmt(a) != b:
            raise AssertionError(
                "the named delta for %s / %s is %s here and %s in cell 9. "
                "The two are meant to be the same quantity computed by the "
                "same helpers." % (cond, model, fmt(a), b))
        if frame_read[(cond, model, "named")] != row[0][10]:
            raise AssertionError(
                "the named reading for %s / %s is %r here and %r in cell 9. "
                "reading_of has drifted from the rule cell 9 applies."
                % (cond, model, frame_read[(cond, model, "named")],
                   row[0][10]))
print("named delta and named reading checked against cell 9: identical.")
print()

show(["condition", "model", "frame", "rows", "stated", "opening ok%",
      "reports .050%", "franka% small", "franka% large", "pos", "delta",
      "lo", "hi", "full flips", "reading"], frame_rows)
write_csv("tab_ex2_q2_frame_cells.csv",
          ["condition", "model", "dims_frame", "n_rows", "n_stated",
           "opening_correct_pct", "reports_small_opening_pct",
           "franka_share_small_pct", "franka_share_large_pct", "n_positions",
           "mean_diff_pts", "paired_lo", "paired_hi", "full_flips",
           "reading"], frame_rows)
print()
print("delta = franka share on small_face minus franka share on large_face,")
print("        paired within position over %d positions, anchored to the FACE"
      % len(USABLE))
print("        THE IMAGE SHOWS. Positive is tracking the scene, negative is")
print("        tracking the text, near zero is tracking neither.")
print()

# --- the one thing these two cells exist to produce -------------------------
print("=" * 78)
print("FRAME EFFECT: does the verdict survive a gloss that names no orientation?")
print("=" * 78)
move_rows = []
for cond in READ_CONDS:
    for model in MODELS:
        dn = frame_delta[(cond, model, "named")]
        de = frame_delta[(cond, model, FRAME_ALT)]
        gap = None if (dn is None or de is None or dn != dn or de != de) \
            else de - dn
        rn, re_ = (frame_read[(cond, model, "named")],
                   frame_read[(cond, model, FRAME_ALT)])
        move_rows.append([cond, model, fmt(dn), fmt(de), fmt(gap), rn, re_,
                          "" if re_ == "NA" else
                          "same" if rn == re_ else "CHANGED"])

show(["condition", "model", "delta named", "delta %s" % FRAME_ALT,
      "difference", "reading named", "reading %s" % FRAME_ALT, "verdict"],
     move_rows)
write_csv("tab_ex2_q2_frame_effect.csv",
          ["condition", "model", "delta_named_pts",
           "delta_%s_pts" % FRAME_ALT, "difference_pts", "reading_named",
           "reading_%s" % FRAME_ALT, "verdict_moved"], move_rows)
print()
print("NO INTERVAL ON THE DIFFERENCE COLUMN, on purpose. It is a difference")
print("of paired differences across two runs, and a t interval on it would be")
print("reporting a precision the design does not have. This is a presence")
print("test: under dims the same quantity moved by roughly 45 points on")
print("gemini at N0 and 30 to 48 on gpt at the treated rungs. Something of")
print("that order is the effect being looked for; a handful of points is not")
print("resolvable here and must not be written up as one.")
print()
print("=" * 78)
print("WHAT THE TWO OUTCOMES MEAN, stated before the numbers are read")
print("=" * 78)
print("  VERDICT SAME      the glossary phrase was not doing the work. What")
print("                    the models followed is the DECLARED FACE, which is")
print("                    what Q2 says they followed. The precedence result")
print("                    stands, and the chapter gains a control that says")
print("                    so rather than an assumption.")
print()
print("  VERDICT CHANGED   part of what was read as text-following was the")
print("                    glossary naming an orientation. Q2's endpoint")
print("                    needs restating: the models follow SOME text, but")
print("                    the experiment did not isolate the declared face,")
print("                    and cell 13's claim that the whole manipulation")
print("                    lives in the state needs the qualification that")
print("                    the PROMPT also asserted a pose.")
print()
print("  Read conflict_face first. conflict supplies opening_needed_m and R3")
print("  names it, so its sign was already caveated as rule-compliance;")
print("  conflict_face is where the sign is diagnostic and where a change")
print("  costs the chapter something.")
print()
for row in move_rows:
    cond, model, gap, moved = row[0], row[1], row[4], row[7]
    if gap == "NA":
        print("  %-14s %-9s NOT BOUGHT YET, or no position carries the "
              "contrast" % (cond, model))
    else:
        print("  %-14s %-9s %8s points   %s -> %s   %s"
              % (cond, model, gap, row[5], row[6], moved))'''


MD15 = r"""---
## Cell 15. Audit: Tables 5.10 and 5.11 against the thesis

Both tables have a `conflict` half and a `conflict_face` half. Only the
`conflict` half had a generator: the cells above write
`tab_ex2_q2_contrasts.csv` and `tab_ex2_q2_source.csv` for that condition
alone, so the `conflict_face` rows in the chapter were transcribed by hand.

That is the half that carries the result. Under `conflict` the opening is
supplied and R3 tells the model to use it, so following the text shows
compliance with a stated value. Under `conflict_face` nothing supplies it and
the model must derive it from a face — the text's or the image's — which is
the direct test of which source governs.

This cell generates both halves and checks every cell against Chapter 5.
"""

C15 = r'''# --- Cell 15. Audit against the thesis. No model calls. ---------------------
# PUBLISHED VALUES, transcribed from Chapter 5 and never computed here.

# Table 5.10: share on the small-face capture, on the large-face capture, the
# paired contrast, its interval where the table prints one, and complete flips.
# Shares are anchored to the CAPTURED face, never the declared one.
THESIS_510 = {
    ("conflict", "gpt_hi"):         (0.0, 100.0, -100.0, None, None, 32),
    ("conflict", "gemini"):         (0.0, 100.0, -100.0, None, None, 32),
    ("conflict", "claude_md"):      (0.0, 100.0, -100.0, None, None, 32),
    ("conflict_face", "gpt_hi"):    (0.0, 89.6, -89.6, -95.0, -84.1, 22),
    ("conflict_face", "gemini"):    (0.0, 100.0, -100.0, None, None, 32),
    ("conflict_face", "claude_md"): (50.0, 42.7, 7.3, -6.7, 21.3, 1),
}

# Table 5.11: where the reported opening came from, as (scene, text, neither).
# The two openings differ by 50 mm and are scored at a 6 mm tolerance, so a
# reply cannot match both.
# Keyed on the chapter's own row labels, which describe what the TEXT says.
#
# DO NOT KEY THIS ON THE ROW'S "direction" FIELD. That field names what the
# SCENE permits, and the two are exact opposites: every "permissive" row
# declares 0.100, which forbids a Franka, on a capture of the small face,
# which allows one. Keying on it transposes the table, and because both halves
# hold percentages in the same range the result looks entirely plausible. The
# audit caught exactly that on its first run.
#
# The text forbids a Franka when the declared width exceeds the 0.080 aperture.
THESIS_511 = {
    ("conflict", "text forbids Franka", "gpt_hi"):         (0.0, 100.0, 0.0),
    ("conflict", "text forbids Franka", "gemini"):         (0.0, 100.0, 0.0),
    ("conflict", "text forbids Franka", "claude_md"):      (0.0, 100.0, 0.0),
    ("conflict", "text permits Franka", "gpt_hi"):         (0.0, 100.0, 0.0),
    ("conflict", "text permits Franka", "gemini"):         (0.0, 100.0, 0.0),
    ("conflict", "text permits Franka", "claude_md"):      (0.0, 100.0, 0.0),
    ("conflict_face", "text forbids Franka", "gpt_hi"):    (0.0, 97.9, 2.1),
    ("conflict_face", "text forbids Franka", "gemini"):    (0.0, 100.0, 0.0),
    ("conflict_face", "text forbids Franka", "claude_md"): (51.0, 47.9, 1.0),
    ("conflict_face", "text permits Franka", "gpt_hi"):    (10.4, 89.6, 0.0),
    ("conflict_face", "text permits Franka", "gemini"):    (0.0, 100.0, 0.0),
    ("conflict_face", "text permits Franka", "claude_md"): (51.0, 47.9, 1.0),
}

# The matched ceiling each conflict cell is read against, from Table 5.7.
THESIS_CEILING = {
    ("conflict", "gpt_hi"): 100.0, ("conflict", "gemini"): 100.0,
    ("conflict", "claude_md"): 100.0,
    ("conflict_face", "gpt_hi"): 89.6, ("conflict_face", "gemini"): 100.0,
    ("conflict_face", "claude_md"): -5.2,
}

OPEN_TOL = 0.006        # the tolerance cell 10 scores the reported opening at
EPS = 0.06              # rounding on a value printed to one decimal
problems = []


def agrees(label, got, want, eps=EPS):
    if want is None:
        return
    if got is None or abs(got - want) > eps:
        problems.append("%s: computed %s, thesis prints %s" % (label, got, want))


# Both conditions, loaded the same way and through the same helpers the cells
# above use, so the audit cannot pass by scoring differently.
AUDIT_FILES = (("conflict", CONFLICT_OUT), ("conflict_face", CONFLICT_FACE_OUT))

share_rows_all, source_rows_all = [], []
for cond, path in AUDIT_FILES:
    raw, _ = load_run(path, cond, MODELS)
    kept = keep_analysable(raw, USABLE)

    for model in MODELS:
        shares = {}
        for face in FACES:
            sub = [r for r in kept if r["model"] == model and r["face"] == face]
            k, n = share_counts(sub)
            shares[face] = (100.0 * k / n) if n else None
            share_rows_all.append([cond, model, face, len(sub), n, k,
                                   round(shares[face], 1) if n else "NA"])
        s, l = shares["small_face"], shares["large_face"]
        want = THESIS_510[(cond, model)]
        agrees("5.10 %s %s small" % (cond, model),
               round(s, 1) if s is not None else None, want[0])
        agrees("5.10 %s %s large" % (cond, model),
               round(l, 1) if l is not None else None, want[1])
        if s is not None and l is not None:
            agrees("5.10 %s %s contrast" % (cond, model), round(s - l, 1), want[2])

        # Complete flips: positions where every repeat took UR on the capture
        # that forbids a Franka and Franka on the one that allows it.
        flips = 0
        for pos in USABLE:
            per = {f: [r for r in kept if r["model"] == model
                       and r["face"] == f and r["position"] == pos]
                   for f in FACES}
            if not all(per[f] for f in FACES):
                continue
            sk, sn = share_counts(per["small_face"])
            lk, ln = share_counts(per["large_face"])
            if sn and ln and abs((100.0 * sk / sn) - (100.0 * lk / ln)) == 100.0:
                flips += 1
        agrees("5.10 %s %s flips" % (cond, model), float(flips),
               float(want[5]), 0.5)

        # Table 5.11, split by what the TEXT declares rather than by the
        # row's "direction" field -- see the note on THESIS_511.
        for direction in ("text forbids Franka", "text permits Franka"):
            forbids = direction == "text forbids Franka"
            sub = [r for r in kept if r["model"] == model
                   and (r["declared_grasp_m"] > FRANKA_MAX) == forbids]
            n = len(sub)
            scene = sum(1 for r in sub if r.get("opening_needed_m") is not None
                        and abs(r["opening_needed_m"] - r["true_grasp_m"]) <= OPEN_TOL)
            text = sum(1 for r in sub if r.get("opening_needed_m") is not None
                       and abs(r["opening_needed_m"] - r["declared_grasp_m"]) <= OPEN_TOL)
            neither = n - scene - text
            got = tuple(round(100.0 * x / n, 1) if n else None
                        for x in (scene, text, neither))
            source_rows_all.append([cond, model, direction, n, scene, text,
                                    neither] + list(got))
            want11 = THESIS_511.get((cond, direction, model))
            if want11:
                for label, g, w in zip(("scene", "text", "neither"), got, want11):
                    agrees("5.11 %s %s %s matches %s"
                           % (cond, direction, model, label), g, w)

print("Table 5.10, Franka share by captured face, both conflict conditions")
show(["condition", "model", "face", "trials", "proposals", "franka", "share %"],
     share_rows_all)
write_csv("tab_ex2_q2_conflict_share.csv",
          ["condition", "model", "resting_face", "n_trials", "n_proposals",
           "franka_n", "franka_share_pct"], share_rows_all)

print()
print("Table 5.11, where the reported opening came from")
show(["condition", "model", "direction", "n", "scene", "text", "neither",
      "scene %", "text %", "neither %"], source_rows_all)
write_csv("tab_ex2_q2_conflict_source.csv",
          ["condition", "model", "direction", "n_trials", "n_scene", "n_text",
           "n_neither", "scene_pct", "text_pct", "neither_pct"], source_rows_all)

print()
print("Experiment 2, Q2: tables checked against the thesis")
show(["Table", "Reports", "Checks"],
     [["5.10", "Franka share, contrast and complete flips, both directions",
       len(THESIS_510) * 4],
      ["5.11", "which source the reported opening came from", len(THESIS_511) * 3]])
print()
for p in problems:
    print("  MISMATCH  %s" % p)
print("%d checks against Chapter 5, %d disagreed"
      % (len(THESIS_510) * 4 + len(THESIS_511) * 3, len(problems)))
assert not problems, "Q2 no longer reproduces the thesis: %s" % problems[:5]
print("every Q2 table still matches what Chapter 5 prints")
'''
