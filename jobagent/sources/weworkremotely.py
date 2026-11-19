"""We Work Remotely - RSS feeds (one per category)."""

from __future__ import annotations

import feedparser

from ..models import Job
from ..utils import is_remote, parse_date, strip_html
from .base import JobSource

DEFAULT_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
]


class WeWorkRemotelySource(JobSource):
    name = "weworkremotely"

    def fetch(self) -> list[Job]:
        feeds = self.settings.get("feeds") or DEFAULT_FEEDS
        jobs: list[Job] = []
        for feed_url in feeds:
            try:
                parsed = feedparser.parse(self.get_text(feed_url))
            except Exception:
                continue  # one bad feed should not kill the source
            for entry in parsed.entries:
                title = entry.get("title", "")
                company = ""
                # WWR titles are usually "Company: Job title".
                if ":" in title:
                    company, title = title.split(":", 1)
                    company, title = company.strip(), title.strip()
                location = entry.get("location", "") or "Remote"
                tags = [t.get("term", "") for t in entry.get("tags", []) or []]
                jobs.append(
                    Job(
                        title=title,
                        company=company,
                        url=entry.get("link", ""),
                        source=self.name,
                        location=location,
                        description=strip_html(entry.get("summary", "")),
                        tags=[t for t in tags if t],
                        posted_at=parse_date(entry.get("published") or entry.get("updated")),
                        remote=is_remote(location, remote_flag=True),
                    )
                )
        return jobs
