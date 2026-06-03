"""SQLite-backed chat session history and pending HITL actions."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any

from agentzero.storage.db import Database, _utc_now_iso

ChatRole = str  # "user" | "assistant" | "tool"


@dataclass(frozen=True, slots=True)
class ChatSessionSummary:
    session_id: str
    title: str
    created_at: str
    updated_at: str
    archived: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "archived": self.archived,
        }


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: int
    session_id: str
    role: ChatRole
    content: str
    tool_calls: list[dict[str, Any]] | None
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class PendingAction:
    id: int
    session_id: str
    tool_name: str
    arguments: dict[str, Any]
    summary: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "summary": self.summary,
            "created_at": self.created_at,
        }


def _row_session(row: sqlite3.Row) -> ChatSessionSummary:
    return ChatSessionSummary(
        session_id=row["session_id"],
        title=row["title"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        archived=bool(row["archived"]),
    )


def _row_message(row: sqlite3.Row) -> ChatMessage:
    raw_tools = row["tool_calls"]
    tool_calls = json.loads(raw_tools) if raw_tools else None
    return ChatMessage(
        id=int(row["id"]),
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        tool_calls=tool_calls,
        created_at=row["created_at"],
    )


def _row_pending(row: sqlite3.Row) -> PendingAction:
    return PendingAction(
        id=int(row["id"]),
        session_id=row["session_id"],
        tool_name=row["tool_name"],
        arguments=json.loads(row["arguments"]),
        summary=row["summary"],
        created_at=row["created_at"],
    )


class ChatStore:
    """Chat persistence using the shared AgentZero SQLite database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create_session(self, *, title: str = "") -> str:
        session_id = uuid.uuid4().hex
        now = _utc_now_iso()

        def _write(conn: sqlite3.Connection) -> str:
            conn.execute(
                """
                INSERT INTO chat_sessions (session_id, title, created_at, updated_at, archived)
                VALUES (?, ?, ?, ?, 0)
                """,
                (session_id, title.strip(), now, now),
            )
            conn.commit()
            return session_id

        return self._db.with_connection(_write)

    def get_session(self, session_id: str) -> ChatSessionSummary | None:
        def _read(conn: sqlite3.Connection) -> ChatSessionSummary | None:
            row = conn.execute(
                """
                SELECT session_id, title, created_at, updated_at, archived
                FROM chat_sessions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            return _row_session(row) if row else None

        return self._db.with_connection(_read)

    def list_sessions(self, *, include_archived: bool = False) -> list[ChatSessionSummary]:
        def _read(conn: sqlite3.Connection) -> list[ChatSessionSummary]:
            if include_archived:
                rows = conn.execute(
                    """
                    SELECT session_id, title, created_at, updated_at, archived
                    FROM chat_sessions
                    ORDER BY updated_at DESC, session_id DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT session_id, title, created_at, updated_at, archived
                    FROM chat_sessions
                    WHERE archived = 0
                    ORDER BY updated_at DESC, session_id DESC
                    """
                ).fetchall()
            return [_row_session(row) for row in rows]

        return self._db.with_connection(_read)

    def touch_session(self, session_id: str, *, title: str | None = None) -> None:
        now = _utc_now_iso()

        def _write(conn: sqlite3.Connection) -> None:
            if title is not None:
                conn.execute(
                    """
                    UPDATE chat_sessions
                    SET updated_at = ?, title = ?
                    WHERE session_id = ?
                    """,
                    (now, title.strip(), session_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?
                    """,
                    (now, session_id),
                )
            conn.commit()

        self._db.with_connection(_write)

    def archive_session(self, session_id: str) -> bool:
        now = _utc_now_iso()

        def _write(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute(
                """
                UPDATE chat_sessions
                SET archived = 1, updated_at = ?
                WHERE session_id = ? AND archived = 0
                """,
                (now, session_id),
            )
            conn.commit()
            return cursor.rowcount > 0

        return self._db.with_connection(_write)

    def delete_session(self, session_id: str) -> bool:
        def _write(conn: sqlite3.Connection) -> bool:
            row = conn.execute(
                "SELECT 1 FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "DELETE FROM chat_pending_actions WHERE session_id = ?",
                (session_id,),
            )
            conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (session_id,),
            )
            conn.execute(
                "DELETE FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return True

        return self._db.with_connection(_write)

    def append_message(
        self,
        session_id: str,
        *,
        role: ChatRole,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        now = _utc_now_iso()
        tools_json = json.dumps(tool_calls) if tool_calls else None

        def _write(conn: sqlite3.Connection) -> ChatMessage:
            cursor = conn.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, tool_calls, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, tools_json, now),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT id, session_id, role, content, tool_calls, created_at
                FROM chat_messages WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
            assert row is not None
            return _row_message(row)

        return self._db.with_connection(_write)

    def list_messages(self, session_id: str) -> list[ChatMessage]:
        def _read(conn: sqlite3.Connection) -> list[ChatMessage]:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, tool_calls, created_at
                FROM chat_messages
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()
            return [_row_message(row) for row in rows]

        return self._db.with_connection(_read)

    def set_pending_action(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        summary: str,
    ) -> PendingAction:
        now = _utc_now_iso()
        args_json = json.dumps(arguments)

        def _write(conn: sqlite3.Connection) -> PendingAction:
            conn.execute(
                "DELETE FROM chat_pending_actions WHERE session_id = ?",
                (session_id,),
            )
            cursor = conn.execute(
                """
                INSERT INTO chat_pending_actions
                    (session_id, tool_name, arguments, summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, tool_name, args_json, summary.strip(), now),
            )
            conn.commit()
            row = conn.execute(
                """
                SELECT id, session_id, tool_name, arguments, summary, created_at
                FROM chat_pending_actions WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
            assert row is not None
            return _row_pending(row)

        return self._db.with_connection(_write)

    def get_pending_action(self, session_id: str) -> PendingAction | None:
        def _read(conn: sqlite3.Connection) -> PendingAction | None:
            row = conn.execute(
                """
                SELECT id, session_id, tool_name, arguments, summary, created_at
                FROM chat_pending_actions
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            return _row_pending(row) if row else None

        return self._db.with_connection(_read)

    def clear_pending_action(self, session_id: str) -> bool:
        def _write(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute(
                "DELETE FROM chat_pending_actions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

        return self._db.with_connection(_write)
