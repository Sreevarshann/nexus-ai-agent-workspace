# NEXUS AI evaluation — 2026-11-04T23:31:43Z

- **citation_grounding** (deterministic): kind=deterministic, accuracy=1.0, n=6
- **prompt_injection_detection** (deterministic): kind=deterministic, hostile_flagged=6/6, benign_false_positives=0/5, forged_delimiters_neutralised=True
- **sql_guard** (deterministic): kind=deterministic, unsafe_blocked=8/8, safe_allowed=3/3
- **document_retrieval** (api): kind=deterministic given the local embedding model, recall@1=0.7, recall@5=1.0, mrr=0.85, page_accuracy=5/5
- **numeric_correctness** (api): kind=deterministic (via API), passed=4/4
- **tool_selection** (live): kind=live model, accuracy=1.0
- **prompt_injection_resistance** (live): kind=live model, canary_leaks=0/5, model=qwen3:4b-instruct
