from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agentzero.config import Settings
from agentzero.models import ApplicationStatus
from agentzero.storage.db import Database
from agentzero.web.chat.agent import run_agent_turn
from agentzero.web.chat.hitl import confirm_pending, execute_pending_action, reject_pending
from agentzero.web.chat.llm import ChatTurnResult, ToolCallResult
from agentzero.web.chat.store import ChatStore
from agentzero.web.scrape_runner import ScrapeRunner
from tests.test_db import _job


class FakeChatLLM:
    def __init__(self, result: ChatTurnResult) -> None:
        self._result = result

    def complete_with_tools(self, *, messages, tools):
        return self._result


@pytest.fixture
def hitl_env(tmp_path: Path):
    db_path = tmp_path / "t.db"
    db = Database(db_path)
    store = ChatStore(db)
    settings = Settings(_env_file=None, db_path=db_path, openai_api_key="sk-test")
    job = _job(status=ApplicationStatus.NEW)
    db.upsert_job(job)
    session_id = store.create_session()
    scrape_runner = ScrapeRunner()
    cover_runner = MagicMock()
    cover_runner.start.return_value = (True, "ok")
    yield db, store, settings, job, session_id, scrape_runner, cover_runner
    db.close()


def test_mutating_tool_creates_pending_action_not_side_effect(hitl_env):
    db, store, _settings, job, session_id, _scrape, _cover = hitl_env
    llm = FakeChatLLM(
        ChatTurnResult(
            content="I'll update status.",
            tool_calls=[
                ToolCallResult(
                    id="c1",
                    name="update_job_status",
                    arguments={"job_id": job.job_id, "status": "applied"},
                )
            ],
        )
    )
    run_agent_turn(store, session_id, "Mark applied", db=db, llm=llm)
    pending = store.get_pending_action(session_id)
    assert pending is not None
    assert pending.tool_name == "update_job_status"
    assert db.get_job(job.job_id).status == ApplicationStatus.NEW


def test_confirm_executes_status_update(hitl_env, tmp_path: Path):
    db, store, settings, job, session_id, scrape_runner, cover_runner = hitl_env
    pending = store.set_pending_action(
        session_id,
        tool_name="update_job_status",
        arguments={"job_id": job.job_id, "status": "applied"},
        summary="Set status",
    )
    result = confirm_pending(
        store,
        session_id,
        db=db,
        settings=settings,
        scrape_runner=scrape_runner,
        cover_letter_runner=cover_runner,
        operator_config_path=tmp_path / "op.json",
    )
    assert result["ok"] is True
    assert db.get_job(job.job_id).status == ApplicationStatus.APPLIED
    assert store.get_pending_action(session_id) is None
    assert pending.tool_name == "update_job_status"


def test_reject_clears_pending(hitl_env):
    db, store, _settings, job, session_id, _scrape, _cover = hitl_env
    store.set_pending_action(
        session_id,
        tool_name="reject_job",
        arguments={"job_id": job.job_id},
        summary="Reject job",
    )
    result = reject_pending(store, session_id)
    assert result["ok"] is True
    assert store.get_pending_action(session_id) is None
    assert db.get_job(job.job_id).status == ApplicationStatus.NEW


def test_scrape_requires_confirm_before_runner_start(hitl_env, tmp_path: Path):
    db, store, settings, _job, session_id, scrape_runner, cover_runner = hitl_env
    started: list[bool] = []

    class TrackingRunner(ScrapeRunner):
        def start(self, **kwargs):
            started.append(True)
            return False, "busy"

    runner = TrackingRunner()
    pending = store.set_pending_action(
        session_id,
        tool_name="start_scrape",
        arguments={},
        summary="Start scrape",
    )
    assert started == []
    execute_pending_action(
        pending,
        db=db,
        settings=settings,
        scrape_runner=runner,
        cover_letter_runner=cover_runner,
        operator_config_path=tmp_path / "op.json",
    )
    assert started == [True]
