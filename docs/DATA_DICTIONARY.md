# The data files, field by field

What is in a probe set and a run file, with units, and the definitions that are
easy to get wrong. Every one of the latter was got wrong at least once while
verifying the tables; they are recorded because anyone recomputing a number
will hit the same forks.

---

## A probe set — `probes/*.json`

A frozen collection of decision states. Content-addressed over the identity
fields of every probe, in order: editing one state moves the hash and
invalidates every run made against it.

| Key | Holds |
|---|---|
| `schema`, `n`, `note` | Version, count, free text |
| `hash` | sha256 over the probes' identity fields. `run_files.PROBES` pins the first 16 characters |
| `sources` | Which harvest runs contributed |
| `probes[]` | The states |

Each probe:

| Field | Holds |
|---|---|
| `state` | The cell as the allocator saw it (below) |
| `provenance` | `source`, `seq`, `round`, `allocator`, `layout`, `condition` |
| `derived` | Counts computed at freeze time: `n_idle_arms`, `n_tasks_open`, `n_legal_pairs`, `legal_pairs`, `binding_cause`, `option_set_key` |
| `frame`, `frame_path`, `frames` | The rendered scene image, for VLM allocators |
| `positions_exact` | Object coordinates, for replay |

`state` carries `arms`, `objects`, `tasks`, `baskets`, `exchange_pads`,
`zone_locks`, `zone_inbound`, `reachability`, `table`, `tick`, `metrics`,
`recent_events`, `tasks_completed`, `tasks_failed`.

### `state.arms[]`

| Field | Units |
|---|---|
| `name` | `ur_w`, `ur_e`, `franka_s`, `franka_n` |
| `type` | `ur10` or `franka` |
| `max_grasp_m` | metres. 0.140 UR10, 0.080 Franka |
| `payload_kg` | kilograms. 10 UR10, 3 Franka |
| `delicate_ok` | Franka true, UR10 false |
| `state` | `IDLE` or a phase such as `TO_PLACE` |
| `holding` | Object id, or null |
| `base_xy`, `ee_xy` | metres, table frame: x east, y north, origin at centre |
| `disabled` | A disabled arm is never available, and its body still blocks where it froze |

### `state.objects[]`

| Field | Units |
|---|---|
| `name` | `ycb_`-prefixed. **The registry keys the same objects without the prefix** |
| `grasp_m` | metres, the smallest horizontal extent in the resting pose. The field Experiment 1 withholds |
| `mass_kg` | kilograms |
| `delicate` | Only an arm with `delicate_ok` may take it |
| `category` | Decides the destination basket |
| `xy`, `zone` | Position and quadrant |
| `reach_ok_arms` | **Authoritative for reach.** The prompt says to use it rather than deriving reach from coordinates |
| `at_pad`, `carried_by` | Handover state |

### `state.tasks[]`

`id`, `object`, `dest_xy`, `dest_zone`, `attempts`, and `status` —
`queued`, `in_progress`, or `waiting_on_…` for the second leg of a handover.
Only `queued` may be assigned.

---

## An Experiment 1 run row — `out/ex1_casta_*.jsonl`

One row per trial: one state, one model, one repeat.

| Field | Holds |
|---|---|
| `task_id`, `arm` | The proposal. `task_id` −1 is a decline |
| `result` | `valid`, `rejected`, or `noop`. **Not `outcome`** — that field is Experiment 2's |
| `model_reason` | The model's one-sentence justification. **Not `reason`** |
| `repeat` | 1, 2 or 3 |
| `rung` | `L3`, `L3-anon`, `L3-swap`, `L3-nowidth`, `L1-nowidth`, `L1-swap`, `L2`, `L4` |
| `binding_cause` | Which constraint blocks a rejected pair. A property of the **state**, computed before any model is called |
| `binds_grasp`, `binds_reach`, `binds_delicate`, `binds_payload`, `binds_no_route` | Whether each constraint binds anywhere in this state |
| `violation`, `violation_cause` | Which constraint the model's proposal actually broke. A property of the **reply** |
| `zero_legal` | True when no legal pair exists, so declining is correct |
| `n_legal_pairs` | Legal pairs available |
| `provenance` | `source`, `seq`, `round` — the key back to the probe |
| `probe_set_hash` | Ties the row to the states it was answered on |
| `derived` | The probe's frozen counts, carried through |
| `latency_ms`, `prompt_chars`, `model_alias`, `prompt_version` | Run metadata |

