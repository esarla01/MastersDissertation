# experiments/ — what the model is actually asked

The prompt modules. Each experiment varies one thing about the same frozen
state, and these are the authority for what that variation is.

## ex1/ — the information ladder

| Module | Does |
|---|---|
| `prompts.py` | `RUNGS` defines the eight conditions and the four rule bodies R3 and R4 select between. Backs Tables 4.4, 4.5, B.1 and B.2 |
| `mislabel.py` | The name swap. `SWAP_PAIRS` backs Table A.2 |
| `anonymise.py` | Identity removed from the state |

The manipulations are **state edits, not prompt rewrites**. One template
renders every condition, so a condition cannot accidentally differ in wording
as well as in content. `h_ex1_prompts.py` holds that the rung table encodes
exactly one removal per step.

A swap pair qualifies only when three things hold at once: the objects straddle
the Franka aperture, neither is delicate, and they share a category. Only the
name moves — `grasp_m`, `mass_kg`, `delicate`, category, zone and
`reach_ok_arms` all stay with the true object, so **the correct answer does not
move**. `h_ex1_mislabel.py` holds exactly that.

## ex2/ — cue conflict

`prompts.py` is the substantial one: the base prompt, the three factors, the
rungs, and `FIELD_ALIASES`.

The aliases are load-bearing. Every field is renamed before the model sees it,
so each constraint arrives as a visibly matched pair — `opening_needed_m`
against `opening_max_m`, `mass_kg` against `max_load_kg` — and the direction of
the comparison is readable from the names alone. `pose` becomes `resting_face`
because a posture label could be read off as an outcome where a geometric name
cannot. `FIELD_ALIASES` backs Table C.1.

Five assertions run **before any trial** and raise rather than warn:

1. The glossary names exactly the fields the state carries.
2. R3 never points at a field the state withholds.
3. The template states no derivation relation above the anchor.
4. The configurations are isolated — each rung is the base plus its own block.
5. The candidate faces carry no pose.

Together they mean a failed derivation is a failed derivation, not a
comprehension puzzle the prompt accidentally set.

The rest of the directory is the instrument: `run.py` turns captured scenes
into trials, `grade.py` scores a reply against measured geometry,
`visibility.py` checks the flip object is actually visible in the render, and
`cue.py`, `mancheck.py`, `seecheck.py`, `twoway.py`, `heightcheck.py` are the
probes that validate the cue before anything is spent on it.

`docs/EX2_GUIDE.md` has the pipeline in running order.

## Spending money

Nothing here calls a model on import. The notebooks drive these modules, and a
paid cell refuses to run unless `CONFIRM_SPEND` equals the call count it has
just printed. `make spend-check` fails if that value is ever committed.

## Changing something here

`RUNGS` and `FIELD_ALIASES` back published tables, so `make appendix` fails if
they drift from what the thesis prints. `make harness` covers the rest.
