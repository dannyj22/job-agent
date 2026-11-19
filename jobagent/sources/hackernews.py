"""Hacker News "Who is hiring?" monthly thread via the Algolia API."""

from __future__ import annotations

from ..models import Job
from ..utils import parse_date, strip_html, truncate
from .base import JobSource

SEARCH_URL = "https://hn.algolia.com/api/v1/search"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"
THREAD_URL = "https://news.ycombinator.com/item?id={id}"


class HackerNewsSource(JobSource):
    name = "hackernews"

    def fetch(self) -> list[Job]:
        payload = self.get_json(
            SEARCH_URL,
            params={
                "query": '"Who is hiring?"',
                "tags": "story",
                "hitsPerPage": 20,
            },
        )
        story = next(
            (
                hit
                for hit in payload.get("hits", [])
                if str(hit.get("title", "")).startswith("Ask HN: Who is hiring?")
            ),
            None,
        )
        if not story:
            return []

        thread = self.get_json(ITEM_URL.format(id=story["objectID"]))
        limit = int(self.settings.get("max_comments", 120))
        jobs: list[Job] = []
        for comment in (thread.get("children") or [])[:limit]:
            text = strip_html(comment.get("text") or "")
            if len(text) < 40:
                continue
            company, title = _split_header(text)
            jobs.append(
                Job(
                    title=title,
                    company=company,
                    url=THREAD_URL.format(id=comment.get("id")),
                    source=self.name,
                    location=_guess_location(text),
                    description=truncate(text, 2000),
                    posted_at=parse_date(comment.get("created_at")),
                    remote="remote" in text.lower(),
                )
            )
        return jobs


def _split_header(text: str) -> tuple[str, str]:
    """HN posts typically start with `Company | Role | Location | ...`."""
    first_line = text.split(".")[0]
    first_line = first_line.split("\n")[0]
    parts = [part.strip() for part in first_line.replace("—", "|").split("|") if part.strip()]
    if len(parts) >= 2:
        return truncate(parts[0], 80), truncate(" ".join(parts[1:3]), 120)
    return "", truncate(first_line, 120) or "Hacker News job post"


def _guess_location(text: str) -> str:
    lowered = text.lower()
    for marker in ("remote", "anywhere", "worldwide"):
        if marker in lowered:
            return "Remote"
    return ""
