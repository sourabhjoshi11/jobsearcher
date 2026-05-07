"""Async Postgres connection pool.

We use a module-level singleton pool that is initialised in the FastAPI
lifespan hook and closed on shutdown. Every query path should go through
`get_pool()` so we never open ad-hoc connections.
"""

from __future__ import annotations

from typing import Optional

import asyncpg
from loguru import logger

from app.config import get_settings

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> asyncpg.Pool:
    """Create the global pool. Safe to call multiple times."""
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings()
    logger.info("Opening Postgres pool")
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=1,
        max_size=10,
        command_timeout=30,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        logger.info("Closing Postgres pool")
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the live pool. Raises if init_pool() was not called yet."""
    if _pool is None:
        raise RuntimeError(
            "Postgres pool is not initialised. "
            "Did you forget to call init_pool() in the app lifespan?"
        )
    return _pool


async def ping() -> bool:
    """Cheap liveness check for /health. Returns True on success."""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            return result == 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres ping failed: {}", exc)
        return False
