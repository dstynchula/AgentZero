#!/usr/bin/env python3
"""Run Google OAuth (Desktop app) and save ``token.json`` for AgentZero.

Usage (from repo root, venv active):

    pip install -e ".[google]"
    python scripts/google_auth.py

A browser window opens — sign in with the Google account that owns (or can edit)
your AgentZero spreadsheet. When finished, ``token.json`` is written next to
``.env`` and this script verifies it can open ``AGENTZERO_SHEET_ID``.

Options:

    python scripts/google_auth.py --full-scopes   # Gmail, Calendar, Drive (future)
    python scripts/google_auth.py --verify-only   # skip OAuth if token.json already valid

Default requests **Sheets scope only** (least privilege). See docs/SECURITY.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentzero.config import get_settings  # noqa: E402
from agentzero.google.auth import FULL_SCOPES, SHEETS_SCOPES, load_credentials  # noqa: E402
from agentzero.google.client import open_spreadsheet  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentZero Google OAuth setup")
    parser.add_argument(
        "--full-scopes",
        action="store_true",
        help="Request Gmail, Calendar, and Drive scopes (not needed for Sheets sync)",
    )
    parser.add_argument(
        "--sheets-only",
        action="store_true",
        help=argparse.SUPPRESS,  # backward compat alias for default behavior
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Use existing token.json; do not open browser unless refresh fails",
    )
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    client_secret = settings.google_client_secret
    token_path = settings.google_token_path

    if not client_secret.is_file():
        print(
            "ERROR: OAuth client secret file not found. Set AGENTZERO_GOOGLE_CLIENT_SECRET "
            "or save the Desktop OAuth client JSON as client_secret.json "
            "(see docs/SECURITY.md / README).",
            file=sys.stderr,
        )
        return 1

    scopes = FULL_SCOPES if args.full_scopes else SHEETS_SCOPES
    print("AgentZero Google OAuth")
    print("  client secret: found")
    print(f"  token path:    {token_path}")
    print(f"  scopes:        {scopes}")
    if settings.sheet_id:
        sid = settings.sheet_id
        masked = f"{sid[:8]}…" if len(sid) > 8 else sid
        print(f"  sheet id:      {masked} (configured)")
    else:
        print("  sheet id:      (not set — OAuth will still run)")
    print()

    if args.verify_only and not token_path.is_file():
        print(
            "ERROR: --verify-only but token.json does not exist. "
            "Run without that flag.",
            file=sys.stderr,
        )
        return 1

    if not args.verify_only:
        print("Opening browser for Google sign-in...")
        print("If no browser opens, copy the URL printed below into your browser.")
        print()

    try:
        creds = load_credentials(
            client_secret_path=client_secret,
            token_path=token_path,
            scopes=scopes,
        )
    except Exception as exc:
        print(f"ERROR: OAuth failed: {exc}", file=sys.stderr)
        return 1

    print(f"OK — credentials saved to {token_path.resolve()}")

    if not settings.sheet_id:
        print("Set AGENTZERO_SHEET_ID in .env, then re-run with --verify-only to test Sheets.")
        return 0

    try:
        spreadsheet = open_spreadsheet(creds, settings.sheet_id)
        title = spreadsheet.title
        worksheet = spreadsheet.sheet1.title
        print(f"OK — opened spreadsheet: {title!r} (worksheet: {worksheet!r})")
    except Exception as exc:
        print(
            f"ERROR: OAuth succeeded but could not open the sheet: {exc}\n"
            "Check AGENTZERO_SHEET_ID and that your Google account has edit access.",
            file=sys.stderr,
        )
        return 1

    print("\nGoogle OAuth is wired up. Sheets sync can use token.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
