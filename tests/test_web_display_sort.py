from agentzero.web.display import sort_job_rows


def test_sort_job_rows_by_each_column():
    rows = [
        {"title": "Beta", "company": "Z Corp", "match_score": 0.5, "source": "indeed"},
        {"title": "Alpha", "company": "A Inc", "match_score": 0.9, "source": "linkedin"},
    ]
    for col in ("title", "company", "source"):
        asc = sort_job_rows(rows, col, descending=False)
        assert asc[0][col] < asc[1][col] or str(asc[0][col]) <= str(asc[1][col])
        desc = sort_job_rows(rows, col, descending=True)
        assert str(desc[0][col]) >= str(desc[1][col])
    by_score = sort_job_rows(rows, "match_score", descending=True)
    assert by_score[0]["match_score"] == 0.9
