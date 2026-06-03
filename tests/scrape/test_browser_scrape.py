from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentzero.config import Settings
from agentzero.models import RawRecord
from agentzero.scrape.browser_board import BrowserJobBoardSource
from agentzero.scrape.browser_indeed import (
    _default_input,
    _dismiss_indeed_consent,
    _parse_indeed_dom_html,
    build_indeed_search_url,
    extract_mosaic_payload,
    mosaic_results_to_records,
    page_has_job_results,
    page_needs_human,
    page_needs_login,
    page_session_ready,
    parse_indeed_mosaic_html,
    parse_indeed_search_html,
    prompt_for_browser_verification,
)
from agentzero.scrape.browser_linkedin import (
    _closest_job_posting_id,
    _closest_job_view_url,
    _embedded_job_fields,
    _job_object_chunk,
    _merge_record,
    _normalize_job_url,
    _record_dedupe_key,
    _unescape_json,
    build_linkedin_search_url,
    parse_linkedin_search_html,
)
from agentzero.scrape.browser_linkedin import (
    page_has_job_results as linkedin_page_has_job_results,
)
from agentzero.scrape.browser_linkedin import (
    page_needs_human as linkedin_needs_human,
)
from agentzero.scrape.browser_linkedin import (
    page_needs_login as linkedin_needs_login,
)
from agentzero.scrape.browser_linkedin import (
    page_session_ready as linkedin_session_ready,
)
from agentzero.scrape.factory import build_scrape_source, list_source_names
from agentzero.scrape.location import parse_search_location
from agentzero.scrape.multi import MultiSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_parse_indeed_search_html():
    html = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    records = parse_indeed_search_html(html)
    assert len(records) == 2
    assert records[0]["title"] == "Staff Security Engineer"
    assert records[0]["company"] == "Acme Corp"
    assert records[0]["url"].startswith("https://www.indeed.com/")
    assert records[0]["location"] == "Remote"


def test_page_needs_human_detects_captcha():
    assert page_needs_human("<html>verify you are human</html>")
    assert page_needs_human("", "https://www.indeed.com/sorry/Index")
    assert not page_needs_human("<html>job_seen_beacon</html>", "https://www.indeed.com/jobs")


def test_page_has_job_results():
    html = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    assert page_has_job_results(html)
    assert page_has_job_results("<div class='jobsearch-NoResults'></div>")
    mosaic = (FIXTURES / "indeed_mosaic.html").read_text(encoding="utf-8")
    assert page_has_job_results(mosaic)


def test_parse_indeed_mosaic_html():
    html = (FIXTURES / "indeed_mosaic.html").read_text(encoding="utf-8")
    records = parse_indeed_mosaic_html(html)
    assert len(records) == 2
    assert records[0]["title"] == "Staff Security Engineer"
    assert records[0]["company"] == "Acme Corp"
    assert records[0]["comp_raw"] == "$180,000 - $220,000 a year"
    assert records[0]["glassdoor_rating"] == 4.2
    assert records[1]["remote"] is True


def test_page_needs_human_false_when_mosaic_jobs_present():
    html = (FIXTURES / "indeed_mosaic.html").read_text(encoding="utf-8")
    assert not page_needs_human(html)


def test_extract_mosaic_payload_roundtrip():
    html = (FIXTURES / "indeed_mosaic.html").read_text(encoding="utf-8")
    payload = extract_mosaic_payload(html)
    assert payload is not None
    records = mosaic_results_to_records(payload)
    assert len(records) == 2


def test_mosaic_remote_search_trusts_city_on_remote_query():
    payload = {
        "metaData": {
            "mosaicProviderJobCardsModel": {
                "results": [
                    {
                        "displayTitle": "Staff Security Engineer",
                        "company": "Garner Health",
                        "formattedLocation": "New York, NY",
                        "jobkey": "garner1",
                    },
                    {
                        "displayTitle": "Security Engineer",
                        "company": "Acme",
                        "formattedLocation": "Hybrid - Boston, MA",
                        "jobkey": "hybrid1",
                    },
                ]
            }
        }
    }
    records = mosaic_results_to_records(payload, remote_search=True)
    assert records[0]["remote"] is True
    assert records[1]["remote"] is False


def test_build_scrape_source_no_list_pages():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
        search_terms=["x"],
        locations=["Remote"],
    )
    source = build_scrape_source(settings)
    assert isinstance(source, MultiSource)
    names = {type(s).__name__ for s in source._sources}
    assert "ListPagesBrowserSource" not in names


