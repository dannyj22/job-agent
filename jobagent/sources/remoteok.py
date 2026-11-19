"""Remote OK - public JSON API. https://remoteok.com/api"""

from __future__ import annotations

from ..models import Job
from ..utils import is_remote, parse_date, strip_html
from .base import JobSource

API_URL = "https://remoteok.com/api"


class RemoteOKSource(JobSource):
    name = "remoteok"

    def fetch(self) -> list[Job]:
        payload = self.get_json(API_URL)
        jobs: list[Job] = []
        for item in payload:
            if not isinstance(item, dict) or "position" not in item:
                continue  # first element is the legal notice
            slug = item.get("slug") or item.get("id") or ""
            url = item.get("url") or f"https://remoteok.com/remote-jobs/{slug}"
            salary = _format_salary(item.get("salary_min"), item.get("salary_max"))
            location = item.get("location") or "Remote"
            jobs.append(
                Job(
                    title=item.get("position", ""),
                    company=item.get("company", ""),
                    url=url,
                    source=self.name,
                    location=location,
                    description=strip_html(item.get("description", "")),
                    tags=[str(t) for t in item.get("tags", []) or []],
                    salary=salary,
                    posted_at=parse_date(item.get("date") or item.get("epoch")),
                    remote=is_remote(location, remote_flag=True),
                )
            )
        return jobs


def _format_salary(low, high) -> str:
    if not low and not high:
        return ""
    try:
        low_i = int(float(low or 0))
        high_i = int(float(high or 0))
    except (TypeError, ValueError):
        return ""
    if low_i and high_i:
        return f"${low_i:,} - ${high_i:,}"
    value = low_i or high_i
    return f"${value:,}" if value else ""
