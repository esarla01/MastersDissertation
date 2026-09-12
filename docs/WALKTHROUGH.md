# How the whole thing works

One pass from the simulated cell to a number in the thesis, naming the module
responsible at each step and how to watch it happen. Read this once and the
other documents become reference rather than narrative.

`docs/REPRODUCE.md` is the short version: install, `make verify`, done. This is
the long version, for changing something rather than checking it.

---

## The shape of it

```
      Isaac Lab                       no simulator from here on
 ┌──────────────────┐   ┌──────────────────────────────────────────────┐
 │ cell + episode   │   │ probe set → prompt → model → run file        │
 │        ↓         │   │                                  ↓           │
 │   audit trail    │──▶│                            notebook → table  │
 └──────────────────┘   └──────────────────────────────────────────────┘
      core/ ycb/              harvest/  experiments/  notebooks/
```

The line down the middle is the design's load-bearing idea. An episode is
expensive, needs a GPU, and never visits the same states twice. So decision
states are **frozen** once, and every experiment replays the frozen set. That
is why `make verify` needs no simulator, and why two models can be compared at
all: they answer the same questions.

---

## 1. The cell — `fourarm/core/`

Four arms on a 2.8 × 1.6 m table: two UR10 on the long sides, two Franka on the
short edges. They differ in the ways the thesis turns on.

| | Reach | Aperture | Payload | Delicate |
|---|---|---|---|---|
| UR10 | 1.300 m | **0.140 m** | 10 kg | no |
| Franka | 0.855 m | **0.080 m** | 3 kg | yes |

`core/cell/cell_config.py` is the authority for those numbers; nothing
restates them. The aperture gap is nearly a factor of two, which is why grasp
is the constraint both experiments manipulate — it binds often enough on the
object set to be measurable.

The package is layered, and the docstrings say so:

| Layer | Directory | Holds |
|---|---|---|
| 1 | `core/cell/` | Geometry, arms, zones, zone locks, reachability rasters |
| 2 | `core/control/` | The task queue, per-arm state machines, the coordinator |
| 3 | `core/decision/` | The allocators, and the state and prompt builder |
| 4 | `core/decision/vlm_allocator.py` | The model-backed allocator |

Reachability is a **precomputed raster per arm**, not a calculation. The
validator uses it, the prompt prints it as `reach_ok_arms`, and the prompt tells
the model to use that list rather than work reach out from coordinates.

**See it:** `python3 -c "import sys; sys.path.insert(0,'fourarm'); from core.cell import cell_config as C; print(C.ARM_TYPES)"`

---

## 2. An episode — `fourarm/ycb/` *(needs Isaac Lab)*

```bash
cd fourarm
python3 ycb/run_ycb_sort.py --allocator b1 --layout capability_trap
```

Objects are placed, and a decision round opens whenever an arm is idle and a
task remains. The allocator names one arm and one task, or declines. The
coordinator reserves zones, the arm executes, the locks release, the next round
opens.

Two things matter for what comes later:

**The allocator only names an arm and a task.** Zone locks, handovers and the
second leg of a handover belong to the coordinator. So a decision is a small,
comparable object: a pair, or a refusal.

**An illegal assignment is recorded as made.** It is judged afterwards by the
validator, never corrected in flight, so the trail is faithful to what was
actually decided.

Which allocator ran matters for provenance. `random_allocator` seeds its RNG on
`(episode seed, sorted idle arms, ready set)` rather than a call counter, so
replaying a state reproduces the choice. **Every probe set here was harvested
under random-valid or rule, never under a VLM** — a set shaped by a model's
behaviour would undercut the design, and `harvest/probe_audit.py` asserts it.

---

## 3. Freezing — `fourarm/harvest/`

An episode writes an audit trail. `probe_store.py` lifts each decision point out
of it and freezes everything needed to re-render the prompt and re-run the real
validator offline: the state dict, exact object positions, the camera frame, and
where it came from.

