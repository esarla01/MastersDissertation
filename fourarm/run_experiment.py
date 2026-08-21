"""Matrix runner: seeds x allocators x disruption profiles x repetitions.

Each cell of the matrix is one run_ycb_sort.py subprocess writing one
episode JSON with a deterministic name, so the runner is RESUMABLE: a
job whose JSON already exists is skipped. Videos are off by default
(pass --record to keep them). Wall-clock is dominated by VLM episodes
(~10 min each); the runner prints the job list and an estimate before
starting and after each episode.

Usage examples:
  python3 run_experiment.py --seeds 0 1 2 --allocators b1 b2 \
      --profiles none mixed --reps 2
  python3 run_experiment.py --seeds 0 --allocators vlm1 vlm2 --reps 3
"""

import argparse
import itertools
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "ycb"))
from cli_names import CLI_CHOICES, normalize_allocator   # noqa: E402

OUT_DIR = "out"
EST_MIN = {"rule": 2.0, "opt": 2.0, "vlm": 10.0}   # keyed by allocator KIND


def job_name(seed, alloc, profile, rep):
    return f"ep_s{seed}_{alloc}_{profile}_r{rep}.json"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, nargs="+", default=[0])
    p.add_argument("--settle-wait", type=int, default=0,
                   help="passed through to the runner; 0 is OFF")
    p.add_argument("--settle-phases", default="tight",
                   choices=["tight", "broad"],
                   help="passed through to the runner")
    p.add_argument("--allocators", nargs="+", default=["b1", "b2"],
                   choices=CLI_CHOICES,
                   help="b1 rule, b2 Hungarian, vlm1 Text, vlm2 Text+Image "
                        "(oracle/opt accepted as legacy aliases)")
    p.add_argument("--profiles", nargs="+", default=["none"])
    p.add_argument("--reps", type=int, default=1,
                   help="repetitions per cell (use more for vlm)")
    p.add_argument("--layout", default="seeded",
                   help="layout mode passed through (seeded/designed)")
    p.add_argument("--record", action="store_true")
    p.add_argument("--max-ticks", type=int, default=12000)
    p.add_argument("--dry", action="store_true",
                   help="print the job list and estimate, run nothing")
    p.add_argument("--timeout-factor", type=float, default=3.0,
                   help="per-job timeout = estimate x this factor")
    p.add_argument("--heartbeat", type=int, default=30,
                   help="seconds between progress lines while a job runs")
    a = p.parse_args()

    # Normalize aliases once; job names and estimates use canonical names.
    normalized = [normalize_allocator(x) for x in a.allocators]
    # dedupe after normalization (e.g. "b1 oracle" is one column, not two)
    a.allocators = list(dict.fromkeys(short for short, _, _ in normalized))
    kinds = {short: kind for short, kind, _ in normalized}
    if (any(k == "vlm" for k in kinds.values())
            and not os.environ.get("DASHSCOPE_API_KEY")):
        sys.exit("DASHSCOPE_API_KEY is not set but a vlm column is in "
                 "the matrix")

    jobs = []
    for seed, alloc, prof, rep in itertools.product(
            a.seeds, a.allocators, a.profiles, range(a.reps)):
        name = job_name(seed, alloc, prof, rep)
        done = os.path.exists(os.path.join(OUT_DIR, name))
        jobs.append((seed, alloc, prof, rep, name, done))

    todo = [j for j in jobs if not j[5]]
    est = sum(EST_MIN[kinds[j[1]]] for j in todo)
    print(f"[matrix] {len(jobs)} jobs total, {len(jobs)-len(todo)} already "
          f"done, {len(todo)} to run, estimated {est:.0f} min wall-clock")
    for j in jobs:
        print(f"  {'DONE' if j[5] else 'todo'}  {j[4]}")
    if a.dry or not todo:
        return

    t0 = time.time()
    results = []
    for i, (seed, alloc, prof, rep, name, _) in enumerate(todo, 1):
        cmd = [sys.executable, "ycb/run_ycb_sort.py", "--headless",
               "--seed", str(seed), "--allocator", alloc,
               "--layout", a.layout, "--disruptions", prof,
               "--max-ticks", str(a.max_ticks), "--out-name", name]
        if a.record:
            cmd.append("--record")
        if a.settle_wait:
            # Only appended when non-zero, so a default matrix run produces
            # exactly the command line it produced before this flag existed.
            cmd += ["--settle-wait", str(a.settle_wait),
                    "--settle-phases", a.settle_phases]
        log = os.path.join(OUT_DIR, name.replace(".json", ".log"))
        # Per-job timeout: 3x the estimate (the seeded-layout hang gate:
        # a wedged episode dies loudly instead of eating the night).
        timeout_s = EST_MIN[kinds[alloc]] * 60 * a.timeout_factor
        print(f"[matrix] ({i}/{len(todo)}) {name} -> {log} "
              f"(timeout {timeout_s/60:.0f} min)", flush=True)
        os.makedirs(OUT_DIR, exist_ok=True)
        job_t0 = time.time()
        with open(log, "w") as lf:
            proc = subprocess.Popen(cmd, stdout=lf,
                                    stderr=subprocess.STDOUT)
            rc = None
            while rc is None:
                try:
                    rc = proc.wait(timeout=a.heartbeat)
                except subprocess.TimeoutExpired:
                    el = time.time() - job_t0
                    if el > timeout_s:
                        proc.kill()
                        proc.wait()
                        rc = "TIMEOUT"
                        break
                    # heartbeat: elapsed + the child's last log line
                    last = ""
                    try:
                        with open(log) as f:
                            lines = f.read().strip().splitlines()
                            last = lines[-1][-100:] if lines else ""
                    except OSError:
                        pass
                    print(f"[matrix]   ... {el/60:5.1f} min  {last}",
                          flush=True)
        jpath = os.path.join(OUT_DIR, name)
        verdict = None
        if os.path.exists(jpath):
            try:
                with open(jpath) as f:
                    verdict = (json.load(f).get("meta") or {}).get("verdict")
            except (OSError, json.JSONDecodeError):
                verdict = "UNREADABLE"
        status = (verdict or ("TIMEOUT" if rc == "TIMEOUT" else "NO-JSON"))
        results.append((name, status, rc, (time.time() - job_t0) / 60))
        print(f"[matrix]   {status}  rc={rc}  "
              f"{(time.time()-job_t0)/60:.1f} min  "
              f"total {(time.time()-t0)/60:.1f} min", flush=True)

    print(f"\n[matrix] SUMMARY ({(time.time()-t0)/60:.1f} min total)")
    for name, status, rc, mins in results:
        print(f"  {status:>8s}  {mins:5.1f} min  {name}")
    bad = [r for r in results if r[1] not in ("PASS",)]
    print(f"[matrix] {len(results)-len(bad)}/{len(results)} PASS"
          + (f"; attention: {[r[0] for r in bad]}" if bad else ""))


if __name__ == "__main__":
    main()
