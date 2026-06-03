"""OpenAI chat completions with tool calling for the web assistant."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from agentzero.config import Settings, get_settings


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChatTurnResult:
    content: str | None
    tool_calls: list[ToolCallResult]


class ChatToolClient(Protocol):
    def complete_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatTurnResult: ...


class OpenAIChatClient:
    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self._client = client

    def complete_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatTurnResult:
        inner = self._client or self._build_client()
        response = inner.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
        )
        message = response.choices[0].message
        content = message.content
        tool_calls: list[ToolCallResult] = []
        for call in message.tool_calls or []:
            raw_args = call.function.arguments or "{}"
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(
                ToolCallResult(
                    id=call.id,
                    name=call.function.name,
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )
        return ChatTurnResult(content=content, tool_calls=tool_calls)

    def _build_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "Chat assistant requires the 'openai' package. "
                "Install with: pip install -e '.[llm]'"
            ) from exc
        return OpenAI(api_key=self.api_key)


def build_chat_client(settings: Settings | None = None) -> ChatToolClient:
    """Construct the OpenAI tool-calling client for the web chat assistant."""
    cfg = settings or get_settings()
    if cfg.llm_provider != "openai":
        raise ValueError(
            "Web chat assistant requires AGENTZERO_LLM_PROVIDER=openai "
            f"(got {cfg.llm_provider!r}). Anthropic chat tools are not supported in v1."
        )
    if not cfg.openai_api_key:
        raise ValueError("Missing API key for chat. Set OPENAI_API_KEY.")
    return OpenAIChatClient(api_key=cfg.openai_api_key, model=cfg.chat_model)
