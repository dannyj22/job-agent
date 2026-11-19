"""Remotive - public JSON API. https://remotive.com/api/remote-jobs"""

from __future__ import annotations

from ..models import Job
from ..utils import is_remote, parse_date, strip_html
from .base import JobSource

API_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(JobSource):
    name = "remotive"

    def fetch(self) -> list[Job]:
        limit = int(self.settings.get("limit", 120))
        payload = self.get_json(API_URL, params={"limit": limit})
        jobs: list[Job] = []
        for item in payload.get("jobs", []) or []:
            if not isinstance(item, dict):
                continue
            location = item.get("candidate_required_location") or "Remote"
            jobs.append(
                Job(
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    url=item.get("url", ""),
                    source=self.name,
                    location=location,
                    description=strip_html(item.get("description", "")),
                    tags=[str(t) for t in item.get("tags", []) or []],
                    salary=item.get("salary") or "",
                    posted_at=parse_date(item.get("publication_date")),
                    remote=is_remote(location, remote_flag=True),
                )
            )
        return jobs