```
episode trail → harvest_trail()      probe_store.py
              → merge + deduplicate  build_master_set.py
              → refreeze             refreeze_probe_set.py
              → probes/ex1_v2.json
```

**Probe sets are content-addressed.** The hash covers the identity fields of
every probe, in order. Edit one state and the hash moves, invalidating every run
made against it. That is the point: a run file only means something paired with
the states it answered.

The cast A chain, exactly as Appendix D describes it:

| Step | States | |
|---|---|---|
| Harvested from six runs | 278 | `master_v1.json` |
| Deduplicated to one state per distinct option set | 185 | `ex1_v1.json`, a loss of 93 |
| Refrozen without `seed_v3` | **162** | `ex1_v2.json` |

`seed_v3` went because it predates a correction to the mustard bottle's grasp
width, 0.058 → 0.096 m. Twenty-three of its 29 states had survived
deduplication; none reaches the reported set. Since grasp is what both
experiments manipulate, a stale width there would bias the measurement rather
than add noise.

`frozen_coord.py` is the shim the whole offline path stands on: it rebuilds a
validator-compatible coordinator from a saved state. If it misrepresented the
cell, every replayed number would be wrong in the same direction and nothing
would look broken — which is why `h_frozen_coord.py` tests it against a real
episode rather than against expectations.

**See it:** `make probes`

---

## 4. Asking a model — `fourarm/experiments/`

A frozen state is rendered into a prompt, sent, and the reply parsed.

**Experiment 1** (`experiments/ex1/prompts.py`) varies what the prompt carries
about the same state. `RUNGS` is the authority for the eight conditions;
`mislabel.py` performs the name swap; `anonymise.py` strips identity. The
manipulations are *state edits*, not prompt rewrites — the template is one code
path, so a condition cannot accidentally differ in wording as well as content.

**Experiment 2** (`experiments/ex2/prompts.py`) varies what the model must
derive. `FIELD_ALIASES` renames every field before the model sees it, so
`grasp_m` arrives as `opening_needed_m` against `opening_max_m` — a visibly
matched pair, so the direction of the comparison is readable from the names
alone. `pose` becomes `resting_face`, because a posture label could be read off
as an outcome where a geometric name cannot.

Five mechanical assertions run before any trial and raise rather than warn: the
glossary matches the state, R3 never names a withheld field, the template
states no relation, the configurations are isolated, and the candidate faces
carry no pose. `docs/EX2_GUIDE.md` has the pipeline in running order.

**See it:** `python3 -B harness/h_ex1_prompts.py` and `h_ex2_prompts.py`

---

## 5. The record — `out/` and `runs/`

One JSONL row per trial: one state, one model, one repeat. Experiment 1 rows
carry `result` and `model_reason`; Experiment 2 rows carry `outcome` and
`reasoning`. Reading the wrong pair yields `None` silently —
`docs/DATA_DICTIONARY.md` has every field with units.

**These files are the primary record, not a cache.** Model calls are not
reproducible: runs were not seeded and two of three providers expose no
temperature control. Re-collecting produces a new dataset, not a reproduction.

Which file backs which published result is decided in exactly one place,
`fourarm/run_files.py`. Its audit fails if a listed file is missing, if one
holds the wrong row count or rung, or if a `.jsonl` appears that no list
accounts for. That last check exists because a real 324-row cast B run sat
unread for weeks while a table it should have backed went unverified.

**Never glob `out/`.** It holds smoke tests and repair runs that fall in the
same `(model, condition)` bucket as real runs; a glob reads alphabetically and
the last wins. That put a wrong figure in the write-up for two days.

**See it:** `make manifest`

---

## 6. Analysis — `fourarm/notebooks/`

Each notebook loads run files, computes the reported quantity, writes a CSV or
`.tex`, and **asserts the result against the thesis**.

