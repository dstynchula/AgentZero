"""Chat agent turn loop — read tools inline, write tools become pending HITL actions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agentzero.web.chat.llm import ChatToolClient, build_chat_client
from agentzero.web.chat.store import ChatStore, PendingAction
from agentzero.web.chat.tools import (
    CHAT_SYSTEM_PROMPT,
    MUTATING_TOOL_NAMES,
    READ_TOOL_NAMES,
    execute_read_tool,
    openai_tool_specs,
    pending_action_summary,
)

_MAX_TOOL_ROUNDS = 8


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    assistant_text: str
    pending_action: PendingAction | None


def _history_for_llm(store: ChatStore, session_id: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    for msg in store.list_messages(session_id):
        if msg.role == "tool":
            messages.append({"role": "tool", "content": msg.content, "tool_call_id": msg.tool_calls[0]["id"] if msg.tool_calls else ""})
            continue
        entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.tool_calls and msg.role == "assistant":
            entry["tool_calls"] = [
                {
                    "id": tc.get("id", f"call_{idx}"),
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("arguments") or {}),
                    },
                }
                for idx, tc in enumerate(msg.tool_calls)
            ]
        messages.append(entry)
    return messages


def run_agent_turn(
    store: ChatStore,
    session_id: str,
    user_text: str,
    *,
    db,
    llm: ChatToolClient | None = None,
    scrape_snapshot: dict[str, Any] | None = None,
) -> AgentTurnResult:
    """Append user message, run LLM tool loop, persist assistant reply."""
    store.append_message(session_id, role="user", content=user_text)
    if not store.get_session(session_id):
        raise LookupError("session not found")

    client = llm or build_chat_client()
    tools = openai_tool_specs()
    messages = _history_for_llm(store, session_id)

    for _ in range(_MAX_TOOL_ROUNDS):
        turn = client.complete_with_tools(messages=messages, tools=tools)
        if not turn.tool_calls:
            text = (turn.content or "").strip() or "Done."
            store.append_message(session_id, role="assistant", content=text)
            if len(user_text) <= 60:
                session = store.get_session(session_id)
                if session is not None and not session.title:
                    store.touch_session(session_id, title=user_text[:60])
            return AgentTurnResult(assistant_text=text, pending_action=None)

        assistant_calls = [
            {
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in turn.tool_calls
        ]
        intro = (turn.content or "").strip()
        store.append_message(
            session_id,
            role="assistant",
            content=intro or "I'll use a tool for that.",
            tool_calls=assistant_calls,
        )
        messages = _history_for_llm(store, session_id)

        for call in turn.tool_calls:
            if call.name in MUTATING_TOOL_NAMES:
                summary = pending_action_summary(call.name, call.arguments)
                pending = store.set_pending_action(
                    session_id,
                    tool_name=call.name,
                    arguments=call.arguments,
                    summary=summary,
                )
                confirm_text = (
                    f"{summary}\n\nPlease review and click Confirm or Reject in the UI."
                )
                if intro:
                    confirm_text = f"{intro}\n\n{confirm_text}"
                store.append_message(session_id, role="assistant", content=confirm_text)
                return AgentTurnResult(assistant_text=confirm_text, pending_action=pending)

            if call.name not in READ_TOOL_NAMES:
                result = {"error": f"unknown tool: {call.name}"}
            else:
                result = execute_read_tool(
                    call.name,
                    call.arguments,
                    db=db,
                    scrape_snapshot=scrape_snapshot,
                )
            tool_content = json.dumps(result)
            store.append_message(
                session_id,
                role="tool",
                content=tool_content,
                tool_calls=[{"id": call.id}],
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": tool_content,
                }
            )

    fallback = "I hit the tool limit — try a simpler question."
    store.append_message(session_id, role="assistant", content=fallback)
    return AgentTurnResult(assistant_text=fallback, pending_action=None)
