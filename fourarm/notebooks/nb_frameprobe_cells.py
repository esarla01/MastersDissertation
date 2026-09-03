"""Cells for ex2_frame_probe.ipynb -- does the dims-frame confound reach the
conditions that STATE a resting face?

WHY THIS EXISTS. The `named` object-field gloss describes the extents as
"measured standing on its smallest face". The block is 0.130 x 0.100 x 0.050,
so its smallest face IS small_face, and under `dims` that phrase is the only
pose-like statement in the state. The Q3 extents runs already showed what it
costs: GPT reports the 0.050 opening on 93.1% of N0 trials under `named` and
3.4% under `extents`, and its face accuracy at N-CD goes 64.2 -> 94.1.

WHAT IS NOT YET KNOWN. `congruent` and `congruent_face` state a resting_face
outright, so the glossary phrase is not the only pose claim and the leak should
not bite. SHOULD NOT is not DOES NOT, and the whole reference-line argument in
the thesis rests on those two conditions being clean. One repeat settles it.

WHY ONE REPEAT IS ENOUGH. This is not estimating an effect, it is asking whether
one is there. Under dims the effect was 90 points on the anchor. An effect that
size does not hide in 68 scenes, and if the answer is "no movement" the existing
three-repeat named runs stand as they are.

HOW THE PAID CELLS BEHAVE. Exactly like Q1's cells 6 and 7, and for the same
reason -- they are the same call. Each writes its own jsonl through
solo.run(), which prints one line per model call as it lands, flushes each row
before the next call is made, and on a re-run reads the file back and skips
every trial_id already answered. So an interrupted run is resumed by running
the cell again, a finished one costs nothing to re-run, and the read-out cell
works from the files on disk rather than from a live handle -- which means it
still works after a kernel restart.

The earlier version of this notebook used experiments.ex2.launch to put one
process per model, which is three times faster and shows nothing: the workers'
stdout goes to runs/*.log, not to the notebook, and L.combine() needs the
`handles` object, so a kernel restart lost the run. Visibility and resumability
are worth more here than 20 minutes.
"""

# ---------------------------------------------------------------------------
# The paid cells
# ---------------------------------------------------------------------------

MD_RUN = """## The probe: does the `named` gloss leak where a face IS stated?

**These two cells make model calls.** Two conditions, three models, one repeat.
Each cell prints its own cost line; set `CONFIRM_SPEND` to that number to let it
run. Roughly 20 minutes per cell.

`congruent` and `congruent_face` both state `resting_face` in the state text.
The `named` gloss additionally says the extents were "measured standing on its
smallest face", which describes `small_face`. If the models are reading that
phrase as a pose claim even when a pose is given, the supplied-face conditions
are partly text-following too, and the reference lines they anchor need
qualifying. If nothing moves, the confound is confined to `dims` and the
correction to the chapter is one subsection.

**Interrupt them freely.** `solo.run` appends and flushes each row as it lands,
and skips every trial already answered when it starts. Re-running a cell resumes
it; re-running a finished cell makes no calls at all and says so.

The `named` twins to compare against are already on disk at three repeats:
`ex2_q1_congruent_N0.jsonl` and `ex2_q1_congruent_face_N0.jsonl`. Nothing here
writes to those files."""

C_RUN_CONG = r'''# --- Congruent at N0, EXTENTS frame. MAKES MODEL CALLS. ---------------------
CONG_EXT = RUNS / "ex2_q1_congruent_N0_extents.jsonl"
CONG_NAMED = RUNS / "ex2_q1_congruent_N0.jsonl"

# CALL_SCENES, not scenes: cell 3 decides which positions are paid for, so
# this cell and the next cannot drift apart, and neither can drift from the
# named runs they are compared against.
n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
print("COST: %d scenes x %d models x %d repeat = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
print("      condition congruent, rung %s, dims frame EXTENTS" % RUNG)
print("      named twin already on disk: %s (%d answered)"
      % (CONG_NAMED.name, answered(CONG_NAMED)))

CONFIRM_SPEND = None            # <-- set to the number in the COST line

# factors= is the guard against a later cell rebinding REPEATS: the gate
# refuses when the counts stop multiplying to the number being confirmed,
# rather than the run quietly coming out a third of the size.
if spend_gate(n_calls, CONFIRM_SPEND, CONG_EXT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", REPEATS))):
    # dims_frames is the ONE thing that differs from the run that produced
    # CONG_NAMED. Everything else -- scenes, models, preference, rung,
    # modality, kind -- is read from cell 1 and cell 3, so the two runs
    # cannot come apart on anything the comparison is not about.
    S.run(str(CAPTURES), out_path=str(CONG_EXT), models=MODELS,
          conditions=("congruent",), preferences=(PREFERENCE,),
          rungs=(RUNG,), modalities=("V",), kind="pair", repeats=REPEATS,
          dims_frames=("extents",))
    print("answered now:", answered(CONG_EXT))'''