**`binding_cause` and `violation` are different things and collapsing them
destroys the attribution.** The first is a property of the frozen state; the
second is a property of the model's reply.

Reading `reason`/`outcome` instead of `model_reason`/`result` yields `None`
silently. It produced an appendix table with an empty prose column that still
passed a numeric check, because that table's only numbers were identifiers.

---

## An Experiment 2 run row — `runs/ex2_q*.jsonl`

| Field | Holds |
|---|---|
| `arm` | The proposal; null is a wait |
| `outcome` | The verdict. **Experiment 2 uses `outcome` where Experiment 1 uses `result`** |
| `opening_needed_m` | metres, the opening the model judged the object needs |
| `resting_face` | The face the model named |
| `face` | The face the capture actually shows — **ground truth** |
| `declared_pose`, `declared_grasp_m` | What the text said, which the conflict conditions falsify |
| `true_grasp_m` | metres, what the captured face implies |
| `direction` | `permissive` or `restrictive`, naming what the **scene** permits. See the warning in `PROVENANCE_EX2.md` |
| `condition` | `congruent`, `congruent_face`, `dims`, `conflict`, `conflict_face` |
| `rung` | `N0`, `N-A`, `N-C`, `N-order`, `N-D`, `N-CD`, `N-ACD`, `N-BCD`, `N-S`, `X-image`, `X-state` |
| `position`, `seq` | `w00`–`w16`, `e00`–`e16`, and the scene id |
| `modality` | Whether an image was attached |
| `legal_true`, `legal_declared` | Legality under the captured and the declared face |
| `self_contradicted`, `flagged` | Hygiene flags; about 55 rows are filtered |

---

## Definitions that are easy to get wrong

**Legality is proposals accepted over proposals made, on picking states.**
Declines are **not** in the denominator, on either side. This is why trial
denominators differ between cells: a model that declines removes that trial
from the fraction. A scene leaves the scene-level denominator entirely when all
three of its repeats were declines.

**The grasp-binding subset is 122 states, but legality is measured on 96.**
The 122 split into 96 picking and 26 refusal; the 26 are scored by correct
refusal instead. Expecting 122 × 3 gives 366 rows where the real denominator
is 288.

**Scene level uses grasp-binding picking scenes, not all picking scenes.**
Majority over three repeats, then a Wilson interval on the scene count. Using
all 126 picking scenes instead of the 96 moves Gemini's No Width from 71.9 to
78.6.

**Flickering is defined on the raw outcome, not on correctness.** A state
flickers when its three repeats did not return the same result. A state
answered wrongly three times in two different ways — `rejected, rejected,
noop` — is flickering, not stable wrong.

**A decline is recorded as `noop`.** On a picking state it is a wrong answer,
but it is **not** an illegal proposal: it is dropped from the legality
fraction, because legality is over proposals made. It is measured instead by
correct refusal, the mirror measure on the 36 refusal states.

**Reference lines are stored as fractions of 1, not percentages.** Keys are
`uniform/mean` and `width_blind/mean`, and `by_cause/<cause>/…` per subset.

**The pairs column of the binding table partitions; the states column does
not.** Pairs sum to 1196, exactly the rejected pairs, because each carries one
cause. States sum to 392 against 162, because one state can have several
binding constraints.

**Cast A and cast B have different reference lines.** Cast A is chance 30.5,
width-blind 74.9; cast B is 34.6 and 69.2. Take cast B's from
`out/ex1_setb_floors.json`.

**Cast B figures appear at two values and both are right.** 98.8 / 90.1 / gap
8.7 is **trial level**; Table 4.11's 100.0 / 87.5 / +12.5 is the **per-scene
majority**, which is the unit the chapter reports throughout.

---

## Naming, and why nothing is renamed

Data file names appear in the thesis, in the provenance record and in the
verification script. The August 2026 rename was done carefully and recorded
with md5s in `out/RENAME_MANIFEST.json`, but its consumers were never updated —
which is why the verification script, six harness gates and the provenance
document were all stale until this branch.

`run_files.py` is now the single manifest, so a rename means editing one file
and running `make manifest`.

**Never pass run files by glob.** `out/` holds smoke tests, repair runs and
superseded duplicates that fall in the same `(model, condition)` bucket as the
real runs; a glob reads them alphabetically and the last one wins. That put a
wrong figure in the write-up for two days. The manifest also fails if a
`.jsonl` appears that no list accounts for — the check that would have caught
the cast B Anonymous run sitting unread for weeks.
