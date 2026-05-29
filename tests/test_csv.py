import csv
from datetime import date

from agentzero.models import JobPosting
from agentzero.storage.csv_export import EXPORT_COLUMNS, export_csv, job_to_row
from agentzero.storage.db import Database


def test_job_to_row_and_posting_age():
    job = JobPosting(
        title="Engineer",
        company="Acme",
        url="https://x.com/1",
        source="indeed",
        date_posted=date(2026, 5, 1),
        match_score=0.8,
    )
    row = job_to_row(job, today=date(2026, 5, 10))
    assert row["company"] == "Acme"
    assert row["posting_age_days"] == 9
    assert set(row.keys()) == set(EXPORT_COLUMNS)


def test_export_csv_writes_all_columns(tmp_path):
    db = Database(tmp_path / "jobs.db")
    job = JobPosting(
        title="Role",
        company="Co",
        url="https://x.com/2",
        source="linkedin",
    )
    db.upsert_job(job)
    out = tmp_path / "jobs.csv"
    count = export_csv(db, out)
    assert count == 1
    with out.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert list(rows[0].keys()) == EXPORT_COLUMNS
    assert rows[0]["title"] == "Role"
    db.close()
