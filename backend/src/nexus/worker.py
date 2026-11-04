"""arq worker: missions, workflow runs and document ingestion run here, independent of any browser tab."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from nexus.agents.runner import run_mission, setup_checkpointer
from nexus.config import get_settings
from nexus.events import control_requested
from nexus.jobs import redis_settings
from nexus.logging import configure_logging, log
from nexus.rag.ingest import ingest_document


async def _with_cancel_watch(task_id: uuid.UUID, coro: Any) -> Any:
    """Run ``coro`` and cancel it promptly (even mid-LLM-call) when a cancel flag appears."""
    work = asyncio.ensure_future(coro)

    async def watch() -> None:
        while not work.done():
            if await control_requested(task_id, "cancel"):
                work.cancel()
                return
            await asyncio.sleep(0.5)

    watcher = asyncio.create_task(watch())
    try:
        return await work
    except asyncio.CancelledError:
        if watcher.done():
            return "cancelled"  # cancelled on request; runner already recorded it
        raise
    finally:
        watcher.cancel()


async def run_task(ctx: dict[str, Any], task_id: str) -> str:
    return str(await _with_cancel_watch(uuid.UUID(task_id), run_mission(uuid.UUID(task_id))))


async def resume_task(ctx: dict[str, Any], task_id: str, decision: dict[str, Any]) -> str:
    return str(await _with_cancel_watch(uuid.UUID(task_id), run_mission(uuid.UUID(task_id), resume=decision)))


async def retry_task(ctx: dict[str, Any], task_id: str) -> str:
    return str(await _with_cancel_watch(uuid.UUID(task_id), run_mission(uuid.UUID(task_id), retry=True)))


async def ingest(ctx: dict[str, Any], document_id: str) -> None:
    await ingest_document(uuid.UUID(document_id))


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    await setup_checkpointer()
    log.info("worker_started", env=get_settings().env)


class WorkerSettings:
    functions = [run_task, resume_task, retry_task, ingest]
    on_startup = startup
    redis_settings = redis_settings()
    max_jobs = 4
    job_timeout = 1800
    max_tries = 1  # missions are retried explicitly from their checkpoint, never blindly re-run
    allow_abort_jobs = True
