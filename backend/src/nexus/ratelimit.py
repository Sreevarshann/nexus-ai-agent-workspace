"""Fixed-window rate limiter backed by Redis."""

from __future__ import annotations

import time

from fastapi import HTTPException, status

from nexus.config import get_settings
from nexus.redis import get_redis


async def enforce(key: str, limit: int, window_s: int) -> None:
    if not get_settings().rate_limits_enabled:
        return
    bucket = f"rl:{key}:{int(time.time() // window_s)}"
    r = get_redis()
    count = await r.incr(bucket)
    if count == 1:
        await r.expire(bucket, window_s)
    if count > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded, try again shortly")
