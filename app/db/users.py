"""User repository — asyncpg queries for the users table."""

from __future__ import annotations

import asyncpg
from telegram import User as TGUser

_VALID_EXPERIENCE = frozenset({"fresher", "0_2", "2_5", "5_10", "10_plus"})


async def upsert_user(conn: asyncpg.Connection, tg_user: TGUser) -> asyncpg.Record:
    """Insert or update a Telegram user row; returns selected columns."""
    return await conn.fetchrow(
        """
        INSERT INTO users (telegram_id, username, first_name)
        VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id) DO UPDATE
            SET username   = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                updated_at = NOW()
        RETURNING user_id, telegram_id, plan, paused, onboarded_at
        """,
        tg_user.id,
        tg_user.username,
        tg_user.first_name,
    )


async def get_user(conn: asyncpg.Connection, telegram_id: int) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT user_id, telegram_id, username, first_name,
               skills, cities, include_remote, experience,
               min_salary_lpa, plan, paused, onboarded_at
        FROM users WHERE telegram_id = $1
        """,
        telegram_id,
    )


async def update_skills(
    conn: asyncpg.Connection, telegram_id: int, skills: list[str]
) -> None:
    await conn.execute(
        "UPDATE users SET skills = $1, updated_at = NOW() WHERE telegram_id = $2",
        skills,
        telegram_id,
    )


async def update_cities(
    conn: asyncpg.Connection,
    telegram_id: int,
    cities: list[str],
    include_remote: bool,
) -> None:
    await conn.execute(
        """
        UPDATE users
        SET cities = $1, include_remote = $2, updated_at = NOW()
        WHERE telegram_id = $3
        """,
        cities,
        include_remote,
        telegram_id,
    )


async def update_experience(
    conn: asyncpg.Connection, telegram_id: int, experience: str
) -> None:
    if experience not in _VALID_EXPERIENCE:
        raise ValueError(f"Invalid experience value: {experience!r}")
    await conn.execute(
        "UPDATE users SET experience = $1, updated_at = NOW() WHERE telegram_id = $2",
        experience,
        telegram_id,
    )


async def set_paused(
    conn: asyncpg.Connection, telegram_id: int, paused: bool
) -> None:
    await conn.execute(
        "UPDATE users SET paused = $1, updated_at = NOW() WHERE telegram_id = $2",
        paused,
        telegram_id,
    )


async def get_active_users(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Return all non-paused users who have at least one skill set."""
    return await conn.fetch(
        """
        SELECT user_id, telegram_id, skills, cities, include_remote,
               experience, min_salary_lpa, plan
        FROM users
        WHERE paused = FALSE
          AND cardinality(skills) > 0
        """
    )
