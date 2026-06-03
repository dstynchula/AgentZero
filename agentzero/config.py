"""Application configuration loaded from environment variables and an optional .env file.

Most settings use the ``AGENTZERO_`` prefix. Provider API keys use their conventional names
(``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``) so existing shell setups work unchanged.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AliasChoices, Field, field_validator, model_validator
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
    llm_model: str = "gpt-5-nano"
    # Cover letters use a separate model (natural tone; higher cost than rank/scrape).
    cover_letter_model: str = "gpt-5.5"
    # Truncate job descriptions in rank prompts to control per-run LLM cost.
    rank_description_max_chars: int = 2_500
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
    remote_preferred: bool = False
    # When true, scrape only remote-USA queries and drop on-site/hybrid listings.
    remote_only: bool = True
    # Minimum acceptable comp (USD/year). Scraper keeps listings whose posted range
    # top (comp_max, or comp_min when no max) meets or exceeds this floor.
    salary_min: float | None = None
    salary_max: float | None = None  # deprecated; ignored at runtime
    # Prompt for titles/locations/salary before each scrape (disable for CI/automation).
    search_interactive: bool = True

    # --- Scraping ---
    proxies: Annotated[list[str], NoDecode] = Field(default_factory=list)
    max_concurrency: int = 4
    # Parallel LLM rank (classification) calls; I/O-bound — safe to raise if API limits allow.
    rank_max_concurrency: int = 8
    # Minimum match_score for CSV export (applied jobs always export).
    # Set to 0 or unset via blank env to disable filtering.
    min_match_score: float | None = 0.75
    # JobSpy HTTP boards (Google + ZipRecruiter). Indeed/LinkedIn/Glassdoor use Playwright.
    scrape_sites: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["google", "zip_recruiter"]
    )
    # Playwright boards — default LinkedIn only; enable Indeed/Glassdoor in Settings or env.
    scrape_browser_sites: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["linkedin"]
    )
    scrape_user_agent: str | None = None
    scrape_delay_seconds: float = 3.0
    # One primary title per run (first search term).
    scrape_primary_query_only: bool = True
    scrape_verbose: int = 1
    scrape_browser_headless: bool = False
    # When visible browser is used, pause for CAPTCHA/consent before scraping.
    scrape_browser_pause_for_captcha: bool = True
    # Persistent Chromium profile — cookies survive between runs after you pass CAPTCHA once.
    scrape_browser_profile_dir: Path = Path("data/indeed_browser_profile")
    # Use installed Chrome/Edge instead of bundled Chromium (e.g. chrome, msedge).
    scrape_browser_channel: str | None = None
    # Attach to Chrome started with --remote-debugging-port (interactive only).
    scrape_cdp_url: str | None = None
    # Allow host.docker.internal when running AgentZero inside Docker (compose sets this).
    cdp_allow_docker_host: bool = False
    # Launch dedicated CDP Chrome when endpoint is down (Windows/Linux/macOS).
    scrape_cdp_auto_launch: bool = True
    # Browser sites that use CDP when scrape_cdp_url is set (Indeed MFA; default indeed only).
    scrape_cdp_sites: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["indeed", "glassdoor"]
    )
    # Optional per-site cookie imports (Playwright storage_state JSON).
    scrape_storage_state_dir: Path = Path("data/browser_storage_state")
    # Fail fast when login wall detected before scrape (skip long CAPTCHA wait).
    scrape_session_preflight: bool = False
    linkedin_fetch_description: bool = False
    # Secondary enrichment: fetch job detail URLs + optional Glassdoor company lookup.
    enrich_fetch_details: bool = True
    enrich_glassdoor_lookup: bool = True
    enrich_delay_seconds: float = 2.0
    # Parallel HTTP + Glassdoor lookups in scripts/enrich_jobs.py (browser fallback stays sequential).
    enrich_max_concurrency: int = 6
    # Web search (DuckDuckGo) for company size, Glassdoor snippets, careers pages.
    enrich_web_search: bool = True
    enrich_web_search_max_results: int = 8
    enrich_web_search_delay_seconds: float = 2.0

    # --- Storage ---
    db_path: Path = Path("data/agentzero.db")

    # --- Web UI (Docker operator dashboard) ---
    web_enabled: bool = False
    web_host: str = "0.0.0.0"
    web_port: int = 8080

    @field_validator("search_terms", "locations", "proxies", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow comma-separated env strings for list fields (e.g. ``a,b,c``)."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("scrape_sites", "scrape_browser_sites", "scrape_cdp_sites", mode="before")
    @classmethod
    def _split_csv_lower(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        return value

    @field_validator("scrape_browser_channel", mode="before")
    @classmethod
    def _empty_channel_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("scrape_cdp_url", mode="before")
    @classmethod
    def _empty_cdp_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _validate_cdp_url(self) -> Self:
        if self.scrape_cdp_url is not None:
            from agentzero.net.cdp_safety import validate_cdp_url

            validated = validate_cdp_url(
                self.scrape_cdp_url,
                allow_docker_host=self.cdp_allow_docker_host,
            )
            object.__setattr__(self, "scrape_cdp_url", validated)
        return self

    @field_validator("web_port")
    @classmethod
    def _web_port_in_range(cls, value: int) -> int:
        if not 1 <= value <= 65_535:
            raise ValueError("web_port must be between 1 and 65535")
        return value

    def use_cdp_for_site(self, site: str) -> bool:
        """True when this site should attach to Chrome over CDP instead of Playwright launch."""
        if not self.scrape_cdp_url:
            return False
        key = site.strip().lower()
        if not self.scrape_cdp_sites:
            return True
        if any(s in ("*", "all") for s in self.scrape_cdp_sites):
            return True
        return key in self.scrape_cdp_sites

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


def reload_settings() -> Settings:
    """Drop cached settings and read the environment again (for tests / CLI)."""
    get_settings.cache_clear()
    return get_settings()
