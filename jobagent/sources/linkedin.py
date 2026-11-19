"""LinkedIn public guest search endpoint.

Note: this uses LinkedIn's unauthenticated jobs-guest endpoint. It is fragile
and subject to LinkedIn's terms; keep request volume low and expect periodic
breakage.
"""

from __future__ import annotations

import logging
import re
import time

from bs4 import BeautifulSoup

from ..models import Job
from ..utils import is_remote, parse_date
from .base import JobSource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
JOB_URL = "https://www.linkedin.com/jobs/view/{id}"


class LinkedInSource(JobSource):
    name = "linkedin"

    def fetch(self) -> list[Job]:
        location = str(self.settings.get("location", "Remote"))
        max_per_query = int(self.settings.get("max_per_query", 25))
        delay = float(self.settings.get("delay_seconds", 2))
        jobs: list[Job] = []

        for index, query in enumerate(self.queries):
            if index:
                time.sleep(delay)
            params = {
                "keywords": query,
                "location": location,
                "start": 0,
                "f_TPR": "r604800",  # posted in the last 7 days
                "f_WT": "2",  # remote workplace type
            }
            try:
                html = self.get_text(SEARCH_URL, params=params)
            except Exception as exc:
                logger.warning("LinkedIn query %r failed: %s", query, exc)
                continue
            jobs.extend(_parse_cards(html, self.name)[:max_per_query])

        return _dedupe(jobs)


def _parse_cards(html: str, source: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    for card in soup.select("li"):
        urn = card.get("data-entity-urn") or ""
        match = re.search(r"jobPosting:(\d+)", urn)
        link = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")
        if not match and link and link.get("href"):
            match = re.search(r"/jobs/view/[^/]*?(\d{6,})", link["href"])
        if not match:
            continue
        job_id = match.group(1)

        title_el = (
            card.select_one(".sr-only")
            or card.select_one(".base-search-card__title")
            or card.select_one("h3")
        )
        company_el = card.select_one(".base-search-card__subtitle") or card.select_one("h4")
        location_el = card.select_one(".job-search-card__location")
        time_el = card.select_one("time")

        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not title:
            continue
        location = location_el.get_text(" ", strip=True) if location_el else ""
        jobs.append(
            Job(
                title=title,
                company=company_el.get_text(" ", strip=True) if company_el else "",
                url=JOB_URL.format(id=job_id),
                source=source,
                location=location,
                posted_at=parse_date(time_el.get("datetime")) if time_el else None,
                remote=is_remote(location),
            )
        )
    return jobs


def _dedupe(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        if job.fingerprint in seen:
            continue
        seen.add(job.fingerprint)
        unique.append(job)
    return unique
