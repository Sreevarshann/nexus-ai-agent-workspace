"""Task event log: persisted to Postgres (source of truth), fanned out over Redis pub/sub (live updates).

SSE clients first replay events after their ``Last-Event-ID`` from Postgres, then follow the Redis channel,
so a reconnecting browser always recovers the complete state.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from nexus.db import session_scope
from nexus.models import Task, TaskEvent
from nexus.redis import get_redis

EventType = Literal[
    "task_started",
    "plan_created",
    "node_started",
    "node_completed",
    "node_failed",
    "node_skipped",
    "tool_call",
    "source_retrieved",
    "evidence",
    "log",
    "approval_required",
    "approval_resolved",
    "paused",
    "resumed",
    "artifact_created",
    "task_completed",
    "task_failed",
    "task_cancelled",
]

TERMINAL = {"completed", "failed", "cancelled"}


def channel(task_id: uuid.UUID | str) -> str:
    return f"task:{task_id}:events"


async def emit(task_id: uuid.UUID, type_: EventType, node: str | None = None, **payload: Any) -> dict[str, Any]:
    async with session_scope() as db:
        ev = TaskEvent(task_id=task_id, type=type_, node=node, payload=_jsonable(payload))
        db.add(ev)
        await db.flush()
        out = serialize(ev)
    await get_redis().publish(channel(task_id), json.dumps(out, default=str))
    return out


async def set_status(
    task_id: uuid.UUID, status: str, error: str | None = None, result: dict[str, Any] | None = None
) -> None:
    async with session_scope() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return
        task.status = status
        now = datetime.now(UTC)
        if status == "running" and task.started_at is None:
            task.started_at = now
        if status in TERMINAL:
            task.finished_at = now
        if error is not None:
            task.error = error
        if result is not None:
            task.result = _jsonable(result)
    await get_redis().publish(channel(task_id), json.dumps({"type": "status", "status": status}))


def serialize(ev: TaskEvent) -> dict[str, Any]:
    return {
        "id": ev.id,
        "task_id": str(ev.task_id),
        "type": ev.type,
        "node": ev.node,
        "payload": ev.payload,
        "created_at": (ev.created_at or datetime.now(UTC)).isoformat(),
    }


def _jsonable(obj: Any) -> Any:
    return json.loads(json.dumps(obj, default=str))


# Control flags checked by running workers between steps.
async def request_control(task_id: uuid.UUID, action: Literal["cancel", "pause"]) -> None:
    await get_redis().set(f"task:{task_id}:{action}", "1", ex=24 * 3600)


async def clear_control(task_id: uuid.UUID, action: Literal["cancel", "pause"]) -> None:
    await get_redis().delete(f"task:{task_id}:{action}")


async def control_requested(task_id: uuid.UUID, action: Literal["cancel", "pause"]) -> bool:
    return bool(await get_redis().exists(f"task:{task_id}:{action}"))
