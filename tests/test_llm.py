import pytest

from agentzero.config import Settings
from agentzero.llm.provider import AnthropicProvider, OpenAIProvider, build_llm_provider


class FakeClient:
    def __init__(self, response: str = "ok") -> None:
        self.calls: list[tuple[str, str]] = []
        self._response = response

    def create_completion(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._response


def test_openai_provider_uses_injected_client():
    client = FakeClient("hello from openai")
    provider = OpenAIProvider(api_key="sk-test", model="gpt-test", client=client)
    assert provider.complete(system="sys", user="hi") == "hello from openai"
    assert client.calls == [("sys", "hi")]


def test_anthropic_provider_uses_injected_client():
    client = FakeClient("hello from anthropic")
    provider = AnthropicProvider(api_key="sk-ant", model="claude-test", client=client)
    assert provider.complete(system="sys", user="hi") == "hello from anthropic"


def test_build_llm_provider_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = Settings(_env_file=None, llm_provider="openai", llm_model="gpt-test")
    provider = build_llm_provider(cfg)
    assert isinstance(provider, OpenAIProvider)


def test_build_llm_provider_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    cfg = Settings(_env_file=None, llm_provider="anthropic", llm_model="claude-test")
    provider = build_llm_provider(cfg)
    assert isinstance(provider, AnthropicProvider)


def test_openai_provider_import_error_without_package(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "openai":
            raise ImportError("No module named 'openai'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    provider = OpenAIProvider(api_key="sk", model="gpt", client=None)
    with pytest.raises(ImportError, match="openai"):
        provider._build_client()


def test_anthropic_provider_import_error_without_package(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    provider = AnthropicProvider(api_key="sk", model="claude", client=None)
    with pytest.raises(ImportError, match="anthropic"):
        provider._build_client()
