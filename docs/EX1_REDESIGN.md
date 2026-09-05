# Experiment 1 redesign: mass as the memorisation carrier

**Status.** Proposal, not yet accepted. Nothing in `experiments/ex1/`,
`probes/` or `out/` has changed. This document records the argument, the
design, the open decisions and the order of work, so the choice can be made
once and referred back to.

**Scope.** This changes what Experiment 1 measures on its third axis
(object identity) and adds a second manipulated constraint. It does not
change the research question, the validator, the freezing discipline or the
analysis machinery.

---

## 1. Why the current design cannot answer RQ1's third clause

RQ1 asks whether a VLM's legal allocations rest on the physical value, the
stated rule, or object identity. The chapter reports the first as a large
effect and the other two as nulls. The three results are not of equal
quality.

The value axis is sound. Removing the declared grasp width costs Gemini
28.1 points [19.2, 37.8] and GPT 26.3 [16.7, 36.2], landing both near the
74.9 percent width-blind line, and the effect reproduces in direction on
cast B. That result stands and the redesign preserves it.

The identity axis cannot currently be read, for two reasons.

### 1.1 Grasp width is not a property an object can have a prior about

This is the decisive point and it is not yet stated in the chapter.

An object's mass is intrinsic, single-valued and widely published. The YCB
set documents it, and product weights are common in ordinary text. If a
model holds any prior about `ycb_power_drill`, a mass is the kind of thing
that prior can contain.

An object's grasp width is not a property of the object at all. It is
defined in the terms appendix as "the object's width across the axis the
gripper closes on, in its current pose", so it is pose-dependent and
task-defined. A model with a perfect prior over a mustard bottle's
dimensions still cannot state its grasp width without knowing the pose and
then selecting the smaller horizontal extent. That is exactly the two-step
conversion Experiment 2 measures and finds broken: GPT reads the face at
89.2 percent in cue validation, maps a stated face to an opening at 89.6,
and yet converts a face it derived itself on only 65.1 percent of replies
(Table `tab:ex2:q3:face`).

So the identity null on width confounds two worlds the design cannot
separate:

- the model holds no prior about this object, or
- the model holds a prior and cannot convert it into the pose-dependent
  quantity the constraint needs.

A null was close to structurally guaranteed. Swapped Names, the strong
directional form of the test, asked the model to resist a false name in
favour of a number it could not have supplied itself. Nothing was
competing.

### 1.2 The swap had almost nowhere to move

The swap appendix already concedes this. Of 763 open tasks in `ex1_v2`,
275 have no legal arm, 448 have exactly one, and 40 offer a choice of two
or more. On roughly 94 percent of tasks the arm is forced, so a model
following the false name and a model following the true width produce the
same answer. "Gemini remained correct on all 288 grasp-binding trials under
a false name" is therefore weaker evidence than it reads.

### 1.3 The supporting problems

Recorded here because the redesign should fix them in the same pass.

| Problem | Evidence |
|---|---|
| Payload never binds | 0 states, 0 pairs (`tab:ex1:binding`). Heaviest object in either cast is 1.580 kg against a 3 kg Franka limit. |
| Delicacy is confounded with size | The only delicate objects in cast A are the banana (0.039 m) and bowl (0.030 m), the two narrowest. |
| Route contaminates legality | 52 rejected pairs on a constraint about handover routing, not capability. At Full Information, 10 of GPT's 19 violations are route errors. |
| The decline channel is polluted | Every decline reason in the GPT runs cites zones or waiting for an arm. The 2026-08-16 guidance test moved noops from 2.4 to 19.0 percent while changing no capability information. |
| The width effect rests on few objects | `ycb_large_clamp` alone produces 64 of GPT's 121 No Width grasp errors. |

---

## 2. The core change

**Mass carries the identity axis. Width stays, as the control that shows
what happens when no prior is available.**

The two constraints have the same algebraic shape, one declared object
number against one declared arm property, so they are interchangeable as
carriers of the value manipulation. They differ in exactly the property
that matters for the identity manipulation.

| | Grasp width | Mass |
|---|---|---|
| Intrinsic to the object | No, pose-dependent | Yes |
| Single-valued per object | No, one per resting face | Yes |
| Documented in ordinary text | No | Yes, YCB publishes it |
| Requires conversion before use | Yes, pose then smaller extent | No, direct comparison |
| A prior can exist | Not usefully | Yes |

Keeping both makes prior availability an experimental factor rather than an
uncontrolled property of the constraint. The design then reads:

