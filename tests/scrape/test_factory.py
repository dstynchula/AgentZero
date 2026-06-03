import importlib.util
from unittest.mock import MagicMock, patch

from agentzero.config import Settings
from agentzero.scrape.factory import CORE_BROWSER_SITES, build_scrape_source, list_source_names
from agentzero.scrape.linkedin_source import LinkedInJobSource


def test_jobspy_source_module_removed():
    assert importlib.util.find_spec("agentzero.scrape.jobspy_source") is None


def test_build_scrape_source_only_browser_boards():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed", "linkedin", "glassdoor"],
        scrape_sites=["google", "zip_recruiter"],
    )
    source = build_scrape_source(settings)
    names = list_source_names(source)
    assert "jobspy" not in names
    assert all(any(site in n for site in CORE_BROWSER_SITES) for n in names)
    assert len(names) == 3


def test_build_scrape_source_ignores_legacy_jobspy_env():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["indeed"],
        scrape_sites=["google"],
    )
    names = list_source_names(build_scrape_source(settings))
    assert names == ["indeed_browser"]


def test_linkedin_browser_source_delegates_to_service():
    settings = Settings(
        _env_file=None,
        scrape_browser_sites=["linkedin"],
    )
    source = build_scrape_source(settings)
    assert isinstance(source, LinkedInJobSource)
    mock_result = MagicMock()
    mock_result.login_required = False
    mock_result.error = None
    mock_result.records = [
        {
            "title": "Staff Security Engineer",
            "company": "Acme",
            "url": "https://www.linkedin.com/jobs/view/1234567890",
            "source": "linkedin",
        }
    ]
    mock_result.parsed_raw = 1
    mock_result.after_title_filter = 1
    with patch.object(source._service, "search", return_value=mock_result):
        rows = source.fetch()
    assert len(rows) == 1


def test_linkedin_job_source_raises_when_empty():
    from agentzero.scrape.linkedin_source import LinkedInFetchError, LinkedInJobSource

    settings = Settings(_env_file=None, scrape_browser_sites=["linkedin"])
    source = LinkedInJobSource(settings)
    mock_result = MagicMock()
    mock_result.records = []
    mock_result.login_required = True
    mock_result.error = None
    mock_result.parsed_raw = 0
    mock_result.after_title_filter = 0
    with patch.object(source._service, "search", return_value=mock_result):
        try:
            source.fetch()
            raised = False
        except LinkedInFetchError:
            raised = True
    assert raised
