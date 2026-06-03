from agentzero.enrich.company_research import enrich_job_web_research, research_company
from agentzero.enrich.company_website import is_job_board_or_aggregator, pick_company_website
from agentzero.enrich.snippet_parse import parse_public_company_from_text
from agentzero.enrich.web_search import SearchHit
from agentzero.models import JobPosting


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


def test_parse_public_company_ignores_unrelated_ticker_in_same_blob():
    text = (
        "Johnson & Johnson (NYSE: JNJ) is a healthcare giant. "
        "Acme Corp is hiring security engineers in Austin."
    )
    is_public, ticker = parse_public_company_from_text(text, company="Acme Corp")
    assert is_public is None
    assert ticker is None


def test_parse_public_company_accepts_ticker_when_company_named_nearby():
    text = "Acme Corp (NASDAQ: ACME) is expanding its security team."
    is_public, ticker = parse_public_company_from_text(text, company="Acme Corp")
    assert is_public is True
    assert ticker == "ACME"


def test_research_company_does_not_merge_foreign_ticker(monkeypatch):
    from agentzero.config import Settings

    def fake_search(query, **kwargs):
        return [
            SearchHit(
                title="Top healthcare stocks",
                url="https://example.com/jnj",
                snippet="Johnson & Johnson (NYSE: JNJ) leads the sector.",
            )
        ]

    monkeypatch.setattr("agentzero.enrich.company_research.search_web", fake_search)
    cfg = Settings(_env_file=None)
    facts = research_company("Acme Corp", settings=cfg)
    assert facts.stock_ticker is None
    assert facts.is_public_company is None


def test_enrich_clears_stale_ticker_on_reenrich(monkeypatch):
    from agentzero.config import Settings
    from agentzero.enrich.company_research import CompanyWebFacts

    job = JobPosting(
        title="Engineer",
        company="Acme Corp",
        url="https://jobs.example.com/1",
        source="linkedin",
        stock_ticker="JNJ",
        is_public_company=True,
    )

    def fake_research(company, *, settings, user_agent=None):
        return CompanyWebFacts(is_public_company=None, stock_ticker=None)

    monkeypatch.setattr(
        "agentzero.enrich.company_research.research_company",
        fake_research,
    )
    cfg = Settings(_env_file=None)
    updated = enrich_job_web_research(job, settings=cfg)
    assert updated.stock_ticker is None
    assert updated.is_public_company is None


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
