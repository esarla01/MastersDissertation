# Experiment Playbook (E1-E6 per the scope PDF)

One block per experiment: what it needs, the exact command, and what to
run afterwards. Repetitions per the agreed statistics: 2 per cell for
deterministic columns (physics jitter bound), 3-5 for VLM columns
(model stochasticity). Seeds: dev 0-4 shakeout only; EXPERIMENT seeds
100-104. Identical worlds across columns per seed. Every claim about a
VLM column is provenance-conditioned (dest_by / arm_by).

Universal gates before ANY experiment block:
  md5sum -c MANIFEST_v1.txt
  python3 experiments/cubes/run_sorting_demo.py --headless    # 8/8
  PROMPT FREEZE: prompts must not change after the first E-episode.

Analysis after any block:
  python3 analysis/episode_metrics.py out/ep_*.json --csv out/metrics.csv
  python3 analysis/episode_trace.py out/<any episode>.json

## E1: overall comparison (RQ1). READY once seeded gates pass.

Prerequisite: seeded-layout hang fixed + sampler route-existence
validation (build queue item 3; py-spy evidence pending).

  python3 run_experiment.py --seeds 100 101 102 103 104 \
      --allocators b1 b2 --layout seeded --profiles none --reps 2
  python3 run_experiment.py --seeds 100 101 102 103 104 \
      --allocators vlm1 vlm2 --layout seeded --profiles none --reps 3

Cells: 5 seeds x (2 columns x 2 reps + 2 columns x 3 reps) = 50
episodes, ~7 h classical-light, VLM dominated (~50 min/seed).
Metrics: M1-M3 (episode_metrics.py). Expect near-parity on easy instances
(structural contention floor); that is a finding, not a failure.

## E2: capability scarcity (RQ2). NEEDS scenario generator (queue 4).

Capability-preserving relocation across seeds; specialist preservation.
Metrics M2-M5. Command once the generator exists:
  python3 run_experiment.py --seeds <e2 seeds> --allocators b1 b2 vlm1 vlm2 \
      --layout seeded --profiles none --reps 2   # 3-5 for vlm columns

## E3: relay reasoning (RQ3). NEEDS relay-fraction mix control (queue 4).

Ground truth from the reachability model (episode_metrics.py M6/M7 already
compute precision/recall from spawn_xy + rasters). Metrics M2, M6, M7.

## E4: temporal coordination (RQ4). NEEDS congestion timing variation
(queue 4). Metrics M2, M8, M9. NOTE: M9 (pad waiting) needs the pad-wait
counter added to the episode JSON first; flagged in episode_metrics.py.

## E5: disruption recovery (RQ5). NEEDS degraded-gripper type (queue 5).

Normal operation, then persistent disruption for the rest of the
episode. Metrics M2, M10-M12. Existing profiles none|mixed run today:
  python3 run_experiment.py --seeds 100 101 --allocators b1 b2 vlm1 vlm2 \
      --profiles mixed --reps 2

## E6: contribution of vision (RQ6). NEEDS anomaly prop spawner (queue 6)
plus a PASSING perception floor test first:

  python3 analysis/ex2_perception_floor.py out/<vlm2 stem>_frames/consult_*.png

Text vs Text+Image on scenes whose structured state INTENTIONALLY omits
camera-visible information; the anomaly is absent from the text in BOTH
conditions; control cells must show Text == Text+Image (no-confound
proof). Metrics M1-M3, M8-M12 under incompleteness; keep
anomaly-consistent-decision rate + time-to-adapt as diagnostics from the
decision logs.

## Reporting rules (all experiments)

Means + ranges per cell; paired per-seed comparisons; proportions with
95% CIs for E6; effect sizes over p-values; no significance claims from
single runs; contention reported as excess over the per-seed structural
floor (analysis/episode_verify_contention.py); never oversell (an 11/11 under
guard is the guard working, not the model).
