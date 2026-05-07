"""Async Redis client singleton.

Used for job URL deduplication (Phase 2), onboarding conversation state
(Phase 1), and alert rate-limiting (Phase 3). Managed by the FastAPI
lifespan hook like the Postgres pool.
"""

from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis
from loguru import logger

from app.config import get_settings

_client: Optional[aioredis.Redis] = None


async def init_redis() -> aioredis.Redis:
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    logger.info("Opening Redis client")
    _client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        logger.info("Closing Redis client")
        await _client.aclose()
        _client = None


def get_redis() -> aioredis.Redis:
    if _client is None:
        raise RuntimeError(
            "Redis client is not initialised. "
            "Did you forget to call init_redis() in the app lifespan?"
        )
    return _client


async def ping() -> bool:
    """Cheap liveness check for /health."""
    try:
        client = get_redis()
        pong = await client.ping()
        return bool(pong)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis ping failed: {}", exc)
        return False
