"""Cells for ex2_frame_probe.ipynb -- does the dims-frame confound reach the
conditions that STATE a resting face?

WHY THIS EXISTS. The `named` dims glossary describes the extents as "measured
standing on its smallest face". The block is 0.130 x 0.100 x 0.050, so its
smallest face IS small_face, and under `dims` that phrase is the only pose-like
statement in the state. Cell 9b of the Q3 notebook already showed what it costs:
GPT reports the 0.050 opening on 93.1% of N0 trials under `named` and 3.4% under
`extents`, and its face accuracy at N-CD goes 64.2 -> 94.1.

WHAT IS NOT YET KNOWN. `congruent` and `congruent_face` state a resting_face
outright, so the glossary phrase is not the only pose claim and the leak should
not bite. SHOULD NOT is not DOES NOT, and the whole reference-line argument in
the thesis rests on those two conditions being clean. One repeat settles it.

WHY ONE REPEAT IS ENOUGH. This is not estimating an effect, it is asking whether
one is there. Under `dims` the effect was 90 points on the anchor. An effect that
size does not hide in 68 scenes, and if the answer is "no movement" the existing
three-repeat named runs stand as they are.
"""

MD_RUN = """
## Frame probe: does the `named` glossary leak where a face IS stated?

**Makes model calls.** Two conditions, three models, one repeat, about 400 calls,
roughly 12 minutes with one process per model.

`congruent` and `congruent_face` both state `resting_face` in the state. The
`named` glossary additionally says the extents were "measured standing on its
smallest face", which describes `small_face`. If the models are reading that
phrase as a pose claim even when a pose is given, the supplied-face conditions
are partly text-following too, and the reference lines they anchor need
qualifying. If nothing moves, the confound is confined to `dims` and the
correction is one subsection.

Existing `named` runs to compare against are already on disk at three repeats:
`ex2_q1_congruent_N0.jsonl` and `ex2_q1_congruent_face_N0.jsonl`.
"""

C_RUN = '''
# --- Frame probe. PAID. -----------------------------------------------------
from experiments.ex2 import launch as L

PROBE_TAG   = "q1_frameprobe_N0_extents"
PROBE_CONDS = ("congruent", "congruent_face")

jobs = L.per_model(
    ("gpt", "gemini", "claude"),
    capture_dir = str(CAPTURES),
    out_dir     = RUNS,
    tag         = PROBE_TAG,
    conditions  = PROBE_CONDS,
    rungs       = (RUNG,),                 # N0, from cell 1
    dims_frames = ("extents",),
    repeats     = 1,
)

print("about to buy:")
for j in jobs:
    print("   %-8s -> %s" % (j["name"], pathlib.Path(j["kwargs"]["out_path"]).name))
print("   %s x %s x 1 repeat" % (PROBE_CONDS, ("gpt", "gemini", "claude")))
print()

handles = L.start(jobs)
print("started, nothing blocks. run the next cell when they finish.")
'''

MD_READ = """
## Frame probe read-out

No model calls. `extents` against the `named` runs already on disk.

**The anchor is what to read.** Both conditions state the true face, so opening
accuracy should already be high under both frames and would not separate the two
explanations. What separates them is whether the numbers MOVE when the only thing
that changed is a phrase the condition has made redundant.
"""

C_READ = '''
# --- Frame probe read-out. No model calls. ----------------------------------
rows = L.combine(handles)

NAMED = {"congruent":      RUNS / "ex2_q1_congruent_N0.jsonl",
         "congruent_face": RUNS / "ex2_q1_congruent_face_N0.jsonl"}

def _load(path):
    if not pathlib.Path(path).exists():
        return []
    return [json.loads(l) for l in open(path)]

def _stats(recs, cond, model):
    r = [x for x in recs if x.get("condition") == cond
         and x.get("model") == model and not x.get("error")]
    op = [x for x in r if x.get("opening_needed_m") is not None]
    ok = sum(1 for x in op
             if abs(x["opening_needed_m"] - x["true_grasp_m"]) < 0.006)
    sml = sum(1 for x in op if abs(x["opening_needed_m"] - 0.050) < 0.006)
    ar = [x for x in r if x.get("arm")]
    fk = sum(1 for x in ar if "franka" in x["arm"])
    pct = lambda k, n: (100.0 * k / n) if n else None
    return len(r), pct(ok, len(op)), pct(sml, len(op)), pct(fk, len(ar))

ext = list(rows)
hdr = ("condition", "model", "frame", "n", "opening ok%",
       "reports .050%", "franka%")
out = []
for cond in PROBE_CONDS:
    for m in MODELS:
        for frame, recs in (("named", _load(NAMED[cond])), ("extents", ext)):
            n, ok, sml, fk = _stats(recs, cond, m)
            f = lambda v: "--" if v is None else "%.1f" % v
            out.append([cond, m, frame, n, f(ok), f(sml), f(fk)])

w = [max(len(str(r[i])) for r in [list(hdr)] + out) for i in range(len(hdr))]
print("  ".join(str(h).ljust(w[i]) for i, h in enumerate(hdr)))
print("  ".join("-" * w[i] for i in range(len(hdr))))
for r in out:
    print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))

print()
print("=" * 70)
print("WHAT THE TWO OUTCOMES MEAN, stated before the numbers are read")
print("=" * 70)
print("  NOTHING MOVES     the glossary phrase is inert once a face is")
print("                    stated. The confound is confined to dims. Q1's")
print("                    reference lines and all of Q2 stand, and the")
print("                    correction is one subsection about dims.")
print()
print("  SOMETHING MOVES   the phrase is read as a pose claim even when a")
print("                    pose is given. The supplied-face conditions are")
print("                    partly text-following, and every reference line")
print("                    drawn from them needs qualifying.")
'''
