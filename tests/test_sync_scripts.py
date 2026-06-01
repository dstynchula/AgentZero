"""Tests for sync_sheets and run_scrape CLI helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentzero.config import Settings
from agentzero.google.sync import sync_jobs_to_sheet
from agentzero.models import JobPosting
from agentzero.storage.db import Database


class FakeWorksheet:
    def __init__(self) -> None:
        self.values: list = []

    def get_all_values(self) -> list:
        return self.values

    def clear(self) -> None:
        self.values = []

    def update(self, _range: str, values: list) -> None:
        self.values = values


class FakeSpreadsheet:
    def __init__(self) -> None:
        self.title = "AgentZero - 2026 Job Search"
        self.sheet1 = FakeWorksheet()


class FakeGspreadClient:
    def __init__(self) -> None:
        self.spreadsheet = FakeSpreadsheet()

    def open_by_key(self, key: str) -> FakeSpreadsheet:
        return self.spreadsheet


def _patch_google(monkeypatch):
    monkeypatch.setattr(
        "agentzero.google.sync.load_credentials",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "agentzero.google.sync.authorize_gspread",
        lambda creds: FakeGspreadClient(),
    )
    monkeypatch.setattr(
        "agentzero.google.client.open_spreadsheet",
        lambda creds, sheet_id: FakeSpreadsheet(),
    )


def test_sync_jobs_to_sheet_writes_rows(tmp_path, monkeypatch):
    db = Database(tmp_path / "jobs.db")
    db.upsert_job(
        JobPosting(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    )
    settings = Settings(
        _env_file=None,
        sheet_id="abc123",
        google_client_secret=tmp_path / "secret.json",
        google_token_path=tmp_path / "token.json",
    )
    settings.google_client_secret.write_text("{}", encoding="utf-8")
    settings.google_token_path.write_text("{}", encoding="utf-8")

    _patch_google(monkeypatch)

    result = sync_jobs_to_sheet(db=db, settings=settings)
    assert result.row_count == 1
    assert result.spreadsheet_title == "AgentZero - 2026 Job Search"


def test_sync_jobs_to_sheet_without_import(tmp_path, monkeypatch):
    db = Database(tmp_path / "jobs.db")
    db.upsert_job(
        JobPosting(title="Eng", company="Acme", url="https://x.com/2", source="indeed")
    )
    settings = Settings(
        _env_file=None,
        sheet_id="abc123",
        google_client_secret=tmp_path / "secret.json",
        google_token_path=tmp_path / "token.json",
    )
    settings.google_client_secret.write_text("{}", encoding="utf-8")
    settings.google_token_path.write_text("{}", encoding="utf-8")
    _patch_google(monkeypatch)

    result = sync_jobs_to_sheet(db=db, settings=settings, import_user_fields=False)
    assert result.row_count == 1
    assert result.imported == 0
    db.close()


def test_sync_jobs_to_sheet_requires_sheet_id(tmp_path):
    db = Database(tmp_path / "jobs.db")
    settings = Settings(_env_file=None, sheet_id=None)
    with pytest.raises(ValueError, match="SHEET_ID"):
        sync_jobs_to_sheet(db=db, settings=settings)


def test_run_scrape_skip_ingest_without_snapshot(tmp_path, monkeypatch):
    import scripts.run_scrape as run_scrape_mod

    monkeypatch.chdir(tmp_path)
    (tmp_path / "resume").mkdir()
    code = run_scrape_mod.run(
        limit=5,
        skip_resume_ingest=True,
        search_prompt=False,
        refresh_search=False,
    )
    assert code == 1



def _install_fake_google_imports(monkeypatch):
    import sys
    import types

    requests_mod = types.ModuleType('google.auth.transport.requests')
    requests_mod.Request = MagicMock()

    transport_mod = types.ModuleType('google.auth.transport')
    transport_mod.requests = requests_mod

    auth_mod = types.ModuleType('google.auth')
    auth_mod.transport = transport_mod

    google_mod = types.ModuleType('google')
    google_mod.auth = auth_mod

    flow_mod = types.ModuleType('google_auth_oauthlib.flow')
    flow_mod.InstalledAppFlow = MagicMock()

    oauth_mod = types.ModuleType('google_auth_oauthlib')
    oauth_mod.flow = flow_mod

    monkeypatch.setitem(sys.modules, 'google', google_mod)
    monkeypatch.setitem(sys.modules, 'google.auth', auth_mod)
    monkeypatch.setitem(sys.modules, 'google.auth.transport', transport_mod)
    monkeypatch.setitem(sys.modules, 'google.auth.transport.requests', requests_mod)
    monkeypatch.setitem(sys.modules, 'google_auth_oauthlib', oauth_mod)
    monkeypatch.setitem(sys.modules, 'google_auth_oauthlib.flow', flow_mod)

def test_client_config_from_secret_installed(tmp_path):
    from agentzero.google.auth import _client_config_from_secret

    path = tmp_path / "secret.json"
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "cid",
                    "client_secret": "csec",
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = _client_config_from_secret(path)
    assert cfg["client_id"] == "cid"


def test_client_config_from_secret_invalid(tmp_path):
    from agentzero.google.auth import _client_config_from_secret

    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"installed": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid OAuth"):
        _client_config_from_secret(path)


def test_load_credentials_valid_token(tmp_path, monkeypatch):
    _install_fake_google_imports(monkeypatch)
    from agentzero.google.auth import load_credentials

    secret = tmp_path / "secret.json"
    token = tmp_path / "token.json"
    secret.write_text(
        json.dumps({"installed": {"client_id": "id", "client_secret": "sec"}}),
        encoding="utf-8",
    )
    token.write_text("{}", encoding="utf-8")

    class FakeCreds:
        valid = True
        expired = False
        refresh_token = None

    monkeypatch.setattr(
        "agentzero.google.auth._credentials_from_token_file",
        lambda token_path, **kwargs: FakeCreds(),
    )

    creds = load_credentials(
        client_secret_path=secret,
        token_path=token,
    )
    assert creds.valid


def test_load_credentials_refreshes_expired(tmp_path, monkeypatch):
    _install_fake_google_imports(monkeypatch)
    from agentzero.google.auth import load_credentials

    secret = tmp_path / "secret.json"
    token = tmp_path / "token.json"
    secret.write_text(
        json.dumps({"installed": {"client_id": "id", "client_secret": "sec"}}),
        encoding="utf-8",
    )
    token.write_text("{}", encoding="utf-8")

    class FakeCreds:
        valid = False
        expired = True
        refresh_token = "refresh"

        def refresh(self, request):
            self.valid = True

    fake = FakeCreds()
    monkeypatch.setattr(
        "agentzero.google.auth._credentials_from_token_file",
        lambda token_path, **kwargs: fake,
    )
    monkeypatch.setattr(
        "agentzero.google.auth.persist_credentials",
        lambda creds, path: None,
    )

    creds = load_credentials(client_secret_path=secret, token_path=token)
    assert creds.valid


def test_load_credentials_runs_local_server_when_no_token(tmp_path, monkeypatch):
    _install_fake_google_imports(monkeypatch)
    from agentzero.google.auth import load_credentials

    secret = tmp_path / "secret.json"
    token = tmp_path / "token.json"
    secret.write_text(
        json.dumps({"installed": {"client_id": "id", "client_secret": "sec"}}),
        encoding="utf-8",
    )

    class FakeCreds:
        valid = True
        expired = False
        refresh_token = None

    flow = MagicMock()
    flow.run_local_server.return_value = FakeCreds()
    import google_auth_oauthlib.flow as flow_pkg
    flow_pkg.InstalledAppFlow.from_client_secrets_file = lambda path, scopes: flow
    monkeypatch.setattr(
        "agentzero.google.auth.persist_credentials",
        lambda creds, path: None,
    )

    creds = load_credentials(client_secret_path=secret, token_path=token)
    assert creds.valid
    flow.run_local_server.assert_called_once()


def test_load_credentials_import_error(monkeypatch):
    import sys

    saved = {k: sys.modules[k] for k in list(sys.modules) if k == "google" or k.startswith("google.") or k.startswith("google_")}
    for k in list(sys.modules):
        if k == "google" or k.startswith("google.") or k.startswith("google_"):
            monkeypatch.delitem(sys.modules, k, raising=False)

    from agentzero.google.auth import load_credentials

    with pytest.raises(ImportError, match="google-auth"):
        load_credentials(client_secret_path=Path("x"), token_path=Path("y"))

def test_authorize_gspread_and_open_spreadsheet(monkeypatch):
    from agentzero.google.client import authorize_gspread, build_sheets_service, open_spreadsheet

    fake_client = MagicMock()
    fake_client.open_by_key.return_value = FakeSpreadsheet()
    gspread_mod = MagicMock()
    gspread_mod.authorize.return_value = fake_client
    monkeypatch.setitem(__import__("sys").modules, "gspread", gspread_mod)

    creds = object()
    client = authorize_gspread(creds)
    assert client.open_by_key("key") is fake_client.open_by_key.return_value

    discovery = MagicMock()
    discovery.build.return_value = "service"
    monkeypatch.setitem(__import__("sys").modules, "googleapiclient.discovery", discovery)
    assert build_sheets_service(creds) == "service"

    assert open_spreadsheet(creds, "sheet-id").title == "AgentZero - 2026 Job Search"


def test_authorize_gspread_import_error(monkeypatch):
    from agentzero.google.client import authorize_gspread

    monkeypatch.delitem(__import__("sys").modules, "gspread", raising=False)

    def fail_import(name, *a, **k):
        if name == "gspread":
            raise ImportError("no gspread")
        return orig(name, *a, **k)

    import builtins

    orig = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", fail_import)

    with pytest.raises(ImportError, match="gspread"):
        authorize_gspread(object())


def test_restrict_token_icacls_on_windows(tmp_path):
    from agentzero.google.auth import _restrict_token_file_permissions

    path = tmp_path / "token.json"
    path.write_text("{}", encoding="utf-8")
    with patch("os.name", "nt"), patch.dict("os.environ", {"USERNAME": "tester"}, clear=False), patch(
        "subprocess.run"
    ) as run:
        _restrict_token_file_permissions(path)
        run.assert_called_once()
