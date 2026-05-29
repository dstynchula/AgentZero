"""SQLite storage with idempotent upserts and a quarantine table for failed scrapes."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from agentzero.models import ApplicationStatus, JobPosting

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    scrape_status TEXT NOT NULL DEFAULT 'pending',
    enrich_status TEXT NOT NULL DEFAULT 'pending',
    rank_status TEXT NOT NULL DEFAULT 'pending',
    draft_status TEXT NOT NULL DEFAULT 'pending',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    raw_payload TEXT NOT NULL,
    error TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

PIPELINE_COLUMNS = ("scrape_status", "enrich_status", "rank_status", "draft_status")


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_default(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, ApplicationStatus):
        return value.value
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


class Database:
    """Thin SQLite wrapper for jobs and quarantine rows."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def upsert_job(self, job: JobPosting) -> None:
        """Insert or replace a job row keyed by ``job_id`` (idempotent)."""
        payload = job.model_dump(mode="json")
        payload["job_id"] = job.job_id
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO jobs (
                job_id, source, company, title, url, payload, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                source = excluded.source,
                company = excluded.company,
                title = excluded.title,
                url = excluded.url,
                payload = excluded.payload,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                job.job_id,
                job.source,
                job.company,
                job.title,
                job.url,
                json.dumps(payload, default=_json_default),
                job.status.value,
                now,
            ),
        )
        self._conn.commit()

    def get_job(self, job_id: str) -> JobPosting | None:
        row = self._conn.execute(
            "SELECT payload FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload"])
        return JobPosting.model_validate(data)

    def count_jobs(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()
        return int(row["n"])

    def list_jobs(self) -> list[JobPosting]:
        rows = self._conn.execute(
            "SELECT payload FROM jobs ORDER BY company COLLATE NOCASE, title COLLATE NOCASE"
        ).fetchall()
        return [
            JobPosting.model_validate(json.loads(row["payload"])) for row in rows
        ]

    def add_quarantine(
        self,
        *,
        raw_payload: dict[str, Any],
        error: str,
        source: str | None = None,
    ) -> int:
        """Store a record that failed validation (append-only audit)."""
        cursor = self._conn.execute(
            """
            INSERT INTO quarantine (source, raw_payload, error, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                source,
                json.dumps(raw_payload, default=str),
                error,
                _utc_now_iso(),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def list_quarantine(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, source, raw_payload, error, created_at FROM quarantine ORDER BY id"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "source": row["source"],
                "raw_payload": json.loads(row["raw_payload"]),
                "error": row["error"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def list_pending(self, pipeline_column: str, *, limit: int | None = None) -> list[str]:
        """Return ``job_id`` values where a pipeline stage is still ``pending``."""
        if pipeline_column not in PIPELINE_COLUMNS:
            raise ValueError(f"Unknown pipeline column: {pipeline_column}")
        query = f"SELECT job_id FROM jobs WHERE {pipeline_column} = 'pending' ORDER BY job_id"
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        rows = self._conn.execute(query).fetchall()
        return [row["job_id"] for row in rows]

    def mark_pipeline(
        self,
        job_id: str,
        pipeline_column: str,
        status: str,
    ) -> None:
        if pipeline_column not in PIPELINE_COLUMNS:
            raise ValueError(f"Unknown pipeline column: {pipeline_column}")
        self._conn.execute(
            f"UPDATE jobs SET {pipeline_column} = ?, updated_at = ? WHERE job_id = ?",
            (status, _utc_now_iso(), job_id),
        )
        self._conn.commit()