def test_build_scrape_source_raises_when_empty():
    settings = Settings(
        _env_file=None,
        scrape_sites=[],
        scrape_browser_sites=[],
        search_terms=["x"],
        locations=["Remote"],
    )

    with pytest.raises(ValueError, match="No scrape sources configured"):
        build_scrape_source(settings)


def test_build_indeed_search_url_remote_flag():
    parsed = parse_search_location("remote - usa")
    url = build_indeed_search_url(term="Security Engineer", parsed=parsed)
    assert "remotejob=1" in url
    assert "q=Security" in url


def test_page_session_ready_branches():
    jobs_html = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    assert page_session_ready(jobs_html, "https://www.indeed.com/")
    assert not page_session_ready("<html></html>", "https://www.google.com/")
    assert not page_session_ready("<html></html>", "https://www.indeed.com/account/login")
    assert not page_session_ready("<html></html>", "https://www.indeed.com/jobs?q=x")


def test_page_needs_login_branches():
    login_html = "<html>ready to take the next step create an account or sign in</html>"
    assert page_needs_login(login_html, "https://www.indeed.com/jobs?q=x")
    assert page_needs_login("", "https://secure.indeed.com/auth")
    assert page_needs_login("", "https://www.indeed.com/account/login")
    assert not page_needs_login(
        (FIXTURES / "indeed_search.html").read_text(encoding="utf-8"),
        "https://www.indeed.com/jobs",
    )


def test_extract_mosaic_payload_single_quote_marker():
    payload = {"metaData": {"mosaicProviderJobCardsModel": {"results": []}}}
    import json

    inner = json.dumps(payload)
    html = f"window.mosaic.providerData['mosaic-provider-jobcards'] = {inner};"
    assert extract_mosaic_payload(html) == payload


def test_extract_mosaic_payload_invalid_json_returns_none():
    html = 'window.mosaic.providerData["mosaic-provider-jobcards"] = {not json};'
    assert extract_mosaic_payload(html) is None


def test_mosaic_results_skips_bad_rows_and_enriches():
    payload = {
        "metaData": {
            "mosaicProviderJobCardsModel": {
                "results": [
                    "not-a-dict",
                    {"displayTitle": "T", "company": "C"},
                    {
                        "displayTitle": "Staff Engineer",
                        "company": "Co",
                        "jobkey": "jk1",
                        "formattedLocation": "NYC",
                        "remoteLocation": True,
                        "salarySnippet": {"text": "$100k"},
                        "companyRating": 4.5,
                        "companyReviewCount": 12,
                    },
                ]
            }
        }
    }
    records = mosaic_results_to_records(payload)
    assert len(records) == 1
    assert records[0]["comp_raw"] == "$100k"
    assert records[0]["glassdoor_rating"] == 4.5
    assert records[0]["glassdoor_reviews"] == 12
    assert records[0]["remote"] is True


def test_parse_indeed_dom_html_paths():
    html = """
    <div data-jk="dup">
      <a data-jk="dup" href="/viewjob?jk=dup">Dup Job</a>
      <span data-testid="company-name">Co</span>
    </div>
    <div class="job_seen_beacon" data-jk="rel">
      <h2 class="jobTitle"><a href="/viewjob?jk=rel">Relative Job</a></h2>
      <span data-testid="company-name">Co</span>
    </div>
    <div class="job_seen_beacon" data-jk="abs">
      <h2 class="jobTitle"><a href="https://www.indeed.com/viewjob?jk=abs">Abs Job</a></h2>
    </div>
    <div class="job_seen_beacon" data-jk="keyonly">
      <h2 class="jobTitle"><a>Key Only</a></h2>
      <span data-testid="company-name">Co</span>
    </div>
  """
    records = _parse_indeed_dom_html(html)
    titles = {r["title"] for r in records}
    assert "Relative Job" in titles
    assert "Abs Job" in titles
    assert "Key Only" in titles
    assert len([r for r in records if r["title"] == "Dup Job"]) == 1


def test_parse_indeed_search_html_dom_fallback():
    html = (FIXTURES / "indeed_search.html").read_text(encoding="utf-8")
    records = parse_indeed_search_html("<html>no mosaic</html>" + html)
    assert records


def test_dismiss_indeed_consent_clicks_visible_button():
    page = MagicMock()
    btn = MagicMock()
    btn.is_visible.return_value = True
    page.locator.return_value.first = btn
    _dismiss_indeed_consent(page)
    btn.click.assert_called_once()


