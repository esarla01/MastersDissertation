"""EX2 conflict analysis, built from the run files.

Step 1: load, clean and verify. Nothing is computed from the replies here.
The purpose is to establish that the rows about to be analysed are the rows
the design calls for, and to surface anything that would make a later table
wrong.

Usage:
    python3 ex2_analyse.py runs/All_conflict.jsonl
"""

import collections
import json
import sys

MODELS = ("gpt", "qwen", "gemini")
PREFERENCES = ("franka", "ur")
RUNGS = ("P0", "P1", "P2a", "P2", "P3a", "P3", "P4")

SCENES_PER_POSE = 11
REPEATS = 3
CELL_N = SCENES_PER_POSE * 2 * REPEATS          # 66
POSE_N = SCENES_PER_POSE * REPEATS              # 33

TRIAL_KEY = ("model", "preference", "rung", "trial_id", "repeat")


def load(paths):
    """Read every row, keeping errors and duplicates for now."""
    rows = []
    for path in paths:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def clean(rows):
    """Drop error rows, then drop duplicate trials, reporting both."""
    kept, errors = [], []
    for r in rows:
        (errors if r.get("error") else kept).append(r)

    seen, unique, dupes = set(), [], []
    for r in kept:
        key = tuple(r.get(k) for k in TRIAL_KEY)
        if key in seen:
            dupes.append(key)
        else:
            seen.add(key)
            unique.append(r)
    return unique, errors, dupes


def report_load(rows, unique, errors, dupes):
    print("=" * 70)
    print("STEP 1  LOAD AND INTEGRITY")
    print("=" * 70)
    print("rows read            %d" % len(rows))
    print("error rows dropped   %d" % len(errors))
    if errors:
        by = collections.Counter(
            (r.get("model"), r.get("rung")) for r in errors)
        for k in sorted(by, key=lambda x: tuple(str(i) for i in x)):
            print("    %-8s %-4s %d" % (k[0], k[1], by[k]))
    print("duplicate trials     %d  (dropped, first occurrence kept)"
          % len(dupes))
    print("rows analysed        %d" % len(unique))


def check_cells(rows):
    """Every model x preference x rung cell must be 33 lying and 33 upright."""
    print()
    print("-" * 70)
    print("CELL COMPLETENESS   expected %d per cell, %d per pose"
          % (CELL_N, POSE_N))
    print("-" * 70)

    counts = collections.Counter()
    poses = collections.Counter()
    for r in rows:
        cell = (r.get("model"), r.get("preference"), r.get("rung"))
        counts[cell] += 1
        poses[cell + (r.get("true_pose"),)] += 1

    faults = []
    for model in MODELS:
        for pref in PREFERENCES:
            line = []
            for rung in RUNGS:
                cell = (model, pref, rung)
                n = counts.get(cell, 0)
                lying = poses.get(cell + ("lying",), 0)
                upright = poses.get(cell + ("upright",), 0)
                ok = (n == CELL_N and lying == POSE_N and upright == POSE_N)
                line.append("%s %s" % (rung, "ok" if ok else "%d/%d/%d"
                                       % (n, lying, upright)))
                if not ok:
                    faults.append((cell, n, lying, upright))
            print("%-7s %-7s %s" % (model, pref, "  ".join(line)))

    if faults:
        print()
        print("FAULTS  cell, total, lying, upright")
        for cell, n, lying, upright in faults:
            print("   %s  %d  %d  %d" % (cell, n, lying, upright))
    return faults


def check_versions(rows):
    """Surface prompt version differences across cells.

    gpt and qwen ran P0 to P3a at one version and P4 at another; gemini ran
    everything at the later one. Whether that matters depends on what the
    version bump changed, which this script cannot know.
    """
    print()
    print("-" * 70)
    print("PROMPT VERSION BY MODEL AND RUNG")
    print("-" * 70)
    seen = collections.defaultdict(set)
    for r in rows:
        seen[(r.get("model"), r.get("rung"))].add(r.get("ex2_prompt_version"))

    versions = set()
    for model in MODELS:
        line = []
        for rung in RUNGS:
            vs = sorted(v or "none" for v in seen.get((model, rung), []))
            versions.update(vs)
            line.append("%s %s" % (rung, ",".join(vs)))
        print("%-7s %s" % (model, "  ".join(line)))

    if len(versions) > 1:
        print()
        print("WARNING  more than one prompt version is present.")
        print("  Cells at different versions are comparable only if the")
        print("  version bump left their rungs unchanged. Diff the prompt")
        print("  builder at these versions before reporting them together.")
    return versions


