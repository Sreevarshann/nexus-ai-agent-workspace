"""Background job dispatch. arq/Redis in normal operation; inline asyncio tasks under NEXUS_ENV=test."""

from __future__ import annotations

import asyncio
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from nexus.config import get_settings

_pool: ArqRedis | None = None
_inline: set[asyncio.Task[Any]] = set()


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


async def enqueue(job: str, *args: Any, job_id: str | None = None) -> str | None:
    if get_settings().env == "test":
        from nexus import worker

        t = asyncio.create_task(getattr(worker, job)({}, *args))
        _inline.add(t)
        t.add_done_callback(_inline.discard)
        return job_id
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    j = await _pool.enqueue_job(job, *args, _job_id=job_id)
    return j.job_id if j else None


async def drain() -> None:
    """Test helper: wait for inline jobs to finish."""
    while _inline:
        await asyncio.gather(*list(_inline), return_exceptions=True)
