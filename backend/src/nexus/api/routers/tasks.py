"""Missions (agent tasks): create, inspect, live events, and human-in-the-loop controls."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from nexus.api.deps import DB, CurrentUser, not_found
from nexus.api.routers.projects import get_owned_project
from nexus.db import get_sessionmaker
from nexus.events import TERMINAL, channel, clear_control, request_control, serialize, set_status
from nexus.jobs import enqueue
from nexus.models import AgentRun, Artifact, Dataset, Document, Source, Task, TaskEvent, ToolCall, WorkflowRun
from nexus.ratelimit import enforce
from nexus.redis import get_redis

router = APIRouter(prefix="/tasks", tags=["missions"])


class MissionIn(BaseModel):
    prompt: str = Field(min_length=5, max_length=4000)
    mode: Literal["quick", "deep", "compare", "doc_web"] = "deep"
    project_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    dataset_id: uuid.UUID | None = None
    require_approval: bool = False


class TaskOut(BaseModel):
    id: uuid.UUID
    kind: str
    mode: str
    title: str
    prompt: str
    status: str
    options: dict[str, Any]
    result: dict[str, Any]
    error: str | None
    project_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


async def owned_task(db: DB, user_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    t = await db.get(Task, task_id)
    if t is None or t.user_id != user_id:
        raise not_found("Task")
    return t


@router.post("", response_model=TaskOut, status_code=201)
async def create_mission(body: MissionIn, user: CurrentUser, db: DB) -> Task:
    await enforce(f"mission:{user.id}", 20, 3600)
    if body.project_id:
        await get_owned_project(db, user.id, body.project_id)
    for did in body.document_ids:
        d = await db.get(Document, did)
        if d is None or d.user_id != user.id:
            raise not_found("Document")
    if body.dataset_id:
        ds = await db.get(Dataset, body.dataset_id)
        if ds is None or ds.user_id != user.id:
            raise not_found("Dataset")
    opts: dict[str, Any] = {"require_approval": body.require_approval}
    if body.document_ids:
        opts["document_ids"] = [str(d) for d in body.document_ids]
    if body.dataset_id:
        opts["dataset_id"] = str(body.dataset_id)
    t = Task(
        user_id=user.id,
        project_id=body.project_id,
        kind="mission",
        mode=body.mode,
        title=body.prompt.strip().splitlines()[0][:240],
        prompt=body.prompt,
        options=opts,
    )
    db.add(t)
    await db.commit()
    await enqueue("run_task", str(t.id))
    return t


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    user: CurrentUser, db: DB, kind: str | None = None, status: str | None = None, limit: int = 50
) -> list[Any]:
    stmt = select(Task).where(Task.user_id == user.id)
    if kind:
        stmt = stmt.where(Task.kind == kind)
    if status:
        stmt = stmt.where(Task.status == status)
    return list((await db.execute(stmt.order_by(Task.created_at.desc()).limit(min(limit, 200)))).scalars())


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, user: CurrentUser, db: DB) -> Task:
    return await owned_task(db, user.id, task_id)


@router.get("/{task_id}/detail")
async def task_detail(task_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    """Everything Mission Control needs to rebuild the view: events, agent runs, tool calls, sources, artifacts."""
    t = await owned_task(db, user.id, task_id)
    events = (await db.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id))).scalars()
    runs = (
        await db.execute(select(AgentRun).where(AgentRun.task_id == task_id).order_by(AgentRun.started_at))
    ).scalars()
    calls = (
        await db.execute(select(ToolCall).where(ToolCall.task_id == task_id).order_by(ToolCall.created_at))
    ).scalars()
    sources = (
        await db.execute(select(Source).where(Source.task_id == task_id).order_by(Source.retrieved_at))
    ).scalars()
    arts = (await db.execute(select(Artifact).where(Artifact.task_id == task_id))).scalars()
    graph = None
    if t.kind == "workflow":
        wr = (await db.execute(select(WorkflowRun).where(WorkflowRun.task_id == task_id))).scalar()
        graph = wr.graph_snapshot if wr else None
    return {
        "graph": graph,
        "task": TaskOut.model_validate(t, from_attributes=True).model_dump(mode="json"),
        "events": [serialize(e) for e in events],
        "agent_runs": [
            {
                "id": str(r.id),
                "node": r.node,
                "agent": r.agent,
                "status": r.status,
                "error": r.error,
                "input_summary": r.input_summary,
                "output_summary": r.output_summary,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in runs
        ],
        "tool_calls": [
            {
                "id": str(c.id),
                "tool": c.tool,
                "args": c.args,
                "status": c.status,
                "error": c.error,
                "result_summary": c.result_summary,
                "duration_ms": c.duration_ms,
                "agent_run_id": str(c.agent_run_id) if c.agent_run_id else None,
                "created_at": c.created_at,
            }
            for c in calls
        ],
        "sources": [
            {
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
                "search_query": s.search_query,
            }
            for s in sources
        ],
        "artifacts": [{"id": str(a.id), "title": a.title, "kind": a.kind} for a in arts],
    }


@router.get("/{task_id}/events")
async def task_events(
    task_id: uuid.UUID, request: Request, user: CurrentUser, db: DB, last_event_id: str | None = Header(default=None)
) -> StreamingResponse:
    """SSE: replay persisted events after Last-Event-ID, then follow live updates."""
    await owned_task(db, user.id, task_id)
    await db.close()
    try:
        after = int(last_event_id or request.query_params.get("after") or 0)
    except ValueError:
        after = 0

    async def gen() -> AsyncIterator[str]:
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(channel(task_id))  # subscribe first so nothing falls between replay and live
        last = after
        try:
            async with get_sessionmaker()() as s:
                rows = (
                    (
                        await s.execute(
                            select(TaskEvent)
                            .where(TaskEvent.task_id == task_id, TaskEvent.id > after)
                            .order_by(TaskEvent.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                status = (await s.get(Task, task_id)).status  # type: ignore[union-attr]
            for e in rows:
                last = e.id
                yield f"id: {e.id}\nevent: task_event\ndata: {json.dumps(serialize(e), default=str)}\n\n"
            yield f"event: status\ndata: {json.dumps({'status': status})}\n\n"
            if status in TERMINAL:
                return  # finished tasks are fully described by the replay
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if msg is None:
                    yield ": keep-alive\n\n"
                    continue
                data = json.loads(msg["data"])
                if "id" in data:
                    if data["id"] <= last:
                        continue
                    last = data["id"]
                    yield f"id: {data['id']}\nevent: task_event\ndata: {msg['data']}\n\n"
                elif data.get("type") == "draft":
                    yield f"event: draft\ndata: {msg['data']}\n\n"
                elif data.get("type") == "status":
                    yield f"event: status\ndata: {msg['data']}\n\n"
                    if data.get("status") in TERMINAL:
                        return
                await asyncio.sleep(0)
        finally:
            await pubsub.unsubscribe(channel(task_id))
            await pubsub.aclose()

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.post("/{task_id}/cancel")
async def cancel(task_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, str]:
    t = await owned_task(db, user.id, task_id)
    if t.status in ("completed", "failed", "cancelled"):
        return {"status": t.status}
    if t.status in ("paused", "waiting_approval", "queued"):
        # nothing is executing; record the cancellation directly
        from nexus.events import emit

        await emit(task_id, "task_cancelled", reason="Cancelled by user")
        await set_status(task_id, "cancelled", error="Cancelled by user")
        return {"status": "cancelled"}
    await request_control(task_id, "cancel")
    return {"status": "cancelling"}


@router.post("/{task_id}/pause")
async def pause(task_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, str]:
    t = await owned_task(db, user.id, task_id)
    if t.status != "running":
        raise HTTPException(409, f"Cannot pause a {t.status} task")
    await request_control(task_id, "pause")
    return {"status": "pausing"}


@router.post("/{task_id}/resume")
async def resume(task_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, str]:
    t = await owned_task(db, user.id, task_id)
    if t.status != "paused":
        raise HTTPException(409, f"Cannot resume a {t.status} task")
    await clear_control(task_id, "pause")
    await set_status(task_id, "queued")
    await enqueue("retry_task", str(task_id))
    return {"status": "queued"}


@router.post("/{task_id}/retry")
async def retry(task_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, str]:
    """Continue a failed task from its last successful checkpoint (completed steps are not re-run)."""
    t = await owned_task(db, user.id, task_id)
    if t.status != "failed":
        raise HTTPException(409, f"Only failed tasks can be retried (task is {t.status})")
    await clear_control(task_id, "cancel")
    await set_status(task_id, "queued", error="")
    await enqueue("retry_task", str(task_id))
    return {"status": "queued"}


class DecisionIn(BaseModel):
    approved: bool
    comment: str = Field(default="", max_length=1000)
    web_queries: list[str] | None = Field(default=None, max_length=6)


@router.post("/{task_id}/approval")
async def decide(task_id: uuid.UUID, body: DecisionIn, user: CurrentUser, db: DB) -> dict[str, str]:
    """Resolve a pending human-approval interrupt. The decision is fed into the LangGraph checkpoint."""
    t = await owned_task(db, user.id, task_id)
    if t.status != "waiting_approval":
        raise HTTPException(409, f"Task is not waiting for approval (status {t.status})")
    await set_status(task_id, "queued")
    await enqueue("resume_task", str(task_id), body.model_dump())
    return {"status": "queued"}
