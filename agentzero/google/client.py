"""Build Google API clients from OAuth credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials


def authorize_gspread(creds: Credentials) -> Any:
    """Return an authorized gspread client."""
    try:
        import gspread
    except ImportError as exc:
        raise ImportError(
            "Sheets sync requires gspread. Install with: pip install -e '.[google]'"
        ) from exc
    return gspread.authorize(creds)


def build_sheets_service(creds: Credentials) -> Any:
    """Return a Google Sheets API v4 service (for lower-level access if needed)."""
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ImportError(
            "Google API client requires google-api-python-client. "
            "Install with: pip install -e '.[google]'"
        ) from exc
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def open_spreadsheet(creds: Credentials, sheet_id: str) -> Any:
    """Open a spreadsheet by ID and return the gspread Spreadsheet object."""
    client = authorize_gspread(creds)
    return client.open_by_key(sheet_id)
