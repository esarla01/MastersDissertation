"""Cell sources for the second half of appendix_tables.ipynb.

Tables B.1, B.2 and E.1 to E.4. Kept in their own module rather than inline in
build_appendix_nb.py because these cells contain triple-quoted docstrings and
LaTeX backslashes, and nesting those inside the builder's own string literals
is how the escaping went wrong the first time.
"""

MD9 = r"""---
# 9. Tables B.1 and B.2 — the rule variants and the edit per condition

Both are prose, so neither is checked on a token sequence. What is checked is
that the text the thesis prints is the text the prompt module actually sends,
word for word, and that every condition the module defines appears with its run
code.

The comparison is on words rather than characters: the thesis joins R3's three
clauses with commas where the module separates them with line breaks, which is
typesetting and not a difference in what the model was asked."""

C9 = r'''
import re


def words(s):
    """LaTeX or module text reduced to a comparable word sequence.

    Markup, punctuation and case are dropped. Underscores are kept, because
    they are part of field names like grasp_m and those are exactly what must
    not drift between the prompt and the appendix.
    """
    s = re.sub(r"\\texttt\{([^}]*)\}", r"\1", s)
    s = s.replace("\\_", "_").replace("$+$", "+")
    s = re.sub(r"\\[a-zA-Z]+", " ", s)
    return re.sub(r"[^a-z0-9_ ]+", " ", s.lower()).split()


def carries(haystack, needle):
    """Is needle an unbroken subsequence of haystack."""
    return any(haystack[i:i + len(needle)] == needle
               for i in range(len(haystack) - len(needle) + 1))


# --- B.1, the four rule bodies R3 and R4 select between --------------------
RULE_BODIES = [
    ("R3 enriched", P1.CAPABILITY_RULE),
    ("R4 enriched", P1.REACH_RULE_ENRICHED),
    ("R3 eligible", P1.CAPABILITY_RULE_ELIGIBLE),
    ("R4 eligible", P1.REACH_RULE_ELIGIBLE),
]
show(["Rule", "Body, first words", "Chars"],
     [[n, " ".join(b.split())[:52] + "...", len(b)] for n, b in RULE_BODIES])

tex_b1 = latex(
    "tab:appendix:rules", "The bodies of R3 and R4.", "lp{0.78\\textwidth}",
    r"Rule & Body",
    [r"%s & %s \\" % (n, " ".join(b.split()).replace("_", r"\_"))
     for n, b in RULE_BODIES])
write_tex("appendix_rules.tex", tex_b1)

body, origin = CK.body("tab:appendix:rules")
if body is None:
    CK.note("tab:appendix:rules", "SKIPPED", "no thesis source, no vendored copy")
    print("tab:appendix:rules       SKIPPED")
else:
    seq = words(body)
    missing = [n for n, b in RULE_BODIES if not carries(seq, words(b))]
    assert not missing, ("the thesis prints a rule body the prompt module does "
                         "not send: %s" % missing)
    CK.note("tab:appendix:rules", "MATCHES",
            "four rule bodies word for word against the %s" % origin)
    print("tab:appendix:rules       MATCHES the %s on all 4 rule bodies, "
          "word for word" % origin)

# --- B.2, the edit that produces each condition ----------------------------
# RUNGS is the authority for which conditions exist. The prose describing each
# edit lives in the appendix and not in the module, so what is checked is the
# roster and the run codes, which is what a reader uses the table for.
codes = list(P1.RUNGS)
show(["Run code", "Width", "Names", "Rules", "Eligible"],
     [[c] + [str(P1.RUNGS[c].get(k)) for k in
             ("declared_width", "names", "rules", "eligible")] for c in codes])

body2, origin2 = CK.body("tab:appendix:edits")
if body2 is None:
    CK.note("tab:appendix:edits", "SKIPPED", "no thesis source, no vendored copy")
    print("tab:appendix:edits       SKIPPED")
else:
    seq2 = words(body2)
    missing = [c for c in codes if not carries(seq2, words(c))]
    assert not missing, "conditions in RUNGS that the appendix omits: %s" % missing
    CK.note("tab:appendix:edits", "MATCHES",
            "%d run codes against the %s" % (len(codes), origin2))
    print("tab:appendix:edits       MATCHES the %s on all %d run codes"
          % (origin2, len(codes)))
'''

