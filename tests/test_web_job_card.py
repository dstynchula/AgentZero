from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.web.app import create_app
from agentzero.web.jobs import job_detail_for_ui
from tests.test_db import _job


def test_job_detail_for_ui_includes_description(tmp_path):
    from agentzero.storage.db import Database

    db = Database(tmp_path / "t.db")
    job = _job(description="Build APIs and lead the platform team.")
    db.upsert_job(job)
    detail = job_detail_for_ui(db, job.job_id)
    db.close()
    assert detail is not None
    assert detail["description"] == "Build APIs and lead the platform team."


def test_job_detail_for_ui_empty_description(tmp_path):
    from agentzero.storage.db import Database

    db = Database(tmp_path / "t.db")
    job = _job()
    db.upsert_job(job)
    detail = job_detail_for_ui(db, job.job_id)
    db.close()
    assert detail is not None
    assert detail["description"] == ""


@pytest.fixture
def card_client(tmp_path: Path):
    db_path = tmp_path / "t.db"
    settings = Settings(_env_file=None, db_path=db_path)
    app = create_app(db_path=db_path, settings=settings)
    with TestClient(app) as client:
        yield client, db_path


def test_job_detail_page_renders_description(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job(description="Build APIs and lead the platform team.")
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    assert "<h2>Description</h2>" in r.text
    assert "Build APIs and lead the platform team." in r.text


def test_job_card_description_before_match_rationale(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job(
        description="Role details here.",
        match_rationale="Strong fit for platform work.",
    )
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    desc_pos = r.text.find("<h2>Description</h2>")
    rationale_pos = r.text.find("<h2>Match rationale</h2>")
    assert desc_pos >= 0 and rationale_pos >= 0
    assert desc_pos < rationale_pos


def test_job_detail_page_shows_empty_description_placeholder(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    assert "No description stored yet" in r.text


def test_job_card_has_status_and_notes_forms(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    assert 'name="return_to" value="detail"' in r.text
    assert "/status" in r.text
    assert "/notes" in r.text
    assert "Save status" in r.text
    assert "Save notes" in r.text
    assert "<h2>Notes</h2>" in r.text
    assert 'id="job-notes"' in r.text


def test_job_card_shows_apply_button_with_posting_fallback(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job(url="https://www.indeed.com/viewjob?jk=abc123")
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    assert "<h2>Apply</h2>" in r.text
    assert 'href="https://www.indeed.com/viewjob?jk=abc123"' in r.text
    assert "easy apply link not located" in r.text.lower() or "Easy apply link not located" in r.text


def test_job_card_shows_easy_apply_not_located_hint_when_no_apply_url(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job(
        url="https://www.linkedin.com/jobs/view/1",
        easy_apply=True,
    )
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    assert "easy apply" in r.text.lower()


def test_job_card_has_notes_section_with_textarea(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job(notes="Prior note")
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    assert "<h2>Notes</h2>" in r.text
    assert "Prior note" in r.text
    assert "<textarea" in r.text


def test_post_status_from_detail_redirects_back_to_job_card(card_client):
    client, db_path = card_client
    from agentzero.models import ApplicationStatus
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job(status=ApplicationStatus.NEW)
    db.upsert_job(job)
    db.close()

    r = client.post(
        f"/jobs/{job.job_id}/status",
        data={"status": "reviewed", "return_to": "detail"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert f"/jobs/{job.job_id}" in r.headers["location"]
    assert "status_saved=1" in r.headers["location"]

    db = Database(db_path)
    assert db.get_job(job.job_id).status == ApplicationStatus.REVIEWED
    db.close()


def test_post_notes_from_detail_persists_and_redirects(card_client):
    client, db_path = card_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    r = client.post(
        f"/jobs/{job.job_id}/notes",
        data={"notes": "Follow up Tuesday", "return_to": "detail"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "notes_saved=1" in r.headers["location"]

    db = Database(db_path)
    assert db.get_job(job.job_id).notes == "Follow up Tuesday"
    db.close()
