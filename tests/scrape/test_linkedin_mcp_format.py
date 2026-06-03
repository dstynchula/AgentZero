from agentzero.scrape.linkedin_mcp_format import (
    format_job_details,
    format_pull_result,
    raw_record_to_preview,
)


def test_format_pull_result_job_ids_and_sections():
    records = [
        {
            "title": "Staff Security Engineer",
            "company": "Acme",
            "url": "https://www.linkedin.com/jobs/view/1234567890",
            "source": "linkedin",
        }
    ]
    out = format_pull_result(
        url="https://www.linkedin.com/jobs/search",
        records=records,
        sections={"search": "snippet"},
    )
    assert out["count"] == 1
    assert len(out["job_ids"]) == 1
    assert out["sections"]["search"] == "snippet"
    assert out["jobs"][0]["title"] == "Staff Security Engineer"


def test_raw_records_include_stable_job_id():
    preview = raw_record_to_preview(
        {
            "title": "Engineer",
            "company": "Co",
            "url": "https://www.linkedin.com/jobs/view/9999999999",
            "source": "linkedin",
        }
    )
    assert preview["job_id"]
    assert preview["company"] == "Co"


def test_format_job_details_from_raw_records():
    record = {
        "title": "Engineer",
        "company": "Co",
        "url": "https://www.linkedin.com/jobs/view/9999999999",
        "source": "linkedin",
    }
    out = format_job_details(url=record["url"], html="<html>detail</html>", record=record)
    assert "job_page" in out["sections"]
    assert out["job_id"] == raw_record_to_preview(record)["job_id"]
