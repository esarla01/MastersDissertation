# Experiment 1 files that are not results

Kept because a paid run is never thrown away. None of these is a result and nothing in the thesis cites any of them. The reason each one cannot be used is stated rather than implied.

The cast-B single-repeat runs are NOT here. They were filed here by mistake on 21 August and moved back to `out/`. They are independent runs at the same prompt version and their trials exist nowhere else.

- `ex1_casta_gemini_norules_r3_DUPLICATE.jsonl`
  byte-identical (md5) to the live three-repeat file. The extension was resumed in place instead of into a copy, so both names held the same 486 rows.
- `ex1_casta_gemini_nowidth_PARTIAL_repair.jsonl`
  133 retry-diagnostic rows from ex1_repair_failures.py. result and ex1_prompt_version are null and the schema is attempt1_*/history, so these are not result rows at all.
- `ex1_casta_gpt_full_SMOKE.jsonl`
  10 rows at prompt version 2026-08-15b, all ten states covered by the live run at a later version. A smoke test, never a result.
- `ex1_casta_gpt_full_r1_SUPERSEDED.jsonl`
  prompt version 2026-08-15b against 2026-08-16b in the live run, so it cannot be pooled with it. Not a repeat-count question.
- `ex1_casta_gpt_norules_r1_SUPERSEDED.jsonl`
  prompt version 2026-08-16b against 2026-08-19a in the live run, so it cannot be pooled with it. Not a repeat-count question.
- `ex1_casta_gpt_nowidth_PARTIAL_repair.jsonl`
  124 retry-diagnostic rows from ex1_repair_failures.py. result and ex1_prompt_version are null and the schema is attempt1_*/history, so these are not result rows at all.
- `ex1_casta_qwen_norules_r3_DUPLICATE.jsonl`
  byte-identical (md5) to the live three-repeat file. The extension was resumed in place instead of into a copy, so both names held the same 486 rows.
- `ex1_casta_qwen_nowidth_PARTIAL_repair.jsonl`
  189 retry-diagnostic rows from ex1_repair_failures.py. result and ex1_prompt_version are null and the schema is attempt1_*/history, so these are not result rows at all.
