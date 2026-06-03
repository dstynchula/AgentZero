"""Scrape source catalog and enabled-state for the web config UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentzero.config import Settings
from agentzero.scrape.factory import CORE_BROWSER_SITES, build_scrape_source, list_source_names
from agentzero.web.operator_config import (
    OperatorScrapeConfig,
    effective_scrape_lists,
    settings_for_scrape,
)

_BROWSER_LABELS = {
    "indeed": "Indeed",
    "linkedin": "LinkedIn",
    "glassdoor": "Glassdoor",
}


@dataclass(frozen=True, slots=True)
class SourceRow:
    id: str
    name: str
    method: str
    group: str
    enabled: bool
    uses_cdp: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "method": self.method,
            "group": self.group,
            "enabled": self.enabled,
            "uses_cdp": self.uses_cdp,
        }


def source_catalog(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> list[SourceRow]:
    browser_on, _jobspy_ignored = effective_scrape_lists(settings, operator)
    browser_set = {s.strip().lower() for s in browser_on}
    rows: list[SourceRow] = []

    def _browser_row(site: str) -> SourceRow:
        return SourceRow(
            id=site,
            name=_BROWSER_LABELS.get(site, site.title()),
            method="Playwright",
            group="browser",
            enabled=site in browser_set,
            uses_cdp=settings.use_cdp_for_site(site),
        )

    for site in CORE_BROWSER_SITES:
        if not settings.use_cdp_for_site(site):
            rows.append(_browser_row(site))
    for site in CORE_BROWSER_SITES:
        if settings.use_cdp_for_site(site):
            rows.append(_browser_row(site))
    return rows


def active_source_names(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> list[str]:
    cfg = settings_for_scrape(settings, operator)
    return list_source_names(build_scrape_source(cfg))