def check_fixed_fields(rows):
    """Anything that should be constant across the file."""
    print()
    print("-" * 70)
    print("FIXED FIELDS")
    print("-" * 70)
    for field in ("condition", "modality", "view", "solo"):
        vals = collections.Counter(r.get(field) for r in rows)
        flag = "" if len(vals) == 1 else "   <-- not constant"
        print("%-12s %s%s" % (field, dict(vals), flag))


def check_repeats(rows):
    """State the repeat structure explicitly.

    A cell of 66 trials is 22 scenes answered three times, not 66
    independent observations. Later steps that report a rate must use the
    per-scene majority as the unit.
    """
    print()
    print("-" * 70)
    print("REPEAT STRUCTURE")
    print("-" * 70)
    reps = collections.Counter(r.get("repeat") for r in rows)
    scenes = len(set(r.get("trial_id", "").rsplit("|", 1)[0]
                     for r in rows if r.get("trial_id")))
    print("repeat values        %s" % dict(sorted(reps.items())))
    print("distinct scene keys  %d" % scenes)
    print("a cell of %d trials is %d scenes x %d repeats; per-scene majority"
          % (CELL_N, SCENES_PER_POSE * 2, REPEATS))
    print("is the unit of analysis for any reported rate.")


# ---------------------------------------------------------------------------
# Step 2: extraction validation.
# ---------------------------------------------------------------------------
# The primary endpoint is a number lifted out of free prose. Three successive
# versions of that extractor produced plausible tables and wrong findings
# before being caught, so nothing here trusts it. Every stated width is
# audited against what the physics allows, and the stored classification is
# recomputed from the raw fields and compared.

TRUE_WIDTHS = (0.058, 0.096)
APERTURES = (0.080, 0.140)      # Franka and UR. Never an object width.


def classify(believed, true_w, declared_w):
    """Recompute width belief from the raw fields, independent of grade.py."""
    if believed is None:
        return None
    if true_w is not None and declared_w is not None and true_w == declared_w:
        return "tie"
    if declared_w is not None and believed == declared_w:
        return "state"
    if true_w is not None and believed == true_w:
        return "image"
    return "other"


