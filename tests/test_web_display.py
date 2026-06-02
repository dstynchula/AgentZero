from agentzero.web.display import (
    DEFAULT_SORT_COLUMN,
    build_list_query,
    parse_sort_params,
    sort_job_rows,
    truncate_display,
)


def test_truncate_short_unchanged():
    cell = truncate_display("hello", 80)
    assert cell.text == "hello"
    assert cell.truncated is False


def test_truncate_long_adds_ellipsis():
    cell = truncate_display("x" * 100, 80)
    assert cell.truncated is True
    assert cell.text.endswith("…")
    assert len(cell.text) == 80
    assert cell.full == "x" * 100


def test_sort_match_score_desc():
    rows = [
        {"match_score": 0.5, "company": "b"},
        {"match_score": 0.9, "company": "a"},
        {"match_score": None, "company": "c"},
    ]
    sorted_rows = sort_job_rows(rows, "match_score", descending=True)
    assert [r["company"] for r in sorted_rows] == ["a", "b", "c"]


def test_sort_company_asc():
    rows = [
        {"company": "Zeta", "match_score": 0.1},
        {"company": "Alpha", "match_score": 0.2},
    ]
    sorted_rows = sort_job_rows(rows, "company", descending=False)
    assert [r["company"] for r in sorted_rows] == ["Alpha", "Zeta"]


def test_sort_invalid_column_falls_back():
    rows = [{"match_score": 0.2}, {"match_score": 0.8}]
    sorted_rows = sort_job_rows(rows, "not_a_column", descending=True)
    assert sorted_rows[0]["match_score"] == 0.8


def test_parse_sort_params_defaults():
    column, descending = parse_sort_params(None, None)
    assert column == DEFAULT_SORT_COLUMN
    assert descending is True


def test_parse_sort_params_asc():
    column, descending = parse_sort_params("company", "asc")
    assert column == "company"
    assert descending is False


def test_build_list_query_includes_sort():
    q = build_list_query(show_rejected=True, sort="company", order="asc")
    assert "show_rejected=1" in q
    assert "sort=company" in q
    assert "order=asc" in q
