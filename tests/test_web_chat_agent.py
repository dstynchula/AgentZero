from pathlib import Path
from typing import Any

import pytest

from agentzero.config import Settings
from agentzero.storage.db import Database
from agentzero.web.chat.agent import run_agent_turn
from agentzero.web.chat.llm import ChatTurnResult, ToolCallResult
from agentzero.web.chat.store import ChatStore
from agentzero.web.chat.tools import execute_read_tool
from tests.test_db import _job


class FakeChatLLM:
    def __init__(self, responses: list[ChatTurnResult]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatTurnResult:
        self.calls.append({"messages": messages, "tools": tools})
        if not self._responses:
            return ChatTurnResult(content="Done.", tool_calls=[])
        return self._responses.pop(0)


@pytest.fixture
def chat_agent_env(tmp_path: Path):
    db_path = tmp_path / "t.db"
    db = Database(db_path)
    store = ChatStore(db)
    settings = Settings(_env_file=None, db_path=db_path, openai_api_key="sk-test")
    job = _job(title="Staff Engineer", company="Acme")
    db.upsert_job(job)
    yield db, store, settings, job
    db.close()


def test_chat_agent_lists_jobs_from_db(chat_agent_env):
    db, store, _settings, job = chat_agent_env
    session_id = store.create_session()
    llm = FakeChatLLM(
        [
            ChatTurnResult(
                content=None,
                tool_calls=[ToolCallResult(id="c1", name="list_jobs", arguments={})],
            ),
            ChatTurnResult(content="Here are your jobs.", tool_calls=[]),
        ]
    )
    run_agent_turn(store, session_id, "List jobs", db=db, llm=llm)
    tool_msgs = [m for m in store.list_messages(session_id) if m.role == "tool"]
    assert tool_msgs
    payload = __import__("json").loads(tool_msgs[0].content)
    assert payload["count"] == 1
    assert payload["jobs"][0]["job_id"] == job.job_id


def test_chat_agent_summarizes_job_detail(chat_agent_env):
    db, store, _settings, job = chat_agent_env
    session_id = store.create_session()
    llm = FakeChatLLM(
        [
            ChatTurnResult(
                content=None,
                tool_calls=[
                    ToolCallResult(id="c1", name="get_job", arguments={"job_id": job.job_id})
                ],
            ),
            ChatTurnResult(content="Found the job.", tool_calls=[]),
        ]
    )
    run_agent_turn(store, session_id, "Tell me about Acme", db=db, llm=llm)
    tool_msgs = [m for m in store.list_messages(session_id) if m.role == "tool"]
    data = __import__("json").loads(tool_msgs[0].content)
    assert data["job"]["title"] == "Staff Engineer"


def test_chat_agent_includes_resume_search_profile(chat_agent_env, monkeypatch):
    db, store, _settings, _job = chat_agent_env
    monkeypatch.setattr(
        "agentzero.web.chat.tools.load_search_profile",
        lambda: None,
    )
    monkeypatch.setattr(
        "agentzero.web.chat.tools.search_profile_summary",
        lambda _snap: {"terms": ["engineer"], "locations": ["Remote"]},
    )
    result = execute_read_tool("get_search_profile_summary", {}, db=db)
    assert result["profile"]["terms"] == ["engineer"]


def test_get_scraper_status_includes_progress(chat_agent_env):
    db, _store, _settings, _job = chat_agent_env
    scrape_snapshot = {
        "running": True,
        "message": "Scraping job boards (1/3) — indeed",
        "phase": "scrape",
        "done": 1,
        "total": 3,
        "detail": "indeed",
        "scraped": None,
        "leads": None,
        "errors": [],
    }
    result = execute_read_tool(
        "get_scraper_status",
        {},
        db=db,
        scrape_snapshot=scrape_snapshot,
    )
    assert result["scrape"]["phase"] == "scrape"
    assert result["scrape"]["done"] == 1
    assert result["scrape"]["total"] == 3


def test_chat_uses_chat_model_setting():
    settings = Settings(
        _env_file=None,
        openai_api_key="sk-test",
        chat_model="gpt-custom-chat",
        llm_provider="openai",
    )
    from agentzero.web.chat.llm import OpenAIChatClient

    client = OpenAIChatClient(api_key="sk-test", model=settings.chat_model, client=object())
    assert client.model == "gpt-custom-chat"