def check_extraction(rows):
    print()
    print("=" * 70)
    print("STEP 2  EXTRACTION VALIDATION")
    print("=" * 70)

    print()
    print("-" * 70)
    print("STATED WIDTHS BY MODEL   only %s are defensible"
          % " and ".join(str(w) for w in TRUE_WIDTHS))
    print("-" * 70)
    faults = []
    for model in MODELS:
        sub = [r for r in rows if r.get("model") == model]
        vals = collections.Counter(r.get("believed_width_m") for r in sub)
        print("%-7s n=%d" % (model, len(sub)))
        for val in sorted(vals, key=lambda v: (v is None, v)):
            note = ""
            if val is None:
                note = "   <-- no width stated or reply unparsed"
            elif val in APERTURES:
                note = "   <-- APERTURE, not an object width: EXTRACTOR FAULT"
                faults.append((model, val, vals[val]))
            elif val not in TRUE_WIDTHS:
                note = "   <-- neither candidate: misderivation or fault"
            print("    %-10s %4d%s" % (val, vals[val], note))

    print()
    print("-" * 70)
    print("OFF-CANDIDATE AND NULL REPLIES, BY MODEL AND RUNG")
    print("-" * 70)
    for model in MODELS:
        line = []
        for rung in RUNGS:
            sub = [r for r in rows
                   if r.get("model") == model and r.get("rung") == rung]
            null = sum(1 for r in sub if r.get("believed_width_m") is None)
            off = sum(1 for r in sub
                      if r.get("believed_width_m") is not None
                      and r.get("believed_width_m") not in TRUE_WIDTHS)
            line.append("%s %d/%d" % (rung, null, off))
        print("%-7s %s" % (model, "  ".join(line)))
    print("(null / off-candidate per cell; both should normally be 0)")

    print()
    print("-" * 70)
    print("OFF-CANDIDATE REPLIES IN FULL")
    print("-" * 70)
    odd = [r for r in rows
           if r.get("believed_width_m") is not None
           and r.get("believed_width_m") not in TRUE_WIDTHS]
    if not odd:
        print("none")
    for r in odd:
        why = r.get("why")
        grasp = why.get("grasp") if isinstance(why, dict) else why
        print("%-7s %-4s %-7s %-8s width=%s arm=%s" %
              (r.get("model"), r.get("rung"), r.get("preference"),
               r.get("true_pose"), r.get("believed_width_m"), r.get("arm")))
        print("    %s" % str(grasp)[:200])

    print()
    print("-" * 70)
    print("STORED CLASSIFICATION vs RECOMPUTED FROM RAW FIELDS")
    print("-" * 70)
    mismatches = []
    ties = []
    for r in rows:
        true_w = r.get("true_grasp_m")
        decl_w = r.get("declared_grasp_m")
        if true_w is not None and decl_w is not None and true_w == decl_w:
            ties.append(r)
        again = classify(r.get("believed_width_m"), true_w, decl_w)
        if again != r.get("width_belief"):
            mismatches.append((r, again))
    print("rows checked         %d" % len(rows))
    print("classification agrees %d" % (len(rows) - len(mismatches)))
    print("mismatches            %d" % len(mismatches))
    for r, again in mismatches[:10]:
        print("    %-7s %-4s stored=%s recomputed=%s width=%s true=%s decl=%s"
              % (r.get("model"), r.get("rung"), r.get("width_belief"), again,
                 r.get("believed_width_m"), r.get("true_grasp_m"),
                 r.get("declared_grasp_m")))
    print("conflict trials where declared == true: %d  (should be 0)"
          % len(ties))

    return faults, mismatches, ties


# ---------------------------------------------------------------------------
# Step 3: width belief, the primary endpoint.
# ---------------------------------------------------------------------------
# A cell of 66 pools two preferences and two poses, and those sub-cells are
# not exchangeable. Under the Franka preference the guidance pulls toward
# franka_n, and the only width admitting a Franka is 0.058. On an upright
# scene 0.058 is ALSO the true width, so a model reaching for the preferred
# arm scores as image-consistent without consulting anything. On a lying
# scene the same pull runs the other way and an image-consistent answer
# costs the model its preferred arm.
#
# So the franka/lying cell is the only one where image use is paid for, and
# it is the cell to read first. The pooled figure is printed for comparison
# with earlier tables and marked as unsafe.


def scene_of(row):
    """Bare scene id, e.g. 'e01_A' from 'e01_A|conflict|gpt|franka|P0|V|r3'."""
    tid = row.get("trial_id") or ""
    return tid.split("|", 1)[0]


def _rate(sub):
    n = len(sub)
    k = sum(1 for r in sub if r.get("width_belief") == "image")
    return k, n


