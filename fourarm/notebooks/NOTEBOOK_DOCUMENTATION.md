# `ex2_q1_derivation.ipynb` — setup and dependencies

Experiment 2, Question 1: *when the text omits the capability-relevant
quantity, can the model obtain it from the scene?* Read at rung `N0` only.

Everything below was checked against the files in this tree, not assumed.
Anything I could not determine is marked **UNVERIFIED**.

---

## 1. Quickstart

```bash
cd fourarm
export OPENAI_API_KEY='...'      # for the `gpt` alias
export GEMINI_API_KEY='...'      # for the `gemini` alias

../.venv/bin/python -m jupyter lab notebooks/ex2_q1_derivation.ipynb
```

Then run cells 1–4 (free), read the cost printed by cell 5, set
`CONFIRM_SPEND` in that cell to the number it printed, and run it.

**Use `../.venv/bin/python`.** It is the only interpreter in the project with
`ipykernel` installed. The system `python3` can import the project stack but
cannot host a Jupyter kernel.

---

## 2. API keys

### Which keys, for which models

The notebook picks its models in cell 1:

```python
MODELS = tuple(a for a in ALIASES if a in ("gemini", "gpt")) or ("gemini", "gpt")
```

which currently resolves to `('gpt', 'gemini')`. Those two aliases need:

| Alias | Environment variable | Endpoint (from `env/models.env`) | Model id |
|---|---|---|---|
| `gpt` | `OPENAI_API_KEY` | `https://api.openai.com/v1/chat/completions` | `gpt-5.6-terra` |
| `gemini` | `GEMINI_API_KEY` | `https://generativelanguage.googleapis.com/...` | `gemini-3.6-flash` |

The variable name is not hardcoded — it comes from `GPT_KEY_VAR` /
`GEMINI_KEY_VAR` in `env/models.env`, defaulting to `<ALIAS>_API_KEY`. If you
change those lines, the variable to export changes with them.

Two other aliases exist and Q1 does not use them: `qwen` (`QWEN_API_KEY`) and
`claude` (`ANTHROPIC_API_KEY`). **`claude` is not configured** — its
`CLAUDE_ENDPOINT` is the literal placeholder
`REPLACE_WITH_OPENAI_COMPATIBLE_GATEWAY`.

### Where the keys go

**In your shell environment, and nowhere else.** This is enforced, not a
convention:

- `env/models.env` is read by `model_registry.load()` using
  `os.environ.setdefault`, so **the real environment always wins** over the
  file.
- `describe()` returns everything about an alias *except* the key, and that is
  what gets stamped into run rows. `resolve()` is the only function that
  touches the key, and it reads it straight from `os.environ`.
- I checked `env/models.env`: 18 variables, **no key-shaped value in any of
  them**. It holds endpoints, model ids, request params and key-variable
  names only.

Do not put a key in `env/models.env`. See the risk note in §6.

### Exact steps to run cell 5

1. `cd fourarm`
2. Export both keys in the shell **before** launching Jupyter — a kernel
   inherits the environment it was started in, so exporting in a terminal
   after the kernel is running will not reach it.
   ```bash
   export OPENAI_API_KEY='...'
   export GEMINI_API_KEY='...'
   ```
3. Launch with the venv interpreter: `../.venv/bin/python -m jupyter lab`
4. Run cells 1–4. Cell 1 prints `models  ('gpt', 'gemini')`; cell 3 must end
   `PASS  inventory complete, 29 positions usable.`
5. Run cell 5 once. It prints:
   ```
   COST: 10 positions x 3 faces x 2 models x 3 repeats = 180 calls
   set CONFIRM_SPEND = 180 in this cell to proceed
   ```
   Nothing is sent on this pass.
6. Edit `CONFIRM_SPEND = None` to `CONFIRM_SPEND = 180` in that cell and run
   it again. This is the only confirmation step; there is no `input()` prompt.

### Verifying a key is live without spending anything

```bash
cd fourarm
python3 -c "
import sys; sys.path[:0]=['.','ycb']
from core.decision.model_registry import resolve
for a in ('gpt','gemini'):
    try: resolve(a); print(a,'OK')
    except Exception as e: print(a,'->',e)
"
```

