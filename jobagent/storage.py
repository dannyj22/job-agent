"""SQLite persistence and dedupe."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    fingerprint  TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    company      TEXT NOT NULL,
    url          TEXT NOT NULL,
    source       TEXT NOT NULL,
    location     TEXT,
    category     TEXT,
    score        INTEGER,
    salary       TEXT,
    tags         TEXT,
    description  TEXT,
    posted_at    TEXT,
    first_seen   TEXT NOT NULL,
    notified     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_notified ON jobs(notified);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
"""


class Storage:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    def save_if_new(self, job: Job) -> bool:
        """Insert the job. Returns True only when it was not already known."""
        # Cross-source duplicates often use different URLs for the same role,
        # so also treat an identical title+company as already seen.
        duplicate = self.conn.execute(
            "SELECT 1 FROM jobs WHERE lower(title) = lower(?) AND lower(company) = lower(?) LIMIT 1",
            (job.title, job.company),
        ).fetchone()
        if duplicate:
            return False

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO jobs
                    (fingerprint, title, company, url, source, location, category,
                     score, salary, tags, description, posted_at, first_seen, notified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    job.fingerprint,
                    job.title,
                    job.company,
                    job.url,
                    job.source,
                    job.location,
                    job.category,
                    job.score,
                    job.salary,
                    json.dumps(job.tags),
                    job.short_description,
                    job.posted_at.isoformat() if job.posted_at else None,
                    now,
                ),
            )
            self.conn.commit()
            return cursor.rowcount == 1
        except sqlite3.Error:
            self.conn.rollback()
            raise

    def mark_notified(self, fingerprints: list[str]) -> None:
        if not fingerprints:
            return
        self.conn.executemany(
            "UPDATE jobs SET notified = 1 WHERE fingerprint = ?",
            [(fp,) for fp in fingerprints],
        )
        self.conn.commit()

    def clear_pending(self) -> int:
        """Mark every queued job as seen and return how many were cleared."""
        cursor = self.conn.execute("UPDATE jobs SET notified = 1 WHERE notified = 0")
        self.conn.commit()
        return cursor.rowcount

    def exists(self, fingerprint: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM jobs WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        return row is not None

    def stats(self) -> dict[str, int]:
        def count(sql: str, params: tuple = ()) -> int:
            return int(self.conn.execute(sql, params).fetchone()[0])

        return {
            "total": count("SELECT COUNT(*) FROM jobs"),
            "notified": count("SELECT COUNT(*) FROM jobs WHERE notified = 1"),
            "pending": count("SELECT COUNT(*) FROM jobs WHERE notified = 0"),
            "last_24h": count(
                "SELECT COUNT(*) FROM jobs WHERE first_seen >= ?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds")[:10],),
            ),
        }

    def recent(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM jobs ORDER BY first_seen DESC LIMIT ?", (limit,)
        ).fetchall()

    def pending(self, limit: int = 20) -> list[Job]:
        """Unnotified jobs, best first. Lets a capped run drain its backlog."""
        rows = self.conn.execute(
            """
            SELECT * FROM jobs
            WHERE notified = 0
            ORDER BY score DESC, COALESCE(posted_at, first_seen) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_job(row) for row in rows]


def _row_to_job(row: sqlite3.Row) -> Job:
    from .utils import parse_date

    try:
        tags = json.loads(row["tags"] or "[]")
    except (TypeError, ValueError):
        tags = []
    return Job(
        title=row["title"],
        company=row["company"],
        url=row["url"],
        source=row["source"],
        location=row["location"] or "",
        description=row["description"] or "",
        tags=tags,
        salary=row["salary"] or "",
        posted_at=parse_date(row["posted_at"]),
        category=row["category"] or "other",
        score=int(row["score"] or 0),
    )
