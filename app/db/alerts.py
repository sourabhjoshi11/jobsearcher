"""Alerts repository — records jobs sent to users."""

from __future__ import annotations

import asyncpg


async def record_alert(
    conn: asyncpg.Connection, user_id: int, job_id: int
) -> bool:
    """Insert an alert record. Returns True if inserted, False if duplicate."""
    result = await conn.execute(
        """
        INSERT INTO alerts_sent (user_id, job_id)
        VALUES ($1, $2)
        ON CONFLICT (user_id, job_id) DO NOTHING
        """,
        user_id,
        job_id,
    )
    return result == "INSERT 0 1"
