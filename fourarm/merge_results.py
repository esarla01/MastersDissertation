import json, sys

def load_jsonl(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def main(out_path, *input_paths):
    # Later files in input_paths win on conflicting trial_ids, so pass your
    # original good rows first, then leftover gpt/qwen, then the gemini
    # retry file last.
    by_id = {}
    n_replaced = 0
    n_new = 0
    for path in input_paths:
        rows = load_jsonl(path)
        for r in rows:
            tid = r["trial_id"]
            if tid in by_id:
                n_replaced += 1
            else:
                n_new += 1
            by_id[tid] = r

    still_failed = [tid for tid, r in by_id.items()
                    if r.get("outcome") == "unparseable" or r.get("error")]

    with open(out_path, "w") as f:
        for r in by_id.values():
            f.write(json.dumps(r) + "\n")

    print(f"Merged {len(by_id)} total rows -> {out_path}")
    print(f"  filled in from failed state: {n_replaced}")
    print(f"  new trial_ids added: {n_new}")
    print(f"  still failing after retry: {len(still_failed)}")
    if still_failed:
        print("  (these may need another backoff pass or manual check)")
        for tid in still_failed[:20]:
            print(f"    {tid}")

if __name__ == "__main__":
    # usage: python3 merge_results.py <out_path> <file1> <file2> ... <fileN>
    main(sys.argv[1], *sys.argv[2:])