| Notebook | Produces |
|---|---|
| `notebooks/ex1/ex1_reproduce_tables.ipynb` | Tables 4.1–4.11, F.1, G.1 |
| `notebooks/ex2/ex2_q1_derivation.ipynb` | Tables 5.6–5.9 |
| `notebooks/ex2/ex2_q2_precedence.ipynb` | Tables 5.10, 5.11 |
| `notebooks/ex2/ex2_q3_repair.ipynb` | Tables 5.12–5.14 |
| `notebooks/appendix/appendix_tables.ipynb` | Tables 3.1, 3.2, 5.2, A.1, A.2, B.1, B.2, C.1, D.1, E.1–E.4 |

The Experiment 2 notebooks are **generated** from `_cells/nb_*_cells.py` by
`_cells/build_*_nb.py`. Edit the cell bank, not the notebook: editing in Jupyter
is how the two drift, and it is how six armed `CONFIRM_SPEND` values reached
git. A rebuild carries stored outputs across, matched on cell source text, so a
cell whose source changed correctly loses its output.

### The spend gate

Cells are labelled `MAKES MODEL CALLS` or `No model calls`. A paid cell prints
its cost — scenes × models × repeats — and refuses to run unless
`CONFIRM_SPEND` is set to exactly that number. **The value must never be
committed.** `make spend-check` fails if it is, and so does a rebuild.

### Checking against the thesis

`fourarm/thesis_check.py` reads the thesis LaTeX from `THESIS_REPO` and reduces
a table to its ordered numeric tokens, so the comparison is immune to spacing
and caption edits and sensitive to exactly one thing: a changed number.

The thesis tree is not in this repository, so each notebook also carries a
`thesis_expected.json` — the tokens each table held when the thesis was last
read.

| | Behaviour |
|---|---|
| Thesis present | Authoritative; the vendored copy is checked against it |
| Thesis absent | Tables still check, against the vendored copy |
| Both, disagreeing | **Fails** — a stale copy would pass against a number no longer printed |

A refresh section rewrites the vendored file, and only when the thesis was
readable: a run that fell back to it cannot certify it.

**One limitation, stated plainly.** A numeric check cannot see a wrong *text*
column. An appendix table with an empty reason column and `None` for every
verdict once passed all 18 of its numeric cells, because its only numbers were
task ids and repeat counts. Cells whose tables are mostly prose assert their
text fields directly.

---

## 7. The gates — `harness/`

49 standalone scripts, each importing the real module and breaking it on
purpose. `harness/README.md` groups them. They are what stops a refactor
silently changing a published number — and the reason this repository's own
verification was found stale rather than trusted.

**See it:** `make harness`

---

## Watching one number end to end

Take Gemini's No Width legality, 71.9%, in Table 4.7.

```bash
cd fourarm

# 1. the states it was measured on: 96 grasp-binding picking states
python3 -B harvest/probe_audit.py | head -4

# 2. the file that holds the answers, named not globbed
python3 -B -c "import run_files; print(run_files.CAST_A[('gemini','nowidth')])"

# 3. recomputed by the standard-library script (the legality block is "spine")
python3 -B analysis/ex1/ex1_verify_tables.py --table spine | grep "gemini No Width"

# 4. and independently by the notebook, asserted against the thesis
cd .. && make verify-ex1
```

Steps 3 and 4 share `run_files.py` — the list of which files to read — and
nothing else. If they ever disagree, the disagreement is the finding.

---

## Where to go next

| To | Read |
|---|---|
| Reproduce every number | `docs/REPRODUCE.md` |
| Change the cell or harvest new states | `docs/SIMULATION.md` |
| Trace a Chapter 4 number | `docs/TABLE_PROVENANCE.md` |
| Trace a Chapter 5 number | `docs/PROVENANCE_EX2.md` |
| Understand a field | `docs/DATA_DICTIONARY.md` |
| Re-run Experiment 2 | `docs/EX2_GUIDE.md` |
| Know where the code disagrees with the thesis | `docs/ERRATA.md` |
