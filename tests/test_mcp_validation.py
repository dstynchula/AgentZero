"""Tests for MCP tool input validation."""

import pytest

from agentzero.mcp.validation import validate_job_ids, validate_scrape_tool_args


def test_validate_scrape_tool_args_ok():
    terms = validate_scrape_tool_args(
        ["Staff Security Engineer"],
        salary_min=200_000.0,
        results_wanted=25,
    )
    assert terms == ["Staff Security Engineer"]


def test_validate_scrape_tool_args_strips_and_skips_blank():
    terms = validate_scrape_tool_args(
        ["  Engineer  ", "", "  "],
        salary_min=None,
        results_wanted=None,
    )
    assert terms == ["Engineer"]


def test_validate_scrape_tool_args_rejects_empty():
    with pytest.raises(ValueError, match="at least one"):
        validate_scrape_tool_args([], salary_min=None, results_wanted=None)


def test_validate_scrape_tool_args_rejects_all_blank_terms():
    with pytest.raises(ValueError, match="non-empty title"):
        validate_scrape_tool_args(["", "  "], salary_min=None, results_wanted=None)


def test_validate_scrape_tool_args_rejects_too_many_terms():
    terms = [f"Title {i}" for i in range(13)]
    with pytest.raises(ValueError, match="limited to 12"):
        validate_scrape_tool_args(terms, salary_min=None, results_wanted=None)


def test_validate_scrape_tool_args_rejects_term_too_long():
    long_term = "x" * 121
    with pytest.raises(ValueError, match="search term too long"):
        validate_scrape_tool_args([long_term], salary_min=None, results_wanted=None)


def test_validate_scrape_tool_args_rejects_salary_out_of_range():
    with pytest.raises(ValueError, match="salary_min must be between"):
        validate_scrape_tool_args(["Engineer"], salary_min=-1.0, results_wanted=None)
    with pytest.raises(ValueError, match="salary_min must be between"):
        validate_scrape_tool_args(["Engineer"], salary_min=10_000_001.0, results_wanted=None)


def test_validate_scrape_tool_args_accepts_salary_boundaries():
    terms = validate_scrape_tool_args(["Engineer"], salary_min=0.0, results_wanted=None)
    assert terms == ["Engineer"]
    terms = validate_scrape_tool_args(["Engineer"], salary_min=10_000_000.0, results_wanted=None)
    assert terms == ["Engineer"]


def test_validate_scrape_tool_args_rejects_results_wanted_zero():
    with pytest.raises(ValueError, match="results_wanted must be >= 1"):
        validate_scrape_tool_args(["Engineer"], salary_min=None, results_wanted=0)


def test_validate_scrape_tool_args_rejects_huge_results():
    with pytest.raises(ValueError, match="results_wanted"):
        validate_scrape_tool_args(["Engineer"], salary_min=None, results_wanted=9999)


def test_validate_scrape_tool_args_accepts_results_wanted_boundary():
    terms = validate_scrape_tool_args(["Engineer"], salary_min=None, results_wanted=200)
    assert terms == ["Engineer"]


def test_validate_job_ids_dedupes():
    assert validate_job_ids(["a", "a", "b"]) == ["a", "b"]


def test_validate_job_ids_strips_whitespace():
    assert validate_job_ids(["  a  ", "b"]) == ["a", "b"]


def test_validate_job_ids_rejects_empty():
    with pytest.raises(ValueError, match="must not be empty"):
        validate_job_ids([])


def test_validate_job_ids_rejects_too_many():
    ids = [f"id-{i}" for i in range(501)]
    with pytest.raises(ValueError, match="limited to 500"):
        validate_job_ids(ids)


def test_validate_job_ids_rejects_all_blank_or_duplicate():
    with pytest.raises(ValueError, match="non-empty id"):
        validate_job_ids(["", "  ", ""])
