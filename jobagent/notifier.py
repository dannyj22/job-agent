"""Discord webhook notifications."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .models import Job
from .utils import truncate

logger = logging.getLogger(__name__)

CATEGORY_COLORS = {
    "frontend": 0x61DAFB,
    "backend": 0x3C873A,
    "fullstack": 0x8A2BE2,
    "api": 0xFF8C00,
    "database": 0x336791,
    "devops": 0xEE0000,
    "mobile": 0x02569B,
    "data_ai": 0x9C27B0,
    "qa": 0x00A86B,
    "other": 0x808080,
}


class NotificationError(RuntimeError):
    pass


class DiscordNotifier:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.webhook = config.discord_webhook
        self.embeds_per_message = int(
            config.discord.get("embeds_per_message", 10) or 10
        )
        if not self.webhook:
            raise NotificationError(
                "DISCORD_WEBHOOK_URL is not set. Copy .env.example to .env and add "
                "your webhook URL (Discord: Server Settings > Integrations > Webhooks)."
            )

    # ------------------------------------------------------------------
    def send_jobs(self, jobs: list[Job]) -> int:
        if not jobs:
            return 0
        sent = 0
        size = max(1, min(self.embeds_per_message, 10))
        for start in range(0, len(jobs), size):
            batch = jobs[start : start + size]
            payload = {
                "username": "JobAgent",
                "content": _header(len(jobs)) if start == 0 else None,
                "embeds": [self._embed(job) for job in batch],
            }
            payload = {k: v for k, v in payload.items() if v is not None}
            self._post(payload)
            sent += len(batch)
            if start + size < len(jobs):
                time.sleep(1.0)
        return sent

    def send_test(self) -> None:
        job = Job(
            title="Senior React / Node.js Developer",
            company="Example Labs",
            url="https://example.com/jobs/123",
            source="test",
            location="Remote (Worldwide)",
            salary="$90,000 - $120,000",
            tags=["react", "node.js", "postgres"],
            description="This is a test alert from your Job Agent. If you can read "
            "this in Discord, notifications are working.",
            category="fullstack",
            score=15,
            remote=True,
        )
        self.send_jobs([job])

    # ------------------------------------------------------------------
    def _embed(self, job: Job) -> dict[str, Any]:
        fields: list[dict[str, Any]] = []

        def add(name: str, value: str, inline: bool = True) -> None:
            if value:
                fields.append(
                    {"name": name, "value": truncate(value, 1024), "inline": inline}
                )

        add("Company", job.company)
        add("Location", job.location or ("Remote" if job.remote else ""))
        add("Salary", job.salary)
        add("Source", job.source)
        add("Category", job.category.replace("_", " ").title())
        add("Match score", str(job.score) if job.score else "")

        embed: dict[str, Any] = {
            "title": truncate(f"{job.title}", 256),
            "url": job.url,
            "description": job.short_description,
            "color": CATEGORY_COLORS.get(job.category, CATEGORY_COLORS["other"]),
            "fields": fields[:10],
            "footer": {"text": truncate(f"JobAgent • {job.source}", 2048)},
        }
        if job.posted_at:
            embed["timestamp"] = job.posted_at.isoformat()
        return embed

    def _post(self, payload: dict[str, Any]) -> None:
        response = requests.post(self.webhook, json=payload, timeout=20)
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "2"))
            logger.warning("Discord rate limited, sleeping %.1fs", retry_after)
            time.sleep(retry_after + 0.5)
            response = requests.post(self.webhook, json=payload, timeout=20)
        if response.status_code >= 300:
            raise NotificationError(
                f"Discord webhook failed ({response.status_code}): {response.text[:300]}"
            )


def _header(total: int) -> str:
    noun = "job" if total == 1 else "jobs"
    return f"**{total} new {noun} matching your filters**"
