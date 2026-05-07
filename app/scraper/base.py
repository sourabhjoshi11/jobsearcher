"""Shared data model and abstract base for all job scrapers.

Every scraper must:
  1. Subclass BaseJobScraper
  2. Set the class-level `source` string (e.g. "naukri")
  3. Implement `scrape() -> list[JobData]`

This keeps the scheduler and DB layer source-agnostic — new platforms are a
single new file under app/scraper/sources/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

import httpx


@dataclass
class JobData:
    """Normalised job record produced by every scraper.

    Fields map directly to the `jobs` DB table so the upsert layer
    needs no source-specific logic.
    """

    source: str
    url: str                            # canonical, absolute URL (unique key with source)
    title: str
    company: str | None = None
    location: str | None = None         # raw location string from the source
    is_remote: bool = False
    skills: list[str] = field(default_factory=list)
    experience_min: float | None = None # years
    experience_max: float | None = None
    salary_min_lpa: float | None = None # Indian LPA (Lakhs Per Annum)
    salary_max_lpa: float | None = None
    description: str | None = None
    posted_at: datetime | None = None
    external_id: str | None = None      # source's native job ID, if exposed
    meta: dict = field(default_factory=dict)


class BaseJobScraper(ABC):
    """All job scrapers must subclass this."""

    source: ClassVar[str]  # overridden by each subclass, e.g. "naukri"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @abstractmethod
    async def scrape(self) -> list[JobData]:
        """Fetch and return normalised job listings for one scrape cycle."""
