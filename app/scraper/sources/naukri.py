"""Naukri.com scraper — uses Naukri's internal search JSON API.

Naukri exposes a JSON search endpoint used by their own frontend.
We set the required app headers and paginate through results.

Rate-limiting: we scrape every 30 min (configured in scheduler.py) and
add a short delay between search iterations — conservative enough to
avoid triggering blocks.

Adding more keyword/experience combos: edit _SEARCHES below.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.scraper.base import BaseJobScraper, JobData

_BASE_URL = "https://www.naukri.com"
_SEARCH_URL = f"{_BASE_URL}/jobapi/v3/search"

_HEADERS = {
    "appid": "109",
    "systemid": "Naukri",
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Each entry: (keyword, exp_min_years, exp_max_years)
# Tune this list to control what gets scraped each cycle.
_SEARCHES: list[tuple[str, int, int]] = [
    ("software developer", 0, 2),
    ("software developer", 2, 5),
    ("python developer", 0, 5),
    ("java developer", 0, 5),
    ("data engineer", 0, 5),
    ("backend developer", 0, 5),
    ("frontend developer react", 0, 5),
    ("full stack developer", 0, 5),
    ("devops engineer", 0, 5),
    ("machine learning engineer", 0, 5),
]

_RESULTS_PER_SEARCH = 20   # Naukri cap per request
_INTER_REQUEST_DELAY = 1.5  # seconds between API calls


class NaukriScraper(BaseJobScraper):
    source = "naukri"

    async def scrape(self) -> list[JobData]:
        jobs: list[JobData] = []
        for keyword, exp_min, exp_max in _SEARCHES:
            try:
                batch = await self._search(keyword, exp_min, exp_max)
                jobs.extend(batch)
                logger.debug(
                    "Naukri | keyword={!r} exp={}-{} fetched={}",
                    keyword, exp_min, exp_max, len(batch),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Naukri | keyword={!r} exp={}-{} error: {}",
                    keyword, exp_min, exp_max, exc,
                )
            await asyncio.sleep(_INTER_REQUEST_DELAY)

        logger.info("Naukri scrape complete | total_jobs={}", len(jobs))
        return jobs

    async def _search(
        self, keyword: str, exp_min: int, exp_max: int
    ) -> list[JobData]:
        params = {
            "noOfResults": _RESULTS_PER_SEARCH,
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": keyword,
            "experience": exp_min,
            "location": "india",
        }
        resp = await self._client.get(
            _SEARCH_URL,
            params=params,
            headers=_HEADERS,
            timeout=20.0,
        )
        resp.raise_for_status()
        data: dict = resp.json()
        return [
            _parse_job(raw)
            for raw in (data.get("jobDetails") or [])
            if raw
        ]


# ---------------------------------------------------------------------------
# Parsing helpers (module-level so they are easily unit-testable)
# ---------------------------------------------------------------------------

def _parse_job(raw: dict[str, Any]) -> JobData:
    # Canonical URL
    jd_path: str = raw.get("jdURL") or ""
    url = jd_path if jd_path.startswith("http") else f"{_BASE_URL}{jd_path}"

    # Skills
    tags_str: str = raw.get("tagsAndSkills") or ""
    skills = [s.strip().lower() for s in tags_str.split(",") if s.strip()]

    # Placeholders carry location, salary, and other display fields
    placeholders: list[dict] = raw.get("placeholders") or []
    ph: dict[str, str] = {p.get("type", ""): p.get("label", "") for p in placeholders}
    location: str | None = ph.get("location") or None
    sal_min, sal_max = _parse_salary_lpa(ph.get("salary", ""))

    # Posted-at: Naukri returns millisecond epoch
    ts_ms: int | None = raw.get("createdDate")
    posted_at = (
        datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc) if ts_ms else None
    )

    is_remote = bool(location and "remote" in location.lower())

    return JobData(
        source="naukri",
        external_id=str(raw.get("jobId") or ""),
        url=url,
        title=(raw.get("title") or "").strip(),
        company=(raw.get("companyName") or "").strip() or None,
        location=location,
        is_remote=is_remote,
        skills=skills,
        experience_min=_to_float(raw.get("minimumExperience")),
        experience_max=_to_float(raw.get("maximumExperience")),
        salary_min_lpa=sal_min,
        salary_max_lpa=sal_max,
        description=(raw.get("jobDescription") or "").strip() or None,
        posted_at=posted_at,
    )


def _to_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _parse_salary_lpa(s: str) -> tuple[float | None, float | None]:
    """Extract (min_lpa, max_lpa) from strings like '3-5 Lacs PA' or '8-12 Lacs'."""
    if not s:
        return None, None
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if len(nums) >= 2:
        return float(nums[0]), float(nums[1])
    if len(nums) == 1:
        return float(nums[0]), None
    return None, None
