"""Isaac-free column shakeout checker (run on the server or anywhere).

Reads the four shakeout episode JSONs and prints one PASS/CHECK line per
criterion per column, then a comparison table. No imports beyond stdlib;
degrades gracefully when a field is absent (reports MISSING, never
crashes).

Usage:
  python3 check_columns.py out/ep_b1.json out/ep_b2.json \
                           out/ep_vlm_a.json out/ep_vlm_v.json

Expectations encoded (seed 0, designed layout, no disruptions):
  all columns: verdict PASS, 11/11 sorted, nonzero travel_m on every arm,
               travel_m_total present, and for VLM columns the prompt
               version READ FROM THE REAL state_builder (classical
               columns have no prompt). That import replaced a hardcoded
               "2026-07-25c", which went stale the moment the prompt
               moved to 2026-07-25d and produced two false CHECK lines.
  b1 (oracle): makespan near 2710 (validated), blocked near 799.
  b2 (opt):    makespan near 3353 (validated), blocked near 322;
               solver verify mismatches 0.
  vlm A:       condition A; expect high model-authored share.
  vlm V:       condition V; FIRST EVER: checks are structural only
               (decisions logged, latency recorded, provenance present).
Tolerance for classical columns: +-5% on makespan (physics jitter after
visual-only scene changes; a larger drift means something non-visual
changed and must be investigated before anything else runs).
"""
import json
import os
import sys


def _expected_prompt_version():
    """(version, reason) from the REAL state_builder, so this checker can
    never drift from the code again. Searches beside the script, one
    level up, the working directory, and a sibling fourarm/ directory,
    since the file is run both from the project root and from harness/.
    Returns (None, reason) rather than failing if the project is not
    importable from here."""
    here = os.path.dirname(os.path.abspath(__file__))
    seen, roots = set(), []
    for base in (here, os.path.dirname(here), os.getcwd()):
        for cand in (base, os.path.join(base, "fourarm")):
            if cand not in seen:      # harness/ sits BESIDE fourarm/ in
                seen.add(cand)        # the delivered tarball
                roots.append(cand)
    for root in roots:
        if os.path.exists(os.path.join(root, "core", "decision",
                                       "state_builder.py")):
            sys.path.insert(0, root)
            try:
                from core.decision.state_builder import PROMPT_VERSION
                return PROMPT_VERSION, None
            except Exception as e:                # numpy missing, etc.
                return None, f"{type(e).__name__}: {str(e)[:60]}"
    return None, "state_builder.py not found from this location"


EXPECTED_PROMPT, PROMPT_REASON = _expected_prompt_version()

TOL = 0.05
EXPECT = {  # validated baselines (seed 0 designed, pre-visual-change)
    "b1": {"makespan": 2710, "blocked": 799},
    "b2": {"makespan": 3353, "blocked": 322},
    # legacy meta names from pre-2026-07-25e episodes
    "oracle": {"makespan": 2710, "blocked": 799},
    "opt":    {"makespan": 3353, "blocked": 322},
}
VLM_CONDITION = {"vlm1": "A", "vlm2": "V"}   # column name -> condition

rows = []
problems = 0


def get(d, *path):
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return None
        d = d[p]
    return d


def line(col, label, ok, detail=""):
    global problems
    tag = "PASS " if ok else ("MISS " if ok is None else "CHECK")
    if ok is not True:
        problems += 1
    print(f"  [{tag}] {col:10s} {label}" + (f": {detail}" if detail else ""))