MD10 = r"""---
# 10. Tables E.1 to E.4 — one worked decision state

`rec_decision_rich` seq 13, the state Appendix E walks through. Three of the
four arms idle, three tasks queued, nine candidate pairs, two of them legal.

E.3 is the one worth generating. It runs the deployed validator twice over the
same state — once as posed, once with both apertures raised so the grasp
comparison can never bind — and the difference between the passes is the
width-blind line, worked on a single state rather than averaged over 96."""

C10 = r'''
WORKED = ("rec_decision_rich", 13)
probes_all = json.load(open(os.path.join(ROOT, "probes", "ex1_v2.json")))["probes"]
worked = next(p for p in probes_all
              if (p["provenance"]["source"], p["provenance"]["seq"]) == WORKED)
st = worked["state"]
objs = {o["name"]: o for o in st["objects"]}

# --- E.1, the arms ---------------------------------------------------------
rows_e1, body_e1 = [], []
for a in st["arms"]:
    state = "idle" if a["state"] == "IDLE" else a["state"]
    if a["holding"]:
        state = "%s, holding %s" % (a["state"], a["holding"])
    rows_e1.append([a["name"], "UR10" if a["type"] == "ur10" else "Franka",
                    "%.3f" % a["max_grasp_m"], "%.1f" % a["payload_kg"],
                    "yes" if a["delicate_ok"] else "no", state])
    body_e1.append(r"\texttt{%s} & %s & %.3f & %.1f & %s & %s \\"
                   % (esc(a["name"]),
                      "UR10" if a["type"] == "ur10" else "Franka",
                      a["max_grasp_m"], a["payload_kg"],
                      "yes" if a["delicate_ok"] else "no",
                      (r"\texttt{%s}, holding \texttt{%s}"
                       % (esc(a["state"]), esc(a["holding"])))
                      if a["holding"] else "idle"))

show(["Arm", "Type", "Aperture (m)", "Payload (kg)", "Delicate", "State"], rows_e1)
tex_e1 = latex("tab:appendix:arms", "The arms.", "llcccl",
               r"Arm & Type & Aperture (m) & Payload (kg) & Delicate & State",
               body_e1)
write_tex("appendix_arms.tex", tex_e1)
CK.check("tab:appendix:arms", tex_e1)

# --- E.2, the open tasks ---------------------------------------------------
queued = [t for t in st["tasks"] if t["status"] == "queued"]
rows_e2, body_e2 = [], []
for t in queued:
    o = objs[t["object"]]
    rows_e2.append([t["id"], t["object"], "%.3f" % o["grasp_m"],
                    "%.3f" % o["mass_kg"], str(o["delicate"]).lower(),
                    o["zone"], t["dest_zone"]])
    body_e2.append(r"%d & \texttt{%s} & %.3f & %.3f & %s & \texttt{%s} & \texttt{%s} \\"
                   % (t["id"], esc(t["object"]), o["grasp_m"], o["mass_kg"],
                      str(o["delicate"]).lower(), o["zone"], t["dest_zone"]))

show(["ID", "Object", "grasp_m", "mass_kg", "delicate", "zone", "Destination"],
     rows_e2)
tex_e2 = latex("tab:appendix:tasks", "The open tasks.", "rlccccc",
               r"ID & Object & grasp\_m & mass\_kg & delicate & zone & Destination",
               body_e2)
write_tex("appendix_tasks.tex", tex_e2)
CK.check("tab:appendix:tasks", tex_e2)

# --- E.3, both validator passes -------------------------------------------
WIDE = 10.0     # wider than any object, so grasp can never be the refusal


def pairs_and_causes(probe, width_blind=False):
    """Legal pairs and binding causes, from the DEPLOYED validator.

    width_blind raises both arm types' aperture first and restores it in a
    finally block: a leaked limit would silently corrupt every state computed
    after it in the same process.
    """
    if not width_blind:
        pairs, _per, causes = legal_options(probe, with_causes=True)
        return {(t, a) for t, a, _k in pairs}, {(t, a): c for t, a, c in causes}
    saved = {k: C.ARM_TYPES[k]["max_grasp_m"] for k in C.ARM_TYPES}
    try:
        for k in C.ARM_TYPES:
            C.ARM_TYPES[k]["max_grasp_m"] = WIDE
        pairs, _per, causes = legal_options(probe, with_causes=True)
        return {(t, a) for t, a, _k in pairs}, {(t, a): c for t, a, c in causes}
    finally:
        for k, v in saved.items():
            C.ARM_TYPES[k]["max_grasp_m"] = v


legal_now, causes_now = pairs_and_causes(worked)
legal_wb, _ = pairs_and_causes(worked, width_blind=True)
assert legal_now <= legal_wb, "ignoring a constraint can only add options"

idle = [a["name"] for a in st["arms"] if a["state"] == "IDLE"]
PRINT_CAUSE = {"delicate": "delicacy", "no_route": "route"}
rows_e3, body_e3 = [], []
for t in queued:
    for a in idle:
        k = (t["id"], a)
        verdict = "legal" if k in legal_now else "rejected"
        cause = ("--" if k in legal_now
                 else PRINT_CAUSE.get(causes_now.get(k), causes_now.get(k, "?")))
        wb = "legal" if k in legal_wb else "rejected"
        rows_e3.append(["task %d, %s" % (t["id"], a), verdict, cause, wb])
        # The one pair that changes hands is bolded in the thesis: it was
        # rejected for width alone, so raising the aperture makes it legal.
        gained = wb == "legal" and verdict == "rejected"
        body_e3.append(r"task~\num{%d}, \texttt{%s} & %s & %s & %s \\"
                       % (t["id"], esc(a), verdict,
                          cause if cause != "--" else "{--}",
                          r"\textbf{legal}" if gained else wb))

show(["Pair", "Verdict as posed", "Binding cause", "Verdict, width blind"],
     rows_e3)
tex_e3 = latex("tab:appendix:widthblind",
               "Both validator passes over the nine candidate pairs.", "llll",
               r"Pair & Verdict as posed & Binding cause & Verdict, width blind",
               body_e3 + [r"\midrule",
                          r"Accepted & %d & & %d \\"
                          % (len(legal_now), len(legal_wb))])
write_tex("appendix_widthblind.tex", tex_e3)
CK.check("tab:appendix:widthblind", tex_e3)

print()
print("this state: %d legal of %d candidate pairs, width-blind %d, so l/b = %.1f%%"
      % (len(legal_now), len(queued) * len(idle), len(legal_wb),
         100.0 * len(legal_now) / len(legal_wb)))
'''

