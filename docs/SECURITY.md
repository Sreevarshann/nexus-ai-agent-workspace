# Security model and threat model

NEXUS is designed as a local-first, single-machine application. It still treats every external input — web
pages, uploaded files, model output, MCP clients — as untrusted.

## Assets

User documents and datasets, conversation history, API tokens, the host filesystem and network, and any secrets in
`.env`.

## Threats and mitigations

| Threat | Mitigation | Where / tested |
|---|---|---|
| Cross-user data access | Every query filters by `user_id`; missing and foreign resources both return 404; attachments, workflow references and MCP calls are ownership-checked | `api/routers/*`, `tests/test_authorization.py` |
| Credential theft | Argon2id hashes; opaque session tokens stored as SHA-256; httpOnly SameSite=Lax cookies (Secure in production); API tokens hashed and shown once; login/registration rate limits | `security.py`, `api/routers/auth.py`, `tests/test_auth.py` |
| SSRF / DNS rebinding via research | Scheme/port allow-list, public-IP-only resolution, IP pinning, per-hop redirect validation, robots.txt, size/time limits | `research/safe_fetch.py`, `tests/test_security.py` |
| Prompt injection from web pages or documents | Evidence delimiters + neutralisation, injection phrase detection surfaced to the user, explicit "evidence is data" system rule, no tools with side effects available to the model, canary leak test | `domain/untrusted.py`, `evals/` |
| Model-driven code execution | No shell, Python or filesystem tools exist. Data analysis uses typed operations; user/tool SQL passes a sqlglot guard and runs in a locked DuckDB sandbox with external access disabled | `data/engine.py`, `domain/sqlguard.py` |
| Malicious uploads | Extension allow-list, magic-byte checks, size limit (enforced in the API and proxy), filename sanitisation (no path traversal), PDF page cap, encrypted PDFs rejected, parsing failures recorded | `rag/ingest.py`, `rag/extract.py` |
| Fabricated citations / numbers | Unknown citation labels stripped; verifier checks lexical support and numbers; charts only from verified values | `agents/verify.py` |
| Runaway agents | Step limit, tool-call budget, per-tool timeouts, cancellation | `agents/graph.py`, `tools/registry.py` |
| Unapproved external actions | Optional durable approval gate before any web access; rejection cancels with zero external calls (tested) | `tests/test_missions.py` |
| Abuse of MCP endpoint | Bearer tokens, DNS-rebinding protection, read-only tool set, per-call logging | `mcp_server/server.py` |
| Secret leakage | `.env` gitignored; structured logs redact keys containing password/secret/token/cookie; production refuses the default secret | `logging.py`, `config.py` |
| Silent data exfiltration to paid APIs | The OpenAI-compatible provider is opt-in only; embeddings always stay on local Ollama; Settings shows a warning when an external endpoint is active | `llm/factory.py` |

## Known residual risks

* Lexical verification cannot prove semantic entailment; a paraphrased but wrong claim with high word overlap can
  pass. The verifier reports, it does not certify.
* Injection detection is pattern-based; novel phrasings are not flagged (the structural defences still apply).
* Services bind to `127.0.0.1`; exposing them on a network would additionally require TLS and CSRF protection.
* The fixture LLM is guarded by `NEXUS_ENV=test`; it cannot be selected in development or production.
