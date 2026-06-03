from agentzero.enrich.detail_fetch import merge_detail_fields
from agentzero.models import JobPosting
from agentzero.scrape.apply_links import extract_apply_fields_from_html, safe_http_url


def test_safe_http_url_rejects_unsafe():
    assert safe_http_url("http://127.0.0.1/apply") is None


def test_parse_linkedin_detail_finds_external_apply():
    html = """
    <html><body>
    <a class="jobs-apply-button" href="https://www.indeed.com/viewjob?jk=apply99">Apply</a>
    <p>Easy Apply</p>
    </body></html>
    """
    fields = extract_apply_fields_from_html(
        html,
        source="linkedin",
        posting_url="https://www.linkedin.com/jobs/view/123",
    )
    assert fields.get("easy_apply") is True
    assert fields.get("apply_url") == "https://www.indeed.com/viewjob?jk=apply99"


def test_merge_detail_fields_sets_apply_url():
    job = JobPosting(
        title="Engineer",
        company="Acme",
        url="https://www.linkedin.com/jobs/view/1",
        source="linkedin",
    )
    merged = merge_detail_fields(
        job,
        {"apply_url": "https://www.indeed.com/viewjob?jk=apply1", "easy_apply": True},
    )
    assert merged.apply_url == "https://www.indeed.com/viewjob?jk=apply1"
    assert merged.easy_apply is True


def test_job_to_row_includes_apply_url():
    from agentzero.storage.csv_export import job_to_row

    job = JobPosting(
        title="Engineer",
        company="Acme",
        url="https://www.indeed.com/viewjob?jk=abc",
        source="indeed",
        apply_url="https://apply.example.com/role",
        easy_apply=True,
    )
    row = job_to_row(job)
    assert row["apply_url"] == "https://apply.example.com/role"
    assert row["easy_apply"] is True