- **No Width** removes a value the model cannot recover from identity.
  Expected result: collapse to the width-blind line, as already measured.
- **No Mass** removes a value the model may be able to recover from
  identity. This is where the memorisation question is actually asked.
- The contrast between them is the finding, whichever way it falls.

This also repairs a weakness in the current generalisation claim. Cast B
reproduces the width effect in direction but not magnitude, 8.7 points
[3.9, 14.3] against 24.0 [18.5, 29.6], and is reported as a partial
success. A second constraint inside the same object set is a stronger
replication than a second object set on the same constraint, and it
supports the sentence the Discussion chapter wants to make, that a
structured capability field is followed rather than checked, which at
present rests on one field.

---

## 3. Prerequisite: the prior probe

**Nothing else in this redesign should be built until this has been run.**
It is the analogue of Experiment 2's cue validation and is load-bearing in
the same three ways: it licenses the interpretation of a null, it selects
what enters the design, and it fixes a parameter that would otherwise be
chosen arbitrarily.

Three probes, run cold with no cell context, on every object in both casts
and every model.

| Probe | Question asked | What it establishes |
|---|---|---|
| **P1 Recall** | What does this object weigh? Give a single number in kg. | Whether a prior exists, and with what precision. |
| **P2 Application** | An arm can lift at most *T* kg. Can it lift this object? Answer yes or no. | Whether the prior converts into a capability verdict. A separate step, and on Experiment 2's evidence the step that breaks. |
| **P3 Use** | The No Mass allocation condition itself. | Whether a prior that exists and converts is actually deployed under task load. |

Cost is roughly 21 objects by 3 models by 3 repeats by 2 probes, about 380
calls for P1 and P2 together.

### 3.1 What the probe decides

**Whether the rebuild is worth doing.** If P1 shows the models cannot place
these objects within a useful tolerance, the identity axis is answered
without a rebuild. The chapter then reports a validated null: there was no
memorised source competing with the declared value. That is a reportable
finding rather than an uninterpretable one, and the existing runs stand with
the probe attached as validation.

**Which objects enter the swap.** Experiment 2 dropped the `edge` face after
cue validation showed GPT could not separate it from `large_face` at better
than chance. The same discipline applies here: run the swap only on objects
all three models place correctly, and report the excluded ones.

**Where the payload threshold goes.** See the next section.

---

## 4. The payload threshold

This is the one genuine obstacle and it needs a decision.

The registered object set spans 0.004 kg (`bracket_small`) to 1.580 kg
(`wood_block`) across 21 distinct objects. The Franka payload limit is 3 kg,
which is why payload binds nowhere. For mass to bind, the threshold has to
move into the object range.

### 4.1 Threshold placement is set by measured prior precision

A model that knows a mustard bottle weighs "about half a kilo" can answer a
threshold at 0.30 kg and cannot answer one at 0.49 kg. So the threshold must
sit in a gap wide enough for the precision P1 actually measures. The rule
is: place it so every object's true mass is further from the threshold than
the model's measured recall error for that object.

Sorted masses of the 21 distinct objects, in kg:

```
0.004 bracket_small    0.194 foam_brick      0.514 sugar_box
0.010 screw_99         0.236 banana          0.586 mac_n_cheese
0.060 t_connector      0.349 soup_can        0.603 mustard
0.121 scissors         0.358 large_clamp     0.670 bowl
0.156 caster           0.407 meat_can        0.964 bleach
0.176 gelatin_box      0.493 mug             1.216 power_drill
0.177 tuna_can         0.493 mug2            1.580 wood_block
```

Two candidate placements, both to be confirmed against P1:

- **0.30 kg.** Twelve objects over, nine under. Nearest margins 0.064 below
  (banana) and 0.049 above (soup can).
- **0.45 kg.** Nine over, twelve under. Nearest margins 0.043 either side
  (meat can, mug).

0.30 kg is the safer of the two on margins and is the current
recommendation, subject to P1.

### 4.2 Justifying a limit below the arm's rating

A Franka Panda is rated at 3 kg at the flange. A cell limit of 0.30 kg is
well below that and must be stated rather than implied. Three options:

1. **Declare a cell task-payload limit.** The cell configures a limit below
   the mechanical rating, which is ordinary practice once gripper mass,
   speed and reach at extension are accounted for. Stated in the prompt, in
   the chapter and in the limitations. *Recommended.* It changes a declared
   cell parameter, not a physical asset, and Experiment 1 is a
   decision-level evaluation over frozen states in which the declared state
   is what the validator and the model both read.
