from datetime import date, datetime

import pytest

from agentzero.models import ApplicationStatus, JobPosting
from agentzero.storage.db import Database, _json_default


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def _job(**overrides) -> JobPosting:
    base = dict(
        title="Engineer",
        company="Acme",
        url="https://jobs.example.com/1",
        source="indeed",
    )
    base.update(overrides)
    return JobPosting(**base)


def test_upsert_is_idempotent(db: Database):
    job = _job()
    db.upsert_job(job)
    db.upsert_job(job)
    assert db.count_jobs() == 1


def test_upsert_updates_existing_row(db: Database):
    job = _job()
    db.upsert_job(job)
    updated = job.model_copy(
        update={"status": ApplicationStatus.REVIEWED, "match_score": 0.91}
    )
    db.upsert_job(updated)
    stored = db.get_job(job.job_id)
    assert stored is not None
    assert stored.status == ApplicationStatus.REVIEWED
    assert stored.match_score == 0.91
    assert db.count_jobs() == 1


def test_get_job_missing_returns_none(db: Database):
    assert db.get_job("nonexistent") is None


def test_quarantine_stores_payload_and_error(db: Database):
    raw = {"job_title": "Broken", "company": None}
    qid = db.add_quarantine(source="linkedin", raw_payload=raw, error="missing url")
    rows = db.list_quarantine()
    assert len(rows) == 1
    assert rows[0]["id"] == qid
    assert rows[0]["raw_payload"] == raw
    assert rows[0]["error"] == "missing url"
    assert rows[0]["source"] == "linkedin"


def test_pipeline_status_gates_pending_work(db: Database):
    job = _job()
    db.upsert_job(job)
    assert db.list_pending("enrich_status") == [job.job_id]
    db.mark_pipeline(job.job_id, "enrich_status", "done")
    assert db.list_pending("enrich_status") == []


def test_list_pending_respects_limit(db: Database):
    for i in range(3):
        db.upsert_job(_job(url=f"https://jobs.example.com/{i}"))
    pending = db.list_pending("scrape_status", limit=2)
    assert len(pending) == 2


def test_unknown_pipeline_column_raises(db: Database):
    with pytest.raises(ValueError, match="Unknown pipeline column"):
        db.list_pending("not_a_column")
    with pytest.raises(ValueError, match="Unknown pipeline column"):
        db.mark_pipeline("x", "bad_column", "done")


def test_json_default_serializes_dates_and_status():
    assert _json_default(date(2026, 5, 1)) == "2026-05-01"
    assert _json_default(datetime(2026, 5, 1, 12, 0, 0)).startswith("2026-05-01")
    assert _json_default(ApplicationStatus.APPLIED) == "applied"
    with pytest.raises(TypeError):
        _json_default(object())