def check_width_belief(rows):
    print()
    print("=" * 70)
    print("STEP 3  WIDTH BELIEF (PRIMARY ENDPOINT)")
    print("=" * 70)

    print()
    print("-" * 70)
    print("3a  POOLED PER CELL, out of 66   NOT THE HEADLINE, see 3b")
    print("-" * 70)
    head = "rung   " + "".join("%-12s" % ("%s/%s" % (m[:3], p[:3]))
                               for m in MODELS for p in PREFERENCES)
    print(head)
    for rung in RUNGS:
        line = "%-7s" % rung
        for model in MODELS:
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung]
                k, n = _rate(sub)
                line += "%-12s" % ("%d/%d" % (k, n))
        print(line)

    print()
    print("-" * 70)
    print("3b  SPLIT BY PREFERENCE AND TRUE POSE, out of 33")
    print("    fr/ly is the only cell where image use overrides the guidance")
    print("-" * 70)
    for model in MODELS:
        print("%s" % model)
        print("  rung    fr/lying   fr/upright  ur/lying   ur/upright")
        for rung in RUNGS:
            cells = []
            for pref in PREFERENCES:
                for pose in ("lying", "upright"):
                    sub = [r for r in rows if r.get("model") == model
                           and r.get("preference") == pref
                           and r.get("rung") == rung
                           and r.get("true_pose") == pose]
                    k, n = _rate(sub)
                    cells.append("%d/%d" % (k, n))
            print("  %-7s %-10s %-11s %-10s %-10s"
                  % (rung, cells[0], cells[1], cells[2], cells[3]))
        print()

    print("-" * 70)
    print("3c  PREFERENCE GAP   |franka rate - ur rate| over the pooled cell")
    print("    A large gap means the arm preference, not the image, is")
    print("    driving the stated width at that rung.")
    print("-" * 70)
    print("rung    " + "".join("%-22s" % m for m in MODELS))
    for rung in RUNGS:
        line = "%-7s " % rung
        for model in MODELS:
            rates = []
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung]
                k, n = _rate(sub)
                rates.append(100.0 * k / n if n else float("nan"))
            gap = abs(rates[0] - rates[1])
            flag = " *" if gap >= 25.0 else "  "
            line += "%-22s" % ("%.0f vs %.0f, gap %.0f%s"
                               % (rates[0], rates[1], gap, flag))
        print(line)
    print("* gap of 25 points or more: treat that cell as preference-driven")

    print()
    print("-" * 70)
    print("3d  PER-SCENE MAJORITY, out of 22 scenes")
    print("    22 scenes answered 3 times each. A scene counts as image only")
    print("    if 2 of its 3 repeats were image-consistent.")
    print("-" * 70)
    print("rung   " + "".join("%-12s" % ("%s/%s" % (m[:3], p[:3]))
                              for m in MODELS for p in PREFERENCES))
    for rung in RUNGS:
        line = "%-7s" % rung
        for model in MODELS:
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung]
                by_scene = collections.defaultdict(list)
                for r in sub:
                    by_scene[scene_of(r)].append(
                        r.get("width_belief") == "image")
                maj = sum(1 for v in by_scene.values()
                          if sum(v) * 2 > len(v))
                line += "%-12s" % ("%d/%d" % (maj, len(by_scene)))
        print(line)


# ---------------------------------------------------------------------------
# Step 4: infeasible assignments.
# ---------------------------------------------------------------------------
# Independent of the width extractor. An assignment is infeasible when the
# named arm is not in legal_true, that is, it cannot span the object's REAL
# width. This is wrong on the physics whatever the model believed or wrote,
# so it survives the objection that a stated width is downstream of the
# text and the arm preference.
#
# Only lying trials can produce one: upright the bottle is 0.058 and every
# arm spans it. Under the UR preference following the guidance is always
# safe, so a non-zero count there is a different fault entirely.


def is_infeasible(row):
    """Named arm outside the arms the validator accepts under the true pose."""
    arm = row.get("arm")
    legal = row.get("legal_true") or []
    if arm is None:
        return False            # a declined assignment is not infeasible
    return arm not in legal


