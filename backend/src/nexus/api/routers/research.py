"""Direct research tools: live search and URL retrieval, plus the user's source library."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from nexus.api.deps import DB, CurrentUser, not_found
from nexus.models import Source
from nexus.ratelimit import enforce
from nexus.tools.registry import ToolContext, ToolError, invoke

router = APIRouter(prefix="/research", tags=["research"])


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    limit: int = Field(default=10, ge=1, le=20)


@router.post("/search")
async def search(body: SearchIn, user: CurrentUser) -> dict[str, Any]:
    await enforce(f"search:{user.id}", 60, 60)
    try:
        return await invoke("web_search", body.model_dump(), ToolContext(user_id=user.id, origin="api"))
    except ToolError as e:
        raise HTTPException(503, str(e)) from e


class FetchIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    query: str = Field(default="", max_length=400)


@router.post("/fetch")
async def fetch(body: FetchIn, user: CurrentUser) -> dict[str, Any]:
    await enforce(f"fetch:{user.id}", 60, 60)
    try:
        return await invoke("fetch_url", body.model_dump(), ToolContext(user_id=user.id, origin="api"))
    except ToolError as e:
        raise HTTPException(422, str(e)) from e


def _src(s: Source, full: bool = False) -> dict[str, Any]:
    d = {
        "id": str(s.id),
        "url": s.url,
        "final_url": s.final_url,
        "domain": s.domain,
        "title": s.title,
        "status": s.status,
        "http_status": s.http_status,
        "excerpt": s.excerpt,
        "error": s.error,
        "published_at": s.published_at,
        "retrieved_at": s.retrieved_at,
        "task_id": str(s.task_id) if s.task_id else None,
        "search_query": s.search_query,
        "chars": len(s.content),
    }
    if full:
        d["content"] = s.content
    return d


@router.get("/sources")
async def list_sources(
    user: CurrentUser, db: DB, task_id: uuid.UUID | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    stmt = select(Source).where(Source.user_id == user.id)
    if task_id:
        stmt = stmt.where(Source.task_id == task_id)
    rows = (await db.execute(stmt.order_by(Source.retrieved_at.desc()).limit(min(limit, 500)))).scalars()
    return [_src(s) for s in rows]


@router.get("/sources/{source_id}")
async def get_source(source_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    s = await db.get(Source, source_id)
    if s is None or s.user_id != user.id:
        raise not_found("Source")
    return _src(s, full=True)
