"""Tests for stale job_id re-key migration."""

from __future__ import annotations

import pytest

from agentzero.models import ApplicationStatus, JobPosting
from agentzero.storage.db import Database
from agentzero.storage.job_id_migration import find_stale_job_keys, migrate_stale_job_ids


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def _linkedin_job(**kwargs) -> JobPosting:
    base = dict(
        title="Senior Enterprise Security Engineer",
        company="Life360",
        url="https://www.linkedin.com/jobs/view/4414960073/",
        source="linkedin",
        status=ApplicationStatus.CONTACTED,
        notes="Patrick intro",
    )
    base.update(kwargs)
    return JobPosting(**base)


def _seed_legacy_linkedin_row(db: Database, job: JobPosting, legacy_id: str) -> None:
    canonical = job.job_id
    assert canonical != legacy_id
    db.upsert_job(job)
    db.rekey_job(canonical, legacy_id, job)


def test_find_stale_job_keys_detects_legacy_linkedin_id(db: Database):
    job = _linkedin_job()
    legacy_id = "c975960ca92297fb"
    _seed_legacy_linkedin_row(db, job, legacy_id)
    stale = find_stale_job_keys(db)
    assert len(stale) == 1
    assert stale[0].stored_id == legacy_id
    assert stale[0].canonical_id == job.job_id


def test_migrate_stale_job_ids_rekeys_row(db: Database):
    job = _linkedin_job()
    legacy_id = "c975960ca92297fb"
    _seed_legacy_linkedin_row(db, job, legacy_id)
    db.mark_pipeline(legacy_id, "enrich_status", "done")

    result = migrate_stale_job_ids(db)
    assert result.rekeyed == 1
    assert db.get_job_by_stored_id(legacy_id) is None
    stored = db.get_job_by_stored_id(job.job_id)
    assert stored is not None
    assert stored.notes == "Patrick intro"
    assert db.list_pending("enrich_status") == []


def test_get_job_resolves_canonical_id_before_migration(db: Database):
    job = _linkedin_job()
    legacy_id = "c975960ca92297fb"
    _seed_legacy_linkedin_row(db, job, legacy_id)

    assert db.get_job_by_stored_id(job.job_id) is None
    resolved = db.get_job(job.job_id)
    assert resolved is not None
    assert resolved.notes == "Patrick intro"


def test_migrate_dry_run_does_not_write(db: Database):
    job = _linkedin_job()
    legacy_id = "c975960ca92297fb"
    _seed_legacy_linkedin_row(db, job, legacy_id)

    result = migrate_stale_job_ids(db, dry_run=True)
    assert result.rekeyed == 1
    assert db.get_job_by_stored_id(legacy_id) is not None
    assert db.get_job_by_stored_id(job.job_id) is None
