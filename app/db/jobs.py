"""Jobs repository — bulk upsert scraped listings.

Uses ON CONFLICT DO NOTHING on (source, url) so re-scraping the same
job is a safe no-op.  asyncpg's executemany batches all rows in one
round-trip for efficiency.

JSONB note: asyncpg requires explicit JSON encoding for JSONB columns.
We pass json.dumps(meta) and cast with ::jsonb in the query.
"""

from __future__ import annotations

import json

import asyncpg
from loguru import logger

from app.scraper.base import JobData


async def bulk_upsert_jobs(
    conn: asyncpg.Connection,
    jobs: list[JobData],
) -> None:
    """Insert new jobs; silently skip duplicates.

    Args:
        conn: Open asyncpg connection or pool proxy.
        jobs: Normalised job records from any scraper.
    """
    if not jobs:
        return

    rows = [
        (
            j.source,
            j.external_id,
            j.url,
            j.title,
            j.company,
            j.location,
            j.is_remote,
            j.skills,                       # TEXT[] — asyncpg handles Python list
            j.experience_min,
            j.experience_max,
            j.salary_min_lpa,
            j.salary_max_lpa,
            j.description,
            j.posted_at,
            json.dumps(j.meta),             # JSONB — must be serialised string
        )
        for j in jobs
    ]

    await conn.executemany(
        """
        INSERT INTO jobs (
            source, external_id, url, title, company,
            location, is_remote, skills,
            experience_min, experience_max,
            salary_min_lpa, salary_max_lpa,
            description, posted_at, meta
        )
        VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8,
            $9, $10,
            $11, $12,
            $13, $14, $15::jsonb
        )
        ON CONFLICT (source, url) DO NOTHING
        """,
        rows,
    )
    logger.info("bulk_upsert_jobs | source={} attempted={}", jobs[0].source, len(jobs))
