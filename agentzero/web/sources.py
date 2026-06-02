"""Scrape source catalog and enabled-state for the web config UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentzero.config import Settings
from agentzero.scrape.factory import (
    CORE_BROWSER_SITES,
    CORE_JOBSPY_SITES,
    build_scrape_source,
    list_source_names,
)
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
_JOBSPY_LABELS = {
    "google": "Google Jobs",
    "zip_recruiter": "ZipRecruiter",
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
    browser_on, jobspy_on = effective_scrape_lists(settings, operator)
    browser_set = {s.strip().lower() for s in browser_on}
    jobspy_set = {s.strip().lower() for s in jobspy_on}
    rows: list[SourceRow] = []
    for site in CORE_BROWSER_SITES:
        rows.append(
            SourceRow(
                id=site,
                name=_BROWSER_LABELS.get(site, site.title()),
                method="Playwright",
                group="browser",
                enabled=site in browser_set,
                uses_cdp=settings.use_cdp_for_site(site),
            )
        )
    for site in CORE_JOBSPY_SITES:
        rows.append(
            SourceRow(
                id=site,
                name=_JOBSPY_LABELS.get(site, site.title()),
                method="JobSpy",
                group="jobspy",
                enabled=site in jobspy_set,
                uses_cdp=False,
            )
        )
    return rows


def active_source_names(
    settings: Settings,
    operator: OperatorScrapeConfig | None,
) -> list[str]:
    cfg = settings_for_scrape(settings, operator)
    return list_source_names(build_scrape_source(cfg))
