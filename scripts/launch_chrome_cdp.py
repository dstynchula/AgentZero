#!/usr/bin/env python3
"""Start Google Chrome with remote debugging (CDP) on a dedicated profile.

Usage (from repo root, venv active):

    python scripts/launch_chrome_cdp.py
    python scripts/launch_chrome_cdp.py --port 9223
    python scripts/launch_chrome_cdp.py --user-data-dir data/browser_profiles/cdp

macOS/Linux shell wrapper: ./scripts/launch_chrome_cdp.sh

Windows PowerShell: .\\scripts\\launch_chrome_cdp.ps1

Then in .env:
    AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:9222
    AGENTZERO_SCRAPE_CDP_SITES=indeed,glassdoor
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agentzero.scrape.cdp_launch import main  # noqa: E402, I001


if __name__ == "__main__":
    raise SystemExit(main())
