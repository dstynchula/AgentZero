from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.generate.cover_letter import save_cover_letter
from agentzero.web.app import create_app
from tests.test_db import _job


@pytest.fixture
def web_client(tmp_path: Path):
    db_path = tmp_path / "t.db"
    letters_dir = tmp_path / "letters"
    settings = Settings(_env_file=None, db_path=db_path, openai_api_key="sk-test")
    app = create_app(db_path=db_path, settings=settings)
    app.state.cover_letters_dir = letters_dir
    with TestClient(app) as client:
        yield client, db_path, letters_dir


def test_post_generate_starts_background_run(web_client, monkeypatch):
    client, db_path, letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    started: list[str] = []

    class FakeRunner:
        def start(self, **kwargs):
            started.append(kwargs["job_id"])
            return True, "ok"

        def snapshot(self):
            return {"running": False, "job_id": None}

    client.app.state.cover_letter_runner = FakeRunner()
    r = client.post(
        f"/jobs/{job.job_id}/cover-letter/generate",
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert f"/jobs/{job.job_id}" in r.headers["location"]
    assert "cover_started=1" in r.headers["location"]
    assert started == [job.job_id]


def test_generate_busy_when_already_running(web_client):
    client, db_path, _letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    class BusyRunner:
        def start(self, **kwargs):
            return False, "busy"

        def snapshot(self):
            return {"running": False, "job_id": None}

    client.app.state.cover_letter_runner = BusyRunner()
    r = client.post(
        f"/jobs/{job.job_id}/cover-letter/generate",
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "cover_busy=1" in r.headers["location"]


def test_post_save_persists_edited_text(web_client):
    client, db_path, letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    r = client.post(
        f"/jobs/{job.job_id}/cover-letter/save",
        data={"text": "My edited cover letter."},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "cover_saved=1" in r.headers["location"]
    from agentzero.generate.cover_letter import read_cover_letter

    assert read_cover_letter(job.job_id, base_dir=letters_dir) == "My edited cover letter."


def test_post_save_redirects_to_job_card(web_client):
    client, db_path, _letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    r = client.post(
        f"/jobs/{job.job_id}/cover-letter/save",
        data={"text": "Letter body"},
        follow_redirects=False,
    )
    assert r.headers["location"].startswith(f"/jobs/{job.job_id}")
    assert "cover_saved=1" in r.headers["location"]


def test_api_cover_letter_status_returns_text_when_file_exists(web_client):
    client, db_path, letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()
    save_cover_letter(job.job_id, "Stored letter.", base_dir=letters_dir)

    r = client.get(f"/api/jobs/{job.job_id}/cover-letter")
    assert r.status_code == 200
    data = r.json()
    assert data["text"] == "Stored letter."
    assert data["running"] is False


def test_download_cover_letter_returns_txt_attachment(web_client):
    client, db_path, letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job(company="Acme Corp", title="Staff Engineer")
    db.upsert_job(job)
    db.close()
    save_cover_letter(job.job_id, "Download me.", base_dir=letters_dir)

    r = client.get(f"/jobs/{job.job_id}/cover-letter/download")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.text == "Download me."


def test_download_reflects_saved_edits(web_client):
    client, db_path, letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()
    save_cover_letter(job.job_id, "Version two.", base_dir=letters_dir)

    r = client.get(f"/jobs/{job.job_id}/cover-letter/download")
    assert r.text == "Version two."


def test_download_404_when_missing(web_client):
    client, db_path, _letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}/cover-letter/download")
    assert r.status_code == 404


def test_download_404_for_invalid_job_id(web_client):
    client, _, _ = web_client
    r = client.get("/jobs/../escape/cover-letter/download")
    assert r.status_code == 404

def test_cover_letter_runner_missing_resume(tmp_path, monkeypatch):
    from agentzero.storage.db import Database
    from agentzero.web.cover_letter_runner import CoverLetterRunner

    db = Database(tmp_path / "t.db")
    job = _job()
    db.upsert_job(job)
    settings = Settings(_env_file=None, openai_api_key="sk-test")
    letters_dir = tmp_path / "letters"

    monkeypatch.setattr(
        "agentzero.web.cover_letter_runner.find_latest_resume",
        lambda *_a, **_k: (_ for _ in ()).throw(FileNotFoundError("none")),
    )

    runner = CoverLetterRunner()
    ok, _msg = runner.start(
        db=db,
        settings=settings,
        job_id=job.job_id,
        cover_letters_dir=letters_dir,
    )
    assert ok is True
    import time

    for _ in range(50):
        if not runner.state.running:
            break
        time.sleep(0.05)
    assert runner.state.last_ok is False
    assert "résumé" in runner.state.last_message.lower()
    db.close()


def test_cover_letter_runner_missing_api_key(tmp_path, monkeypatch):
    from agentzero.storage.db import Database
    from agentzero.web.cover_letter_runner import CoverLetterRunner

    db = Database(tmp_path / "t.db")
    job = _job()
    db.upsert_job(job)
    settings = Settings(_env_file=None, openai_api_key=None)
    letters_dir = tmp_path / "letters"
    resume = tmp_path / "resume"
    resume.mkdir()
    (resume / "cv.txt").write_text("Jane Doe engineer", encoding="utf-8")
    monkeypatch.setattr("agentzero.web.cover_letter_runner.RESUME_DIR", resume)

    runner = CoverLetterRunner()
    ok, _msg = runner.start(
        db=db,
        settings=settings,
        job_id=job.job_id,
        cover_letters_dir=letters_dir,
    )
    assert ok is True
    import time

    for _ in range(50):
        if not runner.state.running:
            break
        time.sleep(0.05)
    assert runner.state.last_ok is False
    assert "API key" in runner.state.last_message
    db.close()


def test_job_card_shows_generate_button(web_client):
    client, db_path, _letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert r.status_code == 200
    assert "cover-letter/generate" in r.text
    assert ">Generate</button>" in r.text or "Generate</button>" in r.text


def test_job_card_cover_letter_is_editable_textarea(web_client):
    client, db_path, letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()
    save_cover_letter(job.job_id, "Editable text.", base_dir=letters_dir)

    r = client.get(f"/jobs/{job.job_id}")
    assert '<textarea name="text"' in r.text
    assert "Editable text." in r.text


def test_job_card_has_save_cover_letter_form(web_client):
    client, db_path, _letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()

    r = client.get(f"/jobs/{job.job_id}")
    assert "cover-letter/save" in r.text
    assert "Save cover letter" in r.text


def test_job_card_shows_download_when_letter_exists(web_client):
    client, db_path, letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()
    save_cover_letter(job.job_id, "x", base_dir=letters_dir)

    r = client.get(f"/jobs/{job.job_id}")
    assert "cover-letter/download" in r.text
    assert "Download .txt" in r.text


def test_regenerate_has_confirm_when_letter_exists(web_client):
    client, db_path, letters_dir = web_client
    from agentzero.storage.db import Database

    db = Database(db_path)
    job = _job()
    db.upsert_job(job)
    db.close()
    save_cover_letter(job.job_id, "existing", base_dir=letters_dir)

    r = client.get(f"/jobs/{job.job_id}")
    assert "Replace existing cover letter" in r.text
