"""Mission execution with durable LangGraph checkpoints (Postgres).

* start:   run from the initial state
* resume:  answer a pending approval interrupt (``Command(resume=...)``)
* retry:   continue from the last successful checkpoint after a failure or pause (``ainvoke(None)``)
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import select

from nexus.agents.graph import MissionCancelled, PauseRequested, build_graph
from nexus.config import get_settings
from nexus.db import session_scope
from nexus.events import clear_control, emit, set_status
from nexus.logging import log
from nexus.models import Message, Task, WorkflowRun
from nexus.workflows.engine import build_workflow_graph

_memory_saver: InMemorySaver | None = None


@asynccontextmanager
async def checkpointer() -> AsyncIterator[Any]:
    s = get_settings()
    if s.env == "test":
        global _memory_saver
        _memory_saver = _memory_saver or InMemorySaver()
        yield _memory_saver
        return
    async with AsyncPostgresSaver.from_conn_string(s.psycopg_url) as saver:
        yield saver


async def setup_checkpointer() -> None:
    if get_settings().env == "test":
        return
    async with checkpointer() as saver:
        await saver.setup()


async def run_mission(task_id: uuid.UUID, *, resume: Any = None, retry: bool = False) -> str:
    """Drive the graph until it finishes, fails, pauses or waits for approval. Returns the final status."""
    async with session_scope() as db:
        task = await db.get(Task, task_id)
        if task is None:
            return "missing"
        initial = {
            "task_id": str(task.id),
            "user_id": str(task.user_id),
            "mode": task.mode,
            "prompt": task.prompt,
            "options": {**task.options, "project_id": str(task.project_id) if task.project_id else None},
            "errors": [],
        }
        conversation_id = task.conversation_id
        kind = task.kind
        if kind == "workflow":
            run_row = (await db.execute(select(WorkflowRun).where(WorkflowRun.task_id == task_id))).scalar()
            if run_row is None:
                return "missing"
            snapshot = run_row.graph_snapshot
            initial = {
                "task_id": str(task.id),
                "user_id": str(task.user_id),
                "input": task.prompt,
                "outputs": {},
                "errors": [],
            }

    s = get_settings()
    config = {"configurable": {"thread_id": str(task_id)}, "recursion_limit": s.mission_max_steps}
    await clear_control(task_id, "pause")
    async with checkpointer() as saver:
        builder = build_workflow_graph(snapshot) if kind == "workflow" else build_graph()
        graph = builder.compile(checkpointer=saver)
        if resume is not None:
            inp: Any = Command(resume=resume)
            await emit(task_id, "resumed", reason="approval")
        elif retry:
            inp = None
            await emit(task_id, "resumed", reason="retry")
        else:
            inp = initial
            await emit(
                task_id, "task_started", kind=kind, mode=initial.get("mode", "workflow"), prompt=task_prompt(initial)
            )
        await set_status(task_id, "running")
        try:
            await graph.ainvoke(inp, config)
        except PauseRequested as e:
            await set_status(task_id, "paused")
            await emit(task_id, "paused", before_node=str(e))
            return "paused"
        except (MissionCancelled, asyncio.CancelledError) as e:
            reason = str(e) if isinstance(e, MissionCancelled) and str(e) else "Cancelled by user"
            await set_status(task_id, "cancelled", error=reason)
            await emit(task_id, "task_cancelled", reason=reason)
            await clear_control(task_id, "cancel")
            await _update_message(conversation_id, task_id, f"Mission cancelled: {reason}", "cancelled")
            if isinstance(e, asyncio.CancelledError):
                raise
            return "cancelled"
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"[:2000]
            log.exception("mission_failed", task_id=str(task_id))
            await set_status(task_id, "failed", error=msg)
            await emit(task_id, "task_failed", error=msg)
            await _update_message(conversation_id, task_id, f"Mission failed: {msg}", "error")
            return "failed"

        snap = await graph.aget_state(config)
        pending = [i.value for t in snap.tasks for i in (t.interrupts or ())]
        if pending:
            await set_status(task_id, "waiting_approval")
            await emit(task_id, "approval_required", node="approval", request=pending[0])
            return "waiting_approval"

        values = snap.values
        ver = values.get("verification") or {}
        result = {
            "artifact_id": values.get("artifact_id"),
            "summary": _summary(values.get("report", "")),
            "sources": len(values.get("evidence", [])),
            "errors": values.get("errors", [])[:20],
            "verification": {k: ver.get(k) for k in ("claims_checked", "supported", "weak", "unsupported")}
            if ver
            else None,
        }
        await set_status(task_id, "completed", result=result)
        await emit(task_id, "task_completed", **result)
        await _update_message(
            conversation_id,
            task_id,
            values.get("report", ""),
            "complete",
            artifact_id=values.get("artifact_id"),
            evidence=values.get("evidence", []),
        )
        return "completed"


def task_prompt(state: dict[str, Any]) -> str:
    return str(state.get("prompt") or state.get("input") or "")


def _summary(report: str) -> str:
    body = report.split("## ", 2)
    section = body[1] if len(body) > 1 else report
    return section.split("\n", 1)[-1].strip()[:1200]


async def _update_message(
    conversation_id: uuid.UUID | None,
    task_id: uuid.UUID,
    content: str,
    status: str,
    artifact_id: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> None:
    """Agent-mode chat messages mirror the mission outcome."""
    if conversation_id is None:
        return
    async with session_scope() as db:
        rows = (
            (
                await db.execute(
                    select(Message).where(Message.conversation_id == conversation_id, Message.role == "assistant")
                )
            )
            .scalars()
            .all()
        )
        for m in rows:
            if (m.meta or {}).get("task_id") == str(task_id):
                m.content = content
                m.status = status
                cites = [
                    {k: v for k, v in e.items() if k != "text"} | {"excerpt": e["text"][:500]}
                    for e in (evidence or [])
                    if f"[{e['label']}]" in content
                ]
                m.citations = cites
                m.meta = {**m.meta, "artifact_id": artifact_id}
