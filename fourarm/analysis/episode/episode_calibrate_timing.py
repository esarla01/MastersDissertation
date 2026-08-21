"""Fit the timing model's coefficients from per-TASK execution windows.

    moving_ticks = ticks_per_m * travel_leg_m + fixed_ticks

fitted separately for "ur10" and "franka", where for each completed task

    moving_ticks = (done_tick - exec_start_tick) - blocked_ticks
    travel_leg_m = metres that arm covered inside that window

WHY THIS REPLACES THE PER-ARM FIT (2026-07-29). The previous version
regressed per-EPISODE productive ticks on per-EPISODE travel. Those two
described different spans: travel accumulated across the whole run,
including folding and drift that belongs to no task, while productive ticks
covered only claim..done. The regression buried the difference in its
constants, travel and leg count were nearly proportional within each arm
type so the split was barely identifiable, and the fitted UR coefficient
implied an end-effector speed of 6.3 m/s, which is not physical.

Three things fix it, and all three are needed:

  1. travel_leg_m is measured inside the same window as the ticks, so
     predictor and target describe the same span.
  2. blocked_ticks is SUBTRACTED. An arm waiting for a zone lock is not
     moving slowly, it is standing still. One episode had a task at 270
     ticks/m that fell to 115 once its 428 blocked ticks were removed,
     in line with every other task that arm ran.
  3. One row per TASK rather than per arm-episode, so distances vary
     properly and the intercept is identifiable.

HOLD THE ARM. Coefficients are a property of the arm, not the task: the
same task assigned to a UR and to a Franka gets two different costs. That
is the heterogeneity the study exists to measure.

WHAT THIS MODEL DOES NOT COVER. The window ends at done_tick, which is
stamped on arrival home, so it spans approach + carry + retreat + travel
home. It excludes the fold (PRE_TUCK + SETTLING) that runs before the arm
reports IDLE, measured at roughly 75 ticks for a UR and 180 for a Franka.
If the cost model is ever extended to "when is the arm free" rather than
"when is the task done", that constant belongs there and must be fitted
separately from arm_idle events.

  python3 analysis/episode/episode_calibrate_timing.py out/*.json

READ THE DIAGNOSTICS. The tool refuses to print a paste-ready block when a
coefficient is non-positive, when a fit rests on too few tasks, or when the
implied end-effector speed falls outside a plausible physical band. Those
guards exist because the previous fit passed R2 0.99 while being wrong.
"""
import argparse
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.cell import cell_config as C                        # noqa: E402

# An EE speed outside this band means the fit is describing something other
# than motion. Wide on purpose: it is a sanity gate, not a prior.
SPEED_MIN_MS, SPEED_MAX_MS = 0.15, 4.0


def rows_from(path):
    """One row per completed task carrying a per-task execution window."""
    ep = json.load(open(path))
    out, skipped = [], 0
    for t in ep.get("tasks", []) or []:
        arm = t.get("arm")
        span_end, span_start = t.get("done_tick"), t.get("exec_start_tick")
        travel = t.get("travel_leg_m")
        if arm is None or travel is None or span_end is None or span_start is None:
            skipped += 1
            continue
        spec = C.ARMS.get(arm)
        if spec is None:
            skipped += 1
            continue
        moving = (span_end - span_start) - (t.get("blocked_ticks") or 0)
        if moving <= 0 or travel <= 0.05:      # degenerate, not informative
            skipped += 1
            continue
        out.append({"episode": os.path.basename(path), "task": t.get("id"),
                    "object": t.get("object"), "arm": arm,
                    "type": spec["type"], "travel_m": float(travel),
                    "moving": int(moving),
                    "blocked": int(t.get("blocked_ticks") or 0)})
    return out, skipped


def ols(rows):
    """Least squares for moving = a * travel + b. Returns (a, b) or None."""
    n = len(rows)
    if n < 3:
        return None, f"need at least 3 tasks; got {n}"
    mx = sum(r["travel_m"] for r in rows) / n
    my = sum(r["moving"] for r in rows) / n
    sxx = sum((r["travel_m"] - mx) ** 2 for r in rows)
    if sxx < 1e-6:
        return None, ("every task covered the same distance, so the slope "
                      "and intercept cannot be separated")
    sxy = sum((r["travel_m"] - mx) * (r["moving"] - my) for r in rows)
    a = sxy / sxx
    return (a, my - a * mx), None