With a key missing you get the exact variable name, before any call:

```
no API key for model alias 'gpt': environment variable OPENAI_API_KEY is not
set. Export it in your shell; it is never stored in .../env/models.env or
anywhere else in the tree.
```

`resolve()` only proves the key *exists*. It does not prove it is valid — that
surfaces as an HTTP error on the first call. `openai_chat` raises on any
network or protocol error; `mancheck` retries once on an exception and then
records the row with an `error` field rather than ending the run.

### How the call is made

`core/decision/vlm_allocator.openai_chat` POSTs to the alias's endpoint using
**stdlib `urllib.request`** — there is no `requests` dependency — with
`Authorization: Bearer <key>`, an OpenAI-compatible `{"model", "messages"}`
body plus the alias's `*_PARAMS`. Both models are called through the same
OpenAI-compatible shape, so the Gemini endpoint in `models.env` must be an
OpenAI-compatible one. **UNVERIFIED:** I could not confirm the configured
Gemini URL speaks that dialect without making a call.

---

## 3. File dependencies

### Working directory

Cell 1 walks up from `Path.cwd()` looking for a directory containing **both**
`out/` and `experiments/`, and sets `ROOT` to it. So run the notebook from
`fourarm/` or anywhere below it — `notebooks/` qualifies. It raises
`SystemExit` if neither is found. Every other path in the notebook is derived
from `ROOT`, so nothing depends on the launch directory beyond that.

### Data the notebook reads

| Path | Used for |
|---|---|
| `out/ex2_capture_block/consults.jsonl` | The 90 captured scenes: state, exact positions, image filenames. Cells 3, 4, 6, 7, 14 |
| `out/ex2_capture_block/*.png` | 90 frames, one per scene, camera `ex2_cam` only. Attached to every prompt |
| `env/models.env` | Endpoints, model ids, request params, key-variable names. Read automatically on first registry use |

### Project modules it imports

| Module | Used for |
|---|---|
| `core/cell/cell_config.py` | Arm apertures (`ARM_TYPES`), table geometry. The source of truth for `FRANKA_MAX` / `UR_MAX` |
| `core/decision/model_registry.py` | `aliases()` in cell 1; `resolve()` inside every call |
| `core/decision/vlm_allocator.py` | `openai_chat`, and the validator behind `legal_arms` |
| `ycb/ycb_objects.py` | `YCB` — the authored cuboid dimensions. Cell 2 derives each opening from `size` and checks it against `transforms` |
| `experiments/ex2/labels.py` | `TRUE_POSE` (prim → resting face), `require_face` |
| `experiments/ex2/transforms.py` | Builds the congruent and dims states; `DIMS_M`, `POSE_FACTS_BY_LABEL` |
| `experiments/ex2/prompts.py` | Renders the prompt; `RESTING_FACES`, `CONDITIONS`, `RUNGS`, the four `assert_*` functions, `manipulation_check` |
| `experiments/ex2/run.py` | `load_scenes`, `legal_arms`, `flip_task_id`, `present_reachable_ur` |
| `experiments/ex2/solo.py` | `S.run` — the trial runner for cells 6 and 7 |
| `experiments/ex2/mancheck.py` | `MC.run` — the two-way perception probe, cell 5 |
| `experiments/ex2/grade.py` | Grading, called inside `solo.run` |
| `analysis/ex2/ex2_stats.py` | `wilson`, `newcombe`, `paired_mean_ci`, `spans_zero` |

### Files beside the notebook

| File | What it is |
|---|---|
| `ex2_q1_derivation.ipynb` | The notebook |
| `nb_cells_a.py`, `nb_cells_b.py` | The cell sources, as plain strings |
| `build_q1_nb.py` | Regenerates the `.ipynb` from those two |

Edit the cell sources and rebuild rather than hand-editing JSON:

```bash
python3 notebooks/build_q1_nb.py notebooks/ex2_q1_derivation.ipynb
```

`nbformat` is not installed in either venv, so the builder emits the notebook
JSON directly. It also parses every code cell and fails if one does not.

### Related but *not* used by this notebook

