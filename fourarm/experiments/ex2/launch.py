"""Run several EX2 sweeps at once, one OS process each, then pool them.

WHY PROCESSES, AND WHY NOT NOTEBOOK CELLS. A notebook has one kernel and
that kernel runs one cell at a time, so three model cells queue rather than
overlap: the wall-clock is the same as one cell doing all three, while
looking like they ran together. Parallelism has to come from separate
processes.

WHY NOT THREADS INSIDE solo.run(). Because nothing in solo.py changes this
way. The run loop, trial_id, the resume set and the write-then-flush that
makes a paid run crash-safe are all exactly as they were, so the code that
produced the results already on disk is the code that produces the rest.
That is worth more than the extra throughput a thread pool would give.

WHAT IT DOES NOT BUY. One process per model is a ceiling of one process per
model. Within a single model's sweep the calls are still sequential. Three
models over 68 scene-conditions goes from about 35 minutes to about 12, not
to 4. To go further, give each process a disjoint slice of the scenes with
`pair=` and its own file; the same launcher runs that without changing.

ONE FILE PER PROCESS, ALWAYS. Three processes appending to one jsonl
interleave partial lines and corrupt it. Each job therefore gets its own
out_path, and pooling happens at read time in combine(), which dedupes on
trial_id exactly as solo.run() does at its close. A crash in one model's
run then costs only that model.

Usage from a notebook:

    from experiments.ex2 import launch as L

    jobs = L.per_model(("gpt", "gemini", "claude"),
                       capture_dir=str(CAPTURES), out_dir=RUNS, tag="ndX",
                       conditions=("dims",), rungs=("N-D",),
                       dims_frames=("extents",))
    handles = L.start(jobs)          # returns at once, nothing blocks

    rows = L.combine(handles)        # later cell: waits, pools, prints

Usage from a shell is the same thing without the notebook:

    python3 -m experiments.ex2.launch --demo
"""

import argparse
import inspect
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parent.parent.parent                      # .../fourarm
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KEYS_FILE = ROOT / "env" / "keys.local.env"


def load_keys(path=KEYS_FILE):
    """Read KEY=value lines into the environment without overwriting.

    The registry deliberately never reads a key from a file it ships, and
    that stays true: this is the separate, gitignored keys file that
    notebook Cell 0 already loads. A worker started from a plain shell does
    not inherit Cell 0's environment, so it loads the file itself and works
    either way. setdefault, so an export still wins.
    """
    if not path or not os.path.exists(path):
        return None
    for raw in open(path):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)
    return str(path)


# ---------------------------------------------------------------------------
# Building jobs
# ---------------------------------------------------------------------------

def per_model(models, capture_dir, out_dir, tag, **kw):
    """One job per model, each with its own output file and log.

    Every other keyword is passed straight to solo.run(), so this supports
    the whole signature including face_orders and dims_frames. Nothing is
    translated through a CLI flag, which is what keeps the launcher from
    going stale every time solo.run() grows a factor -- the argparse block
    in solo.main() still has no --dims-frame, and this does not care.
    """
    out_dir = pathlib.Path(out_dir)
    jobs = []
    for model in models:
        stem = "ex2_%s_%s" % (tag, model)
        jobs.append({"name": model,
                     "kwargs": dict(kw, capture_dir=str(capture_dir),
                                    models=(model,),
                                    out_path=str(out_dir / (stem + ".jsonl"))),
                     "log": str(out_dir / (stem + ".log"))})
    return jobs


# ---------------------------------------------------------------------------
# Starting and waiting
# ---------------------------------------------------------------------------

def start(jobs, python=None):
    """Spawn one process per job and return at once.

    Each process re-enters THIS module with --worker and a JSON blob, which
    calls solo.run(**kwargs) in that process. Passing kwargs as JSON rather
    than as command-line flags is deliberate: solo.run() takes tuples and
    booleans and grows new factors, and a flag layer would have to be
    updated in step with it or silently drop one.
    """
    python = python or sys.executable
    handles = []
    for job in jobs:
        pathlib.Path(job["log"]).parent.mkdir(parents=True, exist_ok=True)
        log = open(job["log"], "w")
        # Interleaved stdout from N processes is unreadable, so each one
        # gets its own log and combine() surfaces the tail.
        proc = subprocess.Popen(
            [python, "-u", str(HERE), "--worker", json.dumps(job["kwargs"])],
            cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ))
        handles.append(dict(job, proc=proc, log_handle=log))
        print("started %-8s pid %-7d -> %s"
              % (job["name"], proc.pid, job["kwargs"]["out_path"]))
    return handles


