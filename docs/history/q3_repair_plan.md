# Q3 Repair: locked plan

Recorded 2026-09-04. Supersedes the "Q3 Remediation" ladder analysis.

Section opens with: each configuration repairs one step, and what it teaches is
not that the step could be repaired but what its repair reveals about why the
step failed.

## Design

Steps 1 and 2 each get two treatments, one supplying a fact, one changing how
the model is asked. Elicitation is the schema, not a treatment. Step 3 needs
nothing.

|                                  | Supply the fact          | Change how it is asked   |
| -------------------------------- | ------------------------ | ------------------------ |
| **Step 1**, read the face        | Description, new         | Attention, already run   |
| **Step 2**, face to opening      | Derivation, already run  | Staged report, new       |

Crop was a second step-1 "change how it is asked" treatment. Dropped on
2026-09-04: not realistic in the time available, and the cell is already filled
by Attention.

## Runs

| # | Condition        | Rung                    | Models      | Repeats | Trials |
| - | ---------------- | ----------------------- | ----------- | ------- | ------ |
| 1 | `dims`           | `N-D` + staged report   | GPT, Claude | 3       | 384    |
| 2 | `dims`           | `N-CD` + description    | GPT, Claude | 3       | 384    |
| 4 | `congruent_face` | `N-CD`                  | GPT, Claude | 1       | 128    |
| 5 | `dims`           | `N-CD`                  | GPT, Claude | 1       | 128    |

About 1,024 calls. Runs 4 and 5 are controls, not treatments.

## Wordings

**Staged report.** State the resting face, then the two horizontal extents of
that face, then the required opening, before naming an arm.

NAME: called "Extents" in the original plan. Renamed because `dims_frame` in
`prompts.py` already has a level called `extents`, which is a state-text
rendering and a different thing. Two meanings for one word in one chapter is
not survivable.

**Description.** The block is resting on one of two faces. They measure
0.130 m by 0.100 m (the larger) and 0.100 m by 0.050 m (the smaller).

## Measures

| Run | Quantity                | Baseline to beat                     |
| --- | ----------------------- | ------------------------------------ |
| 1   | conversion rate         | 65.1 per cent, GPT at `N-D`          |
| 2   | face accuracy, then Δ   | 66.1 per cent and 32.3, GPT at `N-CD`|
| 4   | Δ, must reach about 89  | proves the measurement works         |
| 5   | Δ, must reproduce 32.3 and 0.0 | proves the models have not drifted |

## Predictions, committed before the first call

- Staged report fixes conversion: GPT knew the rule and was not applying it.
  Flat: the rule was genuinely missing.
- Description moves reading: the model lacked a description of what to look for.
- Both move: two separate losses, and the sizes divide them.
- Neither moves while run 4 jumps: reading inside the task is beyond
  instruction. Strongest claim available.

## Build list

1. Two rung blocks and one answer schema in `prompts.py`, plus an exemption in
   the checks assertion for the description block, which names extents by
   design.
2. Scoring for the staged-report fields.
3. `predictions.md`, committed before the first call.
4. Model versions, temperature and seeds matched to the original runs and
   recorded.

Dropped with the crop: the cropped image set and the `image_set` column.

## Limitations

Reported faces are declarations, and their order in the output does not prove
the order of computation. Conversion is measured only on replies that named the
face correctly, so it is noisier where reading is worst.
