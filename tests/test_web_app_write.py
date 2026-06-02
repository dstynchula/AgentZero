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


def test_post_status_redirects(web_client):
    client, db_path = web_client
    db = Database(db_path)
    job = _job(status=ApplicationStatus.LEAD)
    db.upsert_job(job)
    job_id = job.job_id
    db.close()
    response = client.post(
        f"/jobs/{job_id}/status",
        data={"status": "new"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db = Database(db_path)
    assert db.get_job(job_id).status == ApplicationStatus.NEW
    db.close()


def test_post_notes_updates_db(web_client):
    client, db_path = web_client
    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    job_id = job.job_id
    db.close()
    client.post(f"/jobs/{job_id}/notes", data={"notes": "follow up"})
    db = Database(db_path)
    assert db.get_job(job_id).notes == "follow up"
    db.close()


def test_post_reject_hides_from_default_index(web_client):
    client, db_path = web_client
    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    job_id = job.job_id
    db.close()
    client.post(f"/jobs/{job_id}/reject", follow_redirects=False)
    page = client.get("/")
    assert job.title not in page.text


def test_reject_then_show_rejected_lists_row(web_client):
    client, db_path = web_client
    db = Database(db_path)
    job = _job(title="Nope Role")
    db.upsert_job(job)
    job_id = job.job_id
    db.close()
    client.post(f"/jobs/{job_id}/reject")
    page = client.get("/?show_rejected=1")
    assert "Nope Role" in page.text