`analyse.py`, `analyse_conflict.py`, `rescore.py`, `verify_legality.py`,
`ex2_analyse_dims.py`, `cue.py`, `seecheck.py` — these analyse the earlier
P-rung datasets. The notebook does its own analysis from the two run files it
produces.

---

## 4. Execution order, cost and outputs

| Cell | Calls | Writes |
|---|---|---|
| 1 Setup | – | creates `runs/`, `tables/ex2_q1/`, `figures/ex2_q1/` |
| 2 Design check | – | `tab_ex2_q1_design.csv` |
| 3 Capture inventory + legality | – | `tab_ex2_q1_inventory.csv` |
| 4 Prompt inspection | – | – |
| 5 Cue validation | **180** | `runs/ex2_q1_cue_<model>_r<n>.jsonl` (6 files) |
| 5b Cue results | – | `tab_ex2_q1_cue.csv`, `tab_ex2_q1_cue_confusion.csv` |
| 6 Congruent N0 | **540** | `runs/ex2_q1_congruent_N0.jsonl` |
| 7 Dims N0 | **540** | `runs/ex2_q1_dims_N0.jsonl` |
| 8 Load and validate | – | – |
| 9 Franka share | – | `tab_ex2_q1_share.csv` |
| 10 Paired contrasts | – | `tab_ex2_q1_contrasts.csv`, `..._bypos.csv` |
| 11 Wait rate | – | `tab_ex2_q1_waits.csv` |
| 12 Reported opening | – | – (inline) |
| 13 Figure | – | `fig_ex2_q1_share.csv`, `fig_ex2_q1_share.tex` |
| 14 Provenance | – | `tab_ex2_q1_provenance.csv` |

**Total ≈ 1,260 calls.** Cells 1–4 and 8–14 are free; only 5, 6 and 7 spend.

Cells 5, 6 and 7 each require `CONFIRM_SPEND` to be set to the exact number
they print. Cells 6 and 7 also skip entirely if the output file already holds
at least that many rows.

### Re-running is safe

`solo.run` reads its output file, collects the `trial_id`s already answered
without an error, and skips them — so re-running cell 6 or 7 costs nothing and
destroys nothing. There is no `--force` anywhere. Rows are appended and
de-duplicated at read time with last-write-wins, matching `solo.py`'s own
table.

**Cell 5 is the exception to the usual resume pattern.** `mancheck.check_id`
is `seq|view|model` with *no repeat field*, so three repeats in one file would
collide and the second and third would be skipped. The cell therefore writes
one file per repeat. Do not merge them.

### Gate before spending on cells 6 and 7

Cell 5b prints a verdict on `small_face` vs `large_face`. If it is
`NOT SEPARABLE`, **stop**: a null result would be measuring the render, not
the model, and should be reported as an instrument result.

The probe was three-way until 2026-08-27 and this gate was on `edge` vs
`large_face` — both flat, differing only in geometry, which made separating
them the sharp test. That face was withdrawn because no model read it (GPT
58%, Fisher p = 0.76 over 81 answered trials, against 18/18 on a plain
standing-or-flat question). The three-way runs are retained in
`runs/ex2_q1_cue_*.jsonl` as the evidence.

**What the gate no longer covers.** `small_face` stands and `large_face` lies,
so passing it is consistent with reading posture and applying a rule, not only
with deriving the opening from geometry. Cell 10 prints that caveat under every
verdict and it belongs in Limitations.

---

## 5. Inputs and outputs in detail

### Inputs

- 90 captures = 30 positions × 3 resting faces, camera `ex2_cam`.
- Object: a plain cuboid, 0.130 × 0.100 × 0.050 m, no recognisable identity.
- Two conditions: `congruent` (face and opening both stated and true) and
  `dims` (both withheld).
- One rung, `N0`. One preference, `franka`. Three repeats.

### Output columns

Full column specifications are in `ex2_q1_editor_instruction.md`. Two
deviations from that document, both deliberate:

- `tab_ex2_q1_contrasts.csv` carries **both** `newcombe_lo`/`newcombe_hi` and
  `paired_lo`/`paired_hi`. **Quote the paired pair.** The contrasts are
  computed within position and then averaged, so the unit is the position and
  the correct interval is a t interval over the 29 differences. Newcombe is an
  interval on a difference of *independent* proportions and is emitted
  alongside as the conservative unpaired comparison.
