"""Job matching engine.

For each active user (non-paused, has skills set), queries the jobs table
for recent listings that match their skills, location, and experience —
then sends Telegram alerts for any unseen matches.

Experience bands -> year ranges
-------------------------------
fresher  ->  0 – 0.5
0_2      ->  0 – 2
2_5      ->  2 – 5
5_10     ->  5 – 10
10_plus  -> 10 – 99
"""

from __future__ import annotations

import asyncpg
from loguru import logger
from telegram import Bot
from telegram.error import TelegramError

from app.db.alerts import record_alert
from app.db.users import get_active_users

_EXP_RANGES: dict[str, tuple[float, float]] = {
    "fresher": (0.0,  0.5),
    "0_2":     (0.0,  2.0),
    "2_5":     (2.0,  5.0),
    "5_10":    (5.0, 10.0),
    "10_plus": (10.0, 99.0),
}

_MAX_ALERTS_PER_CYCLE = 5   # per user per run
_JOBS_LOOKBACK_HOURS  = 24  # only match jobs scraped recently


async def run_matching_cycle(conn: asyncpg.Connection, bot: Bot) -> int:
    """Match new jobs to every active user and dispatch Telegram alerts.

    Returns total number of alerts sent.
    """
    users = await get_active_users(conn)
    if not users:
        logger.debug("Matching cycle: no active users with skills set")
        return 0

    total_sent = 0
    for user in users:
        try:
            sent = await _process_user(conn, bot, user)
            total_sent += sent
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Matching error | user_id={} error={}", user["user_id"], exc, exc_info=exc
            )

    logger.info("Matching cycle complete | users={} alerts_sent={}", len(users), total_sent)
    return total_sent


async def _process_user(
    conn: asyncpg.Connection, bot: Bot, user: asyncpg.Record
) -> int:
    exp_min, exp_max = _EXP_RANGES.get(user["experience"], (0.0, 99.0))
    jobs = await _find_matching_jobs(
        conn,
        user_id=user["user_id"],
        skills=list(user["skills"]),
        cities=list(user["cities"]),
        include_remote=user["include_remote"],
        exp_min=exp_min,
        exp_max=exp_max,
    )

    sent = 0
    for job in jobs[:_MAX_ALERTS_PER_CYCLE]:
        text = _format_alert(job)
        try:
            await bot.send_message(
                chat_id=user["telegram_id"],
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            await record_alert(conn, user["user_id"], job["job_id"])
            sent += 1
        except TelegramError as exc:
            logger.warning(
                "Alert send failed | telegram_id={} job_id={} error={}",
                user["telegram_id"], job["job_id"], exc,
            )

    return sent


async def _find_matching_jobs(
    conn: asyncpg.Connection,
    *,
    user_id: int,
    skills: list[str],
    cities: list[str],
    include_remote: bool,
    exp_min: float,
    exp_max: float,
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT
            j.job_id, j.source, j.url, j.title, j.company,
            j.location, j.is_remote, j.skills,
            j.experience_min, j.experience_max,
            j.salary_min_lpa, j.salary_max_lpa, j.posted_at
        FROM jobs j
        WHERE
            -- Not already sent to this user
            NOT EXISTS (
                SELECT 1 FROM alerts_sent a
                WHERE a.user_id = $1 AND a.job_id = j.job_id
            )
            -- Only recently scraped jobs
            AND j.scraped_at > NOW() - ($7 || ' hours')::INTERVAL
            -- Skills: job skills overlap user skills, OR job lists no skills
            AND (
                j.skills && $2::text[]
                OR cardinality(j.skills) = 0
            )
            -- Experience range overlap
            AND (j.experience_min IS NULL OR j.experience_min <= $4)
            AND (j.experience_max IS NULL OR j.experience_max >= $3)
            -- Location: remote match OR city substring match OR no city pref
            AND (
                ($5 AND j.is_remote)
                OR EXISTS (
                    SELECT 1 FROM unnest($6::text[]) AS city
                    WHERE j.location ILIKE ('%' || city || '%')
                )
                OR cardinality($6::text[]) = 0
            )
        ORDER BY j.posted_at DESC NULLS LAST
        LIMIT 10
        """,
        user_id,           # $1
        skills,            # $2
        exp_min,           # $3
        exp_max,           # $4
        include_remote,    # $5
        cities,            # $6
        str(_JOBS_LOOKBACK_HOURS),  # $7
    )


def _format_alert(job: asyncpg.Record) -> str:
    lines: list[str] = [f"<b>{job['title']}</b>"]

    if job["company"]:
        lines.append(f"🏢 {job['company']}")

    meta: list[str] = []
    if job["experience_min"] is not None or job["experience_max"] is not None:
        lo = f"{job['experience_min']:.0f}" if job["experience_min"] is not None else "0"
        hi = f"{job['experience_max']:.0f}" if job["experience_max"] is not None else "?"
        meta.append(f"💼 {lo}-{hi} yrs")
    if job["location"]:
        meta.append(f"📍 {job['location']}")
    if meta:
        lines.append("  ".join(meta))

    if job["salary_min_lpa"] or job["salary_max_lpa"]:
        lo = job["salary_min_lpa"] or "?"
        hi = job["salary_max_lpa"] or "?"
        lines.append(f"💰 {lo}-{hi} LPA")

    if job["skills"]:
        lines.append("🔧 " + ", ".join(job["skills"][:6]))

    lines.append(f'\n<a href="{job["url"]}">View Job →</a>')
    return "\n".join(lines)