MD11 = r"""---
# 11. Table E.4 — what the models answered

The nine Full Information replies on the same state, three per model, each with
the validator's verdict. Read from the run files rather than transcribed, so
the quoted reasons are the ones the models actually returned."""

C11 = r'''
import run_files

PRINT_MODEL = {"gemini": "Gemini", "gpt": "GPT", "qwen": "Qwen"}
rows_e4, body_e4 = [], []
for model in run_files.EX1_MODELS:
    path = os.path.join(ROOT, run_files.CAST_A[(model, "full")])
    rows = [json.loads(l) for l in open(path) if l.strip()]
    mine = [r for r in rows
            if (r["provenance"]["source"], r["provenance"]["seq"]) == WORKED]
    mine.sort(key=lambda r: r.get("repeat", 0))
    for r in mine:
        answer = ("task %s, %s" % (r.get("task_id"), r.get("arm"))
                  if r.get("arm") else "decline")
        # The run row calls these model_reason and result. An earlier version
        # of this cell read "reason" and "outcome", got None for both, and
        # still passed the numeric check -- E.4's only numbers are task ids
        # and repeat counts, so a wrong TEXT column is invisible to it. Hence
        # the assertions below.
        reason = " ".join((r.get("model_reason") or "").split())
        verdict = r.get("result")
        assert reason, "no model_reason on %s repeat %s" % (model, r.get("repeat"))
        assert verdict in ("valid", "rejected", "noop"), \
            "unexpected verdict %r" % verdict
        rows_e4.append([PRINT_MODEL[model], answer, r.get("repeat"),
                        reason[:46] + ("..." if len(reason) > 46 else ""),
                        verdict])
        body_e4.append(r"%s & %s & %s & %s & %s \\"
                       % (PRINT_MODEL[model], esc(answer), r.get("repeat"),
                          esc(reason), verdict))

show(["Model", "Answer", "Rep", "Stated reason", "Verdict"], rows_e4)
tex_e4 = latex("tab:appendix:replies",
               "All nine replies at Full Information.",
               "llcp{0.42\\textwidth}l",
               r"Model & Answer & Rep & Stated reason & Verdict", body_e4)
write_tex("appendix_replies.tex", tex_e4)
CK.check("tab:appendix:replies", tex_e4)

n_valid = sum(1 for r in rows_e4 if r[4] == "valid")
assert n_valid == 7, ("Appendix E.4 reports seven of nine valid; "
                      "this run gives %d" % n_valid)
print()
print("%d of %d replies valid. The reasons are printed because a true reason "
      "can still give an illegal answer." % (n_valid, len(rows_e4)))
'''


