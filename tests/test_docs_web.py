from pathlib import Path


def test_docker_doc_mentions_reject_filter():
    text = Path("docs/DOCKER.md").read_text(encoding="utf-8")
    assert "web" in text.lower()
    assert "reject" in text.lower() or "8080" in text


def test_docker_doc_mentions_sort_or_card():
    text = Path("docs/DOCKER.md").read_text(encoding="utf-8")
    assert "job card" in text.lower() or "sort" in text.lower()


def test_docker_doc_mentions_build_cache():
    text = Path("docs/DOCKER.md").read_text(encoding="utf-8")
    assert "DOCKER_BUILDKIT" in text
    assert "docker-compose.override" in text


def test_security_warns_no_auth():
    text = Path("docs/SECURITY.md").read_text(encoding="utf-8")
    assert "web" in text.lower()
    assert "auth" in text.lower() or "unauthenticated" in text.lower()
