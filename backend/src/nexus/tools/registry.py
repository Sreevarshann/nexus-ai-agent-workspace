"""Typed tool registry shared by agents, the workflow engine and the MCP server.

Each tool declares a Pydantic input model, is executed with a per-call timeout, is scoped to the calling
user, and is recorded in ``tool_calls`` regardless of outcome.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from nexus.data.analysis import run_sql
from nexus.data.engine import QueryError
from nexus.db import session_scope
from nexus.domain.sqlguard import UnsafeSQL
from nexus.models import Artifact, Dataset, DocumentChunk, Source, Task, ToolCall
from nexus.rag.retrieve import hybrid_search
from nexus.research.search import SearchUnavailable, get_search
from nexus.research.service import retrieve_source


@dataclass
class ToolContext:
    user_id: uuid.UUID
    origin: str = "agent"  # agent | mcp | workflow | chat | api
    task_id: uuid.UUID | None = None
    agent_run_id: uuid.UUID | None = None


class ToolError(RuntimeError):
    pass


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    fn: Callable[[Any, ToolContext], Awaitable[dict[str, Any]]]
    timeout_s: float = 30.0
    external: bool = False  # performs outbound network access


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str, description: str, input_model: type[BaseModel], timeout_s: float = 30.0, external: bool = False
) -> Callable[[Callable[..., Awaitable[dict[str, Any]]]], Tool]:
    def deco(fn: Callable[..., Awaitable[dict[str, Any]]]) -> Tool:
        t = Tool(name, description, input_model, fn, timeout_s, external)
        REGISTRY[name] = t
        return t

    return deco


def _summary(result: dict[str, Any]) -> str:
    for key in ("results", "hits", "rows", "datasets", "artifacts"):
        if isinstance(result.get(key), list):
            return f"{len(result[key])} {key}"
    return ", ".join(f"{k}={str(v)[:40]}" for k, v in list(result.items())[:3])


async def invoke(name: str, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    t = REGISTRY.get(name)
    if t is None:
        raise ToolError(f"Unknown tool '{name}'")
    started = time.perf_counter()
    status, error, result = "ok", None, {}
    try:
        if ctx.task_id is not None:
            from nexus.config import get_settings
            from nexus.redis import get_redis

            key = f"task:{ctx.task_id}:toolcalls"
            used = await get_redis().incr(key)
            await get_redis().expire(key, 7 * 24 * 3600)
            if used > get_settings().mission_max_tool_calls:
                raise PermissionError(f"Tool-call budget of {get_settings().mission_max_tool_calls} exhausted")
        parsed = t.input_model.model_validate(args)
        result = await asyncio.wait_for(t.fn(parsed, ctx), timeout=t.timeout_s)
        return result
    except ValidationError as e:
        status, error = "error", f"Invalid arguments: {e.errors()[0]['msg']}"
        raise ToolError(error) from e
    except TimeoutError as e:
        status, error = "error", f"Timed out after {t.timeout_s:.0f}s"
        raise ToolError(error) from e
    except PermissionError as e:
        status, error = "denied", str(e)
        raise ToolError(error) from e
    except (ToolError, SearchUnavailable, QueryError, UnsafeSQL, LookupError) as e:
        status, error = "error", str(e)
        raise ToolError(error) from e
    finally:
        async with session_scope() as db:
            db.add(
                ToolCall(
                    user_id=ctx.user_id,
                    task_id=ctx.task_id,
                    agent_run_id=ctx.agent_run_id,
                    tool=name,
                    origin=ctx.origin,
                    args={k: (v if len(str(v)) < 2000 else str(v)[:2000]) for k, v in args.items()},
                    result_summary=_summary(result) if status == "ok" else "",
                    status=status,
                    error=error,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )


def tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_model.model_json_schema(),
            "external": t.external,
        }
        for t in REGISTRY.values()
    ]


# ---------------------------------------------------------------------------------------------------------
# Tool implementations


class WebSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    limit: int = Field(default=8, ge=1, le=20)


@tool("web_search", "Search the live web through the configured search engine.", WebSearchIn, 30, external=True)
async def _web_search(a: WebSearchIn, ctx: ToolContext) -> dict[str, Any]:
    results = await get_search().search(a.query, a.limit)
    return {
        "query": a.query,
        "results": [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "domain": r.domain,
                "engine": r.engine,
                "published": r.published,
            }
            for r in results
        ],
    }


class FetchUrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    query: str = Field(default="", max_length=400)
    title: str = Field(default="", max_length=300)


@tool("fetch_url", "Retrieve a public web page or PDF and extract readable text.", FetchUrlIn, 45, external=True)
async def _fetch_url(a: FetchUrlIn, ctx: ToolContext) -> dict[str, Any]:
    s = await retrieve_source(ctx.user_id, a.url, a.query, ctx.task_id, a.title)
    return {
        "source_id": str(s.id),
        "url": s.url,
        "final_url": s.final_url,
        "title": s.title,
        "domain": s.domain,
        "status": s.status,
        "error": s.error,
        "excerpt": s.excerpt,
        "published_at": s.published_at,
        "chars": len(s.content),
    }


class SearchDocsIn(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    k: int = Field(default=6, ge=1, le=20)
    document_ids: list[uuid.UUID] | None = None


@tool("search_documents", "Hybrid (vector + keyword) search over the user's knowledge library.", SearchDocsIn)
async def _search_documents(a: SearchDocsIn, ctx: ToolContext) -> dict[str, Any]:
    async with session_scope() as db:
        hits = await hybrid_search(db, ctx.user_id, a.query, a.k, a.document_ids)
    return {
        "query": a.query,
        "hits": [
            {
                "chunk_id": str(h.chunk_id),
                "document_id": str(h.document_id),
                "filename": h.filename,
                "page": h.page,
                "text": h.text,
                "score": round(h.score, 5),
                "similarity": h.similarity,
                "signals": h.signals,
            }
            for h in hits
        ],
    }


class CitationIn(BaseModel):
    chunk_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None


@tool("get_citation", "Fetch the exact passage behind a citation (document chunk or web source).", CitationIn)
async def _get_citation(a: CitationIn, ctx: ToolContext) -> dict[str, Any]:
    async with session_scope() as db:
        if a.chunk_id:
            ch = await db.get(DocumentChunk, a.chunk_id)
            if ch is None or ch.user_id != ctx.user_id:
                raise LookupError("Citation not found")
            from nexus.models import Document

            doc = await db.get(Document, ch.document_id)
            return {
                "kind": "chunk",
                "chunk_id": str(ch.id),
                "document_id": str(ch.document_id),
                "filename": doc.filename if doc else "",
                "page": ch.page,
                "text": ch.text,
            }
        if a.source_id:
            src = await db.get(Source, a.source_id)
            if src is None or src.user_id != ctx.user_id:
                raise LookupError("Citation not found")
            return {
                "kind": "source",
                "source_id": str(src.id),
                "url": src.final_url or src.url,
                "title": src.title,
                "excerpt": src.excerpt,
                "retrieved_at": src.retrieved_at.isoformat(),
                "status": src.status,
            }
    raise ToolError("Provide chunk_id or source_id")


class Empty(BaseModel):
    pass


@tool("list_datasets", "List the user's uploaded datasets with their columns.", Empty)
async def _list_datasets(a: Empty, ctx: ToolContext) -> dict[str, Any]:
    async with session_scope() as db:
        rows = (
            (
                await db.execute(
                    select(Dataset).where(Dataset.user_id == ctx.user_id).order_by(Dataset.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
    return {
        "datasets": [
            {
                "id": str(d.id),
                "name": d.name,
                "rows": d.row_count,
                "columns": [{"name": c["name"], "kind": c["kind"]} for c in d.columns],
            }
            for d in rows
        ]
    }


class DatasetIn(BaseModel):
    dataset_id: uuid.UUID


async def owned_dataset(dataset_id: uuid.UUID, user_id: uuid.UUID) -> Dataset:
    async with session_scope() as db:
        d = await db.get(Dataset, dataset_id)
    if d is None or d.user_id != user_id:
        raise LookupError("Dataset not found")
    return d


@tool("profile_dataset", "Return the computed profile (types, nulls, statistics) of a dataset.", DatasetIn)
async def _profile_dataset(a: DatasetIn, ctx: ToolContext) -> dict[str, Any]:
    d = await owned_dataset(a.dataset_id, ctx.user_id)
    return {"dataset_id": str(d.id), "name": d.name, "rows": d.row_count, "columns": d.columns, "summary": d.profile}


class QueryIn(BaseModel):
    dataset_id: uuid.UUID
    sql: str = Field(min_length=6, max_length=5000, description="One read-only SELECT over the table `dataset`")


@tool("query_dataset", "Run an approved read-only SQL SELECT over the table `dataset`.", QueryIn, 20)
async def _query_dataset(a: QueryIn, ctx: ToolContext) -> dict[str, Any]:
    d = await owned_dataset(a.dataset_id, ctx.user_id)
    res = await asyncio.to_thread(run_sql, d.parquet_path, a.sql)
    return {"sql": res.sql, "columns": res.columns, "rows": res.rows[:500], "row_count": res.row_count}


class ArtifactIn(BaseModel):
    artifact_id: uuid.UUID


@tool("get_artifact", "Retrieve a stored artifact's latest content.", ArtifactIn)
async def _get_artifact(a: ArtifactIn, ctx: ToolContext) -> dict[str, Any]:
    async with session_scope() as db:
        art = await db.get(Artifact, a.artifact_id)
        if art is None or art.user_id != ctx.user_id:
            raise LookupError("Artifact not found")
        await db.refresh(art, ["versions"])
        v = art.versions[-1]
        return {
            "artifact_id": str(art.id),
            "title": art.title,
            "kind": art.kind,
            "version": v.version,
            "content": v.content[:50_000],
            "created_at": art.created_at.isoformat(),
        }


@tool("list_artifacts", "List the user's stored artifacts.", Empty)
async def _list_artifacts(a: Empty, ctx: ToolContext) -> dict[str, Any]:
    async with session_scope() as db:
        rows = (
            (
                await db.execute(
                    select(Artifact)
                    .where(Artifact.user_id == ctx.user_id)
                    .order_by(Artifact.updated_at.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
    return {
        "artifacts": [{"id": str(r.id), "title": r.title, "kind": r.kind, "version": r.current_version} for r in rows]
    }


class TaskIn(BaseModel):
    task_id: uuid.UUID


@tool("get_task_status", "Get the status and result summary of an agent mission or workflow run.", TaskIn)
async def _get_task_status(a: TaskIn, ctx: ToolContext) -> dict[str, Any]:
    async with session_scope() as db:
        t = await db.get(Task, a.task_id)
    if t is None or t.user_id != ctx.user_id:
        raise LookupError("Task not found")
    return {
        "task_id": str(t.id),
        "title": t.title,
        "kind": t.kind,
        "mode": t.mode,
        "status": t.status,
        "error": t.error,
        "summary": (t.result or {}).get("summary", "")[:2000],
    }
