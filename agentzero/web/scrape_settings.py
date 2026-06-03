"""Effective Settings for web/UI LinkedIn scrape (operator + search profile)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentzero.config import Settings


def build_web_scrape_settings(
    base: Settings | None = None,
    *,
    operator_config_path: Path | None = None,
) -> Settings:
    """Merge env settings with search profile and ``data/web_operator_config.json``."""
    from agentzero.config import get_settings
    from agentzero.ingest.search_profile import apply_search_profile, load_search_profile
    from agentzero.scrape.remote_policy import apply_remote_only_settings
    from agentzero.web.operator_config import (
        load_operator_config,
    )
    from agentzero.web.operator_config import (
        operator_config_path as default_operator_config_path,
    )
    from agentzero.web.search_targets import apply_operator_search_targets
    from agentzero.web.search_titles import apply_operator_search_terms

    cfg = base or get_settings()
    op_path = operator_config_path or default_operator_config_path(cfg.db_path)
    operator = load_operator_config(op_path)
    snapshot = load_search_profile()
    if snapshot is None:
        return cfg
    return apply_remote_only_settings(
        apply_operator_search_targets(
            apply_operator_search_terms(
                apply_search_profile(cfg, snapshot),
                operator,
            ),
            operator,
        )
    )
