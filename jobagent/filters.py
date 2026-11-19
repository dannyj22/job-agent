"""Relevance scoring and category tagging."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import Job
from .utils import is_remote

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "fullstack": ["full stack", "fullstack", "full-stack", "mern", "mean stack"],
    "frontend": [
        "react", "reactjs", "react.js", "next.js", "nextjs", "vue", "angular",
        "svelte", "html", "css", "tailwind", "redux", "frontend", "front end",
        "ui developer",
    ],
    "backend": [
        "node", "node.js", "nodejs", "express", "python", "django", "flask",
        "fastapi", "java", "spring", "php", "laravel", "ruby", "rails", "c#",
        ".net", "golang", "rust", "backend", "back end",
    ],
    "api": ["rest api", "restful", "graphql", "microservices", "grpc", "api developer"],
    "database": [
        "database", "sql", "postgres", "postgresql", "mysql", "mongodb", "redis",
        "dba", "prisma", "supabase",
    ],
    "devops": [
        "devops", "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
        "ci/cd", "sre", "cloud engineer",
    ],
    "mobile": ["react native", "flutter", "swift", "kotlin", "android", "ios"],
    "data_ai": [
        "machine learning", "data scientist", "data engineer", "ai engineer",
        "llm", "nlp", "pytorch", "tensorflow",
    ],
    "qa": ["qa", "quality assurance", "test automation", "sdet", "cypress", "playwright"],
}


def _compile(keyword: str) -> re.Pattern[str]:
    """Word-boundary-ish regex that also works for c#, .net and node.js."""
    escaped = re.escape(keyword.lower())
    # Treat spaces and hyphens as interchangeable: "full stack" == "full-stack".
    escaped = escaped.replace(r"\ ", r"[\s\-]+").replace(" ", r"[\s\-]+")
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", re.IGNORECASE)


@dataclass
class FilterResult:
    accepted: bool
    score: int = 0
    category: str = "other"
    matched: list[str] = field(default_factory=list)
    reason: str = ""


class JobFilter:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config or {}
        self.min_score = int(self.config.get("min_score", 4))
        self.title_bonus = int(self.config.get("title_bonus", 3))
        self.remote_only = bool(self.config.get("remote_only", False))
        self.locations = [str(x) for x in self.config.get("locations", []) or []]

        groups = self.config.get("include_keywords", {}) or {}
        weights = self.config.get("weights", {}) or {}
        self.weights = {
            "core": int(weights.get("core", 4)),
            "adjacent": int(weights.get("adjacent", 2)),
            "general": int(weights.get("general", 1)),
        }
        self.keywords: dict[str, list[tuple[str, re.Pattern[str]]]] = {
            group: [(kw, _compile(kw)) for kw in groups.get(group, []) or []]
            for group in ("core", "adjacent", "general")
        }
        self.exclude = [
            (kw, _compile(kw)) for kw in self.config.get("exclude_keywords", []) or []
        ]
        # Category patterns are built once; config may override the map.
        category_map = self.config.get("categories") or CATEGORY_KEYWORDS
        self.category_patterns: dict[str, list[tuple[str, re.Pattern[str]]]] = {
            name: [(kw, _compile(kw)) for kw in keywords]
            for name, keywords in category_map.items()
        }

    # ------------------------------------------------------------------
    def evaluate(self, job: Job) -> FilterResult:
        haystack = " ".join(
            [job.title, " ".join(job.tags), job.description[:6000]]
        ).lower()
        title = job.title.lower()

        for keyword, pattern in self.exclude:
            if pattern.search(haystack):
                return FilterResult(False, reason=f"excluded keyword: {keyword}")

        score = 0
        matched: list[str] = []
        for group, items in self.keywords.items():
            for keyword, pattern in items:
                if pattern.search(haystack):
                    score += self.weights[group]
                    matched.append(keyword)

        if any(pattern.search(title) for _, pattern in self.keywords["core"]):
            score += self.title_bonus

        if self.remote_only and not (job.remote or is_remote(job.location)):
            return FilterResult(False, score=score, matched=matched, reason="not remote")

        if not job.matches_location(self.locations):
            return FilterResult(False, score=score, matched=matched, reason="location")

        if score < self.min_score:
            return FilterResult(
                False,
                score=score,
                matched=matched,
                reason=f"low score ({score} < {self.min_score})",
            )

        return FilterResult(
            True, score=score, category=self._category(haystack, title), matched=matched
        )

    def _category(self, haystack: str, title: str) -> str:
        scores: dict[str, int] = {}
        for category, items in self.category_patterns.items():
            total = 0
            for _, pattern in items:
                if pattern.search(haystack):
                    total += 1
                if pattern.search(title):
                    total += 2  # a title mention is a strong signal
            if total:
                scores[category] = total

        if not scores:
            return "other"
        # Prefer fullstack when "full stack" is present, it is the most specific.
        if "fullstack" in scores:
            return "fullstack"
        return max(scores.items(), key=lambda item: item[1])[0]

    def apply(self, job: Job) -> FilterResult:
        result = self.evaluate(job)
        if result.accepted:
            job.score = result.score
            job.category = result.category
        return result

    def filter(self, jobs: Iterable[Job]) -> list[Job]:
        kept: list[Job] = []
        for job in jobs:
            if self.apply(job).accepted:
                kept.append(job)
        return kept
