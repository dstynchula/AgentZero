"""Tests for Google OAuth scope defaults and token persistence."""

import json
from pathlib import Path

from agentzero.google.auth import FULL_SCOPES, SCOPES, SHEETS_SCOPES, persist_credentials


def test_default_scopes_are_sheets_only():
    assert SCOPES == SHEETS_SCOPES
    assert len(SHEETS_SCOPES) == 1
    assert "spreadsheets" in SHEETS_SCOPES[0]


def test_full_scopes_include_optional_integrations():
    assert len(FULL_SCOPES) > len(SHEETS_SCOPES)
    assert any("gmail" in scope for scope in FULL_SCOPES)


class _FakeCreds:
    def to_json(self) -> str:
        return json.dumps(
            {
                "token": "access",
                "refresh_token": "refresh",
                "client_secret": "should-not-persist",
            }
        )


def test_persist_credentials_strips_client_secret(tmp_path: Path):
    path = tmp_path / "token.json"
    persist_credentials(_FakeCreds(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["refresh_token"] == "refresh"
    assert "client_secret" not in data


def test_restrict_token_file_permissions_chmod_on_unix():
    from unittest.mock import MagicMock, patch

    from agentzero.google.auth import _restrict_token_file_permissions

    path = MagicMock()
    with patch("os.name", "posix"):
        _restrict_token_file_permissions(path)
    path.chmod.assert_called_once_with(0o600)

