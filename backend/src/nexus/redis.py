"""Shared async Redis client."""

from __future__ import annotations

from redis.asyncio import Redis

from nexus.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def set_redis(client: Redis | None) -> None:
    """Override the client (tests use fakeredis)."""
    global _client
    _client = client
