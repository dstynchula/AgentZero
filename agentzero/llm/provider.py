"""Provider-agnostic LLM interface selected via settings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol

from agentzero.config import Settings, get_settings


class ChatClient(Protocol):
    def create_completion(self, *, system: str, user: str) -> str: ...


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, *, system: str, user: str) -> str:
        """Return the model's text response."""


class OpenAIProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self._client = client

    def complete(self, *, system: str, user: str) -> str:
        client = self._client or self._build_client()
        response = client.create_completion(system=system, user=user)
        return response

    def _build_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "OpenAI provider requires the 'openai' package. "
                "Install with: pip install -e '.[llm]'"
            ) from exc

        inner = OpenAI(api_key=self.api_key)
        model = self.model

        class _Adapter:
            def create_completion(self, *, system: str, user: str) -> str:
                result = inner.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                return result.choices[0].message.content or ""

        return _Adapter()


class AnthropicProvider(LLMProvider):
    def __init__(self, *, api_key: str, model: str, client: Any | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self._client = client

    def complete(self, *, system: str, user: str) -> str:
        client = self._client or self._build_client()
        return client.create_completion(system=system, user=user)

    def _build_client(self) -> Any:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ImportError(
                "Anthropic provider requires the 'anthropic' package. "
                "Install with: pip install -e '.[llm]'"
            ) from exc

        inner = Anthropic(api_key=self.api_key)
        model = self.model

        class _Adapter:
            def create_completion(self, *, system: str, user: str) -> str:
                result = inner.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                parts = [block.text for block in result.content if hasattr(block, "text")]
                return "".join(parts)

        return _Adapter()


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Construct the configured LLM provider using environment settings."""
    cfg = settings or get_settings()
    key = cfg.active_api_key
    if cfg.llm_provider == "openai":
        return OpenAIProvider(api_key=key, model=cfg.llm_model)
    return AnthropicProvider(api_key=key, model=cfg.llm_model)
