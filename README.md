# Grounded, Memorised, or Declared?

Code and data for *Grounded, Memorised, or Declared? A Decision-Level
Evaluation of Capability Reasoning in VLM Task Allocation for a Heterogeneous
Four-Arm Cell* (MSc, Imperial College London).

Across two experiments and three models the answer is **declared**: the model
follows the value stated in the text, over the object's name and over the
scene image.

The cell is a four-arm sorting workspace in Isaac Lab: two UR10 arms with a
0.140 m gripper aperture and two Franka arms with a 0.080 m aperture, sorting
YCB objects into baskets. The thesis does not benchmark that system. It
evaluates a *model* at the *decision level*. The cell supplies frozen decision
states, the models are asked to allocate, and what varies is the information
the prompt carries.

---

## Reproducing the results without a simulator

Every reported number comes from frozen run files and content-hashed probe
sets that are in this repository. Isaac Lab is **not** required to reproduce
the analysis, only to harvest new states. Neither is a network: the reproduce
path never calls a model.

```bash
make setup      # .venv from requirements.lock, once
make verify     # every check, offline, non-zero exit on any mismatch
```

`make verify` runs, in order:

| | What it checks |
|---|---|
| spend gates | no notebook cell has a filled-in `CONFIRM_SPEND`, which would turn Run All into a paid sweep |
| run-file manifest | every published run file present and holding what it claims, and nothing on disk that no list accounts for |
| Experiment 1 | `ex1_verify_tables.py`, then `ex1_reproduce_tables.ipynb`, which rebuilds all thirteen tables and asserts each against the thesis |
| Experiment 2 | the four EX2 notebooks execute clean |
| harness | the regression gates |

The two Experiment 1 checks are deliberately independent. The script uses only
the standard library and the notebook computes everything from the probe sets
and the deployed validator; they share only `run_files.py`, the list of which
files to read. If they ever disagree, the disagreement is the finding.

See [`docs/TABLE_PROVENANCE.md`](docs/TABLE_PROVENANCE.md) for what each table
reports and the definitions that are easy to get wrong, and
[`docs/ERRATA.md`](docs/ERRATA.md) for the two places the code is right and the
thesis is not.

---

## Layout

```
.
├── Makefile                  make verify runs everything, offline
├── pyproject.toml            deps; requirements.lock pins them
├── docs/
│   ├── REPRODUCE.md          clean checkout -> every number
│   ├── SIMULATION.md         the cell, and how a probe set is made
│   ├── TABLE_PROVENANCE.md   Experiment 1, table by table
│   ├── PROVENANCE_EX2.md     Experiment 2, table by table
│   ├── DATA_DICTIONARY.md    every field, with units
│   ├── ERRATA.md             where the code is right and the thesis is not
│   ├── EX2_GUIDE.md          the Experiment 2 pipeline, in running order
│   └── history/              superseded working notes
├── harness/                  49 regression gates
├── attic/                    superseded code, kept for provenance only
└── fourarm/
    ├── run_files.py          WHICH run file backs which published result
    ├── thesis_check.py       comparing a generated table against the thesis
    ├── core/                 cell, control, allocators
    ├── ycb/                  scene assembly, episode and capture runners
    ├── instrumentation/      episode logging
    ├── harvest/              episode trail -> frozen probe set, and replay
    ├── experiments/          ex1/ and ex2/ prompt modules
    ├── analysis/             scoring helpers, and the EX1 verify script
    ├── notebooks/
    │   ├── ex1/              all thirteen Chapter 4 tables
    │   ├── ex2/              one notebook per Chapter 5 sub-question
    │   ├── appendix/         Chapter 3 and appendix tables
    │   ├── _cells/           the sources the EX2 notebooks are built from
    │   └── publish/          CSV and runs -> the .tex the thesis inputs
    ├── probes/               frozen, content-hashed decision states
    ├── out/                  Experiment 1 run files (see out/README.md)
    ├── runs/                 Experiment 2 run files (see runs/README.md)
    └── tables/  figures/     generated output, one directory per experiment
```

The split that matters is which code needs a simulator. Only `ycb/run_*` and
`ycb/capture_*` import Isaac Lab; everything else is plain Python, which is
what lets a frozen state be re-rendered and re-judged offline.

