# NEXUS AI — Implementation Progress

Living checklist. Update it with every milestone so a new session can resume from the real state.

## Environment notes

- API runs on **port 8010** (port 8000 is occupied by an SSH tunnel on the development Mac).
- Postgres `localhost:5433`, Redis `localhost:6380`, SearXNG `localhost:8888` (docker compose).
- Ollama runs natively (Metal). Models: `qwen3:4b-instruct` (chat), `nomic-embed-text` (embeddings).
- macOS marks `.venv` files hidden, which can make Python skip uv's `.pth`; always run with `PYTHONPATH=src`
  (the Makefile does this).

## Backend

- [x] Config, DB models, Alembic migration (pgvector, HNSW, GIN FTS)
- [x] Auth: Argon2id, session cookies, API tokens, rate limiting
- [x] LLM providers: Ollama, OpenAI-compatible (opt-in), isolated fixture (test only)
- [x] RAG: validation, extraction (PDF/TXT/MD/CSV/XLSX/DOCX), page-aware chunking, embeddings, hybrid RRF retrieval
- [x] Web research: SSRF-safe fetcher, robots.txt, SearXNG provider, readability extraction, injection flags
- [x] Data lab: DuckDB sandbox, sqlglot guard, typed operations, profile-derived analysis catalog
- [x] Tool registry with budgets and `tool_calls` logging
- [x] LangGraph missions: planner, approval, web/doc/data agents, synthesizer, verifier, artifact builder
- [x] Durable checkpoints (Postgres), pause/resume, retry-from-checkpoint, cancel, approvals
- [x] Workflow builder engine: validation, DAG compile to LangGraph, 4 runnable templates
- [x] Chat: resumable Redis-stream SSE, chat/research/analysis/agent modes, regenerate, cancel
- [x] MCP server (Streamable HTTP, bearer API tokens, read-only tools)
- [x] Artifacts: versions, MD/JSON/CSV/PDF export
- [x] Backend tests: 174 passing (fixture LLM; see `backend/tests`), 77 of them offline (no services)
- [x] Live-model / live-search smoke tests (`pytest -m live`) — 4/4 passing
- [x] Evaluation dataset and runner (`make eval`)
- [x] Evaluation quality gates: explicit pass/fail/skip/error outcomes, thresholds, non-zero exit,
      `--offline` / `--require-api` / `--live`, run history + reproducibility metadata, offline tests
      (`make test-offline`), service-free CI gate job. See docs/EVALUATION.md.

## Frontend

- [x] Next.js scaffold, design system, app shell, command palette
- [x] Auth screens
- [x] Intelligence Workspace (chat)
- [x] Mission Control (XYFlow)
- [x] Deep Research Studio
- [x] Knowledge Library (+ PDF viewer)
- [x] Data Lab (+ charts)
- [x] Artifact Studio
- [x] Workflow Builder
- [x] History, Settings (models, MCP connectors, tokens)
- [x] Vitest component tests
- [x] Screenshots: 23 real captures in docs/screenshots
- [x] Full live E2E pass — all 12 steps against the real model and live web (55 s). Fixed: in-flight polling
      paused while the tab was hidden, leaving the Library on "Processing" after ingestion finished.

## Delivery

- [x] Makefile targets, Dockerfiles
- [x] README + docs/*
- [x] GitHub Actions CI
- [x] Published to https://github.com/Sreevarshann/nexus-ai-agent-workspace — CI green

## Notes (2026-11-04)

- The development Mac runs another project's Docker stack alongside NEXUS; swap reached ~11 GB, which made long
  local-model runs and the full E2E journey slow. Default context reduced to 8k tokens.
- Verified manually in the browser: streamed chat, library-grounded citations, compare mission with approval,
  retry from checkpoint, live draft, verifier, artifact viewer, Data Lab analyst.

## Evaluation quality gates (2026-11-05, branch `feat/evaluation-quality-gates`)

- Problem reproduced on `4046d0f`: grounding accuracy 0.0 → exit 0; unreachable API → note + exit 0; any partial run
  overwrote the complete `latest.json`; `tests/test_verify.py` errored without Postgres (session-autouse fixture).
- Decisions: outcomes `pass/fail/skip/error` as validated Pydantic models (inconsistent results unrepresentable);
  executed optional checks are still gated; deterministic thresholds 100%; recall, MRR and tool selection one
  case below baseline; page accuracy and canary leaks exact; `latest.json` only from complete runs, every run kept in `runs/`; model identity from provider
  self-report only; offline-only pytest sessions skip infrastructure (`-m offline`).
- Checks run: ruff + format + mypy (now incl. `evals`) clean; `pytest -m offline` 44 passed with the DB unreachable;
  full backend suite 141 passed against a throwaway pgvector container; CLI exit codes verified for pass (0),
  failing metric (1), required API unavailable (1), optional API unavailable (0), `--live` with fixture (1), usage
  error (2); `--require-api` passed against an isolated fixture-provider API stack (plumbing, not model quality).
- Review fix: a login HTTP 5xx (or any non-401 unexpected status) is now `error`, not an optional skip; 401 stays
  an unavailable prerequisite. After the fix: offline 49 passed, full suite 146 passed, ruff/format/mypy clean;
  the new 5xx test failed (exit 0) on the previous code.
- Not run here: `--require-api` with real `nomic-embed-text` and `--live` with a real model (no local models
  installed; not downloaded for this change).

## Citation numeric verification (2026-11-05, branch `fix/citation-numeric-verification`)

- Problem reproduced on `f4985a1`: wrong years (2019 vs 2024), wrong small counts (2 vs "three"), `80%` vs a bare
  80, and `12%` vs `-12%` were all `supported`; a correctly rounded `20,068,215 [D1]` was unmatched because data
  results render as `2.007e+07`.
- Decisions: years and discrete counts exact; bounded written counts (zero to ninety-nine, `one` not checked in
  claims); measurements match by the claim's displayed precision, widened to the evidence's precision for `[D#]`
  results; sign and percent must agree (bare data values may support percents). Policy in `docs/VERIFICATION.md`.
- Checks run: `test_verify.py` 33 passed (17 fail on the previous verifier); grounding gate 19/19 (0.684 and exit 1
  on the previous verifier, threshold unchanged); offline 77 passed; full suite 174 passed against a throwaway
  pgvector container; ruff/format/mypy clean. No real-model run.
