"""FastAPI application."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from nexus.api.routers import (
    artifacts,
    auth,
    conversations,
    datasets,
    documents,
    projects,
    research,
    system,
    tasks,
    workflows,
)
from nexus.config import get_settings
from nexus.db import dispose_engine
from nexus.logging import configure_logging, log
from nexus.mcp_server.server import build_mcp, transport_security
from nexus.services.chat import mark_interrupted

mcp = build_mcp()
mcp_app = mcp.streamable_http_app(
    streamable_http_path="/", transport_security=transport_security(), stateless_http=True, json_response=True
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(json=get_settings().env == "production")
    if get_settings().env != "test":
        await mark_interrupted()
    async with mcp.session_manager.run():
        log.info("api_started", env=get_settings().env)
        yield
    await dispose_engine()


app = FastAPI(
    title="NEXUS AI API",
    version="0.1.0",
    lifespan=lifespan,
    description="Autonomous research, intelligence and execution workspace.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(request_id=rid)
    started = time.perf_counter()
    try:
        response: Response = await call_next(request)
    except Exception:
        log.exception("unhandled_error", path=request.url.path)
        response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
    ms = int((time.perf_counter() - started) * 1000)
    response.headers["x-request-id"] = rid
    response.headers["x-response-time-ms"] = str(ms)
    response.headers["x-content-type-options"] = "nosniff"
    response.headers["referrer-policy"] = "same-origin"
    if not request.url.path.endswith("/stream") and not request.url.path.endswith("/events"):
        log.info("request", method=request.method, path=request.url.path, status=response.status_code, ms=ms)
    structlog.contextvars.clear_contextvars()
    return response


for r in (auth, projects, conversations, documents, datasets, research, tasks, artifacts, workflows, system):
    app.include_router(r.router, prefix="/api")

app.mount("/mcp", mcp_app)
