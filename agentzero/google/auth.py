"""Google OAuth credential loading (Desktop app flow)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Minimal scope for current production scripts (Sheets sync only).
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Optional future integrations (Gmail, Calendar, Drive). Not used by default.
FULL_SCOPES = [
    *SHEETS_SCOPES,
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]

# Default for new OAuth flows — least privilege.
SCOPES = SHEETS_SCOPES


def persist_credentials(creds: Any, token_path: Path) -> None:
    """Write OAuth tokens to disk without persisting ``client_secret``."""
    data = json.loads(creds.to_json())
    data.pop("client_secret", None)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _restrict_token_file_permissions(token_path)


def _restrict_token_file_permissions(token_path: Path) -> None:
    """Limit token file access to the current user (best-effort)."""
    import os

    if os.name != "nt":
        token_path.chmod(0o600)
        return
    username = os.environ.get("USERNAME") or os.environ.get("USER")
    if not username:
        return
    import subprocess

    subprocess.run(  # noqa: S603
        [
            "icacls",
            str(token_path),
            "/inheritance:r",
            "/grant:r",
            f"{username}:F",
        ],
        check=False,
        capture_output=True,
    )


def _client_config_from_secret(client_secret_path: Path) -> dict[str, str]:
    """Read ``client_id`` / ``client_secret`` from a Google Desktop OAuth JSON file."""
    data = json.loads(client_secret_path.read_text(encoding="utf-8"))
    block = data.get("installed") or data.get("web") or {}
    client_id = block.get("client_id", "")
    client_secret = block.get("client_secret", "")
    if not client_id or not client_secret:
        raise ValueError(f"Invalid OAuth client secret file: {client_secret_path}")
    return {"client_id": client_id, "client_secret": client_secret}


def _credentials_from_token_file(
    token_path: Path,
    *,
    client_secret_path: Path,
    scopes: list[str],
) -> Any:
    """Load credentials from ``token.json``, merging client info from the secret file."""
    from google.oauth2.credentials import Credentials

    token_data = json.loads(token_path.read_text(encoding="utf-8"))
    if not token_data.get("client_secret"):
        token_data.update(_client_config_from_secret(client_secret_path))
    return Credentials.from_authorized_user_info(token_data, scopes)


def load_credentials(
    *,
    client_secret_path: Path,
    token_path: Path,
    scopes: list[str] | None = None,
) -> Any:
    """Load or refresh OAuth credentials from disk."""
    try:
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise ImportError(
            "Google integration requires google-auth and google-auth-oauthlib. "
            "Install with: pip install -e '.[google]'"
        ) from exc

    creds = None
    if token_path.is_file():
        creds = _credentials_from_token_file(
            token_path,
            client_secret_path=client_secret_path,
            scopes=scopes or SCOPES,
        )
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        persist_credentials(creds, token_path)
        return creds
    use_scopes = scopes or SCOPES
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), use_scopes)
    creds = flow.run_local_server(port=0)
    persist_credentials(creds, token_path)
    return creds
