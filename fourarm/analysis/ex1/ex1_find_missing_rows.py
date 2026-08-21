import json, sys, itertools

def load_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

# --- EDIT THESE to match your actual sweep -------------------------------
# trial_id format observed: {seq}|{condition}|{model}|{preference}|{rung}|{modality}|r{repeat}

SCENES = [
    "p02_A", "p02_B", "p03_A", "p03_B", "p04_A", "p04_B",
    "p05_A", "p05_B", "p07_A", "p07_B", "p08_A", "p08_B",
    "e01_A", "e01_B", "e02_A", "e02_B", "e03_A", "e03_B",
    "e04_A", "e04_B", "e05_A", "e05_B",
]
CONDITIONS = ["congruent", "dims", "conflict"]
MODELS = ["gpt", "qwen", "gemini"]
PREFERENCES = ["franka", "ur"]
RUNGS = ["P0", "P2", "P3", "P4"]
MODALITY = "V"
REPEATS = [1, 2]
# ---------------------------------------------------------------------------

def expected_trial_ids():
    ids = set()
    for seq, cond, model, pref, rung, rep in itertools.product(
        SCENES, CONDITIONS, MODELS, PREFERENCES, RUNGS, REPEATS
    ):
        ids.add(f"{seq}|{cond}|{model}|{pref}|{rung}|{MODALITY}|r{rep}")
    return ids

def main(actual_path):
    rows = load_jsonl(actual_path)
    present_ids = {r["trial_id"] for r in rows if "trial_id" in r}

    expected = expected_trial_ids()
    missing = sorted(expected - present_ids)

    # also split missing by whether the whole (condition, rung) is entirely
    # absent vs just some scenes/repeats within it
    from collections import defaultdict
    by_group = defaultdict(list)
    for tid in missing:
        parts = tid.split("|")
        seq, cond, model, pref, rung, mod, rep = parts
        by_group[(cond, model, pref, rung)].append(tid)

    print(f"Expected total: {len(expected)}")
    print(f"Present in file: {len(present_ids)}")
    print(f"Missing (never attempted): {len(missing)}")

    print("\nMissing broken down by (condition, model, preference, rung):")
    for key, ids in sorted(by_group.items()):
        full_group_size = len(SCENES) * len(REPEATS)
        status = "ENTIRELY MISSING" if len(ids) == full_group_size else f"{len(ids)}/{full_group_size} missing"
        print(f"  {key}: {status}")

    # Per-model summary so you can see at a glance whether gpt/qwen are clean
    # and only gemini + a leftover rung need attention.
    by_model = defaultdict(int)
    for tid in missing:
        model = tid.split("|")[2]
        by_model[model] += 1
    print("\nMissing count by model (across all groups):")
    for model, count in sorted(by_model.items()):
        print(f"  {model}: {count}")

    with open("/home/claude/retry/never_run_trial_ids.txt", "w") as f:
        for tid in missing:
            f.write(tid + "\n")
    print(f"\nWrote {len(missing)} never-run trial_ids to never_run_trial_ids.txt")

if __name__ == "__main__":
    main(sys.argv[1])
