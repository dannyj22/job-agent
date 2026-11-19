"""Arbeitnow - public JSON job board API."""

from __future__ import annotations

from ..models import Job
from ..utils import is_remote, parse_date, strip_html
from .base import JobSource

API_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource(JobSource):
    name = "arbeitnow"

    def fetch(self) -> list[Job]:
        pages = int(self.settings.get("pages", 2))
        jobs: list[Job] = []
        for page in range(1, pages + 1):
            payload = self.get_json(API_URL, params={"page": page})
            rows = payload.get("data", []) or []
            if not rows:
                break
            for item in rows:
                if not isinstance(item, dict):
                    continue
                location = item.get("location") or ""
                jobs.append(
                    Job(
                        title=item.get("title", ""),
                        company=item.get("company_name", ""),
                        url=item.get("url", ""),
                        source=self.name,
                        location=location,
                        description=strip_html(item.get("description", "")),
                        tags=[str(t) for t in item.get("tags", []) or []],
                        posted_at=parse_date(item.get("created_at")),
                        remote=is_remote(location, remote_flag=bool(item.get("remote"))),
                    )
                )
        return jobs
