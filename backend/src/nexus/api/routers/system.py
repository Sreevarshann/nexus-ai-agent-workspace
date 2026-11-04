"""Health, configuration, tool catalogue, MCP status and observability metrics."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select, text

from nexus.api.deps import DB, CurrentUser
from nexus.config import get_settings
from nexus.db import get_sessionmaker
from nexus.llm.factory import get_llm
from nexus.models import ApiToken, Message, Source, Task, ToolCall
from nexus.redis import get_redis
from nexus.research.search import get_search
from nexus.tools.registry import tool_specs

router = APIRouter(tags=["system"])


async def _check(name: str, fn: Any) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        out = await fn()
        out = out if isinstance(out, dict) else {"ok": True}
    except Exception as e:
        out = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    out["latency_ms"] = int((time.perf_counter() - started) * 1000)
    return out


@router.get("/health")
async def health() -> dict[str, Any]:
    """Unauthenticated liveness + dependency status (no user data)."""

    async def db() -> dict[str, Any]:
        async with get_sessionmaker()() as s:
            await s.execute(text("SELECT 1"))
        return {"ok": True}

    async def redis() -> dict[str, Any]:
        await get_redis().ping()
        return {"ok": True}

    checks = {
        "database": await _check("db", db),
        "redis": await _check("redis", redis),
        "llm": await _check("llm", get_llm().health),
        "search": await _check("search", get_search().health),
    }
    return {
        "status": "ok" if checks["database"]["ok"] and checks["redis"]["ok"] else "degraded",
        "env": get_settings().env,
        "checks": checks,
    }


@router.get("/system/config")
async def config(user: CurrentUser) -> dict[str, Any]:
    s = get_settings()
    llm = get_llm()
    return {
        "llm": {
            "provider": llm.name,
            "model": llm.model,
            "embed_model": s.embed_model,
            "temperature": s.temperature,
            "num_ctx": s.num_ctx,
            "timeout_s": s.llm_timeout_s,
            "external": s.llm_provider == "openai_compat",
        },
        "search": {"provider": s.search_provider, "url": s.searxng_url if s.search_provider == "searxng" else None},
        "limits": {
            "max_upload_mb": s.max_upload_bytes // (1024 * 1024),
            "max_dataset_rows": s.max_dataset_rows,
            "query_timeout_s": s.query_timeout_s,
            "mission_max_steps": s.mission_max_steps,
            "mission_max_tool_calls": s.mission_max_tool_calls,
        },
    }


@router.get("/system/tools")
async def tools(user: CurrentUser, db: DB) -> dict[str, Any]:
    from nexus.mcp_server.server import EXPOSED_TOOLS

    stats = (
        await db.execute(
            select(
                ToolCall.tool,
                func.count(),
                func.max(ToolCall.created_at),
                func.sum(func.cast(ToolCall.status != "ok", type_=func.count().type)),
            )
            .where(ToolCall.user_id == user.id)
            .group_by(ToolCall.tool)
        )
    ).all()
    by_tool = {t: {"calls": c, "last_called_at": last, "errors": int(errs or 0)} for t, c, last, errs in stats}
    last_errors = (
        await db.execute(
            select(ToolCall)
            .where(ToolCall.user_id == user.id, ToolCall.status != "ok")
            .order_by(ToolCall.created_at.desc())
            .limit(10)
        )
    ).scalars()
    mcp_calls = (
        await db.execute(
            select(ToolCall)
            .where(ToolCall.user_id == user.id, ToolCall.origin == "mcp")
            .order_by(ToolCall.created_at.desc())
            .limit(20)
        )
    ).scalars()
    tokens = await db.scalar(select(func.count()).select_from(ApiToken).where(ApiToken.user_id == user.id))
    return {
        "tools": [
            {**t, "mcp_exposed": t["name"] in EXPOSED_TOOLS, **by_tool.get(t["name"], {"calls": 0})}
            for t in tool_specs()
        ],
        "mcp": {
            "endpoint": "/mcp",
            "transport": "streamable-http",
            "auth": "Bearer API token (scope: mcp)",
            "tokens": tokens or 0,
            "recent_calls": [
                {
                    "tool": c.tool,
                    "status": c.status,
                    "duration_ms": c.duration_ms,
                    "created_at": c.created_at,
                    "error": c.error,
                }
                for c in mcp_calls
            ],
        },
        "recent_errors": [
            {"tool": c.tool, "origin": c.origin, "error": c.error, "created_at": c.created_at} for c in last_errors
        ],
    }


@router.get("/system/metrics")
async def metrics(user: CurrentUser, db: DB) -> dict[str, Any]:
    """Aggregates computed from persisted records — nothing here is estimated."""
    tool_rows = (
        await db.execute(
            select(
                ToolCall.tool,
                func.count(),
                func.avg(ToolCall.duration_ms),
                func.percentile_cont(0.95).within_group(ToolCall.duration_ms),
                func.count().filter(ToolCall.status != "ok"),
            )
            .where(ToolCall.user_id == user.id)
            .group_by(ToolCall.tool)
        )
    ).all()
    task_rows = (
        await db.execute(
            select(Task.kind, Task.status, func.count()).where(Task.user_id == user.id).group_by(Task.kind, Task.status)
        )
    ).all()
    msg = (
        await db.execute(
            select(
                func.count(),
                func.avg(Message.meta["latency_ms"].as_float()),
                func.sum(Message.meta["tokens"]["completion"].as_integer()),
                func.count().filter(Message.status == "error"),
            )
            .select_from(Message)
            .join(Message.conversation)
            .where(Message.role == "assistant", Message.conversation.has(user_id=user.id))
        )
    ).one()
    src = (
        await db.execute(select(Source.status, func.count()).where(Source.user_id == user.id).group_by(Source.status))
    ).all()
    return {
        "tools": [
            {"tool": t, "calls": c, "avg_ms": round(a or 0, 1), "p95_ms": round(p or 0, 1), "errors": e}
            for t, c, a, p, e in tool_rows
        ],
        "tasks": [{"kind": k, "status": s, "count": c} for k, s, c in task_rows],
        "generation": {
            "assistant_messages": msg[0],
            "avg_latency_ms": round(msg[1] or 0, 1),
            "completion_tokens": msg[2] or 0,
            "errors": msg[3],
        },
        "sources": {s: c for s, c in src},
    }
