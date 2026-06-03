from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.web.app import create_app
from agentzero.web.operator_config import load_operator_config


@pytest.fixture
def client(tmp_path: Path):
    db_path = tmp_path / "t.db"
    settings = Settings(
        _env_file=None,
        db_path=db_path,
        scrape_browser_sites=["indeed"],
        scrape_sites=["google"],
        scrape_cdp_url="http://127.0.0.1:9222",
        scrape_cdp_sites=["indeed"],
    )
    app = create_app(db_path=db_path, settings=settings)
    with TestClient(app) as c:
        yield c, tmp_path


def test_config_redirects_to_scraper(client):
    c, _ = client
    r = c.get("/config", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/scraper"


def test_config_redirect_rejects_open_redirect_path(client):
    c, _ = client
    r = c.get("/config//evil.example", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/scraper"


def test_config_post_redirect_rejects_open_redirect_path(client):
    c, _ = client
    r = c.post("/config//evil.example", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/scraper"


def test_config_redirect_known_path_to_scraper_route(client):
    c, _ = client
    r = c.get("/config/sources?saved=1&next=https://evil.example", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/scraper/sources?saved=1"


def test_api_config_redirects_to_api_scraper(client):
    c, _ = client
    r = c.get("/api/config", follow_redirects=False)
    assert r.status_code == 307
    assert "/api/scraper" in r.headers["location"]


def test_scraper_page_omits_chrome_cdp_when_no_cdp_sources(tmp_path: Path):
    db_path = tmp_path / "t.db"
    settings = Settings(
        _env_file=None,
        db_path=db_path,
        scrape_browser_sites=["linkedin"],
        scrape_sites=["google"],
    )
    app = create_app(db_path=db_path, settings=settings)
    with TestClient(app) as c:
        r = c.get("/scraper")
    assert r.status_code == 200
    assert "<h2>Chrome CDP</h2>" not in r.text
    assert "Connect" not in r.text


def test_scraper_page_renders(client):
    c, _ = client
    r = c.get("/scraper")
    assert r.status_code == 200
    assert "<h1>Scraper</h1>" in r.text
    assert "Scrape sources" in r.text
    assert "Search titles" in r.text
    assert "Search targets" in r.text
    assert 'action="/scraper/search-targets"' in r.text
    assert "Load résumé" in r.text
    assert "Chrome CDP" in r.text
    assert "Connect" in r.text
    assert "launch_chrome_cdp.ps1" in r.text
    assert "launch_chrome_cdp.py" in r.text
    assert "Start Chrome on the host" in r.text
    assert 'id="scrape-progress"' in r.text
    assert "agentzeroPollScrape" in r.text


def test_jobs_page_defaults_to_dark_theme(client):
    c, _ = client
    r = c.get("/jobs")
    assert r.status_code == 200
    assert "Scraper" in r.text
    assert 'data-theme="dark"' in r.text
    assert 'setAttribute("data-theme", "dark")' in r.text


def test_save_sources_persists(client):
    c, tmp_path = client
    r = c.post(
        "/scraper/sources",
        data={"browser_sites": ["indeed"], "jobspy_sites": ["google"]},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/scraper?" in r.headers["location"]
    cfg_path = tmp_path / "web_operator_config.json"
    assert cfg_path.is_file()
    loaded = load_operator_config(cfg_path)
    assert loaded is not None
    assert loaded.scrape_browser_sites == ["indeed"]
    assert loaded.scrape_sites == []


def test_save_sources_requires_one(client):
    c, _ = client
    r = c.post("/scraper/sources", data={}, follow_redirects=False)
    assert r.status_code == 400


def test_api_scraper_json(client):
    c, _ = client
    r = c.get("/api/scraper")
    assert r.status_code == 200
    body = r.json()
    assert "sources" in body
    assert "cdp" in body
    assert len(body["sources"]) == 3
    scrape = body["scrape"]
    assert "phase" in scrape
    assert "done" in scrape
    assert "total" in scrape
    assert "detail" in scrape


def test_api_scraper_reflects_runner_progress(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(c.app.state.scrape_runner, "_process_alive", lambda: True)
    c.app.state.scrape_runner.state.running = True
    c.app.state.scrape_runner.state.phase = "scrape"
    c.app.state.scrape_runner.state.done = 1
    c.app.state.scrape_runner.state.total = 3
    c.app.state.scrape_runner.state.detail = "linkedin"
    r = c.get("/api/scraper")
    scrape = r.json()["scrape"]
    assert scrape["running"] is True
    assert scrape["phase"] == "scrape"
    assert scrape["done"] == 1
    assert scrape["total"] == 3


def test_cdp_connect_redirect(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(
        "agentzero.web.app.retry_cdp_connection",
        lambda _s, _o: (True, "Connected to Chrome at http://127.0.0.1:9222."),
    )
    r = c.post("/scraper/cdp/connect", follow_redirects=False)
    assert r.status_code == 303
    assert "cdp_ok=1" in r.headers["location"]
    assert "/scraper?" in r.headers["location"]


def test_resume_load_redirect(client, monkeypatch):
    c, _ = client

    def fake_start(_path, *, force_refresh=True):
        return True, "started"

    monkeypatch.setattr(c.app.state.resume_loader, "start", fake_start)
    r = c.post("/scraper/resume/load", follow_redirects=False)
    assert r.status_code == 303
    assert "resume_loading=1" in r.headers["location"]


def test_save_search_titles_requires_profile(client):
    c, _ = client
    r = c.post("/scraper/search-titles", data={"search_terms": ["Dev"]}, follow_redirects=False)
    assert r.status_code == 400


def test_scraper_page_add_title_form(client, tmp_path: Path):
    c, root = client
    from agentzero.ingest.search_profile import ResumeSearchProfile, save_search_profile

    save_search_profile(
        ResumeSearchProfile(
            search_terms=["Engineer"],
            locations=["Remote"],
            source_resume_path="resume/x.txt",
            source_fingerprint="fp",
            updated_at="2026-01-01T00:00:00Z",
        ),
        settings=Settings(_env_file=None, db_path=root / "t.db"),
    )
    r = c.get("/scraper")
    assert "Add title" in r.text
    assert 'action="/scraper/search-titles/add"' in r.text


def test_add_search_title_redirect(client, tmp_path: Path):
    c, root = client
    from agentzero.ingest.search_profile import ResumeSearchProfile, save_search_profile

    save_search_profile(
        ResumeSearchProfile(
            search_terms=["Engineer"],
            locations=["Remote"],
            source_resume_path="resume/x.txt",
            source_fingerprint="fp",
            updated_at="2026-01-01T00:00:00Z",
        ),
        settings=Settings(_env_file=None, db_path=root / "t.db"),
    )
    r = c.post(
        "/scraper/search-titles/add",
        data={"term": "Staff Engineer"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "title_added=1" in r.headers["location"]
    saved = load_operator_config(root / "web_operator_config.json")
    assert saved is not None
    assert "Staff Engineer" in saved.search_terms


def test_remove_search_title_updates_list(client, tmp_path: Path):
    c, root = client
    from agentzero.ingest.search_profile import ResumeSearchProfile, save_search_profile
    from agentzero.web.operator_config import patch_operator_config

    cfg = root / "web_operator_config.json"
    settings = Settings(_env_file=None, db_path=root / "t.db")
    save_search_profile(
        ResumeSearchProfile(
            search_terms=["Engineer", "Architect"],
            locations=["Remote"],
            source_resume_path="resume/x.txt",
            source_fingerprint="fp",
            updated_at="2026-01-01T00:00:00Z",
        ),
        settings=settings,
    )
    patch_operator_config(cfg, search_terms=["Engineer", "Architect"])
    r = c.post(
        "/scraper/search-titles/remove",
        data={"term": "Engineer"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    saved = load_operator_config(cfg)
    assert saved is not None
    assert saved.search_terms == ["Architect"]
    page = c.get("/scraper")
    assert 'value="Engineer"' not in page.text
    assert 'value="Architect"' in page.text


def _save_minimal_profile(root: Path) -> None:
    from agentzero.ingest.search_profile import ResumeSearchProfile, save_search_profile

    save_search_profile(
        ResumeSearchProfile(
            search_terms=["Engineer"],
            locations=["remote - usa"],
            remote_preferred=True,
            salary_min=150_000.0,
            source_resume_path="resume/x.txt",
            source_fingerprint="fp",
            updated_at="2026-01-01T00:00:00Z",
        ),
        settings=Settings(_env_file=None, db_path=root / "t.db"),
    )


def test_save_search_targets_round_trip(client, tmp_path: Path):
    c, root = client
    _save_minimal_profile(root)
    r = c.post(
        "/scraper/search-targets",
        data={
            "work_mode": "remote",
            "locations": "",
            "salary_min": "180000",
            "scrape_remote_only": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "search_targets_saved=1" in r.headers["location"]
    cfg_path = root / "web_operator_config.json"
    loaded = load_operator_config(cfg_path)
    assert loaded is not None
    assert loaded.search_targets_configured is True
    assert loaded.work_mode == "remote"
    assert loaded.salary_min == 180_000.0
    assert loaded.scrape_remote_only is True
    page = c.get("/scraper")
    assert 'value="180000"' in page.text
    assert "Remote (USA)" in page.text


def test_save_search_targets_in_office(client, tmp_path: Path):
    c, root = client
    _save_minimal_profile(root)
    r = c.post(
        "/scraper/search-targets",
        data={
            "work_mode": "in_office",
            "locations": "Los Angeles, CA",
            "salary_min": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    loaded = load_operator_config(root / "web_operator_config.json")
    assert loaded is not None
    assert loaded.work_mode == "in_office"
    assert "Los Angeles" in loaded.locations[0]


def test_save_search_targets_rejects_empty_in_office(client, tmp_path: Path):
    c, root = client
    _save_minimal_profile(root)
    cfg_path = root / "web_operator_config.json"
    r = c.post(
        "/scraper/search-targets",
        data={"work_mode": "in_office", "locations": "", "salary_min": ""},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "at least one location" in r.text.lower()
    if cfg_path.is_file():
        loaded = load_operator_config(cfg_path)
        assert loaded is None or not loaded.search_targets_configured


def test_save_search_targets_rejects_script_in_location(client, tmp_path: Path):
    c, root = client
    _save_minimal_profile(root)
    cfg_path = root / "web_operator_config.json"
    r = c.post(
        "/scraper/search-targets",
        data={
            "work_mode": "in_office",
            "locations": "<script>alert(1)</script>",
            "salary_min": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "<script>alert(1)</script>" not in r.text or "invalid characters" in r.text.lower()
    if cfg_path.is_file():
        loaded = load_operator_config(cfg_path)
        assert loaded is None or not loaded.search_targets_configured


def test_config_redirect_search_targets_to_scraper(client):
    c, _ = client
    r = c.get("/config/search-targets?search_targets_saved=1", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/scraper/search-targets?search_targets_saved=1"


def test_scrape_endpoint_returns_redirect(client, monkeypatch):
    c, _ = client

    def fake_start(**_kwargs):
        return True, "started"

    monkeypatch.setattr(c.app.state.scrape_runner, "start", fake_start)
    r = c.post("/scraper/scrape", follow_redirects=False)
    assert r.status_code == 303
    assert "scrape_started=1" in r.headers["location"]
