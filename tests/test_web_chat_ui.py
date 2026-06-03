from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.web.app import create_app


@pytest.fixture
def web_client(tmp_path: Path):
    db_path = tmp_path / "t.db"
    settings = Settings(_env_file=None, db_path=db_path)
    app = create_app(db_path=db_path, settings=settings)
    with TestClient(app) as client:
        yield client


def test_root_renders_chat_page(web_client):
    r = web_client.get("/")
    assert r.status_code == 200
    assert 'id="chat-form"' in r.text
    assert 'id="new-chat"' in r.text
    assert 'id="session-list"' in r.text


def test_jobs_list_at_slash_jobs(web_client):
    r = web_client.get("/jobs")
    assert r.status_code == 200
    assert 'id="jobs-table"' in r.text


def test_chat_page_has_new_chat_and_history_controls(web_client):
    r = web_client.get("/")
    assert "New chat" in r.text
    assert "History" in r.text
    assert 'id="hitl-confirm"' in r.text


def test_nav_includes_chat_jobs_scraper(web_client):
    r = web_client.get("/")
    assert ">Chat</a>" in r.text or ">Chat<" in r.text
    assert 'href="/jobs"' in r.text
    assert 'href="/scraper"' in r.text
