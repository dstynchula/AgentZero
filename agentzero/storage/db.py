"""SQLite storage with idempotent upserts and a quarantine table for failed scrapes."""

from __future__ import annotations

import json
import sqlite3
import threading
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

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON chat_messages(session_id, id);

CREATE TABLE IF NOT EXISTS chat_pending_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
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
        self._lock = threading.Lock()
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def with_connection(self, fn):
        """Run *fn(conn)* under the database lock (for chat store helpers)."""
        with self._lock:
            return fn(self._conn)

    def upsert_job(self, job: JobPosting) -> None:
        """Insert or replace a job row keyed by ``job_id`` (idempotent)."""
        payload = job.model_dump(mode="json")
        payload["job_id"] = job.job_id
        now = _utc_now_iso()
        with self._lock:
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

    def get_job_by_stored_id(self, job_id: str) -> JobPosting | None:
        """Load a job by SQLite primary key."""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        data = json.loads(row["payload"])
        return JobPosting.model_validate(data)

    def iter_jobs_with_stored_ids(self) -> list[tuple[str, JobPosting]]:
        """Return ``(stored_job_id, job)`` for every row."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT job_id, payload FROM jobs ORDER BY job_id"
            ).fetchall()
        out: list[tuple[str, JobPosting]] = []
        for row in rows:
            job = JobPosting.model_validate(json.loads(row["payload"]))
            out.append((row["job_id"], job))
        return out

    def find_stored_id_for_canonical(self, canonical_id: str) -> str | None:
        """Map a computed ``JobPosting.job_id`` to the row's stored primary key."""
        for stored_id, job in self.iter_jobs_with_stored_ids():
            if job.job_id == canonical_id:
                return stored_id
        return None

    def get_job(self, job_id: str) -> JobPosting | None:
        """Load by stored id, then by canonical ``JobPosting.job_id``."""
        job = self.get_job_by_stored_id(job_id)
        if job is not None:
            return job
        stored_id = self.find_stored_id_for_canonical(job_id)
        if stored_id is None:
            return None
        return self.get_job_by_stored_id(stored_id)

    def rekey_job(self, old_id: str, new_id: str, job: JobPosting) -> bool:
        """Move a row to *new_id* preserving pipeline columns. Returns False if *old_id* missing."""
        if old_id == new_id:
            return True
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (old_id,)
            ).fetchone()
            if row is None:
                return False
            payload = job.model_dump(mode="json")
            payload["job_id"] = new_id
            now = _utc_now_iso()
            self._conn.execute("DELETE FROM jobs WHERE job_id = ?", (old_id,))
            self._conn.execute(
                """
                INSERT INTO jobs (
                    job_id, source, company, title, url, payload, status,
                    scrape_status, enrich_status, rank_status, draft_status,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id,
                    job.source,
                    job.company,
                    job.title,
                    job.url,
                    json.dumps(payload, default=_json_default),
                    job.status.value,
                    row["scrape_status"],
                    row["enrich_status"],
                    row["rank_status"],
                    row["draft_status"],
                    now,
                ),
            )
            self._conn.commit()
        return True

    def count_jobs(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()
        return int(row["n"])

    def clear_jobs(self) -> int:
        """Delete all job rows. Returns the number of rows removed."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()
            deleted = int(row["n"])
            self._conn.execute("DELETE FROM jobs")
            self._conn.commit()
        return deleted

    def delete_jobs(self, job_ids: list[str]) -> int:
        """Delete jobs by ``job_id``. Returns the number of rows removed."""
        if not job_ids:
            return 0
        placeholders = ",".join("?" for _ in job_ids)
        with self._lock:
            cursor = self._conn.execute(
                f"DELETE FROM jobs WHERE job_id IN ({placeholders})",
                job_ids,
            )
            self._conn.commit()
            return int(cursor.rowcount)

    def list_job_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT job_id FROM jobs ORDER BY job_id").fetchall()
        return [row["job_id"] for row in rows]

    def clear_quarantine(self) -> int:
        """Delete all quarantine rows. Returns the number of rows removed."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM quarantine").fetchone()
            deleted = int(row["n"])
            self._conn.execute("DELETE FROM quarantine")
            self._conn.commit()
        return deleted

    def clear_all(self) -> tuple[int, int]:
        """Remove all jobs and quarantine rows. Returns ``(jobs, quarantine)`` deleted."""
        jobs = self.clear_jobs()
        quarantine = self.clear_quarantine()
        return jobs, quarantine

    def list_jobs(self) -> list[JobPosting]:
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            self._conn.execute(
                f"UPDATE jobs SET {pipeline_column} = ?, updated_at = ? WHERE job_id = ?",
                (status, _utc_now_iso(), job_id),
            )
            self._conn.commit()
