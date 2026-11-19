"""Fetch -> filter -> dedupe -> notify pipeline."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .config import Config
from .filters import JobFilter
from .models import Job
from .notifier import DiscordNotifier
from .sources import build_sources
from .storage import Storage

logger = logging.getLogger(__name__)


def collect(config: Config, storage: Storage, job_filter: JobFilter) -> tuple[list[Job], dict]:
    """Run every enabled source and return genuinely new, relevant jobs."""
    raw_total = 0
    new_jobs: list[Job] = []
    per_source: dict[str, dict[str, int]] = {}

    for source in build_sources(config):
        try:
            raw_jobs = source.fetch()
        except Exception as exc:  # isolate a broken board from the rest
            logger.warning("[%s] failed: %s", source.name, exc)
            per_source[source.name] = {"fetched": 0, "new": 0, "error": 1}
            continue

        fresh = 0
        for job in raw_jobs:
            result = job_filter.apply(job)
            if not result.accepted:
                continue
            if storage.save_if_new(job):
                new_jobs.append(job)
                fresh += 1

        raw_total += len(raw_jobs)
        per_source[source.name] = {"fetched": len(raw_jobs), "new": fresh}
        logger.info("[%s] fetched %d, new matching %d", source.name, len(raw_jobs), fresh)

    new_jobs.sort(key=_sort_key, reverse=True)
    summary = {"fetched": raw_total, "new": len(new_jobs), "sources": per_source}
    return new_jobs, summary


def _sort_key(job: Job) -> tuple[int, float]:
    timestamp = job.posted_at.timestamp() if job.posted_at else 0.0
    return (job.score, timestamp)


def run(
    config: Config,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    notify: bool = True,
) -> dict:
    storage = Storage(config.db_path)
    try:
        job_filter = JobFilter(config.filters)
        jobs, summary = collect(config, storage, job_filter)

        cap = int(config.discord.get("max_jobs_per_run", 20) or 20)
        if limit is not None:
            cap = limit

        # Drain the unanswered backlog, not just this run's new finds, so a cap
        # never strands older matches forever.
        backlog = storage.pending(max(0, cap))

        sent = 0
        if backlog and notify and not dry_run:
            notifier = DiscordNotifier(config)
            sent = notifier.send_jobs(backlog)
            storage.mark_notified([job.fingerprint for job in backlog])

        summary.update(
            {
                "selected": len(backlog),
                "sent": sent,
                "dry_run": dry_run,
                "new_found": len(jobs),
            }
        )
        return summary
    finally:
        storage.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
