"""RemoteOK scraper — uses RemoteOK's public JSON API.

API: GET https://remoteok.com/api
Returns a JSON array; first element is a legal notice (skip it).
Rate limit: be polite — we scrape every 60 min with a User-Agent.

Salary is in USD/year. We store it in meta; salary_min/max_lpa is left
null since USD->LPA conversion is noisy without a live FX rate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.scraper.base import BaseJobScraper, JobData

_API_URL = "https://remoteok.com/api"
_HEADERS = {
    "User-Agent": "JobAlertBot/1.0 (github.com/jobsearcher; contact via bot)",
    "Accept": "application/json",
}


class RemoteOKScraper(BaseJobScraper):
    source = "remoteok"

    async def scrape(self) -> list[JobData]:
        resp = await self._client.get(_API_URL, headers=_HEADERS, timeout=30.0)
        resp.raise_for_status()
        data: list[dict] = resp.json()

        # First element is a legal/meta object — skip it
        jobs = [_parse_job(item) for item in data[1:] if isinstance(item, dict) and item.get("id")]
        logger.info("RemoteOK scrape complete | total={}", len(jobs))
        return jobs


def _parse_job(raw: dict[str, Any]) -> JobData:
    tags: list[str] = [t.lower().strip() for t in (raw.get("tags") or []) if t]

    date_str: str = raw.get("date") or ""
    posted_at: datetime | None = None
    if date_str:
        try:
            posted_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass

    url: str = raw.get("url") or f"https://remoteok.com/remote-jobs/{raw.get('id', '')}"
    if not url.startswith("http"):
        url = f"https://remoteok.com{url}"

    return JobData(
        source="remoteok",
        external_id=str(raw.get("id", "")),
        url=url,
        title=(raw.get("position") or "").strip(),
        company=(raw.get("company") or "").strip() or None,
        location=raw.get("location") or "Remote",
        is_remote=True,  # all RemoteOK jobs are remote
        skills=tags,
        posted_at=posted_at,
        meta={
            "salary_usd_min": raw.get("salary_min"),
            "salary_usd_max": raw.get("salary_max"),
        },
    )
