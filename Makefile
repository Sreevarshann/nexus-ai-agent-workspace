# NEXUS AI developer commands. Run `make help` for the list.
SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend
PY := cd $(BACKEND) && PYTHONPATH=src uv run --no-sync
CHAT_MODEL ?= qwen3:4b-instruct
EMBED_MODEL ?= nomic-embed-text

.PHONY: stop-demo help setup models up down dev api worker web migrate seed test test-backend test-frontend test-live e2e lint typecheck build screenshots demo eval clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend + frontend dependencies, create .env, pull models
	@test -f .env || (cp .env.example .env && sed -i.bak "s/change-me-to-a-long-random-string/$$(openssl rand -hex 32)/; s/change-me-searxng-secret/$$(openssl rand -hex 24)/" .env && rm -f .env.bak && echo "created .env")
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm ci
	cd $(FRONTEND) && npx playwright install chromium
	$(MAKE) models

models: ## Pull the local Ollama models (one-time, ~2.8 GB)
	@command -v ollama >/dev/null || (echo "Install Ollama first: brew install ollama && brew services start ollama" && exit 1)
	ollama pull $(CHAT_MODEL)
	ollama pull $(EMBED_MODEL)

up: ## Start Postgres (pgvector), Redis and SearXNG
	docker compose up -d --wait postgres redis searxng
	$(MAKE) migrate

down: ## Stop infrastructure containers (data volumes are kept)
	docker compose down

migrate: ## Apply database migrations
	$(PY) alembic upgrade head

api: ## Run the API with reload on :8010
	$(PY) uvicorn nexus.main:app --reload --port 8010

worker: ## Run the background worker
	$(PY) arq nexus.worker.WorkerSettings

web: ## Run the Next.js dev server on :3001
	cd $(FRONTEND) && npm run dev

dev: up ## Start infra, then API + worker + web together (Ctrl-C stops all)
	@trap 'kill 0' EXIT; \
	  ($(PY) uvicorn nexus.main:app --reload --port 8010) & \
	  ($(PY) arq nexus.worker.WorkerSettings) & \
	  (cd $(FRONTEND) && npm run dev) & \
	  wait

seed: ## Create the demo account and load the synthetic sample content (API must be running)
	$(PY) python scripts/generate_samples.py
	$(PY) python scripts/seed.py

test: test-backend test-frontend ## Run backend and frontend unit/integration tests

test-backend: ## Backend tests (real Postgres+pgvector, fakeredis, fixture LLM)
	$(PY) pytest -q

test-frontend: ## Frontend component tests (Vitest)
	cd $(FRONTEND) && npm test

test-live: ## Smoke tests against the real Ollama model and live SearXNG
	$(PY) pytest -q -m live

e2e: ## Playwright end-to-end tests against the running stack
	cd $(FRONTEND) && npx playwright test

lint: ## Ruff + ESLint
	cd $(BACKEND) && uv run --no-sync ruff check src tests && uv run --no-sync ruff format --check src tests
	cd $(FRONTEND) && npx eslint src

typecheck: ## mypy + tsc
	$(PY) mypy
	cd $(FRONTEND) && npx tsc --noEmit

build: ## Production frontend build and Docker images
	cd $(FRONTEND) && npm run build
	docker compose --profile app build

screenshots: ## Capture real browser screenshots into docs/screenshots (stack + seed required)
	cd $(FRONTEND) && npx playwright test --project=screenshots

demo: up ## Start API, worker and web in the background, seed demo data, print the login (logs in .demo/)
	@mkdir -p .demo
	@(cd $(BACKEND) && PYTHONPATH=src nohup uv run --no-sync uvicorn nexus.main:app --port 8010 > ../.demo/api.log 2>&1 & echo $$! > ../.demo/api.pid)
	@(cd $(BACKEND) && PYTHONPATH=src nohup uv run --no-sync arq nexus.worker.WorkerSettings > ../.demo/worker.log 2>&1 & echo $$! > ../.demo/worker.pid)
	@(cd $(FRONTEND) && nohup npm run dev > ../.demo/web.log 2>&1 & echo $$! > ../.demo/web.pid)
	@for i in $$(seq 1 60); do curl -sf localhost:8010/api/health >/dev/null && break; sleep 1; done
	$(MAKE) seed
	@echo ""; echo "NEXUS AI is running: http://localhost:3001  (login: see NEXUS_DEMO_EMAIL / NEXUS_DEMO_PASSWORD in .env)"; echo "Stop with: make stop-demo"

stop-demo: ## Stop the background processes started by `make demo`
	-@for f in .demo/*.pid; do kill $$(cat $$f) 2>/dev/null; rm -f $$f; done; echo stopped

eval: ## Run the reproducible evaluation suite (writes evals/results/*.json)
	$(PY) python -m evals.run

clean: ## Remove build artifacts and caches
	rm -rf $(FRONTEND)/.next $(FRONTEND)/test-results $(FRONTEND)/playwright-report $(BACKEND)/.pytest_cache
