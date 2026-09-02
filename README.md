# Grounded or Memorised?

Code and data for *Grounded or Memorised? A Decision-Level Evaluation of
Capability Reasoning and Judgement in VLM Task Allocation for a Heterogeneous
Four-Arm Cell* (MSc, Imperial College London).

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
the analysis, only to harvest new states.

```bash
cd fourarm
python3 analysis/ex1/ex1_verify_tables.py
```

That regenerates every table in the Experiment 1 chapter from the raw data
and diffs it against the published values. It uses only the standard library,
so it is an independent check on `analysis/ex1/ex1_report.py` rather than a re-run
of it. Exit status is 0 when everything passes.

Expected output ends with `264/264 checks passed`.

See [`docs/TABLE_PROVENANCE.md`](docs/TABLE_PROVENANCE.md) for what each table
reports, which files it comes from, and the definitions that are easy to get
wrong.

---

## Layout

```
.
├── README.md
├── docs/                     how to reproduce each experiment
│   ├── TABLE_PROVENANCE.md   Experiment 1 tables, sources, commands
│   ├── EX1_REDESIGN.md       Experiment 1 v2, the serialised redesign
│   └── EX2_GUIDE.md          Experiment 2 pipeline, in running order
├── harness/                  regression gates, one per subsystem
├── attic/                    superseded code, kept for provenance only
└── fourarm/                  the package
    ├── core/                 cell, control and decision layers
    ├── experiments/          ex1/ and ex2/ prompt and runner modules
    ├── analysis/             harvest, replay, scoring, reporting
    │   ├── ex1/ ex2/         one directory per experiment
    │   ├── episode/ cell/    pre-reframe episode tools, cell geometry
    │   ├── retired/          dead, kept for one import
    │   └── *.py              shared infrastructure, imported by the rest
    ├── ycb/                  scene assembly and the episode runner
    ├── instrumentation/      episode logging and recording
    ├── probes/               frozen, content-hashed decision states
    ├── out/                  Experiment 1 run files (see out/README.md)
    └── runs/                 Experiment 2 run files, plus the EX1 image cell
```

`out/` holds Experiment 1 results and `runs/` holds Experiment 2 results. The
one exception is the Experiment 1 image-on cell, `runs/ex1_L1-nowidth_V_gpt.jsonl`,
which sits with the Experiment 2 files for historical reasons.

---

## Finding your way around

Four README files carry the map. Each sits next to what it describes.

| File | Answers |
|---|---|
| `docs/TABLE_PROVENANCE.md` | Where does each published number come from, and how do I check it |
| `fourarm/analysis/README.md` | What is each script for, which are shared, which belong to which experiment |
| `fourarm/out/README.md` | What do the Experiment 1 run filenames mean, which must never be used |
| `fourarm/runs/README.md` | The same for Experiment 2 |
| `docs/EX2_GUIDE.md` | How do I run the Experiment 2 pipeline end to end |
| `docs/EX1_REDESIGN.md` | The Experiment 1 v2 redesign: what changes, what must be preserved, and the pipeline in running order |

Scripts in `analysis/` are grouped by scope into `ex1/`, `ex2/`, `episode/`
for pre-reframe episode tools used by no reported result, `cell/` for
geometry, and `retired/` for dead code. Shared infrastructure that other
modules import stays at the top of `analysis/`. Run every script from
`fourarm/`, as in the command above, not from its own directory.

**Data files are never renamed.** Their names appear in the thesis, in the
provenance record and in the verification script, so a rename would break the
trail from a published number to the data behind it. The README in each data
directory does the decoding instead.

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

The Experiment 1 v2 set is not in this table because it has not been built
yet. When it is, it is a separate file with its own hash: serialised states
and contended states cannot be pooled, so no v2 run is comparable with any
row above.

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
python3 analysis/probe_store.py   # harvest the trail into a frozen probe set
```

Note that `--allocator b2` wires a retired contention-aware design. The
Hungarian matcher is `--allocator opt`.

`--serialised` runs the cell ONE TASK AT A TIME: a round is offered only when
every arm is idle, and only the first assignable task in pool order is offered.
That is the Experiment 1 v2 harvesting mode, and it costs makespan and makes
every contention measure vacuous, so it is never used for Experiment 3. See
[`docs/EX1_REDESIGN.md`](docs/EX1_REDESIGN.md).

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
