# instrumentation/ — observation without influence

Three modules that watch an episode and change nothing about it.

| Module | Does |
|---|---|
| `episode_logger.py` | One machine-readable JSON file per run. This is the audit trail probe sets are built from |
| `recorder.py` | Saves the overhead camera to a video during a run |

The contract is frozen and `harness/h_logging_lock.py` holds it, because the
trail's shape is what `harvest/probe_store.py` reads. A field renamed here
silently changes what can be harvested later.

Nothing here decides anything. An illegal assignment is logged as made and
judged afterwards by the validator, never corrected in flight, so the trail is
faithful to what was actually decided.

`docs/SIMULATION.md` puts this in the pipeline.