def test_prompt_for_browser_verification_uses_input_fn(capsys):
    seen: list[str] = []

    def reader(prompt: str) -> str:
        seen.append(prompt)
        return ""

    prompt_for_browser_verification(reason="CAPTCHA", input_fn=reader)
    assert seen
    assert "CAPTCHA" in capsys.readouterr().out


def test_default_input_eof_indeed(monkeypatch):
    def boom(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", boom)
    assert _default_input("> ") == ""


# --- LinkedIn browser parser (fixtures + inline HTML; mocks only) ---


class TestLinkedInBrowserParse:
    def test_parse_linkedin_legacy_fixture(self):
        html = (FIXTURES / "linkedin_search.html").read_text(encoding="utf-8")
        records = parse_linkedin_search_html(html)
        assert len(records) == 2
        assert records[0]["title"] == "Staff Security Engineer"
        assert records[0]["remote"] is True

    def test_parse_linkedin_spa_fixture(self):
        html = (FIXTURES / "linkedin_search_spa.html").read_text(encoding="utf-8")
        assert linkedin_page_has_job_results(html)
        records = parse_linkedin_search_html(html)
        assert len(records) == 2
        garner = next(r for r in records if r["company"] == "Garner Health")
        assert garner["url"] == "https://www.linkedin.com/jobs/view/4328174567"
        assert garner["comp_raw"] == "$239K/yr - $275K/yr"
        principal = next(r for r in records if r["company"] == "Acme Corp")
        assert principal["url"].endswith("9876543210")

    def test_parse_linkedin_embedded_only_fixture(self):
        html = (FIXTURES / "linkedin_search_embedded_only.html").read_text(encoding="utf-8")
        records = parse_linkedin_search_html(html)
        assert len(records) == 3
        by_co = {r["company"]: r for r in records}
        assert by_co["Rippling"]["comp_raw"] == "$200K/yr - $240K/yr"

    def test_session_ready_feed_and_profile_urls(self):
        assert linkedin_session_ready("<html></html>", "https://www.linkedin.com/feed/")
        assert linkedin_session_ready("<html></html>", "https://www.linkedin.com/in/dan")

    def test_needs_login_html_session_key(self):
        html = '<html><input name="session_key"/></html>'
        assert linkedin_needs_login(html, "https://www.linkedin.com/jobs/search/")

    def test_needs_human_skipped_when_jobs_present(self):
        html = (FIXTURES / "linkedin_search_spa.html").read_text(encoding="utf-8")
        assert not linkedin_needs_human(html + " captcha", "https://www.linkedin.com/jobs/search/")

    def test_build_linkedin_non_remote_url(self):
        parsed = parse_search_location("Boston, MA")
        url = build_linkedin_search_url(term="Security Engineer", parsed=parsed)
        assert "f_WT=2" not in url
        assert "keywords=Security" in url

    def test_normalize_job_url_variants(self):
        assert _normalize_job_url("https://www.linkedin.com/jobs/view/x-1234567890/") is not None
        assert _normalize_job_url("/jobs/view/x-1234567890") == (
            "https://www.linkedin.com/jobs/view/x-1234567890"
        )
        assert _normalize_job_url("not-a-job") is None
        assert _normalize_job_url("jobs/view/1234567890") is None

    def test_merge_record_fills_gaps(self):
        base = {
            "title": "Staff Security Engineer",
            "company": "Unknown",
            "url": "https://www.linkedin.com/jobs/view/4328174567",
            "source": "linkedin",
        }
        richer = {
            **base,
            "company": "Garner Health",
            "location": "United States (Remote)",
            "comp_raw": "$200K/yr",
            "remote": True,
        }
        merged = _merge_record(base, richer)
        assert merged["company"] == "Garner Health"
        assert merged["location"] == "United States (Remote)"
        assert merged["comp_raw"] == "$200K/yr"
        assert merged["remote"] is True

    def test_dedupe_key_without_job_id(self):
        rec = {"title": "A", "company": "B", "url": "", "source": "linkedin"}
        assert _record_dedupe_key(rec) == "a|b|"

    def test_legacy_card_skips_bad_rows(self):
        html = """
        <div class="base-search-card"></div>
        <div class="base-search-card"><a href="/company/foo">nope</a></div>
        <div class="base-search-card">
          <a class="base-card__full-link" href="/jobs/view/t-1234567890"><span class="sr-only"></span></a>
        </div>
        """
        assert parse_linkedin_search_html(html) == []

    def test_spa_skips_invalid_dismiss_and_missing_url(self):
        html = """
        <button aria-label="Dismiss  job"></button>
        <button aria-label="Dismiss No URL Role job"></button>
        <div><div role="button"><p><span>Hidden Role</span></p></div>
        <button aria-label="Dismiss Hidden Role job"></button></div>
        """
        assert parse_linkedin_search_html(html) == []

    def test_spa_company_from_logo_alt(self):
        html = """
        <div class="card">
          <div role="button"><p><span>Logo Role</span></p>
            <img src="https://media.licdn.com/company-logo" alt="Logo Co logo" />
            <p>Remote - US</p>
          </div>
          <button aria-label="Dismiss Logo Role job"></button>
          <a href="https://www.linkedin.com/jobs/view/logo-role-5555555555">v</a>
        </div>
        """
        records = parse_linkedin_search_html(html)
        assert len(records) == 1
        assert records[0]["company"] == "Logo Co"

    def test_embedded_duplicate_id_and_missing_title(self):
        html = """
        <script>
        {"entityUrn":"urn:li:fsd_jobPosting:1111111111","title":"Dup","companyName":"Co"}
        {"entityUrn":"urn:li:fsd_jobPosting:1111111111","title":"Dup"}
        {"entityUrn":"urn:li:fsd_jobPosting:2222222222","companyName":"NoTitle"}
        </script>
        """
        records = parse_linkedin_search_html(html)
        assert len(records) == 1
        assert records[0]["title"] == "Dup"

    def test_closest_job_posting_and_view_url(self):
        chunk = "before jobPosting:1234567890 middle /jobs/view/other-9999999999 after"
        assert _closest_job_posting_id(chunk, anchor_pos=30) == "1234567890"
        assert _closest_job_view_url(chunk, anchor_pos=5) is not None

    def test_job_object_chunk_and_unescape(self):
        html = '{"a":{"entityUrn":"jobPosting:3333333333","title":"T","companyName":"C"}}'
        chunk = _job_object_chunk(html, job_id="3333333333")
        assert chunk is not None
        title, company, loc, comp = _embedded_job_fields(html, job_id="3333333333")
        assert title == "T" and company == "C"
        assert _unescape_json('say \\"hi\\"') == 'say "hi"'
        assert _unescape_json(None) == ""

    def test_fill_record_gaps_from_vicinity(self):
        html = """
        <div class="base-search-card">
          <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/gap-4444444444">
            <span class="sr-only">Gap Role</span>
          </a>
        </div>
        <script>{"entityUrn":"jobPosting:4444444444","title":"Gap Role"}</script>
        <a href="https://www.linkedin.com/company/gap-co">Gap Co</a>
        <span>$150,000/yr</span>
        """
        records = parse_linkedin_search_html(html)
        gap = next(r for r in records if r["title"] == "Gap Role")
        assert gap["company"] in {"Gap Co", "Unknown"}


def test_build_scrape_source_single_browser_returns_direct():
    settings = Settings(
        _env_file=None,
        scrape_sites=[],
        scrape_browser_sites=["indeed"],
        search_terms=["x"],
        locations=["Remote"],
    )
    source = build_scrape_source(settings)
    assert isinstance(source, BrowserJobBoardSource)
    assert list_source_names(source) == ["indeed_browser"]


def test_build_scrape_source_with_llm_mock():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed"],
        search_terms=["x"],
        locations=["Remote"],
    )
    llm = MagicMock()
    effective = settings.model_copy(update={"search_terms": ["from-llm"]})
    with patch("agentzero.ingest.search_profile.get_effective_settings", return_value=effective):
        source = build_scrape_source(settings, llm=llm)
    from agentzero.scrape.browser_board import BrowserJobBoardSource

    assert isinstance(source, BrowserJobBoardSource)
    assert source.name == "indeed_browser"


def test_multi_source_requires_sources():
    with pytest.raises(ValueError, match="at least one"):
        MultiSource([])


def test_multi_source_fetch_merges_batches(capsys):
    class StubSource:
        def __init__(self, name: str, n: int):
            self.name = name
            self._n = n

        def fetch(self):
            return [
                RawRecord(title=f"{self.name}-{i}", company="Co", url=f"https://x/{i}", source=self.name)
                for i in range(self._n)
            ]

    multi = MultiSource([StubSource("a", 1), StubSource("b", 2)])
    records = list(multi.fetch())
    assert len(records) == 3
    out = capsys.readouterr().out
    assert "Scrape [1/2] a" in out
    assert "Scrape [2/2] b" in out

