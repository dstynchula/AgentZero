from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.web.app import create_app


@pytest.fixture
def brand_client(tmp_path: Path):
    db_path = tmp_path / "t.db"
    settings = Settings(_env_file=None, db_path=db_path)
    app = create_app(db_path=db_path, settings=settings)
    with TestClient(app) as client:
        yield client


def test_packaged_brand_matches_repo_root():
    root = Path("AgentZero.svg")
    packaged = Path("agentzero/web/static/AgentZero.svg")
    assert root.is_file()
    assert packaged.is_file()
    assert root.read_bytes() == packaged.read_bytes()


def test_brand_logo_route_returns_svg(brand_client: TestClient):
    response = brand_client.get("/static/brand/agentzero.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in response.content
    assert b"AgentZero" in response.content


def test_chat_page_header_includes_brand_logo(brand_client: TestClient):
    response = brand_client.get("/")
    assert response.status_code == 200
    assert 'src="/static/brand/agentzero.svg"' in response.text
    assert 'class="brand-logo"' in response.text
    assert 'alt="AgentZero"' in response.text


def test_jobs_page_header_includes_brand_logo(brand_client: TestClient):
    response = brand_client.get("/jobs")
    assert response.status_code == 200
    assert 'src="/static/brand/agentzero.svg"' in response.text
