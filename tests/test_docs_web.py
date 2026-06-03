from pathlib import Path


def test_getting_started_mentions_cover_letter():
    text = Path("docs/GETTING_STARTED.md").read_text(encoding="utf-8")
    assert "cover letter" in text.lower()
    assert "download" in text.lower() or ".txt" in text


def test_readme_mentions_cover_letter_model():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "AGENTZERO_COVER_LETTER_MODEL" in text
    assert "gpt-5.5" in text


def test_cost_doc_mentions_cover_letter_model():
    text = Path("docs/COST_AND_MODELS.md").read_text(encoding="utf-8")
    assert "AGENTZERO_COVER_LETTER_MODEL" in text


def test_docker_doc_mentions_reject_filter():
    text = Path("docs/DOCKER.md").read_text(encoding="utf-8")
    assert "web" in text.lower()
    assert "reject" in text.lower() or "8080" in text


def test_docker_doc_mentions_sort_or_card():
    text = Path("docs/DOCKER.md").read_text(encoding="utf-8")
    assert "job card" in text.lower() or "sort" in text.lower()


def test_getting_started_mentions_cdp_launch_scripts():
    text = Path("docs/GETTING_STARTED.md").read_text(encoding="utf-8")
    assert "launch_chrome_cdp.ps1" in text
    assert "launch_chrome_cdp.py" in text
    assert "launch_chrome_cdp.sh" in text


def test_docker_doc_mentions_scraper_page():
    text = Path("docs/DOCKER.md").read_text(encoding="utf-8")
    assert "/scraper" in text
    assert "scraper" in text.lower()


def test_docker_doc_mentions_data_search_profile():
    text = Path("docs/DOCKER.md").read_text(encoding="utf-8")
    assert "data/search_profile.json" in text


def test_docker_doc_mentions_build_cache():
    text = Path("docs/DOCKER.md").read_text(encoding="utf-8")
    assert "DOCKER_BUILDKIT" in text
    assert "docker-compose.override" in text


def test_security_warns_no_auth():
    text = Path("docs/SECURITY.md").read_text(encoding="utf-8")
    assert "web" in text.lower()
    assert "auth" in text.lower() or "unauthenticated" in text.lower()