`out/` holds Experiment 1 results and `runs/` holds Experiment 2 results, with
no exceptions: the image-on cell that earlier notes place in `runs/` was moved
to `out/` by the August rename.

Which of them backs a published result is decided in one place,
`fourarm/run_files.py`. Its audit fails if a listed file is missing, if one
holds the wrong row count or rung, or if a `.jsonl` turns up that no list
accounts for.

---

## Finding your way around

Start with the question, not the directory.

| Question | Read |
|---|---|
| How does the whole thing work? | **`docs/WALKTHROUGH.md`** — start here |
| How do I reproduce every number? | `docs/REPRODUCE.md` |
| Where does this Chapter 4 number come from? | `docs/TABLE_PROVENANCE.md` |
| Where does this Chapter 5 number come from? | `docs/PROVENANCE_EX2.md` |
| What is this field, and in what units? | `docs/DATA_DICTIONARY.md` |
| How does the cell work, and how is a probe set made? | `docs/SIMULATION.md` |
| Which notebook produces which table? | `fourarm/notebooks/README.md` |
| What do these run filenames mean? | `fourarm/out/README.md`, `fourarm/runs/README.md` |
| How do I re-run the Experiment 2 pipeline? | `docs/EX2_GUIDE.md` |
| What do the 49 regression gates check? | `harness/README.md` |
| Where is the code right and the thesis wrong? | `docs/ERRATA.md` |

Run everything from the repository root through `make`. Scripts and notebooks
assume the working directory is `fourarm/` or below, which the Makefile
handles.

**Data files are never renamed or moved.** Their names appear in the thesis, in
the provenance record and in the verification script, so a rename breaks the
trail from a published number to the data behind it. The August 2026 rename was
recorded with md5s in `out/RENAME_MANIFEST.json` and still broke the verify
script, six harness gates and the provenance document, because its consumers
were never updated. `run_files.py` exists so that a rename now means editing one
file.

---

## The data

| Probe set | States | Hash (first 16) | Used by |
|---|---|---|---|
| `probes/ex1_v2.json` | 162 | `e23cd23479778f76` | Experiment 1, cast A |
| `probes/ex1_setb_v1.json` | 108 | `b8abfb3391dd6d52` | Experiment 1, cast B |
| `probes/ex3_v1.json` | 135 | `047eb6b3fb2d9c7c` | harvested, unused |
| `probes/ex3_setb_v1.json` | 72 | `c5451710996cd3d9` | harvested, unused |

Probe sets are content-addressed. Changing a state changes the hash and
invalidates every run made against it.

Experiment 1 has 18 cast A run files (6,804 rows), 3 cast B files (972 rows)
and 1 image-on file (486 rows). Experiment 2's main dataset is
`runs/All_conflict.jsonl` at 2,827 rows.

---

## One trap worth knowing before you run anything

`out/` contains `ex1_smoke_gpt_L3.jsonl` and several `*_repair*.jsonl` files.
They land in the same `(model, condition)` bucket as the real runs and
overwrite them, because files are read in alphabetical order. This produced a
wrong published figure that stood for two days.

**Pass run files by name, never by glob.** `ex1_verify_tables.py` hardcodes
the 18 good files for exactly this reason.

---

## Running an episode

Isaac Lab is required for this part only.

```bash
cd fourarm
python3 ycb/run_ycb_sort.py --allocator b1 --layout capability_trap
python3 harvest/probe_store.py   # harvest the trail into a frozen probe set
```

Note that `--allocator b2` wires a retired contention-aware design. The
Hungarian matcher is `--allocator opt`.

---

## Attic

`attic/` holds code that is no longer part of any live path: the abandoned
Experiment 3 trap detector, three superseded milestone tests, the cut
mechanism analysis, and a stale playbook describing the pre-August scope. It
is kept so the lineage of the work stays legible, not because anything imports
it. See `attic/README.md`.

---

## Notes

API keys live in the shell environment and never in the tree. `env/models.env`
carries endpoint configuration only.

Determinism is not comparable across the three models by construction: GPT is
pinned to low reasoning effort, Gemini exposes no temperature control and
cannot disable reasoning, and Qwen is pinned to temperature 0. Self-consistency
is therefore reported per model with its cause rather than compared across
them.
