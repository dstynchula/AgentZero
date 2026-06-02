from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.web.app import create_app


@pytest.fixture
def jobs_client(tmp_path: Path):
    db_path = tmp_path / "t.db"
    settings = Settings(_env_file=None, db_path=db_path)
    app = create_app(db_path=db_path, settings=settings)
    with TestClient(app) as c:
        yield c


def test_jobs_page_has_centered_table_wrapper(jobs_client):
    r = jobs_client.get("/")
    assert r.status_code == 200
    assert 'class="tracker-table-wrap"' in r.text


def test_jobs_table_compact_styles_present(jobs_client):
    r = jobs_client.get("/")
    assert r.status_code == 200
    assert ".tracker-table-wrap" in r.text
    assert "width: max-content" in r.text
    assert "0.28rem 0.45rem" in r.text