def check_infeasible(rows):
    print()
    print("=" * 70)
    print("STEP 4  PHYSICALLY INFEASIBLE ASSIGNMENTS")
    print("=" * 70)

    print()
    print("-" * 70)
    print("4a  LYING TRIALS, out of 33   the only trials where a choice can")
    print("    be illegal; upright admits every arm")
    print("-" * 70)
    print("rung   " + "".join("%-12s" % ("%s/%s" % (m[:3], p[:3]))
                              for m in MODELS for p in PREFERENCES))
    for rung in RUNGS:
        line = "%-7s" % rung
        for model in MODELS:
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung
                       and r.get("true_pose") == "lying"]
                k = sum(1 for r in sub if is_infeasible(r))
                line += "%-12s" % ("%d/%d" % (k, len(sub)))
        print(line)

    print()
    print("-" * 70)
    print("4b  UPRIGHT TRIALS   expected 0 everywhere; any count is a fault")
    print("-" * 70)
    bad = 0
    for model in MODELS:
        line = "%-7s" % model
        for rung in RUNGS:
            sub = [r for r in rows if r.get("model") == model
                   and r.get("rung") == rung
                   and r.get("true_pose") == "upright"]
            k = sum(1 for r in sub if is_infeasible(r))
            bad += k
            line += "%s %d  " % (rung, k)
        print(line)
    if bad:
        print("WARNING  %d infeasible assignment(s) on upright trials, which"
              " should be impossible." % bad)

    print()
    print("-" * 70)
    print("4c  DECLINED ASSIGNMENTS (arm is null), lying trials, out of 33")
    print("    Declining is not infeasible. A model that believes no arm")
    print("    fits should decline, so these are counted apart.")
    print("-" * 70)
    print("rung   " + "".join("%-12s" % ("%s/%s" % (m[:3], p[:3]))
                              for m in MODELS for p in PREFERENCES))
    for rung in RUNGS:
        line = "%-7s" % rung
        for model in MODELS:
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung
                       and r.get("true_pose") == "lying"]
                k = sum(1 for r in sub if r.get("arm") is None)
                line += "%-12s" % ("%d/%d" % (k, len(sub)))
        print(line)

    print()
    print("-" * 70)
    print("4d  AGREEMENT BETWEEN STATED WIDTH AND CHOSEN ARM")
    print("    franka preference, lying trials, out of 33.")
    print("    'image + legal' is the model overriding the guidance on both")
    print("    the width and the arm. 'image + illegal' would mean it said")
    print("    0.096 and named a Franka anyway.")
    print("-" * 70)
    for model in MODELS:
        print("%s" % model)
        print("  rung    img+legal  img+illegal  state+legal  state+illegal")
        for rung in RUNGS:
            sub = [r for r in rows if r.get("model") == model
                   and r.get("preference") == "franka"
                   and r.get("rung") == rung
                   and r.get("true_pose") == "lying"]
            cells = []
            for belief in ("image", "state"):
                for want_bad in (False, True):
                    k = sum(1 for r in sub
                            if r.get("width_belief") == belief
                            and is_infeasible(r) == want_bad)
                    cells.append(k)
            print("  %-7s %-10d %-12d %-12d %-12d"
                  % (rung, cells[0], cells[1], cells[2], cells[3]))
        print()


# ---------------------------------------------------------------------------
# Step 5: self-contradiction.
# ---------------------------------------------------------------------------
# A reply is self-contradictory when the width it states and the arm it
# names cannot both hold: 0.096 m stated alongside franka_n, whose gripper
# opens to 0.080 m. No belief about the scene produces that pairing.
#
# This is a validity filter on Step 3 rather than a finding of its own. The
# width classifier assigns every reply to image or state from the stated
# width alone, and that assignment is meaningless when the arm contradicts
# it. Contradictory replies are therefore reported apart and excluded from
# any source-following claim.

GRIPPER = {"franka": 0.080, "ur": 0.140}


def aperture_of(arm):
    """Aperture of a named arm, from its prefix. None if unrecognised."""
    if not arm:
        return None
    for prefix, width in GRIPPER.items():
        if arm.startswith(prefix):
            return width
    return None


def contradicts(row):
    """Stated width exceeds the aperture of the arm the model named."""
    width = row.get("believed_width_m")
    ap = aperture_of(row.get("arm"))
    if width is None or ap is None:
        return False
    return width > ap