MD12 = r"""---
# 12. Table 5.2 — the block's three resting faces

The only table in Chapter 5 with geometry rather than results in it, and the
one the whole of Experiment 2 turns on: which face is down decides which
extents lie horizontal, which decides the opening a gripper needs, which
decides whether a Franka can take the object at all.

Derived from the block's three dimensions rather than transcribed, and
cross-checked against the three variants the scene registry actually spawns."""

C12 = r'''
# The block, 0.130 x 0.100 x 0.050 m. Taken from the registry rather than
# typed: these are the numbers the simulator spawns.
VARIANTS = {"small_face": "block_upright",   # smallest face down, so tallest
            "edge": "block_small",
            "large_face": "block_large"}
DIMS = sorted({round(YCB[v]["height"], 3) for v in VARIANTS.values()}, reverse=True)
assert len(DIMS) == 3, "the three variants must present three distinct heights"

rows_52, body_52 = [], []
for face in ("small_face", "edge", "large_face"):
    spec = YCB[VARIANTS[face]]
    vertical = round(spec["height"], 3)
    # Whichever two dimensions are not vertical lie flat. The gripper closes
    # on the smaller of them, so that is the opening the object needs.
    horizontal = sorted((d for d in DIMS if d != vertical), reverse=True)
    opening = min(horizontal)
    # The registry's own grasp_m for this variant must agree, or the scene
    # spawns an object the table does not describe.
    assert abs(spec["grasp_m"] - opening) < 1e-9, \
        "%s: registry grasp_m %.3f, geometry implies %.3f" % (
            VARIANTS[face], spec["grasp_m"], opening)
    feasible = {t: opening <= C.ARM_TYPES[t]["max_grasp_m"] for t in ("franka", "ur10")}
    rows_52.append([face, "%.3f" % vertical, "%.3f" % horizontal[0],
                    "%.3f" % horizontal[1], "%.3f" % opening,
                    "yes" if feasible["franka"] else "no",
                    "yes" if feasible["ur10"] else "no"])
    body_52.append(r"\texttt{%s} & %.3f & %.3f & %.3f & %.3f & %s & %s \\"
                   % (esc(face), vertical, horizontal[0], horizontal[1], opening,
                      "yes" if feasible["franka"] else "no",
                      "yes" if feasible["ur10"] else "no"))

show(["Resting face", "Vertical (m)", "Horizontal (m)", "Horizontal (m)",
      "Opening needed (m)", "Franka", "UR10"], rows_52)

tex_52 = latex("tab:ex2:object", "The block's three resting faces.", "lccccc",
               r"Resting face & Vertical (m) & \multicolumn{2}{c}{Horizontal extents (m)} "
               r"& Opening needed (m) & Franka & UR10", body_52)
write_tex("ex2_object.tex", tex_52)
CK.check("tab:ex2:object", tex_52)

# The design rests on exactly one face changing the answer. If all three
# agreed, the experiment would have no contrast to measure.
_franka = [r[5] for r in rows_52]
assert _franka.count("no") == 1, \
    "exactly one resting face must exclude the Franka; got %s" % _franka
print()
print("only %s excludes the Franka, which is the contrast Experiment 2 measures"
      % [r[0] for r in rows_52 if r[5] == "no"][0])
'''
