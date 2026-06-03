import time
from pathlib import Path

import pytest

from agentzero.storage.db import Database
from agentzero.web.chat.store import ChatStore


@pytest.fixture
def chat_store(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    store = ChatStore(db)
    yield store
    db.close()


def test_create_session_returns_id(chat_store: ChatStore):
    session_id = chat_store.create_session(title="Hello")
    assert len(session_id) == 32
    session = chat_store.get_session(session_id)
    assert session is not None
    assert session.title == "Hello"
    assert session.archived is False


@pytest.mark.slow
@pytest.mark.timeout(10)
def test_list_sessions_newest_first(chat_store: ChatStore):
    first = chat_store.create_session(title="First")
    time.sleep(1.1)
    second = chat_store.create_session(title="Second")
    time.sleep(1.1)
    chat_store.touch_session(first)
    sessions = chat_store.list_sessions()
    assert [s.session_id for s in sessions] == [first, second]


def test_append_message_round_trip(chat_store: ChatStore):
    session_id = chat_store.create_session()
    user = chat_store.append_message(session_id, role="user", content="Hi")
    assistant = chat_store.append_message(
        session_id,
        role="assistant",
        content="Hello",
        tool_calls=[{"name": "list_jobs", "arguments": {}}],
    )
    messages = chat_store.list_messages(session_id)
    assert len(messages) == 2
    assert messages[0].id == user.id
    assert messages[1].tool_calls == [{"name": "list_jobs", "arguments": {}}]
    assert messages[1].id == assistant.id


def test_delete_or_archive_session(chat_store: ChatStore):
    session_id = chat_store.create_session(title="Remove me")
    chat_store.append_message(session_id, role="user", content="x")
    assert chat_store.archive_session(session_id) is True
    assert chat_store.list_sessions() == []
    assert chat_store.list_sessions(include_archived=True)[0].archived is True

    other = chat_store.create_session(title="Delete me")
    assert chat_store.delete_session(other) is True
    assert chat_store.get_session(other) is None
