"""Local web UI for browsing and editing jobs in SQLite (Docker operator dashboard)."""

from agentzero.web.app import create_app
from agentzero.web.jobs import list_jobs_for_ui
from agentzero.web.mutations import (
    JobNotFoundError,
    reject_job,
    update_job_notes,
    update_job_status,
)

__all__ = [
    "JobNotFoundError",
    "create_app",
    "list_jobs_for_ui",
    "reject_job",
    "update_job_notes",
    "update_job_status",
]
