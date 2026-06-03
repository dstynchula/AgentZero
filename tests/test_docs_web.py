from pathlib import Path


def test_getting_started_mentions_cover_letter():
    text = Path("docs/GETTING_STARTED.md").read_text(encoding="utf-8")
    assert "cover letter" in text.lower()
    assert "download" in text.lower() or ".txt" in text


def test_readme_mentions_cover_letter_model():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "AGENTZERO_COVER_LETTER_MODEL" in text
    assert "gpt-5.5" in text


def test_readme_mentions_three_boards_only():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "Indeed" in text and "LinkedIn" in text and "Glassdoor" in text
    assert "ZipRecruiter" not in text
    assert "Google Jobs" not in text


def test_readme_includes_agentzero_svg():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "AgentZero.svg" in text
    assert Path("AgentZero.svg").is_file()


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


def test_readme_mentions_chat_default_route():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "AGENTZERO_CHAT_MODEL" in text
    assert "/jobs" in text


def test_getting_started_mentions_chat_hitl():
    text = Path("docs/GETTING_STARTED.md").read_text(encoding="utf-8")
    assert "AGENTZERO_CHAT_MODEL" in text
    assert "Confirm" in text


def test_docker_doc_mentions_chat_landing():
    text = Path("docs/DOCKER.md").read_text(encoding="utf-8")
    assert "Chat" in text
    assert "/jobs" in text


def test_cost_doc_mentions_chat_model():
    text = Path("docs/COST_AND_MODELS.md").read_text(encoding="utf-8")
    assert "AGENTZERO_CHAT_MODEL" in text


def test_readme_no_jobspy_scrape_stack():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "JobSpy" not in text


def test_readme_mentions_p40_three_boards():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "three boards" in text.lower() or "Indeed, LinkedIn, and Glassdoor" in text


def test_progress_lists_p41_epic():
    text = Path("PROGRESS.md").read_text(encoding="utf-8")
    assert "P41 — Chat delete UI" in text
    assert "P42 — Data tab backup" in text


def test_readme_architecture_mermaid_valid():
    text = Path("README.md").read_text(encoding="utf-8")
    assert "```mermaid" in text
    assert "flowchart TB" in text
    assert text.count('subgraph SC["① Scrape') <= 1

