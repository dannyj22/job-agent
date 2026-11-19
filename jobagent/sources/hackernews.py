"""Hacker News "Who is hiring?" monthly thread via the Algolia API."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..models import Job
from ..utils import parse_date, strip_html, truncate
from .base import JobSource

# search_by_date (not `search`) so the newest thread wins. `search` ranks by
# relevance and returns a years-old thread with the most upvotes.
SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"
THREAD_URL = "https://news.ycombinator.com/item?id={id}"

MAX_THREAD_AGE_DAYS = 45

ROLE_RE = re.compile(
    r"\b(engineer|developer|designer|scientist|analyst|architect|manager|devops|sre|"
    r"programmer|intern|researcher|lead|administrator)\b",
    re.IGNORECASE,
)


class HackerNewsSource(JobSource):
    name = "hackernews"

    def fetch(self) -> list[Job]:
        payload = self.get_json(
            SEARCH_URL,
            params={
                "query": "Ask HN: Who is hiring?",
                "tags": "story",
                "hitsPerPage": 30,
            },
        )
        hits = [
            hit
            for hit in payload.get("hits", [])
            if str(hit.get("title", "")).startswith("Ask HN: Who is hiring?")
        ]
        if not hits:
            return []
        story = max(hits, key=lambda hit: hit.get("created_at_i") or 0)

        posted = parse_date(story.get("created_at"))
        if posted and datetime.now(timezone.utc) - posted > timedelta(days=MAX_THREAD_AGE_DAYS):
            # The newest available thread is stale; better to emit nothing than
            # to post decade-old jobs.
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
    """HN posts typically start with `Company | Role | Location | ...`.

    The role segment is picked by keyword rather than position, because many
    posts put the location or the employment type in the second slot.
    """
    first_line = text.split("\n")[0]
    parts = [
        part.strip(" •-–—")
        for part in re.split(r"[|—]", first_line)
        if part.strip(" •-–—")
    ]
    if len(parts) >= 2:
        role = next((part for part in parts if ROLE_RE.search(part) and len(part) <= 90), "")
        if role:
            company = parts[0] if not ROLE_RE.search(parts[0]) else ""
            return truncate(company, 80), truncate(role, 120)
        return truncate(parts[0], 80), truncate(" ".join(parts[1:3]), 120)
    return "", truncate(first_line, 120) or "Hacker News job post"


def _guess_location(text: str) -> str:
    lowered = text.lower()
    for marker in ("remote", "anywhere", "worldwide"):
        if marker in lowered:
            return "Remote"
    return ""
