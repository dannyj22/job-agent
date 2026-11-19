"""Jobicy - public JSON API. https://jobicy.com/api/v2/remote-jobs"""

from __future__ import annotations

from ..models import Job
from ..utils import is_remote, parse_date, strip_html
from .base import JobSource

API_URL = "https://jobicy.com/api/v2/remote-jobs"


class JobicySource(JobSource):
    name = "jobicy"

    def fetch(self) -> list[Job]:
        count = int(self.settings.get("count", 50))
        payload = self.get_json(API_URL, params={"count": count})
        jobs: list[Job] = []
        for item in payload.get("jobs", []) or []:
            if not isinstance(item, dict):
                continue
            location = item.get("jobGeo") or "Remote"
            tags = item.get("jobIndustry") or []
            if isinstance(tags, str):
                tags = [tags]
            salary = _format_salary(
                item.get("annualSalaryMin"), item.get("annualSalaryMax"),
                item.get("salaryCurrency"),
            )
            jobs.append(
                Job(
                    title=item.get("jobTitle", ""),
                    company=item.get("companyName", ""),
                    url=item.get("url", ""),
                    source=self.name,
                    location=location,
                    description=strip_html(
                        item.get("jobDescription") or item.get("jobExcerpt") or ""
                    ),
                    tags=[str(t) for t in tags],
                    salary=salary,
                    posted_at=parse_date(item.get("pubDate")),
                    remote=is_remote(location, remote_flag=True),
                )
            )
        return jobs


def _format_salary(low, high, currency) -> str:
    if not low and not high:
        return ""
    currency = currency or ""
    if low and high:
        return f"{currency} {low} - {high}".strip()
    return f"{currency} {low or high}".strip()
