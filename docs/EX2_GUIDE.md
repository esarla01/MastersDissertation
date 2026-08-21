# Experiment 2: cue conflict and grounding

The pipeline in running order, with the commands that were used. Every command
assumes you are in `fourarm/`. The instructions here are consolidated from the
module docstrings, which remain the authority for options this guide does not
cover.

Prompt version: `2026-08-07e`. Main dataset: `runs/All_conflict.jsonl`, 2,827
rows across three models, seven rungs, 22 scenes and three repeats. Chats cite
2,772 usable rows, so roughly 55 are filtered in hygiene.

---

## Stage 0: capture the scenes

Requires Isaac Lab. Skip this unless you are building a new scene set.

```bash
python3 ycb/capture_ex2_scene.py          # writes into out/ex2_capture/
```

Scene lists: `ycb/ex2_scenes.txt`, `ycb/ex2_east.txt`, `ycb/ex2_west.txt`.

---

## Stage 1 to 3: build the trials

These modules are imported by the runners rather than invoked directly.

| Step | Module | Does |
|---|---|---|
| 1 | `experiments/ex2/labels.py` | Pose-neutral object labels |
| 2 | `experiments/ex2/transforms.py` | The three state transforms |
| 3 | `experiments/ex2/prompts.py` | The attention rungs and the justification schema |

---

## Stage 4: run

Always dry-run first. It renders the trials without spending a model call.

```bash
# smallest runnable form: three conditions, one prompt, one view
python3 -m experiments.ex2.cue --dry-run
python3 -m experiments.ex2.cue --out runs/ex2_cue.jsonl --repeats 3

# the main runner
python3 -m experiments.ex2.run --probes out/ex2_capture --dry-run
python3 -m experiments.ex2.run --probes out/ex2_capture \
    --model qwen --limit 12 --out runs/ex2_smoke.jsonl

# the solo design: one queued task, one arm, counterbalanced preference
python3 -m experiments.ex2.solo --dry-run
python3 -m experiments.ex2.solo --out runs/ex2_solo.jsonl --repeats 3
```

**Flag trap.** `--models` takes a comma list. `--condition`, `--rung`,
`--preference` and `--modality` all append. Mixing the two conventions
silently halved one run.

---

## Stage 5: grade and rescore

`experiments/ex2/grade.py` is invoked by the runners. To re-grade an existing
run with the self-contradiction detector:

```bash
python3 -m experiments.ex2.rescore --run runs/ex2_solo.jsonl \
    --probes out/ex2_capture
```

---

## Stage 6: analyse

```bash
# the four diagnostic views, from one instrument
python3 -m experiments.ex2.analyse --run runs/All_conflict.jsonl --view odd
python3 -m experiments.ex2.analyse --run runs/All_conflict.jsonl --view stable
python3 -m experiments.ex2.analyse --run runs/All_conflict.jsonl \
    --probes out/ex2_capture --view reason --model qwen --rung P3

# the eight-step conflict analysis
python3 experiments/ex2/analyse_conflict.py runs/All_conflict.jsonl

# independent cross-check of the legality table
python3 experiments/ex2/verify_legality.py runs/All_conflict.jsonl

# the dimension-only condition
python3 analysis/ex2_analyse_dims.py runs/piece_dims_P2.jsonl
```

**Run `--view extract` before quoting any width-derived number.** Three
successive extractor rules each failed on an unseen sentence shape and
produced a false finding before being caught. Every extraction fault returns
0.080 or 0.140, the two gripper apertures rather than an object width, so that
is the diagnostic tell.

**The dims file is `runs/piece_dims_P2.jsonl`**, 1,759 rows, with
`runs/piece_dims_P2_ur.jsonl` at 396 rows for the UR preference. Some earlier
notes name a `piece_dims_P2-2.jsonl`, which does not exist in this tree. Pair
scenes are filtered via `r['seq'][0] in ('p','e')`.

---

## Instrument validation

| File | Checks |
|---|---|
| `runs/ex2_cue.jsonl` | Cue validation |
| `runs/ex2_mancheck.jsonl`, `runs/ex2_mancheck_gpt.jsonl` | Can the model read pose when asked about nothing else |
| `runs/ex2_seecheck.jsonl` | What the model says it sees, alongside the pose it names |
| `runs/ex2_floor*.jsonl` | Perception floor |

```bash
python3 -m experiments.ex2.mancheck --probes out/ex2_capture \
    --model qwen --out runs/ex2_mancheck.jsonl
python3 -m experiments.ex2.seecheck --probes out/ex2_capture \
    --model qwen --out runs/ex2_seecheck.jsonl
```

---

## Analysis discipline

Carried forward because each rule exists because something went wrong once.

- Prefer the physical infeasibility column over outcome labels for conflict
  trials. It is unaffected by the width extractor and by the grader's
  uninformative classification.
- Per-scene majority is the unit of analysis. 33 trials per cell are 11 scenes
  by 3 repeats, not 33 independent observations.
- Preserve binding cause against violation type. Binding cause is a property of
  the frozen state, computed before any model call. Violation type is a
  property of the model's reply.
- Wilson 95% for proportions, Newcombe 95% for differences. Flag any interval
  that spans zero.
- Never merge two files into one report bucket. Pass files explicitly.

---

## Superseded run files

`A_conflict_gemini.jsonl`, `A_conflict_noimage_P4.jsonl`, `A0_textonly.jsonl`,
`B_baseline*.jsonl` and `C_all_r2.jsonl` use an earlier condition-A/B/C naming
and are superseded by `All_conflict.jsonl`. They are retained for provenance.
The nine `ex2_solo*.jsonl` files are development and pilot runs of the solo
design.