- `tab_ex2_q1_contrasts_bypos.csv` has `conditions × models × positions × 1`
  rows. The last factor was 2 until 2026-08-27, when `edge_minus_large` was
  withdrawn with the face it names; the position count is whatever survives
  the legality and visibility gates, so the row count is derived and not
  predicted here — see §6.

`tab_ex2_q1_design.csv` uses the 10 column names the instruction lists; the
instruction says "12 columns" but names 10, and I followed the names.

---

## 6. Issues and assumptions

Each of these must be disclosed in the chapter. Cell 14 prints them.

**1. The idle UR is chosen per position.** All 90 captures were written with
`capture_ex2_scene`'s default `--idle ur_w,franka_n`. That is right for the 15
west positions and wrong for the 15 east ones, where the object is reached by
`ur_e`: there, idle-and-reachable collapsed to `franka_n` alone, so on
`small_face` the only legal arm was also the preferred one, and on
`large_face` **no arm was legal at all**. The east half carried no contrast.

`run.present_reachable_ur` corrects this at load time by presenting whichever
UR is in the object's own reach list as the idle one. This is a text-layer
change, not a rewriting of the record: `capture_ex2_scene` sets `ag.state` by
attribute write *after* the frames are rendered and never commands an arm to
move, and all four `ee_xy` are symmetric rest positions, so the picture shows
four parked arms whichever labels the text carries. `ex2_block.txt` states the
intent was "reachable by franka_n **and by the nearer UR**". Read the captures
as written with `load_scenes(..., present_ur=False)`.

**2. 29 of 30 positions, not 30.** `e02` is excluded: `franka_n` cannot reach
it at all, so the Franka is never legal there whatever the idle set and there
is no arm choice to measure. Cell 3 prints the per-position grid and raises if
fewer than 20 positions survive. The design document's §7 says 30 positions
and needs correcting.

**3. Only `ex2_cam` was captured**, so Q1 has no viewpoint control. A
`table_cam` comparison would need a new capture run.

**4. Cell 5's sample is all east.** `CUE_POSITIONS = USABLE[:10]` takes the
first ten usable positions in sort order, which are `e00, e01, e03, e04, e05,
e06, e07, e08, e09, e10` — every one of them east, because `e` sorts before
`w`. That is fine for a legibility check on the block itself, but it does not
sample the west half, and the two halves differ in which UR is idle and in how
the object sits relative to the camera.

**If you want the probe spread across both halves, change `CUE_POSITIONS` in
cell 5**, for example:

```python
CUE_POSITIONS = [p for p in USABLE if p.startswith("e")][:5] + \
                [p for p in USABLE if p.startswith("w")][:5]
```

Sampling rather than probing all 90 is deliberate — the instruction says to
probe 8–10 positions before capturing confidence in the full set.

**5. `env/models.env` is not in `.gitignore`.** It currently holds no secrets
and is untracked, so nothing is exposed today. But the file sits in a place
where a key would be committed if someone ever put one there. Consider adding
`fourarm/env/models.env` to `.gitignore`. Keys belong in the shell, and the
registry is built so that they only work from there.

**6. The `claude` alias is unconfigured** — placeholder endpoint. Q1 does not
use it; it will raise if selected.

**7. `matplotlib` and `nbformat` are installed in neither venv.** Cell 13
therefore writes plotted values plus a self-contained TikZ picture instead of
a raster. The `.tex` declares three colours locally so it stands alone; delete
those `\definecolor` lines once the thesis `includes.tex` supplies the
palette.

**8. UNVERIFIED — endpoint dialect.** Both models are called through one
OpenAI-compatible client. I did not make a call, so I cannot confirm the
configured Gemini endpoint accepts that request shape or returns
`choices[0].message.content`. If cell 5 fails on Gemini with a protocol error,
that is where to look first.

**9. UNVERIFIED — cost in money.** The counts above are *calls*, not currency.
Per-call cost depends on each provider's image tokenisation, which the code
deliberately does not estimate: `solo.run` records the provider's own `usage`
figures per row, and `solo.cost_table` reports them after the fact.
