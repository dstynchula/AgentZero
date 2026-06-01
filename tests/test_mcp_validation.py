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


def test_validate_scrape_tool_args_rejects_empty():
    with pytest.raises(ValueError, match="at least one"):
        validate_scrape_tool_args([], salary_min=None, results_wanted=None)


def test_validate_scrape_tool_args_rejects_huge_results():
    with pytest.raises(ValueError, match="results_wanted"):
        validate_scrape_tool_args(["Engineer"], salary_min=None, results_wanted=9999)


def test_validate_job_ids_dedupes():
    assert validate_job_ids(["a", "a", "b"]) == ["a", "b"]