2. **Add heavier assets.** Physically honest, but it needs simulation work,
   and any object added outside YCB has no documented mass for a model to
   have a prior about, which defeats the purpose.
3. **Drop payload from the validator.** Cheapest and honest, but it forfeits
   the redesign and leaves the constraints table listing a constraint that
   binds nowhere, which is the first thing a viva will find.

Option 1 carries one cost that belongs in the limitations: an unusual
threshold is itself something a model has no prior about, so P2 tests the
comparison rather than the convention. That is a reason to state the limit
prominently in the prompt, which the design already does.

---

## 5. The decision task

The current task offers 1 to 11 queued tasks and 1 to 4 idle arms, a median
of eight candidate pairs. Experiment 2 offers one task and a determinate
binary, and that is where its power comes from. Import it.

| Change | Reason |
|---|---|
| One queued task per state | Removes task selection as a competing degree of freedom. |
| Destination pre-assigned | R7 and basket choice stop firing, so sorting guidance cannot move the answer. |
| Exactly one idle UR and one idle Franka | Every trial becomes a binary with a known correct answer. |
| Guidance prefers the Franka | Without a preference a UR is legal everywhere and the arm named carries no information. This is what makes Franka share a measure rather than a description. |
| No pads, no handover | Removes the route constraint, which contributed 52 rejected pairs and 10 of GPT's 19 baseline violations without being a capability failure. |
| No zones in state or prompt | The 2026-08-16 record shows zone guidance driving 19 percent of noops with no capability information changed. |
| Wait permitted only when no idle arm is capable | Makes a decline mean one thing, so correct refusal sits on a clean denominator. |

The resulting decision table, matching the form of `tab:ex2:decision`:

| Franka capable | UR capable | Expected allocation |
|---|---|---|
| yes | yes | Franka |
| yes | no | Franka |
| no | yes | UR |
| no | no | wait |

### 5.1 The prompt

Adopt the Experiment 2 structure from the Experiment 2 prompt appendix.
Sections in the order THE CELL, WHAT THE STATE TELLS YOU, the object
glossary, HARD RULES, GUIDANCE, YOUR ANSWER. One constraint per rule with
its own heading, so R3 opening, R4 load, R5 delicate, R6 reach. The
Experiment 2 alias set, so each constraint is a visibly matched pair:
`mass_kg` against `max_load_kg`, `opening_needed_m` against
`opening_max_m`. No `resting_face` and no `size_upright_m`, since
Experiment 1 states the opening directly and the face manipulation belongs
to Experiment 2.

Splitting the rules has a second payoff. No Rules currently withholds R3 and
R4 together, and R3 bundles grasp, payload and delicacy into one sentence,
so a null covers four checks at once. With the rules split, the condition
becomes four attributable contrasts.

---

## 6. The conditions

Two value factors crossed with three identity levels, plus the existing
controls. The identity levels are unchanged in form; what changes is that
they now act on a constraint that can carry a prior.

| Condition | Mass | Width | Identity | Answers |
|---|---|---|---|---|
| Full Information | given | given | true | the ceiling |
| Anonymous | given | given | withheld | does removing the name cost anything |
| Swapped Names | given | given | false | does a false name move the answer |
| No Mass | withheld | given | true | is the mass recovered from identity |
| No Mass + Anon. | withheld | given | withheld | the same with no name to recover from |
| No Mass + Swapped | withheld | given | false | the directional test, where it can bite |
| No Width | given | withheld | true | the no-prior control, replicating the existing result |
| No Width + Anon. | given | withheld | withheld | as above with the name removed |
| No Rules (four cells) | given | given | true | one rule withheld at a time |
| Legal-Arm Control | given | given | true | the obedience ceiling |

The swap for the mass conditions relabels across the payload threshold
rather than the aperture, under the same three constraints
`experiments/ex1/mislabel.py` already enforces: straddle the threshold,
category-matched, and no delicate objects. Objects that fail P1 are excluded
and reported.

Running all of these at three repeats is a large sweep. Section 11 gives an
order that lets it be stopped early.

---

## 7. Measures and reference lines

Unchanged in kind: legality on states where the manipulated constraint
binds, correct refusal on states with no legal arm, Franka share as the
attribution measure, outcome consistency across repeats, scene majority as
the unit of analysis, Wilson intervals for rates and Newcombe for contrasts.

Three additions.

**A mass-blind line.** The exact analogue of the width-blind line: the score
of an allocator applying every constraint except the payload comparison and
then choosing uniformly among the arms that remain. Computed the same way,
by raising both arms' payload limits so the constraint cannot bind and
re-running the deployed validator, so it reuses the real validator and
restates no rule.

