"""Indeed - best-effort adapter.

Indeed no longer serves a public RSS feed and its HTML pages return a captcha
(HTTP 403) to datacenter IPs. This adapter still tries, and fails softly, so
the rest of the run is unaffected. Set INDEED_PROXY in .env to route through a
residential proxy, or enable the Adzuna source for similar coverage.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from ..models import Job
from ..utils import is_remote, parse_date
from .base import JobSource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.indeed.com/jobs"
RSS_URL = "https://www.indeed.com/rss"


class IndeedSource(JobSource):
    name = "indeed"

    def __init__(self, config, session=None) -> None:
        super().__init__(config, session)
        if getattr(config, "indeed_proxy", ""):
            self.session.proxies.update(
                {"http": config.indeed_proxy, "https": config.indeed_proxy}
            )
        self._blocked = False

    def fetch(self) -> list[Job]:
        if self._blocked:
            return []
        location = str(self.settings.get("location", "Remote"))
        jobs: list[Job] = []
        for query in self.queries:
            jobs.extend(self._fetch_query(query, location))
            if self._blocked:
                break
        return jobs

    def _fetch_query(self, query: str, location: str) -> list[Job]:
        # 1) RSS is cheapest when it is available.
        try:
            text = self.get_text(RSS_URL, params={"q": query, "l": location})
            if "<rss" in text[:500]:
                return _parse_rss(text, self.name)
        except Exception:
            pass

        # 2) HTML fallback.
        try:
            html = self.get_text(SEARCH_URL, params={"q": query, "l": location, "sort": "date"})
        except Exception as exc:
            logger.info("Indeed HTML unavailable: %s", exc)
            return []
        if _looks_blocked(html):
            self._blocked = True
            logger.warning(
                "Indeed is blocking requests (captcha/403). Skipping it for this run. "
                "Set INDEED_PROXY or use the Adzuna source."
            )
            return []
        return _parse_html(html, self.name)


def _looks_blocked(html: str) -> bool:
    lowered = html.lower()
    return "captcha" in lowered or "just a moment" in lowered or "verify you are human" in lowered


def _parse_rss(text: str, source: str) -> list[Job]:
    import feedparser

    parsed = feedparser.parse(text)
    jobs: list[Job] = []
    for entry in parsed.entries:
        location = entry.get("location", "")
        jobs.append(
            Job(
                title=entry.get("title", ""),
                company=entry.get("company", ""),
                url=entry.get("link", ""),
                source=source,
                location=location,
                description=entry.get("summary", ""),
                posted_at=parse_date(entry.get("published")),
                remote=is_remote(location),
            )
        )
    return jobs


def _parse_html(html: str, source: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    for card in soup.select("div.job_seen_beacon, div.jobsearch-SerpJobCard, li.css-5lfssm"):
        link = card.select_one("h2 a") or card.select_one("a[href*='jk=']")
        if not link:
            continue
        href = link.get("href", "")
        job_key = _job_key(href)
        if not job_key:
            continue
        title = link.get_text(" ", strip=True)
        company_el = card.select_one("[data-testid='company-name'], .companyName")
        location_el = card.select_one("[data-testid='text-location'], .companyLocation")
        date_el = card.select_one("[data-testid='myJobsStateDate'], .date")
        location = location_el.get_text(" ", strip=True) if location_el else ""
        jobs.append(
            Job(
                title=title,
                company=company_el.get_text(" ", strip=True) if company_el else "",
                url=f"https://www.indeed.com/viewjob?jk={job_key}",
                source=source,
                location=location,
                posted_at=parse_date(date_el.get_text(" ", strip=True)) if date_el else None,
                remote=is_remote(location),
            )
        )
    return jobs


def _job_key(href: str) -> str:
    match = re.search(r"[?&]jk=([a-f0-9]+)", href)
    if match:
        return match.group(1)
    match = re.search(r"/viewjob/([a-f0-9]+)", href)
    return match.group(1) if match else ""
