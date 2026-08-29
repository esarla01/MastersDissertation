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
                   ("conflict", CONFLICT_OUT),
                   ("dims", DIMS_OUT)):
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
