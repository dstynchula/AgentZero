import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.models import ApplicationStatus
from agentzero.storage.db import Database
from agentzero.web.app import create_app
from tests.test_db import _job


@pytest.fixture
def web_client(tmp_path):
    db_path = tmp_path / "jobs.db"
    app = create_app(db_path=db_path, settings=Settings(_env_file=None))
    with TestClient(app) as client:
        yield client, db_path


def test_health(web_client):
    client, _ = web_client
    assert client.get("/health").json() == {"status": "ok"}


def test_index_hides_rejected_by_default(web_client):
    client, db_path = web_client
    db = Database(db_path)
    db.upsert_job(_job(title="Visible"))
    db.upsert_job(
        _job(title="Hidden", url="https://x.com/2", status=ApplicationStatus.REJECTED)
    )
    db.close()
    response = client.get("/")
    assert response.status_code == 200
    assert "Visible" in response.text
    assert "Hidden" not in response.text


def test_show_rejected_query(web_client):
    client, db_path = web_client
    db = Database(db_path)
    db.upsert_job(_job(status=ApplicationStatus.REJECTED))
    db.close()
    response = client.get("/?show_rejected=1")
    assert response.status_code == 200
    assert "Hide rejected" in response.text


def test_api_jobs_include_rejected_param(web_client):
    client, db_path = web_client
    db = Database(db_path)
    db.upsert_job(_job())
    db.upsert_job(
        _job(url="https://x.com/2", status=ApplicationStatus.REJECTED)
    )
    db.close()
    assert len(client.get("/api/jobs").json()) == 1
    assert len(client.get("/api/jobs?include_rejected=true").json()) == 2


def test_index_sort_query_reorders(web_client):
    client, db_path = web_client
    db = Database(db_path)
    db.upsert_job(_job(title="Alpha", match_score=0.2))
    db.upsert_job(_job(title="Zulu", url="https://x.com/2", match_score=0.9))
    db.close()
    page = client.get("/?sort=title&order=asc")
    assert page.text.index("Alpha") < page.text.index("Zulu")


def test_index_header_links_include_sort(web_client):
    client, _ = web_client
    page = client.get("/")
    assert "sort=company" in page.text
    assert "sorted" in page.text or "match_score" in page.text


def test_index_truncates_long_notes_in_html(web_client):
    client, db_path = web_client
    db = Database(db_path)
    db.upsert_job(_job(notes="z" * 100))
    db.close()
    page = client.get("/")
    assert "…" in page.text
    assert 'class="cell-truncated"' in page.text


def test_index_row_links_to_detail(web_client):
    from agentzero.storage.db import Database

    client, db_path = web_client
    db = Database(db_path)
    job = _job(title="CardTarget")
    db.upsert_job(job)
    job_id = job.job_id
    db.close()
    assert f'/jobs/{job_id}' in client.get("/").text
