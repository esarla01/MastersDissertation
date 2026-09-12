# From a clean checkout to every number

For how the pieces fit together rather than how to check them, read
`docs/WALKTHROUGH.md` first.

```bash
make setup      # .venv from requirements.lock, once
make verify     # every check, offline, non-zero exit on any mismatch
```

Expected output:

```
== spend gates ==        no cell arms the spend gate
== run-file manifest ==  audit: clean
== probe sets ==         probe audit: clean
== Experiment 1 ==       303/303 checks passed
                         ex1_reproduce_tables.ipynb: 13 of 13 tables regenerated
== Experiment 2 ==       q1, q2, q3_remediation, q3_repair ok
== appendix tables ==    13 of 13 appendix tables
== harness ==            49 passed, 0 failed
all checks passed
```

Around four minutes, almost all of it executing notebooks. No simulator, no
network, no API key. `make verify` passes with networking disabled, which is
the real proof the reproduce path never calls a model.

`make setup` was exercised from empty on 11 September 2026: a fresh venv built
from `requirements.lock` runs the notebooks and reports 13 of 13. The lock is a
plain freeze of the environment the tables were rebuilt in — 94 packages,
Python 3.13.7 — not a hash-pinned install.

Individual targets: `make probes`, `make verify-ex1`, `make verify-ex2`,
`make appendix`, `make harness`, `make manifest`, `make spend-check`.

---

## What each check establishes

| Target | Establishes |
|---|---|
| `spend-check` | No notebook cell carries a filled-in `CONFIRM_SPEND`. Committing one turns Run All into a paid sweep; six cells reached git that way |
| `manifest` | Every published run file is present and holds what it claims — row count, rung, probe-set hash — and nothing sits in `out/` or `runs/` that no list accounts for |
| `probes` | All nine probe sets still hash to what they hashed when frozen, and the 278 → 185 → 162 derivation reproduces Appendix D |
| `verify-ex1` | Tables 4.1–4.11, F.1 and G.1, by two independent routes (see below) |
| `verify-ex2` | Tables 5.6–5.14: 216 checks against the emitted CSVs, and the transcribed constants checked against the thesis LaTeX |
| `appendix` | Tables 3.1, 3.2, **5.2**, A.1, A.2, B.1, B.2, C.1, D.1, E.1–E.4 |
| `harness` | 49 regression gates over the cell, the allocators, the prompts and the analysis helpers |

Experiment 1 is checked twice on purpose. `ex1_verify_tables.py` recomputes
everything with the standard library alone; `ex1_reproduce_tables.ipynb`
computes from the probe sets and the deployed validator. They share
`run_files.py` — the list of which files to read — and nothing else. **If they
ever disagree, the disagreement is the finding.**

---

## The thesis source

The notebooks check each generated table against the thesis LaTeX, read from
`THESIS_REPO` (default `~/Desktop/msc-paper`). That tree is not in this
repository, so each notebook also carries `thesis_expected.json`: a committed
copy of the numeric tokens and body text every table held when the thesis was
last read.

| | Behaviour |
|---|---|
| Thesis present | It is authoritative; the vendored copy is checked against it |
| Thesis absent | All tables still check, against the vendored copy |
| Both, disagreeing | **Fails.** A stale vendored copy would let a notebook pass against a number the thesis no longer prints |

Refresh sections write the vendored file, and only when the thesis was
readable — a run that fell back to the vendored copy cannot refresh it, which
would be the file certifying itself. When the thesis changes, re-run with
`THESIS_REPO` set and commit the result.

**A numeric check cannot see a wrong text column.** Tables whose only numbers
are identifiers — E.4's task ids and repeat counts, for instance — can pass
the token comparison with a prose column empty. Those cells assert their text
fields directly. See `notebooks/appendix/README.md`.

---

## What cannot be re-run

Three regimes, and only the first is reproducible in the strict sense.

**Analysis is deterministic.** Pure functions over frozen files. This is what
`make verify` guarantees.

**Harvesting is deterministic but needs Isaac Lab.**
`core/decision/random_allocator.py` seeds its RNG on `(episode seed, sorted
idle arms, ready set)` rather than a call counter, so replaying a state
reproduces the choice. `docs/SIMULATION.md` covers the path.

**Model calls are not reproducible, by construction.** Section 5.3.1.4 of the
thesis says so: runs were not seeded, and two of the three providers expose no
temperature control. GPT varies through test-time reasoning, Gemini's reasoning
cannot be disabled, and Qwen at temperature 0 still shows serving
nondeterminism — it agreed on 14 of 15 states in a repeat check.

The run files are therefore **the primary record, not a cache**. Re-collecting
produces a new dataset, not a reproduction of this one. Every notebook prints a
provenance table with each input's sha256 and row count, and the manifest
audit fails if one changes.

The same applies to the probe sets. Freezing them is what removes the induced
state distribution problem — two models run live never meet the same states —
so re-harvesting would give a different and equally valid set, and would
invalidate every run made against the old one. That is what the content hash
is for.

---

## Costs, if you do re-collect

Paid cells are inert unless `CONFIRM_SPEND` is set to the exact call count the
cell has just printed, and the value must never be committed. Each such cell
prints its own cost line first: scenes × models × repeats. Experiment 2's
ladder is 612 calls per condition at three repeats; the Q3 remediation cells
are 1836 and 2448.

Keys come from the environment, or from `env/keys.local.env`, which is
gitignored. `env/models.env` carries endpoint configuration only and is
checked by the harness to hold no key value, because it ships inside every zip.

---

## If something fails

| Symptom | Cause |
|---|---|
| `0 of 13 tables regenerated` | `THESIS_REPO` unset *and* `thesis_expected.json` missing |
| `the vendored copy disagrees with the thesis` | The thesis changed; re-run the refresh section with `THESIS_REPO` set and commit |
| `on disk but in no list` | A `.jsonl` appeared that no manifest mentions. Add it to `run_files.EXCLUDED` with a reason, or to the published lists |
| `hash is …, manifest says …` | A probe set was edited. Every run made against it is invalid |
| `ARMED SPEND GATE` | A `CONFIRM_SPEND` value was committed. Set it back to `None` |
| A stale `.pyc` serving old code | `make clean`. `CONFIRM_SPEND = None` and `= 1836` are both four characters, so an edit can leave size and mtime-second identical — the pair Python's bytecode cache validates on. Every target sets `PYTHONDONTWRITEBYTECODE` |
