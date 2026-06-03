from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.models import ApplicationStatus
from agentzero.storage.db import Database
from agentzero.web.app import create_app
from agentzero.web.chat.agent import AgentTurnResult
from tests.test_db import _job


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "t.db"
    settings = Settings(_env_file=None, db_path=db_path, openai_api_key="sk-test")
    app = create_app(db_path=db_path, settings=settings)
    db = Database(db_path)
    db.upsert_job(_job(status=ApplicationStatus.NEW))
    db.close()

    def fake_turn(store, session_id, content, *, db, llm=None, scrape_snapshot=None):
        if "status" in content.lower():
            pending = store.set_pending_action(
                session_id,
                tool_name="update_job_status",
                arguments={"job_id": db.list_job_ids()[0], "status": "applied"},
                summary="Set status",
            )
            store.append_message(session_id, role="user", content=content)
            store.append_message(session_id, role="assistant", content="Please confirm.")
            return AgentTurnResult(assistant_text="Please confirm.", pending_action=pending)
        store.append_message(session_id, role="user", content=content)
        store.append_message(session_id, role="assistant", content="Hello.")
        return AgentTurnResult(assistant_text="Hello.", pending_action=None)

    monkeypatch.setattr("agentzero.web.app.run_agent_turn", fake_turn)
    with TestClient(app) as client:
        yield client


def test_post_message_persists_and_returns_assistant(api_client):
    created = api_client.post("/api/chat/sessions", json={})
    session_id = created.json()["session_id"]
    r = api_client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "Hi"},
    )
    assert r.status_code == 200
    assert r.json()["assistant_text"] == "Hello."
    detail = api_client.get(f"/api/chat/sessions/{session_id}")
    roles = [m["role"] for m in detail.json()["messages"]]
    assert "user" in roles and "assistant" in roles


def test_confirm_endpoint_applies_pending(api_client):
    created = api_client.post("/api/chat/sessions", json={})
    session_id = created.json()["session_id"]
    api_client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "Update status please"},
    )
    r = api_client.post(f"/api/chat/sessions/{session_id}/confirm")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    detail = api_client.get(f"/api/chat/sessions/{session_id}")
    assert detail.json()["pending_action"] is None
