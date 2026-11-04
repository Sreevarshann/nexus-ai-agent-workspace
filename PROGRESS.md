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
- [x] Backend tests: 101 passing (fixture LLM; see `backend/tests`)
- [ ] Live-model / live-search smoke tests (`pytest -m live`)
- [ ] Evaluation dataset and runner

## Frontend

- [ ] Next.js scaffold, design system, app shell, command palette
- [ ] Auth screens
- [ ] Intelligence Workspace (chat)
- [ ] Mission Control (XYFlow)
- [ ] Deep Research Studio
- [ ] Knowledge Library (+ PDF viewer)
- [ ] Data Lab (+ charts)
- [ ] Artifact Studio
- [ ] Workflow Builder
- [ ] History, Settings (models, MCP connectors, tokens)
- [ ] Vitest component tests
- [ ] Playwright E2E + screenshots

## Delivery

- [ ] Makefile targets, Dockerfiles
- [ ] README + docs/*
- [ ] GitHub Actions CI
- [ ] Publish to github.com/Sreevarshann/nexus-ai-agent-workspace
