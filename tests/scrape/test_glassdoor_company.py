"""Tests for Glassdoor employer name resolution."""

from pathlib import Path

from agentzero.scrape.browser_glassdoor import parse_glassdoor_search_html
from agentzero.scrape.glassdoor_company import (
    company_from_glassdoor_description,
    company_from_glassdoor_job_url,
    resolve_glassdoor_company,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_company_from_glassdoor_job_url():
    url = (
        "https://www.glassdoor.com/job-listing/"
        "cyber-security-engineer-lawrence-berkeley-national-laboratory-JV_KO0,23_KE24,61.htm"
    )
    company = company_from_glassdoor_job_url(url, title="Cyber Security Engineer")
    assert company == "Lawrence Berkeley National Laboratory"


def test_company_from_glassdoor_description_openings_for():
    description = (
        "<div>Lawrence Berkeley National Laboratory has multiple openings for a "
        "Cybersecurity Engineer in Berkeley, CA.</div>"
    )
    company = company_from_glassdoor_description(
        description,
        title="Cyber Security Engineer",
    )
    assert company == "Lawrence Berkeley National Laboratory"


def test_parse_glassdoor_search_html_resolves_company_from_job_listing_url():
    html = (FIXTURES / "glassdoor_job_listing_slug.html").read_text(encoding="utf-8")
    records = parse_glassdoor_search_html(html)
    assert len(records) == 1
    assert records[0]["company"] == "Lawrence Berkeley National Laboratory"


def test_company_from_lockheed_description():
    description = (
        "The coolest jobs on this planet... or any other... are with Lockheed Martin Space. "
        "At the dawn of a new space age, Lockheed Martin Space is a pioneer."
    )
    company = company_from_glassdoor_description(description, title="Cyber Security Engineer")
    assert company == "Lockheed Martin Space"


def test_company_from_amplitude_description():
    description = "Amplitude is the leading AI analytics platform, helping over 4,700 customers"
    company = company_from_glassdoor_description(description, title="Staff IT Security Engineer")
    assert company == "Amplitude"


def test_resolve_glassdoor_company_prefers_description():
    company = resolve_glassdoor_company(
        title="Staff IT Security Engineer",
        description="Acme Corp has multiple openings for a Staff IT Security Engineer.",
    )
    assert company == "Acme Corp"
