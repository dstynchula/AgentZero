from agentzero.config import Settings
from agentzero.web.operator_config import OperatorScrapeConfig
from agentzero.web.search_titles import (
    add_operator_title,
    apply_operator_search_terms,
    effective_search_terms,
    merge_title_selection,
    normalize_title_selection,
    remove_operator_title,
    title_rows,
)


def test_effective_search_terms_defaults_to_profile():
    profile = ["Engineer", "Architect"]
    assert effective_search_terms(profile, None) == profile


def test_effective_search_terms_operator_subset():
    op = OperatorScrapeConfig(search_terms=["Architect"])
    assert effective_search_terms(["Engineer", "Architect"], op) == ["Architect"]


def test_title_rows_reflect_selection():
    op = OperatorScrapeConfig(search_terms=["Architect"])
    rows = title_rows(["Engineer", "Architect"], op)
    assert rows[0].selected is False
    assert rows[1].selected is True


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
    cfg = tmp_path / "web_operator_config.json"
    profile = ["Engineer", "Architect"]
    terms = add_operator_title(cfg, "Staff Engineer", profile_terms=profile)
    assert terms == ["Engineer", "Architect", "Staff Engineer"]


def test_remove_title(tmp_path):
    cfg = tmp_path / "web_operator_config.json"
    profile = ["Engineer", "Architect"]
    add_operator_title(cfg, "Staff Engineer", profile_terms=profile)
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
    assert "Custom Role" in labels