def poll(handles):
    """One line per job: running, or its exit code. Never blocks."""
    for h in handles:
        code = h["proc"].poll()
        rows = 0
        p = h["kwargs"]["out_path"]
        if os.path.exists(p):
            with open(p) as f:
                rows = sum(1 for line in f if line.strip())
        print("%-8s %-9s rows=%-5d %s"
              % (h["name"], "running" if code is None else "exit %d" % code,
                 rows, p))
    return all(h["proc"].poll() is not None for h in handles)


def wait(handles, tick=10.0, quiet=False):
    """Block until every job has exited. Returns the failed ones."""
    while not all(h["proc"].poll() is not None for h in handles):
        if not quiet:
            poll(handles)
            print("-" * 60)
        time.sleep(tick)
    for h in handles:
        h["log_handle"].close()
    bad = [h for h in handles if h["proc"].returncode != 0]
    for h in bad:
        print("\n%s FAILED (exit %d), last lines of %s:"
              % (h["name"], h["proc"].returncode, h["log"]))
        with open(h["log"]) as f:
            for line in f.readlines()[-15:]:
                print("   " + line.rstrip())
    return bad


# ---------------------------------------------------------------------------
# Pooling
# ---------------------------------------------------------------------------

def combine(handles_or_paths, report=True):
    """Pool every job's rows into one list, newest row per trial_id.

    Same rule solo.run() applies to its own file at the end of a run: read
    everything, key on trial_id, later wins. Across models a collision
    cannot happen anyway, because the alias is part of the id.
    """
    paths = [h["kwargs"]["out_path"] if isinstance(h, dict) else h
             for h in handles_or_paths]
    seen, per_file = {}, []
    for p in paths:
        n = 0
        if os.path.exists(p):
            for line in open(p):
                if line.strip():
                    r = json.loads(line)
                    seen[r.get("trial_id")] = r
                    n += 1
        per_file.append((p, n))
    rows = list(seen.values())
    if report:
        from experiments.ex2 import solo as S
        for p, n in per_file:
            print("%6d rows  %s" % (n, p))
        print("%6d pooled, %d unique trial_id" % (sum(n for _, n in per_file),
                                                  len(rows)))
        errs = sum(1 for r in rows if r.get("error"))
        if errs:
            print("%6d of them carry an error. A rate-limited run looks "
                  "like a finished one until you read this line." % errs)
        print()
        print(S.table(rows))
        print()
        print(S.cost_table(rows))
    return rows


# ---------------------------------------------------------------------------
# Worker entry point
# ---------------------------------------------------------------------------

def _worker(blob):
    load_keys()
    from experiments.ex2 import solo as S
    kw = json.loads(blob)
    # Fail on the kwargs themselves rather than deep inside run(). A name
    # solo.run() does not take is a typo in the launcher call, and finding
    # it after the first paid call would be finding it too late.
    known = set(inspect.signature(S.run).parameters)
    unknown = sorted(set(kw) - known)
    if unknown:
        raise SystemExit(
            "solo.run() takes no %s. Known parameters: %s"
            % (", ".join(repr(u) for u in unknown), sorted(known)))
    # JSON has no tuples, and solo.run() indexes and multiplies these.
    for k in ("models", "conditions", "preferences", "rungs", "modalities",
              "face_orders", "dims_frames"):
        if k in kw and kw[k] is not None:
            kw[k] = tuple(kw[k])
    S.run(**kw)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--worker", default=None,
                    help="internal: JSON kwargs for one solo.run()")
    ap.add_argument("--demo", action="store_true",
                    help="dry-run three jobs to show the shape, no calls")
    a = ap.parse_args(argv)
    if a.worker:
        return _worker(a.worker)
    if a.demo:
        jobs = per_model(("gpt", "gemini", "claude"),
                         capture_dir="out/ex2_capture_block",
                         out_dir=ROOT / "runs", tag="demo",
                         conditions=("dims",), rungs=("N-D",),
                         dims_frames=("extents",), dry_run=True)
        for j in jobs:
            print(json.dumps(j, indent=1))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
