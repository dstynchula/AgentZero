from pathlib import Path

from agentzero.scrape.ats.greenhouse import parse_greenhouse_html
from agentzero.scrape.ats.lever import parse_lever_html
from agentzero.scrape.glassdoor import parse_glassdoor_company_html
from agentzero.scrape.validate import validate_raw

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_greenhouse_html_fixture():
    html = (FIXTURES / "greenhouse.html").read_text(encoding="utf-8")
    records = parse_greenhouse_html(html)
    assert len(records) == 2
    assert records[0]["title"] == "Software Engineer"


def test_parse_lever_html_fixture():
    html = (FIXTURES / "lever.html").read_text(encoding="utf-8")
    records = parse_lever_html(html)
    assert len(records) == 1
    assert records[0]["company"] == "Beta Inc"


def test_greenhouse_records_validate_to_job_posting():
    html = (FIXTURES / "greenhouse.html").read_text(encoding="utf-8")
    raw = parse_greenhouse_html(html)[0]
    outcome = validate_raw(raw, source="greenhouse")
    assert outcome.ok


def test_parse_glassdoor_company_html():
    html = (FIXTURES / "glassdoor_company.html").read_text(encoding="utf-8")
    rating, reviews = parse_glassdoor_company_html(html)
    assert rating == 4.3
    assert reviews == 842
