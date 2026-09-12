# probes/ — the frozen decision states

The input to both experiments. Each file is a collection of decision points
lifted out of an episode's audit trail, carrying everything needed to re-render
the prompt and re-run the real validator without a simulator.

**Content-addressed.** The hash covers the identity fields of every probe, in
order. Edit one state and the hash moves, invalidating every run made against
it — which is the point: a run file only means something paired with the states
it answered.

| File | States | Hash (first 16) | Role |
|---|---|---|---|
| `ex1_v2.json` | 162 | `e23cd23479778f76` | **Cast A, the reported set** |
| `ex1_setb_v1.json` | 108 | `b8abfb3391dd6d52` | **Cast B, the generalisation check** |
| `ex1_v1.json` | 185 | `d8c9b796173f0c6f` | Pre-refreeze; still carries `seed_v3` |
| `master_v1.json` | 278 | `2b53744f433a866e` | Everything harvested, before deduplication |
| `setb_master_v1.json` | 118 | `dc0e07aa4eaa86d5` | The cast B master |
| `ex1_v2_tablecam.json` | 162 | `e23cd23479778f76` | `ex1_v2`'s states under the table camera. Same hash: the image is not an identity field |
| `seed_v3.json` | 29 | `468293e8afeac654` | **Excluded.** Predates the mustard width correction |
| `ex3_v1.json` | 135 | `047eb6b3fb2d9c7c` | Harvested, never used |
| `ex3_setb_v1.json` | 72 | `c5451710996cd3d9` | Harvested, never used |

## The chain, as Appendix D describes it

278 harvested → deduplicate to one state per distinct option set → **185** (a
loss of 93) → refreeze without `seed_v3` → **162**.

`seed_v3` went because it predates a correction to the mustard bottle's
declared grasp width, 0.058 → 0.096 m. Twenty-three of its 29 states had
survived deduplication into `ex1_v1`; none reaches `ex1_v2`. Since grasp is the
constraint both experiments manipulate, a stale width there would bias the
measurement rather than merely add noise.

## Verifying

```bash
make probes
```

Checks every hash, recomputes the chain against Appendix D, confirms no
`seed_v3` state leaks into the reported set, and checks the six per-source
counts in Table D.1. `harness/h_probe_sets.py` additionally tampers with a
state to confirm the hash actually moves.

The two unused `ex3_*` sets are audited too, so "unused" stays a recorded
decision rather than an oversight.

## Not renamed, not moved

Their names appear in the thesis, in the provenance record and in
`run_files.py`. `docs/SIMULATION.md` covers how a set is made;
`docs/DATA_DICTIONARY.md` covers what is in one.
