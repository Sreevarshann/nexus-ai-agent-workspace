# Engineering decisions

| Decision | Why | Trade-off |
|---|---|---|
| `qwen3:4b-instruct` via native Ollama | Runs at ~25 tok/s on an M4 with 16 GB, supports JSON-schema-constrained output and tools; the instruct variant has no thinking preamble. Native (not Docker) for Metal acceleration. | Long reports take 1–3 minutes; reasoning is weaker than large hosted models. The provider abstraction allows a larger local or OpenAI-compatible model. |
| Constrained decoding + validation + one repair retry | Small models drift from schemas; Ollama's `format` makes structured calls reliable. | Retry adds latency on failure. |
| Analyst selects from a derived catalog | A 4B model composing free-form analysis plans produced invalid or poor plans in testing; selecting from valid candidates fixed that. | Fewer exotic analyses; the catalog is the vocabulary. |
| Deterministic verifier instead of LLM-as-judge | Reproducible, cheap, cannot be talked out of a result; catches fabricated labels and wrong numbers. | Lexical, not semantic. |
| LangGraph + Postgres checkpointer | Durable interrupts for approvals, pause/resume and retry-from-checkpoint without custom state machines. | Graph code must be idempotent per node. |
| arq on Redis | Async-native, tiny, supports job ids and aborts; Celery would be heavier than needed. | No built-in UI; task state lives in our own tables. |
| Redis streams for chat, Postgres+pub/sub for tasks | Chat tokens are ephemeral and high-volume (stream with TTL); task events must be durable and replayable. | Two mechanisms to understand. |
| SearXNG self-hosted | Free, no API key, real results from multiple engines, JSON API. | Some upstream engines rate-limit/CAPTCHA; results vary by engine availability. |
| Hybrid RRF retrieval | Vectors miss exact numbers/names; keywords miss paraphrase; RRF needs no score calibration. | Two queries per search. |
| DuckDB over Parquet per query | Fast analytics, strict sandboxing by loading one file and locking config. | Reloads the file per query (fine at ≤2M rows). |
| Next.js rewrites proxy | Same-origin cookies, no CORS for the app, SSE works with compression off. | Proxy timeout/body limits had to be raised for local-model latency and uploads. |
| `cacheComponents` disabled | Every page renders per-user data fetched client-side; component caching adds complexity without benefit here. | Not using PPR. |
| API on port 8010 | Port 8000 was occupied on the development machine. | Non-default port. |
| No arbitrary code execution | Removes an entire class of model-driven compromise. | Analyses limited to the typed operation set and guarded SQL. |
