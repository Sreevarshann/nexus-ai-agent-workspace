# NEXUS AI — Architecture Plan

This is the working plan written before implementation. `PROGRESS.md` tracks the live state.

## Environment (inspected 2026-11-04)

- Apple M4, 10 cores, 16 GB RAM; Docker Desktop with ~8 GB allotted
- Node 24, Python 3.12 (via uv), Ollama 0.40 (native, Metal-accelerated)
- Chosen models: `qwen3:4b-instruct` (chat, tool use, JSON schema output — ~25 tok/s locally) and
  `nomic-embed-text` (768-dim embeddings). Both run locally; no paid API is required.

## Services

| Process | Runs in | Purpose |
|---|---|---|
| `web` (Next.js) | host (`make dev`) or compose | UI, proxies `/api/*` to the API so auth cookies stay same-origin |
| `api` (FastAPI) | host or compose | REST + SSE, chat streaming, MCP endpoint at `/mcp` |
| `worker` (arq) | host or compose | Missions (LangGraph), document ingestion, workflow runs |
| `postgres` + pgvector | compose | Relational data, vectors, FTS, LangGraph checkpoints |
| `redis` | compose | Job queue, event fan-out (pub/sub), chat token streams, cancel/pause flags |
| `searxng` | compose | Self-hosted meta search with JSON output |
| `ollama` | host | LLM + embedding inference (Docker on macOS has no GPU access) |

## Backend layering

`api/routers` (HTTP) → `services` (use cases, authorization) → `domain` (pure logic: chunking, citation parsing,
SQL guards, graph validation) → `repositories`/`models` (SQLAlchemy). Integrations live in `llm/`, `research/`,
`rag/`, `data/`, `agents/`, `mcp_server/`.

## Database (Alembic-managed)

users, sessions, api_tokens, workspaces, projects, conversations, messages, tasks, task_events, agent_runs,
tool_calls, documents, document_chunks (vector(768) + tsvector), sources, citations, datasets, artifacts,
artifact_versions, workflow_definitions, workflow_runs. Every user-owned row carries `user_id` (or reaches it through
`project_id`) and every query in the service layer filters by it.

## LLM strategy

`LLMProvider` protocol with `stream_chat`, `chat`, `structured` (JSON schema) and `embed`. Implementations:
`OllamaProvider`, `OpenAICompatibleProvider` (opt-in, never default), `FixtureProvider` (deterministic, only
selectable when `NEXUS_ENV=test`). Health endpoint reports real connectivity and installed models.

## Agent graph (LangGraph)

```
planner → router ─┬→ web_researcher ─┐
                  ├→ doc_researcher ─┼→ synthesizer → verifier → [approval] → artifact_builder → final
                  └→ data_analyst ───┘
```

The planner emits a typed plan (`steps`, `needs_web`, `needs_docs`, `needs_data`, `queries`, `entities`).
Conditional edges skip agents that the plan does not need. Modes: `quick` (1 query, 3 sources, no verifier),
`deep` (multi-query, 8 sources, verifier), `compare` (per-entity research + comparison table/chart),
`doc_web` (library + web). Budgets: max steps, max tool calls, per-tool timeouts. Every node emits typed
`task_events` (persisted, then published on Redis) that Mission Control renders. Human approval and pause use
LangGraph `interrupt()` with the Postgres checkpointer, so they survive worker restarts.

## Tools

Typed (Pydantic in/out) and registered once; used by agents, the workflow engine and the MCP server:
`web_search`, `fetch_url`, `search_documents`, `get_citation`, `list_datasets`, `profile_dataset`,
`query_dataset`, `get_artifact`, `get_task_status`. Every invocation is written to `tool_calls`.

## RAG pipeline

validate (size, magic bytes) → store under `data/uploads/<user>/<sha256>` → extract (PyMuPDF per page, docx, md,
txt, csv/xlsx summaries) → chunk (~900 chars, overlap, page-aware) → embed (Ollama) → pgvector HNSW + Postgres
`tsvector` GIN → hybrid retrieval with reciprocal rank fusion → citations `[S#]` mapped to chunk ids and pages.

## Data lab

Uploaded CSV/XLSX is normalised to Parquet. DuckDB in-memory connections with external access disabled read only
that Parquet file. User SQL and LLM SQL pass through a `sqlglot` guard: one `SELECT`, allow-listed functions,
table name must be `dataset`. The AI analyst produces a typed analysis plan (aggregate / timeseries / compare /
top-n / correlation) that is executed deterministically; the LLM only writes the narrative from computed values.

## Frontend

Next.js App Router, strict TS, Tailwind v4, shadcn/ui primitives, XYFlow, Zustand (UI/layout state, persisted),
TanStack Query (server state), Recharts, react-markdown (+GFM, KaTeX, highlight), cmdk, react-resizable-panels,
react-pdf. Structure: `src/app` (routes), `src/features/*`, `src/components/{ui,shell}`, `src/lib/api`, `src/stores`.

## Security boundaries

Session cookies (httpOnly, SameSite=Lax) + Argon2id; per-user authorization in services; SSRF-safe fetcher
(scheme allow-list, DNS resolution with private/loopback/link-local rejection, pinned IP connection, redirect
re-validation, size + time limits, robots.txt); untrusted content wrapped in delimited data blocks with an explicit
system rule; LLM has no shell/filesystem tools; SQL guard; upload limits; rate limiting on auth + LLM endpoints.

## Testing

pytest against a real Postgres (pgvector) and fakeredis, with the fixture LLM provider; respx for HTTP mocking.
Separately marked `live` tests hit real Ollama and SearXNG. Vitest + Testing Library for components; Playwright E2E
(fixture mode in CI, live mode locally) and screenshots at 1920/1440/768/390.
