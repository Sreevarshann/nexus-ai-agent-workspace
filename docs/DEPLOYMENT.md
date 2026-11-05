# Deployment and local operations

## Local (recommended)

```bash
make setup     # deps, .env with random secrets, Playwright browser, Ollama models
make up        # Postgres, Redis, SearXNG (+ migrations)
make dev       # API :8010, worker, web :3001
make seed      # demo account + sample content (credentials written to .env)
```

Or `make demo` to start everything in the background and seed in one go (`make stop-demo` to stop).

## Containers

`docker compose --profile app up --build` runs the API, worker and web as containers alongside the infrastructure.
They reach Ollama on the host through `host.docker.internal:11434`. Images: `backend/Dockerfile` (python:3.12-slim,
uv, non-root user) and `frontend/Dockerfile` (Next.js standalone output, non-root).

## Resource footprint (measured on an M4, 16 GB)

The chat model occupies ~3.9 GB when loaded with a 16k context; the embedding model ~0.3 GB. The three containers
use well under 1 GB together. Use a smaller context (`NEXUS_NUM_CTX=8192`) on lower-memory machines.

## Configuration

See `.env.example`. Notable: `NEXUS_LLM_PROVIDER` (`ollama` | `openai_compat`), `NEXUS_CHAT_MODEL`,
`NEXUS_SEARCH_PROVIDER` (`searxng` | `none`), `NEXUS_MISSION_MAX_STEPS`, `NEXUS_MISSION_MAX_TOOL_CALLS`,
`NEXUS_MAX_UPLOAD_BYTES`. In production set `NEXUS_ENV=production` and a real `NEXUS_SECRET_KEY` (enforced),
and put the stack behind TLS.
