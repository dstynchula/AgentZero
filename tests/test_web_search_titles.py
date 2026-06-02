from agentzero.config import Settings
from agentzero.web.operator_config import OperatorScrapeConfig, patch_operator_config
from agentzero.web.search_titles import (
    add_operator_title,
    all_display_terms,
    apply_operator_search_terms,
    effective_search_terms,
    merge_title_selection,
    normalize_title_selection,
    remove_operator_title,
    sync_operator_titles_after_resume_load,
    title_rows,
)


def test_effective_search_terms_defaults_to_profile():
    profile = ["Engineer", "Architect"]
    assert effective_search_terms(profile, None) == profile


def test_effective_search_terms_operator_subset():
    op = OperatorScrapeConfig(search_terms=["Architect"])
    assert effective_search_terms(["Engineer", "Architect"], op) == ["Architect"]


def test_title_rows_hide_excluded_profile_terms():
    op = OperatorScrapeConfig(
        search_terms=["Architect"],
        excluded_search_terms=["Engineer"],
    )
    rows = title_rows(["Engineer", "Architect"], op)
    assert len(rows) == 1
    assert rows[0].term == "Architect"


def test_all_display_terms_shows_new_profile_and_custom():
    op = OperatorScrapeConfig(
        search_terms=["Engineer", "Custom Role"],
        excluded_search_terms=[],
    )
    labels = all_display_terms(["Engineer", "Architect", "Staff Engineer"], op)
    assert labels == ["Engineer", "Architect", "Staff Engineer", "Custom Role"]


def test_remove_hides_title_from_display(tmp_path):
    from agentzero.web.operator_config import load_operator_config, patch_operator_config

    cfg = tmp_path / "web_operator_config.json"
    profile = ["Engineer", "Architect"]
    patch_operator_config(cfg, search_terms=list(profile))
    remove_operator_title(cfg, "Engineer", profile_terms=profile)
    op = load_operator_config(cfg)
    rows = title_rows(profile, op)
    assert [r.term for r in rows] == ["Architect"]


def test_sync_adds_new_resume_titles(tmp_path):
    cfg = tmp_path / "web_operator_config.json"
    profile = ["Engineer", "Architect"]
    patch_operator_config(cfg, search_terms=["Engineer"])
    merged = sync_operator_titles_after_resume_load(cfg, profile)
    assert merged == ["Engineer", "Architect"]
    op = OperatorScrapeConfig(search_terms=merged)
    assert "Architect" in all_display_terms(profile, op)


def test_sync_skips_excluded_on_reload(tmp_path):
    cfg = tmp_path / "web_operator_config.json"
    profile = ["Engineer", "Architect", "Staff Engineer"]
    patch_operator_config(
        cfg,
        search_terms=["Architect"],
        excluded_search_terms=["Engineer"],
    )
    merged = sync_operator_titles_after_resume_load(cfg, profile)
    assert "Engineer" not in merged
    assert "Staff Engineer" in merged


def test_normalize_title_selection_order():
    terms = normalize_title_selection(
        ["Architect", "Engineer"],
        ["Engineer", "Architect", "Manager"],
    )
    assert terms == ["Architect", "Engineer"]


def test_apply_operator_search_terms():
    base = Settings(_env_file=None, search_terms=["A", "B", "C"])
    op = OperatorScrapeConfig(search_terms=["B", "A"])
    merged = apply_operator_search_terms(base, op)
    assert merged.search_terms == ["B", "A"]
    assert merged.scrape_primary_query_only is False


def test_add_custom_title(tmp_path):
    from agentzero.web.operator_config import patch_operator_config

    cfg = tmp_path / "web_operator_config.json"
    profile = ["Engineer", "Architect"]
    patch_operator_config(cfg, search_terms=list(profile))
    terms = add_operator_title(cfg, "Staff Engineer", profile_terms=profile)
    assert terms == ["Engineer", "Architect", "Staff Engineer"]


def test_remove_title(tmp_path):
    from agentzero.web.operator_config import patch_operator_config

    cfg = tmp_path / "web_operator_config.json"
    profile = ["Engineer", "Architect"]
    patch_operator_config(cfg, search_terms=["Engineer", "Architect", "Staff Engineer"])
    terms = remove_operator_title(cfg, "Staff Engineer", profile_terms=profile)
    assert "Staff Engineer" not in terms
    assert terms == ["Engineer", "Architect"]


def test_merge_title_selection_keeps_custom(tmp_path):
    op = OperatorScrapeConfig(search_terms=["Engineer", "Custom Role"])
    merged = merge_title_selection(["Engineer"], ["Engineer", "Architect"], op)
    assert merged == ["Engineer", "Custom Role"]


def test_title_rows_include_custom():
    op = OperatorScrapeConfig(search_terms=["Engineer", "Custom Role"])
    rows = title_rows(["Engineer", "Architect"], op)
    labels = [r.term for r in rows]
    assert "Engineer" in labels
    assert "Custom Role" in labels
    assert "Architect" in labels