**A prior-consistent line.** New, and the reason the redesign is worth
doing. It is the score of an allocator that answers No Mass using each
model's own P1 recall value in place of the withheld field. A model landing
on this line has fallen back on its prior. A model landing on the mass-blind
line has not. These two lines are what turn the identity axis from a null
into a measurement, and they are only computable because P1 was run.

**Equal repeats at every condition.** No Rules and Legal-Arm Control ran at
one repeat while the crossed conditions ran at three, so the controls cannot
be read through the scene-majority convention the rest of the chapter uses.
Three everywhere.

---

## 8. Predictions

Written before the run so this is a test rather than an exploration. The
design is well posed under every outcome, which is the point.

| Outcome at No Mass | Reading |
|---|---|
| Falls to the mass-blind line, as width does | Models do not deploy priors even where priors exist. The calibration finding generalises and strengthens: removing a field produces a default regardless of whether a fallback was available. |
| Lands on the prior-consistent line | Models fall back on parametric knowledge when it exists. The width null is then explained as absence of a usable prior rather than as indifference to identity, and RQ1's third clause is answered positively. |
| Falls between the two | Partial reliance, reported as a proportion with the two lines bracketing it. More informative than either endpoint. |

| Outcome at No Mass + Swapped | Reading |
|---|---|
| Franka share moves toward the false name | Identity retrieval, the positive result the title asks about. |
| No movement, with P1 confirming the prior exists | The model resisted a misleading cue it demonstrably holds, which is stronger evidence of grounding than the current removal null. |
| No movement, with P1 showing no prior | The object should not have been in the swap set. Excluded and reported. |

---

## 9. What is preserved and what is superseded

**Preserved.** The rung table and its no-defaulting discipline, the guarded
substitution in `withhold_rules`, `state_at_rung` in
`analysis/probe_replay.py`, `anonymise.py` and its leak assertions,
`mislabel.py` and its three swap constraints, the report, the verification
harness, content addressing, and the rule that the validator never sees the
edit.

**Superseded.** The `ex1_v2` and `ex1_setb_v1` probe sets, since the
decision task changes shape. The 24 cast A and 6 cast B run files built on
them. The chapter tables that read from those files.

**Reproduced rather than lost.** The width effect, the calibration
signatures and the Legal-Arm Control ceiling should all reappear, and more
cleanly, once route rejections and zone-driven declines leave the
denominators.

---

## 10. Open decisions

1. **The payload limit.** Section 4.2, options 1 to 3. Recommendation is
   option 1, a declared cell task limit at 0.30 kg subject to P1.
2. **Whether to keep the harvested set.** Designed states weaken the
   offline-equals-deployed argument. The thesis has already made this trade
   once: Experiment 2 uses purpose-built matched pairs and the system
   chapter says so. Recommendation is two tiers, a designed balanced set as
   the primary instrument and a harvested set retained as a secondary
   ecological check, which is structurally what cast A and cast B already
   are.
3. **Whether to keep delicacy as a third carrier.** It has the right shape,
   a boolean against a boolean, and a plausible prior, but it is currently
   confounded with object size and would need the cast rebalanced to cross
   the two. Recommendation is to defer it and state the confound.
4. **Scale.** Ten conditions at three repeats across three models is a large
   sweep. Section 11 orders the work so it can be stopped after any stage.

---

## 11. Order of work

Each stage is a decision point. Stop after any of them and the work to that
point still reports something.

1. **P1 and P2, both casts, all three models.** About 380 calls. Decides
   whether the rest is worth doing and fixes the payload threshold. If the
   priors are not there, write the validated null, attach the probe to the
   existing chapter as validation, and stop.
2. **Prompt rewrite and harness update.** Split rules, adopt the Experiment
   2 aliases, remove zones and pads, restrict the wait licence. Extend
   `harness/h_ex1_prompts.py` to cover the split rules, the new wait wording
   and the new alias leak list. No model calls.
3. **New state generator and probe set.** Balanced across constraint, margin
   and identity level. Report per-constraint binding counts before freezing,
   then content-hash and freeze.
4. **Full Information, No Mass, No Width, three models, three repeats.** The
   core result, read against the mass-blind, width-blind and
   prior-consistent lines.
5. **The identity levels and the four No Rules cells**, in that order, since
   the identity axis is the one the title rests on.
6. **Legal-Arm Control at three repeats**, so the controls are readable
   through the same scene-majority convention as everything else.