for path in sys.argv[1:]:
    with open(path) as f:
        ep = json.load(f)
    meta = ep.get("meta", {})
    alloc_name = meta.get("allocator", "?")
    cond = meta.get("condition")
    col = f"{alloc_name}" + (f"/{cond}" if cond else "")
    print(f"\n== {path}  ({col})")

    verdict = meta.get("verdict") or get(ep, "summary", "verdict")
    line(col, "verdict PASS", verdict == "PASS", str(verdict))

    sorted_s = get(ep, "summary", "sorted")
    line(col, "11/11 sorted", sorted_s == "11/11", str(sorted_s))

    mk = get(ep, "summary", "makespan_ticks")
    exp = EXPECT.get(alloc_name)
    if exp and mk is not None:
        drift = abs(mk - exp["makespan"]) / exp["makespan"]
        line(col, f"makespan near {exp['makespan']}", drift <= TOL,
             f"{mk} (drift {drift * 100:.1f}%)")
    else:
        line(col, "makespan recorded", mk is not None, str(mk))

    blocked = get(ep, "summary", "blocked_ticks_total")
    if exp and blocked is not None:
        line(col, f"blocked near {exp['blocked']}", True, str(blocked))
    else:
        line(col, "blocked recorded", blocked is not None, str(blocked))

    per_arm = ep.get("per_arm", {})
    travels = {a: v.get("travel_m") for a, v in per_arm.items()}
    ok_travel = (len(travels) == 4 and
                 all(t is not None and t > 0 for t in travels.values()))
    line(col, "travel_m > 0 on all 4 arms", ok_travel, str(travels))
    line(col, "travel_m_total present",
         get(ep, "metrics", "travel_m_total") is not None,
         str(get(ep, "metrics", "travel_m_total")))

    if str(alloc_name).startswith("vlm"):
        if alloc_name in VLM_CONDITION:
            line(col, f"condition matches column ({VLM_CONDITION[alloc_name]})",
                 cond == VLM_CONDITION[alloc_name], str(cond))
        if EXPECTED_PROMPT:
            line(col, f"prompt_version {EXPECTED_PROMPT} (from the code)",
                 meta.get("prompt_version") == EXPECTED_PROMPT,
                 str(meta.get("prompt_version")))
        else:                       # cannot import the project from here
            line(col, "prompt_version recorded",
                 bool(meta.get("prompt_version")),
                 f"{meta.get('prompt_version')} (expected version "
                 f"unavailable: {PROMPT_REASON})")
        stats = get(ep, "allocator", "stats") or {}
        calls = stats.get("calls")
        line(col, "model consulted", bool(calls), f"calls={calls}")
        line(col, "decision log present",
             bool(get(ep, "allocator", "log")),
             f"{len(get(ep, 'allocator', 'log') or [])} rounds")
        authored = stats.get("rule_assigned")
        line(col, "rule_assigned recorded", authored is not None,
             f"rule_assigned={authored}, fallback={stats.get('fallback')}, "
             f"valid_first={stats.get('valid_first')}, "
             f"noop={stats.get('noop')}")
        lat = stats.get("latency_ms_total")
        line(col, "model latency recorded"
             + (" (image path exercised)" if cond == "V" else ""),
             lat is not None and lat > 0, str(lat))
        # Regression guard (bug found 2026-07-25): vlm columns must submit
        # tasks WITHOUT a pre-given destination, so at least one task's
        # dest_by must be model or oracle. All-"given" means the runner's
        # kind dispatch broke and the model never chose baskets.
        dest_bys = {t.get("dest_by") for t in ep.get("tasks", [])}
        line(col, "model owns destinations (dest_by not all 'given')",
             bool(dest_bys & {"model", "oracle"}), str(sorted(
                 str(d) for d in dest_bys)))
    rows.append((col, mk, blocked,
                 round(sum(t for t in travels.values() if t), 2)
                 if travels else None))

print("\n== comparison")
print(f"  {'column':12s} {'makespan':>9s} {'blocked':>8s} {'travel_m':>9s}")
for col, mk, bl, tr in rows:
    print(f"  {col:12s} {str(mk):>9s} {str(bl):>8s} {str(tr):>9s}")
print(f"\nRESULT: {'ALL PASS' if problems == 0 else str(problems) + ' item(s) to look at'}")
sys.exit(0 if problems == 0 else 1)
