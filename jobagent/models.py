"""The Job model shared by every source, filter and notifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .utils import clean_text, is_remote, normalize_url, sha1, truncate


@dataclass
class Job:
    title: str
    company: str
    url: str
    source: str
    location: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    salary: str = ""
    posted_at: datetime | None = None
    remote: bool = False
    category: str = "other"
    score: int = 0

    def __post_init__(self) -> None:
        self.title = clean_text(self.title) or "Untitled role"
        self.company = clean_text(self.company) or "Unknown company"
        self.url = normalize_url(self.url)
        self.location = clean_text(self.location)
        self.source = clean_text(self.source)
        self.salary = clean_text(self.salary)
        self.tags = [clean_text(t) for t in self.tags if clean_text(t)]
        if self.posted_at and self.posted_at.tzinfo is None:
            self.posted_at = self.posted_at.replace(tzinfo=timezone.utc)

    @property
    def fingerprint(self) -> str:
        """Stable identity used for dedupe across runs and sources."""
        key = "|".join(
            [
                self.title.lower(),
                self.company.lower(),
                normalize_url(self.url) or self.location.lower(),
            ]
        )
        return sha1(key)

    @property
    def short_description(self) -> str:
        return truncate(self.description, 280)

    def matches_location(self, wanted: list[str]) -> bool:
        if not wanted:
            return True
        if self.remote or is_remote(self.location):
            return True
        haystack = self.location.lower()
        return any(item.lower() in haystack for item in wanted)
