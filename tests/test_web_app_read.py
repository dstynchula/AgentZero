from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentzero.config import Settings
from agentzero.web.app import create_app
from agentzero.web.jobs import LIST_VIEW_DEFAULT_COLUMNS, UI_COLUMNS


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


def test_jobs_table_has_column_picker(jobs_client):
    r = jobs_client.get("/")
    assert r.status_code == 200
    assert 'id="column-picker"' in r.text
    assert 'data-column="title"' in r.text
    assert "column-picker-reset" in r.text
    assert 'id="tracker-column-config"' in r.text
    assert "initTrackerColumns" in r.text
    assert r.text.find('id="jobs-table"') < r.text.find("initTrackerColumns")
    assert "col-resizer" in r.text


def test_jobs_page_sort_chips_for_all_columns(jobs_client):
    r = jobs_client.get("/")
    assert r.status_code == 200
    assert 'class="sort-toolbar"' in r.text
    for col in UI_COLUMNS:
        assert f'href="?sort={col}' in r.text or f"sort={col}&" in r.text
        assert 'class="sort-chip' in r.text


def test_jobs_page_header_sort_links(jobs_client):
    r = jobs_client.get("/")
    assert r.status_code == 200
    assert 'class="th-sort-link"' in r.text
    assert "sort-indicator" in r.text


def test_jobs_list_default_columns(jobs_client):
    r = jobs_client.get("/")
    assert r.status_code == 200
    assert tuple(LIST_VIEW_DEFAULT_COLUMNS) == (
        "source",
        "company",
        "title",
        "comp_max",
        "match_score",
        "status",
    )
    for col in LIST_VIEW_DEFAULT_COLUMNS:
        assert f'data-column="{col}"' in r.text
    assert 'data-col="location"' in r.text
    assert 'data-col="location" col-hidden' in r.text or 'col-hidden' in r.text
    assert '"comp_max"' in r.text


def test_jobs_table_readable_title_styles(jobs_client):
    r = jobs_client.get("/")
    assert r.status_code == 200
    assert 'data-col="title"' in r.text
    assert "cell-text" in r.text