C_RUN_FACE = r'''# --- Congruent-face at N0, EXTENTS frame. MAKES MODEL CALLS. ----------------
FACE_EXT = RUNS / "ex2_q1_congruent_face_N0_extents.jsonl"
FACE_NAMED = RUNS / "ex2_q1_congruent_face_N0.jsonl"

n_calls = len(CALL_SCENES) * len(MODELS) * REPEATS
print("COST: %d scenes x %d models x %d repeat = %d calls"
      % (len(CALL_SCENES), len(MODELS), REPEATS, n_calls))
print("      condition congruent_face, rung %s, dims frame EXTENTS" % RUNG)
print("      named twin already on disk: %s (%d answered)"
      % (FACE_NAMED.name, answered(FACE_NAMED)))

# THE GLOSS THIS CONDITION GETS UNDER EXTENTS, printed rather than trusted.
# prompts._object_fields dispatched on `condition == "dims"` until this
# notebook was written, which handed congruent_face the FULL gloss -- the one
# that announces an "opening_needed_m" the condition withholds. That would
# have changed two things at once and made this cell unreadable. It is fixed
# in prompts.py; this is the assertion that it stays fixed.
_gloss = P._object_fields("congruent_face", "extents")
assert "opening_needed_m" not in _gloss and "No opening is given" in _gloss, (
    "the extents gloss for congruent_face names an opening the state does "
    "not carry:\n" + _gloss)
assert "smallest face" not in _gloss, (
    "the extents gloss still contains the phrase this probe exists to "
    "remove:\n" + _gloss)
print("      gloss checked: no opening named, no 'smallest face'")

CONFIRM_SPEND = None            # <-- set to the number in the COST line

if spend_gate(n_calls, CONFIRM_SPEND, FACE_EXT,
              factors=(("scenes", len(CALL_SCENES)), ("models", len(MODELS)),
                       ("repeats", REPEATS))):
    S.run(str(CAPTURES), out_path=str(FACE_EXT), models=MODELS,
          conditions=("congruent_face",), preferences=(PREFERENCE,),
          rungs=(RUNG,), modalities=("V",), kind="pair", repeats=REPEATS,
          dims_frames=("extents",))
    print("answered now:", answered(FACE_EXT))'''

# ---------------------------------------------------------------------------
# The read-out
# ---------------------------------------------------------------------------

MD_READ = """## Read-out

No model calls. Reads the four files off disk -- two `named`, two `extents` --
so it survives a kernel restart and can be run part-way through a paid cell to
see what has landed so far.

Same helpers Q1 uses (`load_run`, `keep_analysable`, `paired_diffs`,
`paired_mean_ci`), so the `named` columns here should reproduce the numbers
already in the Q1 tables rather than being a second, differently-computed
version of them.

**What to read.** Both conditions state the true face, so opening accuracy is
already high under both frames and will not separate the two explanations. What
separates them is whether anything MOVES when the only thing that changed is a
phrase the condition has made redundant.

The repeat counts differ on purpose: `named` is the existing three-repeat run,
`extents` is one repeat. That is fine for a presence test and is why the `n`
column is printed."""