def check_contradiction(rows):
    print()
    print("=" * 70)
    print("STEP 5  SELF-CONTRADICTION")
    print("=" * 70)

    print()
    print("-" * 70)
    print("5a  RECOMPUTED FROM APERTURE ARITHMETIC vs THE STORED FLAG")
    print("-" * 70)
    mismatch = 0
    for r in rows:
        stored = r.get("self_contradicted")
        if stored is None:
            continue
        if bool(stored) != contradicts(r):
            mismatch += 1
    print("rows with a stored flag  %d"
          % sum(1 for r in rows if r.get("self_contradicted") is not None))
    print("disagreements            %d" % mismatch)
    if mismatch:
        print("WARNING  the grader and this script disagree about which")
        print("  replies are contradictory. Resolve before reporting.")

    print()
    print("-" * 70)
    print("5b  CONTRADICTORY REPLIES PER CELL, out of 66")
    print("-" * 70)
    print("rung   " + "".join("%-12s" % ("%s/%s" % (m[:3], p[:3]))
                              for m in MODELS for p in PREFERENCES))
    for rung in RUNGS:
        line = "%-7s" % rung
        for model in MODELS:
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung]
                k = sum(1 for r in sub if contradicts(r))
                line += "%-12s" % ("%d/%d" % (k, len(sub)))
        print(line)

    print()
    print("-" * 70)
    print("5c  BY TRUE POSE   franka preference only; UR cannot contradict")
    print("    because its aperture spans both candidate widths")
    print("-" * 70)
    for model in MODELS:
        line = "%-7s" % model
        for rung in RUNGS:
            sub = [r for r in rows if r.get("model") == model
                   and r.get("preference") == "franka"
                   and r.get("rung") == rung]
            ly = sum(1 for r in sub
                     if contradicts(r) and r.get("true_pose") == "lying")
            up = sum(1 for r in sub
                     if contradicts(r) and r.get("true_pose") == "upright")
            line += "%s %d/%d  " % (rung, ly, up)
        print(line)
    print("(lying / upright)")

    print()
    print("-" * 70)
    print("5d  EFFECT ON THE PRIMARY ENDPOINT")
    print("    image belief with contradictory replies excluded")
    print("-" * 70)
    print("rung   " + "".join("%-14s" % ("%s/%s" % (m[:3], p[:3]))
                              for m in MODELS for p in PREFERENCES))
    for rung in RUNGS:
        line = "%-7s" % rung
        for model in MODELS:
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung
                       and not contradicts(r)]
                k = sum(1 for r in sub if r.get("width_belief") == "image")
                line += "%-14s" % ("%d/%d" % (k, len(sub)))
        print(line)
    print("Compare with table 3a. A cell whose denominator has shrunk had")
    print("contradictory replies counted in it there.")


# ---------------------------------------------------------------------------
# Step 7: per-scene stability across repeats.
# ---------------------------------------------------------------------------
# Each cell is 22 scenes asked three times on identical input. A scene whose
# three answers differ is not evidence that the model read it; it is
# evidence that the answer is not a property of the scene. This decides
# whether a rate describes reliable reading or a stable core plus noise.


def check_stability(rows):
    print()
    print("=" * 70)
    print("STEP 7  PER-SCENE STABILITY ACROSS REPEATS")
    print("=" * 70)

    print()
    print("-" * 70)
    print("7a  SCENES BY PATTERN, out of 22   always image / always state /")
    print("    flipping across the three repeats")
    print("-" * 70)
    for model in MODELS:
        print("%s" % model)
        print("  rung    franka                  ur")
        for rung in RUNGS:
            cells = []
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung]
                by_scene = collections.defaultdict(list)
                for r in sub:
                    by_scene[scene_of(r)].append(
                        r.get("width_belief") == "image")
                always_i = sum(1 for v in by_scene.values() if all(v))
                always_s = sum(1 for v in by_scene.values() if not any(v))
                flip = len(by_scene) - always_i - always_s
                cells.append("%2d img  %2d st  %2d flip"
                             % (always_i, always_s, flip))
            print("  %-7s %-23s %s" % (rung, cells[0], cells[1]))
        print()

    print("-" * 70)
    print("7b  DETERMINISM   scenes whose three repeats agree, out of 22")
    print("-" * 70)
    print("rung   " + "".join("%-12s" % ("%s/%s" % (m[:3], p[:3]))
                              for m in MODELS for p in PREFERENCES))
    for rung in RUNGS:
        line = "%-7s" % rung
        for model in MODELS:
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung]
                by_scene = collections.defaultdict(list)
                for r in sub:
                    by_scene[scene_of(r)].append(
                        r.get("width_belief") == "image")
                same = sum(1 for v in by_scene.values()
                           if all(v) or not any(v))
                line += "%-12s" % ("%d/%d" % (same, len(by_scene)))
        print(line)

    print()
    print("-" * 70)
    print("7c  SCENES THAT FLIP UNDER BOTH PREFERENCES")
    print("    instability attaching to the model rather than the picture")
    print("-" * 70)
    for model in MODELS:
        line = "%-7s" % model
        for rung in RUNGS:
            flip_sets = []
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung]
                by_scene = collections.defaultdict(list)
                for r in sub:
                    by_scene[scene_of(r)].append(
                        r.get("width_belief") == "image")
                flip_sets.append({s for s, v in by_scene.items()
                                  if any(v) and not all(v)})
            line += "%s %d  " % (rung, len(flip_sets[0] & flip_sets[1]))
        print(line)


