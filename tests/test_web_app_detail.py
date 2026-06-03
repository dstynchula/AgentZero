import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.web.app import create_app
from tests.test_db import _job


@pytest.fixture
def web_client(tmp_path):
    db_path = tmp_path / "jobs.db"
    app = create_app(db_path=db_path, settings=Settings(_env_file=None))
    with TestClient(app) as client:
        yield client, db_path


def test_job_detail_200(web_client):
    from agentzero.storage.db import Database

    client, db_path = web_client
    db = Database(db_path)
    job = _job(match_rationale="Great match")
    db.upsert_job(job)
    job_id = job.job_id
    db.close()
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert "Great match" in response.text
    assert job.title in response.text


def test_job_detail_404(web_client):
    client, _ = web_client
    assert client.get("/jobs/deadbeef00000001").status_code == 404


def test_back_link_preserves_show_rejected(web_client):
    from agentzero.storage.db import Database

    client, db_path = web_client
    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    job_id = job.job_id
    db.close()
    response = client.get(f"/jobs/{job_id}?show_rejected=1&sort=company&order=asc")
    assert "show_rejected=1" in response.text
    assert "sort=company" in response.text
