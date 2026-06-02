from agentzero.models import ApplicationStatus
from agentzero.storage.csv_export import SHEET_COLUMNS
from agentzero.storage.db import Database
from agentzero.web.jobs import list_jobs_for_ui
from tests.test_db import _job


def test_list_excludes_rejected_by_default(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_job(_job(title="Active"))
    db.upsert_job(_job(title="Noped", url="https://jobs.example.com/2", status=ApplicationStatus.REJECTED))
    rows = list_jobs_for_ui(db)
    assert len(rows) == 1
    assert rows[0]["title"] == "Active"
    db.close()


def test_list_include_rejected(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_job(_job(status=ApplicationStatus.REJECTED))
    assert len(list_jobs_for_ui(db, include_rejected=True)) == 1
    db.close()


def test_list_includes_leads(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_job(_job(status=ApplicationStatus.LEAD))
    rows = list_jobs_for_ui(db)
    assert len(rows) == 1
    assert rows[0]["status"] == "lead"
    db.close()


def test_row_shape(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_job(_job(match_score=0.9, notes="note"))
    row = list_jobs_for_ui(db)[0]
    assert set(row.keys()) == set(SHEET_COLUMNS)
    db.close()
