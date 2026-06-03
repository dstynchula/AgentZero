"""Persist operator scrape source toggles beside the SQLite DB."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agentzero.config import Settings
from agentzero.scrape.factory import CORE_BROWSER_SITES

WorkModeField = Literal["remote", "in_office"]


class OperatorScrapeConfig(BaseModel):
    """Saved operator overrides beside the DB; empty lists fall back to env/profile."""

    scrape_browser_sites: list[str] = Field(default_factory=list)
    scrape_sites: list[str] = Field(default_factory=list)
    # Active scrape titles (résumé + custom). Empty with no config file → use full profile.
    search_terms: list[str] = Field(default_factory=list)
    # Profile titles the operator removed (hidden until re-added manually).
    excluded_search_terms: list[str] = Field(default_factory=list)
    # Search targets (location / comp / remote) — applied when search_targets_configured.
    work_mode: WorkModeField | None = None
    locations: list[str] = Field(default_factory=list)
    salary_min: float | None = None
    scrape_remote_only: bool = False
    search_targets_configured: bool = False


def operator_config_path(db_path: Path) -> Path:
    return db_path.parent / "web_operator_config.json"


def load_operator_config(path: Path) -> OperatorScrapeConfig | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return OperatorScrapeConfig.model_validate(data)


def save_operator_config(path: Path, config: OperatorScrapeConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2) + "\n", encoding="utf-8")


def patch_operator_config(path: Path, **updates: object) -> OperatorScrapeConfig:
    """Update selected fields; leave others unchanged."""
    existing = load_operator_config(path) or OperatorScrapeConfig()
    merged = existing.model_copy(update=updates)
    save_operator_config(path, merged)
    return merged


def effective_scrape_lists(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> tuple[list[str], list[str]]:
    """Return (browser_sites, legacy_jobspy_sites) after optional operator overlay."""
    browser = list(settings.scrape_browser_sites)
    if operator is not None and operator.scrape_browser_sites:
        browser = operator.scrape_browser_sites
    return browser, []


def settings_for_scrape(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> Settings:
    browser, jobspy = effective_scrape_lists(settings, operator)
    return settings.model_copy(
        update={
            "scrape_browser_sites": browser,
            "scrape_sites": jobspy,
            "search_interactive": False,
        }
    )


def normalize_source_selection(
    browser_sites: list[str],
    jobspy_sites: list[str] | None = None,
) -> OperatorScrapeConfig:
    _ = jobspy_sites
    browser = [s for s in browser_sites if s in CORE_BROWSER_SITES]
    return OperatorScrapeConfig(
        scrape_browser_sites=browser,
        scrape_sites=[],
    )
