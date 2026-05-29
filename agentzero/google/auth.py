"""Google OAuth credential loading (Desktop app flow)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.file",
]


def load_credentials(
    *,
    client_secret_path: Path,
    token_path: Path,
    scopes: list[str] | None = None,
) -> Any:
    """Load or refresh OAuth credentials from disk."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise ImportError(
            "Google integration requires google-auth and google-auth-oauthlib. "
            "Install with: pip install -e '.[google]'"
        ) from exc

    use_scopes = scopes or SCOPES
    creds = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), use_scopes)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), use_scopes)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
