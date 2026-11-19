"""Adzuna - official aggregator API (optional, needs a free API key).

Great fallback for Indeed-style coverage. Register at
https://developer.adzuna.com/ and put the keys in .env.
"""

from __future__ import annotations

import logging

from ..models import Job
from ..utils import is_remote, parse_date, strip_html
from .base import JobSource

logger = logging.getLogger(__name__)

API_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


class AdzunaSource(JobSource):
    name = "adzuna"

    def fetch(self) -> list[Job]:
        app_id = getattr(self.config, "adzuna_app_id", "")
        app_key = getattr(self.config, "adzuna_app_key", "")
        if not app_id or not app_key:
            logger.info("Adzuna skipped: missing ADZUNA_APP_ID / ADZUNA_APP_KEY")
            return []

        country = str(self.settings.get("country", "us"))
        jobs: list[Job] = []
        for query in self.queries:
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": 50,
                "what": query,
                "content-type": "application/json",
                "sort_by": "date",
            }
            try:
                payload = self.get_json(API_URL.format(country=country, page=1), params=params)
            except Exception as exc:
                logger.warning("Adzuna query %r failed: %s", query, exc)
                continue
            for item in payload.get("results", []) or []:
                location = (item.get("location") or {}).get("display_name", "")
                salary = _format_salary(item.get("salary_min"), item.get("salary_max"))
                jobs.append(
                    Job(
                        title=item.get("title", ""),
                        company=(item.get("company") or {}).get("display_name", ""),
                        url=item.get("redirect_url", ""),
                        source=self.name,
                        location=location,
                        description=strip_html(item.get("description", "")),
                        tags=[(item.get("category") or {}).get("label", "")],
                        salary=salary,
                        posted_at=parse_date(item.get("created")),
                        remote=is_remote(location),
                    )
                )
        return jobs


def _format_salary(low, high) -> str:
    if not low and not high:
        return ""
    if low and high:
        return f"${float(low):,.0f} - ${float(high):,.0f}"
    value = low or high
    return f"${float(value):,.0f}"
