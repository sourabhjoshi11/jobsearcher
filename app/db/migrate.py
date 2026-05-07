"""Tiny SQL migration runner.

Applies every `*.sql` file in `app/db/migrations/` in filename order and
records applied files in a `schema_migrations` table so re-runs skip
already-applied migrations.

Run with: `python -m app.db.migrate`
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg
from loguru import logger

from app.config import get_settings
from app.logging_setup import configure_logging

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def _ensure_meta_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename    TEXT         PRIMARY KEY,
            applied_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
        """
    )


async def _already_applied(conn: asyncpg.Connection, filename: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM schema_migrations WHERE filename = $1", filename
    )
    return row is not None


async def _apply(conn: asyncpg.Connection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    # Wrap each migration in a transaction so a failing file can't leave
    # the schema half-applied. `asyncpg` doesn't auto-tx multi-statement
    # execute() calls, so we do it explicitly here.
    async with conn.transaction():
        await conn.execute(sql)
        await conn.execute(
            "INSERT INTO schema_migrations (filename) VALUES ($1)", path.name
        )
    logger.info("Applied migration: {}", path.name)


async def run() -> int:
    configure_logging()
    settings = get_settings()

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        logger.warning("No migration files found in {}", MIGRATIONS_DIR)
        return 0

    logger.info("Connecting to {}", _sanitise_dsn(settings.database_url))
    conn = await asyncpg.connect(settings.database_url)
    try:
        await _ensure_meta_table(conn)

        applied = 0
        for path in files:
            if await _already_applied(conn, path.name):
                logger.debug("Skip (already applied): {}", path.name)
                continue
            await _apply(conn, path)
            applied += 1

        logger.info("Migration run complete: {} applied, {} total on disk",
                    applied, len(files))
        return applied
    finally:
        await conn.close()


def _sanitise_dsn(dsn: str) -> str:
    """Strip password from DSN so it's safe to log."""
    try:
        # postgresql://user:pass@host:port/db -> postgresql://user:***@host:port/db
        before_at, at, rest = dsn.rpartition("@")
        if not at:
            return dsn
        scheme_user, _, _password = before_at.rpartition(":")
        return f"{scheme_user}:***@{rest}"
    except Exception:  # noqa: BLE001
        return "<dsn hidden>"


if __name__ == "__main__":
    try:
        applied = asyncio.run(run())
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        logger.error("Migration failed: {}", exc)
        sys.exit(1)
