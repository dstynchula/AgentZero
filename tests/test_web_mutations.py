import inspect

import pytest

from agentzero.models import ApplicationStatus
from agentzero.storage.db import Database
from agentzero.web import mutations
from agentzero.web.mutations import (
    JobNotFoundError,
    reject_job,
    update_job_notes,
    update_job_status,
)
from tests.test_db import _job


def test_update_status_persists(tmp_path):
    db = Database(tmp_path / "t.db")
    job = _job(status=ApplicationStatus.LEAD)
    db.upsert_job(job)
    update_job_status(db, job.job_id, "new")
    assert db.get_job(job.job_id).status == ApplicationStatus.NEW
    db.close()


def test_update_notes_strips(tmp_path):
    db = Database(tmp_path / "t.db")
    job = _job()
    db.upsert_job(job)
    update_job_notes(db, job.job_id, "  hello  ")
    assert db.get_job(job.job_id).notes == "hello"
    db.close()


def test_reject_sets_rejected(tmp_path):
    db = Database(tmp_path / "t.db")
    job = _job(status=ApplicationStatus.NEW)
    db.upsert_job(job)
    reject_job(db, job.job_id)
    assert db.get_job(job.job_id).status == ApplicationStatus.REJECTED
    db.close()


def test_reject_idempotent(tmp_path):
    db = Database(tmp_path / "t.db")
    job = _job(status=ApplicationStatus.REJECTED)
    db.upsert_job(job)
    reject_job(db, job.job_id)
    assert db.get_job(job.job_id).status == ApplicationStatus.REJECTED
    db.close()


def test_reject_unknown_404(tmp_path):
    db = Database(tmp_path / "t.db")
    with pytest.raises(JobNotFoundError):
        reject_job(db, "missing")
    db.close()


def test_invalid_status_raises(tmp_path):
    db = Database(tmp_path / "t.db")
    job = _job()
    db.upsert_job(job)
    with pytest.raises(ValueError, match="invalid status"):
        update_job_status(db, job.job_id, "not-a-status")
    db.close()


def test_notes_too_long_raises(tmp_path):
    db = Database(tmp_path / "t.db")
    job = _job()
    db.upsert_job(job)
    with pytest.raises(ValueError, match="notes exceed"):
        update_job_notes(db, job.job_id, "x" * 9000)
    db.close()


def test_mutations_module_does_not_delete_jobs():
    source = inspect.getsource(mutations)
    assert "delete_jobs" not in source
