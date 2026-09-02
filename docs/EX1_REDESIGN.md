# Experiment 1 v2: one task at a time

The redesign, in running order, with the commands. Every command assumes you
are in `fourarm/`. The module docstrings remain the authority for options this
guide does not cover.

Nothing here is a change to the published Experiment 1. `experiments/ex1/prompts.py`,
`probes/ex1_v2.json`, `probes/ex1_setb_v1.json` and every file in `out/` are
untouched, and `analysis/ex1/ex1_verify_tables.py` still regenerates the
published tables from them. The v2 code sits beside the v1 code and every run
records which design it was made under.

**Nothing in this guide has been run.** The code is in place and its gates
pass; the episodes, the probe set and the model calls are still to be done.

---

## What changes, and what it buys

| Change | Effect |
|---|---|
| **One task at a time**, so every arm is idle at every decision | both arm types are available at almost every state, so the gripper opening can discriminate far more often. On the v1 set it bound on 96 of 162 states, a 59% share among picking states |
| **Tasks handled in coordinator pool order** | the allocator no longer chooses *which* task. The decision becomes one arm for one named task, which removes task selection as a source of variance and of error |
| **Rules separated per constraint** | the ablation can withhold one constraint at a time instead of the capability rule and the reach rule as a pair |
| **Field names aligned with Experiment 2** | the two chapters describe the same quantity with the same word, which is what makes the cross-chapter comparison legible |

### Why the rerun resolves the pooling objection

A serialised cell draws states from a different distribution than a contended
one, so old and new states cannot be pooled. Because every cell is being rerun,
nothing is pooled and the objection does not apply. The existing runs stay on
disk as the record of the contended design, not as data to combine with the new
ones. `probe_replay` enforces this: `--resume` refuses to append across a design
mismatch, and every row carries `design`.

---

## What must be preserved, and where each one is enforced

| Property | Why it matters | Where it is held |
|---|---|---|
| **The width-blind line** | a bare legality figure means nothing; the chapter reads scores as distances from it | recomputed by `analysis/ex1/ex1_chance_floor.py` on the new set. It is legal / width-blind-legal, and serialising changes the arms surviving every non-grasp check on every state, so the published 74.9% does not transfer |
| **The chance floor** | the uninformed anchor | same script, same run. With one task offered it becomes uniform over *arms* rather than over task-arm pairs, which changes its value |
| **The negative control** | states where the opening binds nothing, at 100% legality, are what localise the width effect to the opening | `--nongrasp-floor` in `analysis/build_ex1_set_v2.py`, declared before any model call and recorded in the set. Five of the eleven objects are 0.080 m or narrower, so the opening can never bind on them |
| **Binding cause fixed before any model call** | it is what makes restricting the endpoint to grasp-binding states a restriction on the state rather than a selection on the outcome | unchanged. `probe_store.probe_from_consult` classifies at harvest, and the stratifier reads that classification rather than recomputing one |
| **No VLM in the source runs** | the set is not shaped by any model's behaviour | unchanged. Harvest with `--allocator random` or `b1` |
| **Correct refusal** | a second endpoint with its own reference line | `--refusal-floor`, and G2 keeps declining licensed in the prompt |

### The refusal endpoint is the second thing at risk, and the redesign spec does not mention it

Under the contended cell a state was zero-legal whenever the arms that
happened to be **free** could not take any open task, and with two arms working
that was common: the published set carries 36 of them in 162, about 22%.
Serialised, a zero-legal state needs the one queued object to be unservable by
**all four arms at once**. No object in the cast is intrinsically unservable,
since the URs cover every width and mass and the Frankas cover every delicate
object, so the only routes left to a refusal state are geometric: an object no
capable arm can reach, or one with no delivery route to any basket.

Those states exist, and `relay_heavy` and `capability_trap` produce them, but
they now have to be harvested deliberately rather than collected as a
by-product. Harvest those layouts to meet `--refusal-floor` rather than
dropping it: a correct-refusal rate computed over no refusal states is not a
weaker measurement, it is no measurement, and §4.3.5 rests on it.

The one at real risk is the negative control. If freeing all arms and
stratifying toward grasp-binding states removed the states where the opening
binds nothing, the control column disappears and the specificity claim becomes
an assertion. The floor is not advisory: `build_ex1_set_v2.py` **fails the
build** when the pool cannot meet it, and says what is missing. Harvest more
episodes rather than lowering a floor after seeing the pool.

---

## Stage 0: check the prompts before anything is spent

No simulator, no model calls.

