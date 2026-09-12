# harness/ — 49 regression gates

```bash
make harness          # all of them; non-zero exit if any fails
python3 -B harness/h_ex1_prompts.py    # one of them, with its reasoning printed
```

Each gate is a standalone script that **imports the real module and breaks it
on purpose**. None uses a test framework, none mocks the thing it is testing,
and each prints a sentence per check saying what would go wrong if the check
failed. Run one directly and it reads as an argument, not a pass list.

They exist because this repository has twice had a refactor silently change a
published number. The gates are what stop the third time — and it was the
gates, not a person, that found the run-file rename had broken six of them.

---

## What they cover

### The cell and its physics — 10

| Gate | Holds |
|---|---|
| `h_timing`, `h_timing_table` | The timing model, and `leg_cost` in `cell_config` |
| `h_travel_d1`, `h_leg_travel` | Travel accumulation and the per-task execution window |
| `h_settle_wait` | A round is held only when the cell has actually stopped moving, evidenced by two successive frames agreeing rather than a fixed hold |
| `h_pad_router` | Extracting the pad router did not change the rule allocator's behaviour |
| `h_disruption_fixes` | The seven robustness fixes |
| `h_random_valid` | The zero-knowledge floor |
| `h_frame_rot`, `h_frame_gate` | North-up frame rotation, and the capture gate |

### Validation and state — 7

| Gate | Holds |
|---|---|
| `h_violations` | **Every rejection the validator can produce classifies to a cause.** If one fell through, an unattributed failure would be silently bucketed |
| `h_eligible_arms` | The eligible-arms ablation |
| `h_state_enrich`, `h_condition_v` | The enriched state variant and two-condition prompt construction |
| `h_frozen_coord` | A coordinator rebuilt from a saved state produces the same verdicts as a real episode — tested against an episode, not against expectations, because a shim that misrepresents the cell makes every replayed number wrong in the same direction |
| `h_probe_store`, `h_probe_replay` | Probe sets count legal options correctly and cannot change under replay |

### The data contract — 3

| Gate | Holds |
|---|---|
| `h_run_files` | The manifest agrees with the disk, **and both its guards fire**: it breaks the manifest on purpose with a missing file and a stray `.jsonl` |
| `h_probe_sets` | Every probe set hashes to what it hashed when frozen, the Appendix D derivation reproduces, and **tampering with a state moves the hash** |
| `h_logging_lock` | The frozen logging contract |

### Experiment 1 — 3

| Gate | Holds |
|---|---|
| `h_ex1_prompts` | The rung table encodes exactly one removal per step |
| `h_ex1_mislabel` | The swap renames six objects and changes nothing else — no physical field moves with the name |
| `h_audit_trail` | The VLM consult trail |

### Experiment 2 — 15

`h_ex2_prompts` is the important one: the rungs differ in exactly the intended
way and no rung leaks another's wording. The rest cover the instrument —
`h_ex2_cue`, `h_ex2_grade`, `h_ex2_labels`, `h_ex2_mancheck`, `h_ex2_seecheck`,
`h_ex2_twoway`, `h_ex2_heightcheck`, `h_ex2_visibility`, `h_ex2_transforms`,
`h_ex2_run`, `h_ex2_solo`, `h_ex2_analyse`, `h_ex2_q_common`, `h_ex2_stats`.

`h_ex2_visibility` checks the occlusion measurement reads the block and not the
arm in front of it. `h_ex2_stats` pins the interval estimators the chapter
quotes.

### Models, CLI and reporting — 10

| Gate | Holds |
|---|---|
| `h_model_registry` | An alias resolves to endpoint, model and parameters; **no key value appears in `models.env`**, which ships inside every zip |
| `h_anthropic_client` | The OpenAI-to-Anthropic message translation |
| `h_model_relay` | Proposed-versus-executed reporting |
| `h_cli_names` | Allocator names, auto out-names, and the **live** scene spec: 34 positions, 17 per bank, and the screening claim in `ex2_block.txt`'s header actually verified by running `screen_ex2_block.py` |
| `h_analyze`, `h_input_audit`, `h_trace_state`, `h_buffer_density`, `h_floor_test` | The analysis and diagnostic modules |
| `h_rejections` | Rejected-proposal logging |

`check_columns.py` is a column shakeout that runs anywhere, Isaac-free.

---

## The one that reaches furthest

`h_cli_names` runs `ycb/screen_ex2_block.py` over all 34 scene positions and
requires that **exactly one fail** — `e10`, which sits in the band the oblique
camera occludes. That is the position Chapter 5 excludes as "the block is
hidden behind an arm", and the screen derives it from the reachability rasters
alone, with no model involved. The gate also ties both documented exclusions to
the Q1 inventory: `e02` and `e10`, for the two reasons the chapter gives.

Any *other* position failing the screen means a scene was captured that should
not have been.

---

## Writing a new one

Follow the shape of `h_run_files.py`:

1. Import the **real** module. A gate that tests a copy tests the copy.
2. Check the normal case.
3. **Break it on purpose and check the guard fires**, then restore. A guard
   that cannot fail is not a guard — `make probes` passed a tampered probe set
   for a day because its exit status was being swallowed by a pipe.
4. Print a sentence per check saying what failing would mean.
5. Exit non-zero on any failure.

Gates import from the package root, so run them from the repository root or
through `make harness`.

---

## Two notes

**Six of these were broken for three weeks** and nobody noticed, because the
August run-file rename moved `analysis/` modules without updating the gates
that imported them. They failed with `ImportError`, which looks like an
environment problem rather than a regression. `make harness` is now part of
`make verify`, so a broken gate fails the build.

**A green harness is not a green thesis.** These check the machinery. Whether a
published number is right is `make verify-ex1`, `verify-ex2` and `appendix`,
which check against the thesis itself.