# ---------------------------------------------------------------------------
# Step 8: the reasoning text.
# ---------------------------------------------------------------------------
# Every other step reads the stated width or the chosen arm, and neither can
# see behind the report. A model that consulted the image and then deferred
# to the text would be invisible to them. The justification is the only
# place that could show it.
#
# Indicative only. Text mentioning the image is not proof the image was
# used: the perception probe found one model producing fluent descriptions
# of a bottle it could not see. The value here is the cross-tabulation. A
# reply that discusses the scene while reporting the declared width is the
# category the objection predicts, and it is countable.


def check_reasoning(rows):
    print()
    print("=" * 70)
    print("STEP 8  REASONING TEXT")
    print("=" * 70)

    print()
    print("-" * 70)
    print("8a  REPLIES REFERENCING THE IMAGE OR THE POSE, out of 66")
    print("    stored classification over why.grasp; indicative only")
    print("-" * 70)
    print("rung   " + "".join("%-12s" % ("%s/%s" % (m[:3], p[:3]))
                              for m in MODELS for p in PREFERENCES))
    for rung in RUNGS:
        line = "%-7s" % rung
        for model in MODELS:
            for pref in PREFERENCES:
                sub = [r for r in rows if r.get("model") == model
                       and r.get("preference") == pref
                       and r.get("rung") == rung]
                k = sum(1 for r in sub
                        if r.get("reasoning") == "image_referenced")
                line += "%-12s" % ("%d/%d" % (k, len(sub)))
        print(line)

    print()
    print("-" * 70)
    print("8b  SAYING CROSSED WITH USING, out of 66")
    print("    ref+img   talks about the scene and reports its width")
    print("    ref+state TALKS ABOUT THE SCENE AND REPORTS THE TEXT'S WIDTH")
    print("    sil+img   reports the scene's width without discussing it")
    print("    sil+state neither")
    print("-" * 70)
    for model in MODELS:
        print("%s" % model)
        print("  rung    ref+img  ref+state  sil+img  sil+state")
        for rung in RUNGS:
            sub = [r for r in rows if r.get("model") == model
                   and r.get("rung") == rung]
            cells = []
            for ref in (True, False):
                for belief in ("image", "state"):
                    k = sum(1 for r in sub
                            if (r.get("reasoning") == "image_referenced")
                            is ref and r.get("width_belief") == belief)
                    cells.append(k)
            print("  %-7s %-8d %-10d %-8d %-8d"
                  % (rung, cells[0], cells[1], cells[2], cells[3]))
        print()

    print("-" * 70)
    print("8c  SAMPLES FROM THE 'TALKS ABOUT THE SCENE, REPORTS THE TEXT'")
    print("    CELL   the category the looked-but-deferred account predicts")
    print("-" * 70)
    for model in MODELS:
        sub = [r for r in rows if r.get("model") == model
               and r.get("reasoning") == "image_referenced"
               and r.get("width_belief") == "state"]
        print("%s   %d such replies" % (model, len(sub)))
        for r in sub[:4]:
            why = r.get("why")
            grasp = why.get("grasp") if isinstance(why, dict) else why
            print("   %-4s %-7s %-8s  %s"
                  % (r.get("rung"), r.get("preference"), r.get("true_pose"),
                     str(grasp)[:150]))
        print()


# ---------------------------------------------------------------------------
# Step 6: the headline table, on the correct unit.
# ---------------------------------------------------------------------------
# Earlier steps print counts out of 66 and 33. Those are repeat counts, not
# sample sizes: 66 is 22 scenes answered three times, 33 is 11. Treating
# them as independent observations triples the apparent evidence. Here the
# three repeats collapse to a majority verdict per scene, giving n = 11
# lying scenes per cell, with Wilson intervals over scenes.
#
# Lying scenes only. Upright admits every arm, so no assignment there can be
# illegal and the cell carries no information about capability judgement.
#
# Both preferences are shown, but only the Franka column is informative. A
# UR gripper spans both candidate widths, so under the UR preference the
# guidance-consistent choice is legal whatever the model believes, and the
# cell is at ceiling by construction. Under the Franka preference the
# guidance and the physics conflict on a lying bottle, so the model must
# override the guidance to assign legally, and the rate measures something.