```bash
python3 -m experiments.ex1.prompts_v2                    # every static check
python3 -m experiments.ex1.prompts_v2 --show nowidth --directive elicit
python3 ../harness/h_ex1_prompts_v2.py                   # the gate
```

The harness pins the design claims: the spine removes one thing per step, no
rule cites another except R6's scope pointer at R7, each `norules` cell moves
exactly one rule block, the withheld text names no state field, no cell states
a size or an extent, the aliases are Experiment 2's by import, and the
serialised coordinator holds the round until every arm is idle.

---

## Stage 1: harvest serialised episodes

Requires Isaac Lab. This is compute and nothing else: no model calls.

```bash
python3 ycb/run_ycb_sort.py --allocator random --layout decision_rich \
    --serialised --record-states --out-name ser_rich
python3 ycb/run_ycb_sort.py --allocator random --layout capability_trap \
    --serialised --record-states --out-name ser_captrap
python3 ycb/run_ycb_sort.py --allocator b1 --layout decision_rich \
    --serialised --record-states --out-name ser_rule
```

`--serialised` makes the coordinator offer a round only when every non-disabled
arm is idle, and offer only the first assignable task in pool order. Generate
generously: selection is the cheap part, and the build fails rather than
compromises if the pool is thin.

`capability_trap` is the layout that produces wide-object states, so it is the
one that feeds the endpoint.

---

## Stage 2: build and freeze the probe set

No model calls.

```bash
python3 analysis/build_ex1_set_v2.py --dry-run --n 200 \
    --trails ser_rich:random:decision_rich \
    --trails ser_captrap:random:capability_trap \
    --trails ser_rule:b1:decision_rich

python3 analysis/build_ex1_set_v2.py --n 200 \
    --trails ser_rich:random:decision_rich \
    --trails ser_captrap:random:capability_trap \
    --trails ser_rule:b1:decision_rich \
    --out probes/ex1_v2_serial.json
```

**Pick the total from the grasp-binding count you want, not from the total.**
The endpoint lives on grasp-binding states and interval width scales as one
over the square root of that count. At an 80% share, 120 states yields roughly
the 96 the published chapter has and 200 yields about 160, which would narrow
the null intervals by about a quarter.

Defaults: `--grasp-target 0.80`, `--nongrasp-floor 0.15`, `--refusal-floor
0.08`, `--seed 0`. All four are recorded in the set's `selection` block
alongside the composition actually achieved, so the file answers "what is this
set made of" without recomputing anything.

The builder refuses a pool whose states are not serialised, and refuses a pool
naming more than one object cast.

---

## Stage 3: recompute the reference lines

No model calls. **Before any model is asked.**

```bash
python3 analysis/ex1/ex1_chance_floor.py --probes probes/ex1_v2_serial.json \
    --out out/ex1_v2_chance_floor.json
```

Read the per-cause block: the grasp subset has its own floor and its own
width-blind line, and that pair is what the primary endpoint is read against.
A pooled floor read against a subset is the wrong comparison.

---

## Stage 4: the knowledge probe

About a hundred calls. The cheapest cell in the project and the one that
changes what the chapter can claim.

```bash
python3 -m experiments.ex1.knowledge_probe --dry-run
python3 -m experiments.ex1.knowledge_probe --model gpt --model qwen \
    --model gemini --repeats 3 --out out/ex1_v2_knowledge.jsonl
python3 -m experiments.ex1.knowledge_probe --summarise out/ex1_v2_knowledge.jsonl
```

It asks each model, outside the allocation task, how wide a gripper must open
for each object. That turns the chapter's central null into a measurement: at
present the chapter can say the models do not recover the opening from the
name, and cannot say whether they could.

Three readings are reported. **`side` is the endpoint**: which side of the
0.080 m Franka aperture the answer falls on, since that binary is all the
allocation decision reads. `band` is the answer within a declared tolerance and
`abs_error` is the strict reading. The two authored widths (drill by the
handle, bowl by the rim) are flagged on every row and reported separately: no
amount of product knowledge recovers a number the registry authored.

---

## Stage 5: the information conditions

The spine. Three models, three repeats, condition A.

```bash
for c in full nowidth anon nowidth-anon swap nowidth-swap givenset; do
  python3 analysis/probe_replay.py --design v2 --rung $c \
      --probes probes/ex1_v2_serial.json --model gpt --repeats 3 \
      --out out/ex1_v2_gpt_$c.jsonl
done
```

`givenset` is reported as a **treatment**, not only as an obedience bound: it
is the cell that says what the model does when the answer is handed to it,
which is what makes a shortfall anywhere else attributable to the reasoning
rather than to the format.

