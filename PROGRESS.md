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
- [x] Backend tests: 102 passing (fixture LLM; see `backend/tests`)
- [x] Live-model / live-search smoke tests (`pytest -m live`) — 4/4 passing
- [x] Evaluation dataset and runner (`make eval`)

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
- [ ] Full live E2E pass — steps 1–8 passed in one live run; later runs failed waits under memory pressure.
      Open item: in the last run a document was `ready` in Postgres within 8 s but the Library list still showed
      `Processing` 2 minutes later. Investigate `useDocuments` polling vs. proxy latency on a machine with free memory.

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
