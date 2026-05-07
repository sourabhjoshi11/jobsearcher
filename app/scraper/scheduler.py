"""APScheduler wiring for periodic scrape + match jobs.

Jobs
----
naukri_scrape  — every 30 min
remoteok_scrape — every 60 min  (added in Phase 6)
run_matching   — every 30 min, offset 5 min after startup

Adding a new scraper source
---------------------------
1. Create app/scraper/sources/<name>.py with a BaseJobScraper subclass.
2. Add a _run_<name> coroutine below.
3. Register it with _scheduler.add_job() inside get_scheduler().
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from app.db import connection as db
from app.db.jobs import bulk_upsert_jobs
from app.scraper.sources.naukri import NaukriScraper
from app.scraper.sources.remoteok import RemoteOKScraper

_scheduler: AsyncIOScheduler | None = None


# ---------------------------------------------------------------------------
# Scrape jobs
# ---------------------------------------------------------------------------

async def _run_naukri() -> None:
    logger.info("Scrape job started | source=naukri")
    try:
        async with httpx.AsyncClient() as client:
            jobs = await NaukriScraper(client).scrape()
        async with db.get_pool().acquire() as conn:
            await bulk_upsert_jobs(conn, jobs)
        logger.info("Scrape job complete | source=naukri total={}", len(jobs))
    except Exception as exc:  # noqa: BLE001
        logger.error("Scrape job failed | source=naukri error={}", exc, exc_info=exc)


async def _run_remoteok() -> None:
    logger.info("Scrape job started | source=remoteok")
    try:
        async with httpx.AsyncClient() as client:
            jobs = await RemoteOKScraper(client).scrape()
        async with db.get_pool().acquire() as conn:
            await bulk_upsert_jobs(conn, jobs)
        logger.info("Scrape job complete | source=remoteok total={}", len(jobs))
    except Exception as exc:  # noqa: BLE001
        logger.error("Scrape job failed | source=remoteok error={}", exc, exc_info=exc)



# ---------------------------------------------------------------------------
# Matching job
# ---------------------------------------------------------------------------

async def _run_matching() -> None:
    logger.info("Matching job started")
    try:
        from app.bot.application import get_application
        from app.matching.engine import run_matching_cycle

        bot = get_application().bot
        async with db.get_pool().acquire() as conn:
            sent = await run_matching_cycle(conn, bot)
        logger.info("Matching job complete | alerts_sent={}", sent)
    except RuntimeError:
        # Bot not initialised yet (e.g. no token set) — skip silently
        logger.debug("Matching job skipped — bot not initialised")
    except Exception as exc:  # noqa: BLE001
        logger.error("Matching job failed | error={}", exc, exc_info=exc)


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    now = datetime.now(tz=timezone.utc)
    _scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    _scheduler.add_job(
        _run_naukri,
        trigger=IntervalTrigger(minutes=30),
        id="naukri_scrape",
        name="Naukri scraper",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now + timedelta(seconds=10),  # first run 10s after start
    )

    _scheduler.add_job(
        _run_remoteok,
        trigger=IntervalTrigger(minutes=60),
        id="remoteok_scrape",
        name="RemoteOK scraper",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now + timedelta(minutes=2),
    )


    _scheduler.add_job(
        _run_matching,
        trigger=IntervalTrigger(minutes=30),
        id="run_matching",
        name="Job matcher",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
        next_run_time=now + timedelta(minutes=5),   # first run 5 min after scraper
    )

    return _scheduler


def start_scheduler() -> None:
    sched = get_scheduler()
    sched.start()
    logger.info("Scheduler started | jobs={}", [j.id for j in sched.get_jobs()])


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None