The v1 rung names resolve as aliases (`--rung L3` runs `full`), but the row
records the canonical v2 name so one file never holds both spellings.

---

## Stage 6: the separated rule ablations and the treatments

Last, because they are additions rather than replacements.

```bash
for c in norules-opening norules-load norules-delicate norules-reach; do
  python3 analysis/probe_replay.py --design v2 --rung $c \
      --probes probes/ex1_v2_serial.json --model gpt --repeats 3 \
      --out out/ex1_v2_gpt_$c.jsonl
done

for d in recall report elicit; do
  python3 analysis/probe_replay.py --design v2 --rung nowidth --directive $d \
      --probes probes/ex1_v2_serial.json --model gpt --repeats 3 \
      --out out/ex1_v2_gpt_nowidth_$d.jsonl
done
```

**The recall directive is what licenses the design claim.** "No instruction
repairs a retrieval failure" is an assertion until one instruction has been
tried and failed. It names the source to use, exactly as Experiment 2's
precedence directive does, and it names no number.

**Read `report` and `elicit` as a pair.** `report` asks for the judged opening
before the arm is named; `elicit` additionally asks for the arm to be chosen to
fit it. So `elicit` minus `report` is the instruction to use the number, and
`report` minus plain `nowidth` is the cost of being asked for it at all.
Neither is coherent where the state supplies the opening, and `system_prompt`
refuses those cells rather than rendering a copy instruction under an
elicitation label.

A treatment cell **only needs the grasp-binding states**, since that is where
legality is measured. Running the new cells on that subset alone costs the
negative control for those cells, which is worth declaring where the results
are read.

---

## Cost

Per condition, per model: states times repeats. Three repeats is what the
published design uses and what the intervals need.

| States | Per condition, 3 models x 3 repeats | 10 conditions | 14 conditions |
|---|---|---|---|
| 120 | 1,080 | 10,800 | 15,120 |
| 162 | 1,458 | 14,580 | 20,412 |
| 200 | 1,800 | 18,000 | 25,200 |

Fourteen is the seven information conditions plus the four separated rule
cells plus the three directive cells. The redesign's own estimate counted the
rule ablation as one line and reached ten or eleven; the split is what makes it
fourteen, and the four rule cells are the cheapest to drop if the budget binds,
since only the opening cell is read in the chapter's argument.

Two ways to reduce it without weakening the primary endpoint: run the treatment
cells on the grasp-binding subset alone, and note that the knowledge probe is
**per object, not per state**, so it stays at about a hundred calls whatever
the set size.

---

## What this costs beyond the calls

Tables 4.6 through 4.11 are all recomputed. Cast B is invalidated unless it is
regenerated serialised too. And §3.2's description of the coordinator, the
candidate pairs and the relays no longer matches the cell that produced the
data: Chapter 3 needs a paragraph saying Experiment 1 runs the cell serialised
and why, or the apparatus chapter will describe a system the results did not
come from. That paragraph is in the thesis repository on the same branch.

---

## The one departure from the published design, stated plainly

At `nowidth`, R3 no longer names the withdrawn field.

The v1 module left R3 naming `grasp_m` after the field was removed and called
that the manipulation itself: the model is told which quantity it must supply
and is not given it. Experiment 2 does the opposite in the same situation, on
the argument that a model reading a rule which names a missing field could
reasonably conclude the rule is inapplicable, so a rule-reading failure would
be scored as a retrieval failure.

v2 follows Experiment 2, because the two chapters are meant to be read as one
argument and this is the exact sentence the comparison runs through. The v1
form is kept in the module as `R3_NO_OPENING_V1_STYLE`, so running the other
cell and reporting both is a call-site change rather than a rewrite.

---

## Where each piece lives

| File | What it owns |
|---|---|
| `core/control/tasks.py` | `Coordinator(serialised=True)`: the round gate and the pool-order offer |
| `ycb/run_ycb_sort.py` | `--serialised` |
| `experiments/ex1/prompts_v2.py` | the condition table, the seven rules, the directives, the rendering, and every static check |
| `experiments/ex1/knowledge_probe.py` | the per-object opening probe and its three readings |
| `analysis/build_ex1_set_v2.py` | harvest, serialisation check, stratification, freeze |
| `analysis/probe_replay.py` | `--design v2`, `--directive`, and the per-constraint violation attribution |
| `analysis/ex1/ex1_chance_floor.py` | the reference lines, unchanged and run on the new set |
| `harness/h_ex1_prompts_v2.py` | the gate |

`experiments/ex1/prompts.py` and `harness/h_ex1_prompts.py` are the v1 design
and are unchanged.