C_READ = r'''# --- Read-out. No model calls. ----------------------------------------------
FILES = {
    ("congruent",      "named"):   RUNS / "ex2_q1_congruent_N0.jsonl",
    ("congruent",      "extents"): RUNS / "ex2_q1_congruent_N0_extents.jsonl",
    ("congruent_face", "named"):   RUNS / "ex2_q1_congruent_face_N0.jsonl",
    ("congruent_face", "extents"): RUNS / "ex2_q1_congruent_face_N0_extents.jsonl",
}

# A file that is missing or part-written is REPORTED, not silently rendered as
# a blank row. A probe read part-way through its own paid cell is a normal
# thing to do here, and "extents has not been bought yet" and "extents was
# bought and moved nothing" must not look the same.
loaded, status = {}, []
for (cond, frame), path in sorted(FILES.items()):
    if not path.exists():
        status.append([cond, frame, path.name, 0,
                       len(USABLE) * len(FACES) * len(MODELS),
                       "MISSING", "-"])
        loaded[(cond, frame)] = []
        continue
    rows, skipped = load_run(path, cond, MODELS)
    # trial_id carries the frame, so a file can only hold the frame it was
    # written for -- but check rather than assume: an out_path typo would
    # otherwise pool extents rows into the named column.
    frames = sorted({r.get("dims_frame", "named") for r in rows})
    if frames not in ([frame], []):
        raise AssertionError("%s holds dims_frame %s, expected %r. The two "
                             "frames must not share a file."
                             % (path.name, frames, frame))
    keep = keep_analysable(rows, USABLE)
    reps = sorted(r for r in {x.get("repeat") for x in keep} if r is not None)
    # One repeat's worth is every usable position, both faces, every model.
    # Reported as a RATIO rather than as "complete", because the two frames
    # legitimately hold different repeat counts and a flat complete/partial
    # flag would call the one-repeat extents run short against the
    # three-repeat named one.
    per_rep = len(USABLE) * len(FACES) * len(MODELS)
    status.append([cond, frame, path.name, len(keep), per_rep,
                   "%.2f" % (len(keep) / float(per_rep)),
                   ",".join("r%s" % r for r in reps) or "-"])
    loaded[(cond, frame)] = keep
    if skipped:
        print("  %s: %d rows from models outside MODELS, not counted"
              % (path.name, sum(skipped.values())))

show(["condition", "frame", "file", "analysable", "per repeat",
      "repeats worth", "repeats present"], status)
print()
print("analysable = no transport error, reply parsed, and the position is one")
print("of the %d that carry the contrast and show the block. A run still in" % len(USABLE))
print("progress shows a fractional repeats-worth; that is expected and the")
print("cells below are still readable, just noisier.")
print()

# --- the per-cell numbers ---------------------------------------------------
TOL = 0.006                       # as Q1 cell 12
SMALL_OPEN = FACTS["small_face"]["grasp_m"]

def opening_stats(rows):
    """(n stated, % correct for the face actually shown, % reporting 0.050).

    The third column is the ANCHOR. Under dims it is what the frame moved:
    the gloss names small_face, and a model reading it as a pose claim reports
    that face's opening whatever the picture shows. Correctness and the anchor
    come apart only when the true face is large_face, which is exactly half
    these rows.
    """
    stated = [r for r in rows if r.get("opening_needed_m") is not None]
    if not stated:
        return 0, None, None
    ok = sum(1 for r in stated
             if abs(r["opening_needed_m"] - FACTS[r["face"]]["grasp_m"]) <= TOL)
    anchored = sum(1 for r in stated
                   if abs(r["opening_needed_m"] - SMALL_OPEN) <= TOL)
    return len(stated), pct(ok, len(stated)), pct(anchored, len(stated))

rows_out = []
deltas = {}
for cond in CONDITIONS:
    for model in MODELS:
        for frame in ("named", "extents"):
            sub = [r for r in loaded[(cond, frame)] if r["model"] == model]
            n_open, ok, anchor = opening_stats(sub)
            # THE SAME quantity Q1 reports: Franka share on small_face minus
            # Franka share on large_face, paired within position, positions
            # averaged. Not a pooled difference -- see paired_diffs.
            pairs = paired_diffs(sub, USABLE, "small_face", "large_face")
            diffs = [d for _, d in pairs]
            mean, lo, hi, npos = paired_mean_ci(diffs)
            fk, fn = full_flip_count(diffs)
            deltas[(cond, model, frame)] = mean
            rows_out.append([cond, model, frame, len(sub), n_open,
                             fmt(ok), fmt(anchor),
                             fmt(share_at([r for r in sub
                                           if r["face"] == "small_face"])),
                             fmt(share_at([r for r in sub
                                           if r["face"] == "large_face"])),
                             npos, fmt(mean), fmt(lo), fmt(hi),
                             "%d/%d" % (fk, fn)])

show(["condition", "model", "frame", "rows", "stated", "opening ok%",
      "reports .050%", "franka% small", "franka% large", "pos",
      "delta", "lo", "hi", "full flips"], rows_out)
print()
print("delta = franka share on small_face minus franka share on large_face,")
print("        paired within position over %d positions. 100 is the ceiling:" % len(USABLE))
print("        the Franka every time the block is on its small face and never")
print("        when it is on its large face. 0 is no contrast at all.")
print()

# --- the one number the probe exists to produce -----------------------------
print("=" * 72)
print("FRAME EFFECT: delta(extents) - delta(named), per condition and model")
print("=" * 72)
move_rows = []
for cond in CONDITIONS:
    for model in MODELS:
        dn, de = deltas[(cond, model, "named")], deltas[(cond, model, "extents")]
        gap = None if (dn is None or de is None
                       or dn != dn or de != de) else de - dn
        move_rows.append([cond, model, fmt(dn), fmt(de), fmt(gap)])
show(["condition", "model", "delta named", "delta extents", "extents - named"],
     move_rows)
print()
print("NO INTERVAL ON THE LAST COLUMN, on purpose. It is a difference of")
print("paired differences across two runs of different sizes -- three repeats")
print("against one -- and a t interval on it would be reporting a precision")
print("the design does not have. This is a presence test: under dims the same")
print("quantity moved by roughly 45 points on Gemini at N0 and 30 to 48 on")
print("GPT at the treated rungs. Something of that order is the effect being")
print("looked for; a handful of points is not resolvable here and must not be")
print("written up as one.")
print()
print("=" * 72)
print("WHAT THE TWO OUTCOMES MEAN, stated before the numbers are read")
print("=" * 72)
print("  NOTHING MOVES     the gloss phrase is inert once a face is stated.")
print("                    The confound is confined to dims. Q1's reference")
print("                    lines and all of Q2 stand, and the correction to")
print("                    the chapter is one subsection about dims.")
print()
print("  SOMETHING MOVES   the phrase is read as a pose claim even when a")
print("                    pose is given. The supplied-face conditions are")
print("                    partly text-following, and every reference line")
print("                    drawn from them needs qualifying.")'''