def diagnose(rows, a, b):
    pred = [a * r["travel_m"] + b for r in rows]
    obs = [r["moving"] for r in rows]
    mean = sum(obs) / len(obs)
    ss_res = sum((o - p) ** 2 for o, p in zip(obs, pred))
    ss_tot = sum((o - mean) ** 2 for o in obs)
    r2 = (1 - ss_res / ss_tot) if ss_tot > 1e-9 else None
    resid = [o - p for o, p in zip(obs, pred)]
    sd = statistics.pstdev(resid) if len(resid) > 1 else 0.0
    return r2, resid, sd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="+")
    ap.add_argument("--min-tasks", type=int, default=8,
                    help="refuse to publish a coefficient fitted on fewer "
                         "tasks than this (default 8)")
    ap.add_argument("--show-outliers", type=int, default=5,
                    help="how many worst-residual tasks to list per type")
    a = ap.parse_args()

    paths = []
    for pat in a.episodes:
        paths.extend(sorted(glob.glob(pat)) or [pat])

    rows, skipped = [], 0
    for p in paths:
        got, sk = rows_from(p)
        rows.extend(got)
        skipped += sk

    if not rows:
        print("No usable tasks. Episodes need the per-task execution window "
              "(exec_start_tick, travel_leg_m, blocked_ticks). Re-run after "
              "installing the instrumentation.")
        return 2

    print(f"\n{len(rows)} completed tasks from {len(paths)} episodes "
          f"({skipped} skipped: no window, or degenerate)\n")

    table, usable = {}, True
    for typ in sorted({r["type"] for r in rows}):
        sub = [r for r in rows if r["type"] == typ]
        coef, err = ols(sub)
        print("=" * 70)
        print(f"{typ}   {len(sub)} tasks")
        print("=" * 70)
        if coef is None:
            print(f"  NOT IDENTIFIABLE: {err}")
            usable = False
            continue
        p, q = coef
        r2, resid, sd = diagnose(sub, p, q)
        speed = (1.0 / (p * C.SIM_DT)) if p > 0 else float("nan")
        print(f"  ticks_per_m  {p:9.1f}   ({p * C.SIM_DT:5.2f} s/m"
              f"  = {speed:4.2f} m/s)")
        print(f"  fixed_ticks  {q:9.1f}   ({q * C.SIM_DT:5.2f} s per task)")
        print(f"  R2           {('%9.3f' % r2) if r2 is not None else '      n/a'}"
              f"   residual sd {sd:.0f} ticks")

        if p <= 0 or q <= 0:
            print("  WARNING a coefficient is <= 0; the linear model does "
                  "not hold on this data.")
            usable = False
        if not (SPEED_MIN_MS <= speed <= SPEED_MAX_MS):
            print(f"  WARNING implied EE speed {speed:.2f} m/s is outside "
                  f"[{SPEED_MIN_MS}, {SPEED_MAX_MS}]; the fit is describing "
                  f"something other than motion.")
            usable = False
        if len(sub) < a.min_tasks:
            print(f"  WARNING fitted on {len(sub)} tasks, below --min-tasks "
                  f"{a.min_tasks}.")
            usable = False

        worst = sorted(zip(sub, resid), key=lambda z: -abs(z[1]))[:a.show_outliers]
        print(f"\n  {'worst residuals':<22}{'travel':>8}{'moving':>8}"
              f"{'blocked':>9}{'resid':>8}")
        for r, e in worst:
            tag = f"{r['episode'][:14]}#{r['task']}"
            print(f"  {tag:<22}{r['travel_m']:>8.2f}{r['moving']:>8}"
                  f"{r['blocked']:>9}{e:>8.0f}")
        table[typ] = (p, q)
        print()

    if len(table) >= 2:
        types = sorted(table)
        ratio = table[types[0]][0] / table[types[1]][0]
        print(f"RELATIVE SPEED  a {types[0]} metre costs {ratio:.2f}x "
              f"a {types[1]} metre.\n")

    print("=" * 70)
    print("PASTE INTO cell_config.py" if usable else
          "NOT READY TO PASTE (see warnings above)")
    print("=" * 70)
    print("TIMING = {")
    for typ in sorted(table):
        p, q = table[typ]
        print(f'    "{typ}": {{"ticks_per_m": {p:.1f}, '
              f'"fixed_ticks": {q:.1f}}},')
    print("}")
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(main())
