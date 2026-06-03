from agentzero.enrich.company_website import is_job_board_or_aggregator, pick_company_website
from agentzero.enrich.snippet_parse import parse_public_company_from_text
from agentzero.enrich.web_search import SearchHit


def test_parse_public_company_from_snippet_nasdaq():
    text = "Acme Corp (NASDAQ: ACME) is a publicly traded security software company."
    is_public, ticker = parse_public_company_from_text(text)
    assert is_public is True
    assert ticker == "ACME"


def test_parse_public_company_negative_private():
    text = "Acme is a privately held startup and not publicly traded."
    is_public, ticker = parse_public_company_from_text(text)
    assert is_public is False
    assert ticker is None


def test_company_website_not_job_board():
    assert is_job_board_or_aggregator("https://www.linkedin.com/company/acme")
    assert not is_job_board_or_aggregator("https://www.acme.com/")


def test_pick_company_website_from_search_hits():
    hits = [
        SearchHit(
            title="Acme Corporation",
            url="https://www.acme.com/",
            snippet="Official site",
        ),
        SearchHit(
            title="Jobs at Acme",
            url="https://www.indeed.com/cmp/acme",
            snippet="Open roles",
        ),
    ]
    url = pick_company_website(hits, company="Acme")
    assert url == "https://www.acme.com/"