def wilson(k, n, z=1.96):
    """Wilson score interval, as percentages. Used because several cells
    sit at 0 or 100 where the normal approximation leaves the range."""
    if n == 0:
        return (0.0, 0.0)
    p = float(k) / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (100 * max(0.0, centre - half), 100 * min(1.0, centre + half))


def _majority(rows, model, pref, rung, pose, predicate):
    sub = [r for r in rows if r.get("model") == model
           and r.get("preference") == pref
           and r.get("rung") == rung
           and r.get("true_pose") == pose]
    by_scene = collections.defaultdict(list)
    for r in sub:
        by_scene[scene_of(r)].append(bool(predicate(r)))
    k = sum(1 for v in by_scene.values() if sum(v) * 2 > len(v))
    return k, len(by_scene)


def _legal(r):
    arm = r.get("arm")
    return arm is not None and arm in (r.get("legal_true") or [])


def _image(r):
    return r.get("width_belief") == "image"


def check_headline(rows):
    print()
    print("=" * 70)
    print("STEP 6  HEADLINE TABLE, PER-SCENE MAJORITY, LYING SCENES")
    print("=" * 70)
    print("n = 11 scenes per cell. Each scene is one majority verdict over")
    print("three repeats. Brackets are Wilson 95 percent intervals over")
    print("scenes. Upright scenes are excluded: every arm spans 0.058 m, so")
    print("no assignment there can be illegal.")

    for label, predicate in (("LEGAL ASSIGNMENT", _legal),
                             ("IMAGE-CONSISTENT WIDTH BELIEF", _image)):
        for pref in PREFERENCES:
            note = ""
            if pref == "ur":
                note = ("   (uninformative: a UR spans both widths, so the"
                        " guidance-consistent choice is always legal)")
            print()
            print("-" * 70)
            print("%s, %s preference%s" % (label, pref, note))
            print("-" * 70)
            print("rung   " + "".join("%-24s" % m for m in MODELS))
            for rung in RUNGS:
                line = "%-7s" % rung
                for model in MODELS:
                    k, n = _majority(rows, model, pref, rung, "lying",
                                     predicate)
                    lo, hi = wilson(k, n)
                    line += "%-24s" % ("%2d/%d  [%2.0f-%3.0f]"
                                       % (k, n, lo, hi))
                print(line)

    print()
    print("-" * 70)
    print("WHY THE UR PREFERENCE IS NOT REPORTED AS A RESULT")
    print("-" * 70)
    for model in MODELS:
        ks = []
        for rung in RUNGS:
            k, n = _majority(rows, model, "ur", rung, "lying", _legal)
            ks.append("%d" % k)
        print("%-7s legal assignment across rungs: %s  (out of %d)"
              % (model, " ".join(ks), n))
    print("A flat line at or near ceiling confirms the cell cannot")
    print("discriminate: following the guidance is legal regardless of what")
    print("the model believes about the width.")


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    rows = load(argv)
    unique, errors, dupes = clean(rows)
    report_load(rows, unique, errors, dupes)
    faults = check_cells(unique)
    check_versions(unique)
    check_fixed_fields(unique)
    check_repeats(unique)

    print()
    print("=" * 70)
    if faults:
        print("STEP 1 INCOMPLETE: %d cell(s) do not match the design."
              % len(faults))
        print("Resolve before computing anything from the replies.")
    else:
        print("STEP 1 PASSED: every cell matches the design.")
    print("=" * 70)

    ext_faults, mismatches, ties = check_extraction(unique)

    print()
    print("=" * 70)
    problems = []
    if ext_faults:
        problems.append("%d aperture value(s) in the width column"
                        % len(ext_faults))
    if mismatches:
        problems.append("%d classification mismatch(es)" % len(mismatches))
    if ties:
        problems.append("%d conflict trial(s) with no disagreement"
                        % len(ties))
    if problems:
        print("STEP 2 FAILED: " + "; ".join(problems))
        print("No width-derived number may be quoted until these are"
              " resolved.")
    else:
        print("STEP 2 PASSED: extraction is sound; width figures may be"
              " quoted.")
    print("=" * 70)

    if not problems:
        check_headline(unique)
        check_width_belief(unique)
        check_infeasible(unique)
        check_contradiction(unique)
        check_stability(unique)
        check_reasoning(unique)

    return 1 if (faults or problems) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))