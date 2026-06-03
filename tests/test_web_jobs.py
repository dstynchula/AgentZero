from agentzero.models import ApplicationStatus
from agentzero.storage.csv_export import TRACKER_UI_COLUMNS
from agentzero.storage.db import Database
from agentzero.web.jobs import job_detail_for_ui, jobs_for_table, list_jobs_for_ui
from tests.test_db import _job


def test_list_jobs_filters_by_company_title_status_score_comp_min(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_job(
        _job(
            title="Staff Security Engineer",
            company="SecureCo",
            match_score=0.92,
            comp_min=220_000,
            comp_max=260_000,
            status=ApplicationStatus.LEAD,
        )
    )
    db.upsert_job(
        _job(
            title="Account Executive",
            company="SalesCo",
            url="https://jobs.example.com/sales",
            match_score=0.4,
            comp_min=90_000,
            comp_max=110_000,
            status=ApplicationStatus.NEW,
        )
    )
    from agentzero.web.jobs import JobListFilters, list_jobs_for_ui

    filters = JobListFilters(
        company="secure",
        title="security",
        status="lead",
        min_score=0.9,
        min_comp=200_000,
    )
    rows = list_jobs_for_ui(db, filters=filters)
    assert len(rows) == 1
    assert rows[0]["company"] == "SecureCo"
    db.close()


def test_list_excludes_rejected_by_default(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_job(_job(title="Active"))
    db.upsert_job(
        _job(title="Noped", url="https://jobs.example.com/2", status=ApplicationStatus.REJECTED)
    )
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
    assert set(row.keys()) == set(TRACKER_UI_COLUMNS)
    db.close()


def test_list_jobs_sorted_by_match_score(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_job(_job(title="Low", match_score=0.3))
    db.upsert_job(_job(title="High", url="https://x.com/2", match_score=0.95))
    rows = list_jobs_for_ui(db, sort="match_score", order="desc")
    assert rows[0]["title"] == "High"
    db.close()


def test_jobs_for_table_truncates_notes(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert_job(_job(notes="n" * 120))
    table = jobs_for_table(db)
    assert table[0]["cells"]["notes"].truncated is True
    assert len(table[0]["cells"]["notes"].text) <= 80
    db.close()


def test_job_detail_for_ui(tmp_path):
    db = Database(tmp_path / "t.db")
    job = _job(match_rationale="Strong fit", notes="hello")
    db.upsert_job(job)
    detail = job_detail_for_ui(db, job.job_id)
    assert detail is not None
    assert detail["match_rationale"] == "Strong fit"
    assert "description" in detail
    assert job_detail_for_ui(db, "missing") is None
    db.close()


def test_jobs_list_additive_filter_merge(tmp_path):
    from fastapi.testclient import TestClient

    from agentzero.config import Settings
    from agentzero.web.app import create_app

    db_path = tmp_path / "jobs.db"
    db = Database(db_path)
    db.upsert_job(_job(title="Staff Security Engineer", company="SecureCo"))
    db.upsert_job(
        _job(title="Account Executive", company="SalesCo", url="https://jobs.example.com/2")
    )
    db.close()
    app = create_app(db_path=db_path, settings=Settings(_env_file=None))
    with TestClient(app) as client:
        response = client.get(
            "/jobs",
            params={
                "company": "secure",
                "filter_key": "title",
                "filter_value": "security",
            },
        )
        assert response.status_code == 200
        assert "SecureCo" in response.text
        assert "SalesCo" not in response.text


def test_job_list_filters_merge_and_without():
    from agentzero.web.jobs import JobListFilters

    base = JobListFilters.from_query(company="acme")
    merged = JobListFilters.merge_filter(base, "title", "engineer")
    assert merged.company == "acme"
    assert merged.title == "engineer"
    replaced = JobListFilters.merge_filter(merged, "company", "beta")
    assert replaced.company == "beta"
    assert replaced.title == "engineer"
    trimmed = merged.without("company")
    assert trimmed.company is None
    assert trimmed.title == "engineer"


def test_clear_filters_href_omits_filter_params():
    from agentzero.web.jobs import JobListFilters, list_context

    ctx = list_context(
        filters=JobListFilters.from_query(company="acme", title="eng"),
        sort="match_score",
        order="desc",
    )
    href = ctx["clear_filters_href"]
    assert "company=" not in href
    assert "title=" not in href
    assert "sort=match_score" in href
    assert "order=desc" in href
