"""Application configuration loaded from environment variables and an optional .env file.

Most settings use the ``AGENTZERO_`` prefix. Provider API keys use their conventional names
(``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``) so existing shell setups work unchanged.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LLMProvider = Literal["openai", "anthropic"]


class Settings(BaseSettings):
    """Typed application settings.

    Construct with ``Settings()`` to read the process environment (and ``.env``), or
    ``Settings(_env_file=None)`` to read only explicitly-set environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENTZERO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- LLM ---
    llm_provider: LLMProvider = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "AGENTZERO_OPENAI_API_KEY"),
    )
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "AGENTZERO_ANTHROPIC_API_KEY"),
    )

    # --- Search profile ---
    search_terms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["software engineer"]
    )
    locations: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["Remote"])
    results_wanted: int = 50
    hours_old: int = 168
    country_indeed: str = "USA"

    # --- Scraping ---
    proxies: Annotated[list[str], NoDecode] = Field(default_factory=list)
    max_concurrency: int = 4

    # --- Storage ---
    db_path: Path = Path("data/agentzero.db")

    # --- Google ---
    google_client_secret: Path = Path("client_secret.json")
    google_token_path: Path = Path("token.json")
    sheet_id: str | None = None

    @field_validator("search_terms", "locations", "proxies", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow comma-separated env strings for list fields (e.g. ``a,b,c``)."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def active_api_key(self) -> str:
        """Return the API key for the selected provider, or raise a clear error."""
        key = self.openai_api_key if self.llm_provider == "openai" else self.anthropic_api_key
        if not key:
            env_name = "OPENAI_API_KEY" if self.llm_provider == "openai" else "ANTHROPIC_API_KEY"
            raise ValueError(
                f"Missing API key for llm_provider='{self.llm_provider}'. "
                f"Set the {env_name} environment variable."
            )
        return key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (reads the environment + .env once)."""
    return Settings()
