#!/usr/bin/env python3
"""Compare bundled Playwright profile vs CDP-attached Chrome for one job board.

Usage (from repo root):

    # Bundled Chromium profile only (default):
    python scripts/cdp_browser_spike.py --site glassdoor

    # Attach to Chrome you started with remote debugging:
    #   Close normal Chrome first, then:
    #   & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" `
    #     --remote-debugging-port=9222 `
    #     --user-data-dir="$env:LOCALAPPDATA\\Google\\Chrome\\User Data"
    python scripts/cdp_browser_spike.py --site glassdoor --cdp-url http://127.0.0.1:9222

    # Both modes in one run:
    python scripts/cdp_browser_spike.py --site glassdoor --compare
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _probe_site(settings, *, site: str, cdp_url: str | None) -> dict:
    from agentzero.scrape.browser_board import SITE_CONFIGS
    from agentzero.scrape.browser_common import (
        close_browser_session,
        launch_browser_page,
        primary_scrape_query,
        wait_for_html,
    )

    if site not in SITE_CONFIGS:
        raise ValueError(f"Unsupported site: {site}")

    display, needs_human, has_results, build_url, parse_html, consent = SITE_CONFIGS[site]
    term, parsed = primary_scrape_query(settings)
    url = build_url(term=term, parsed=parsed)

    overrides: dict = {}
    if cdp_url:
        overrides["scrape_cdp_url"] = cdp_url
        overrides["scrape_cdp_sites"] = [site]
    else:
        overrides["scrape_cdp_url"] = None

    run_settings = settings.model_copy(update=overrides)
    mode = "cdp" if cdp_url else "bundled"

    playwright = context = None
    result = {
        "mode": mode,
        "site": site,
        "url": url,
        "listings": 0,
        "blocked": False,
        "error": None,
    }
    try:
        playwright, context, page = launch_browser_page(run_settings, site=site)
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        html = wait_for_html(page, predicate=has_results, timeout_ms=20_000)
        if not html:
            html = page.content()
        result["blocked"] = needs_human(html, page.url)
        records = parse_html(html, source=site)
        result["listings"] = len(records)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        close_browser_session(playwright, context, run_settings, site=site)

    return result


def _print_result(result: dict) -> None:
    mode = result["mode"]
    if result.get("error"):
        print(f"  [{mode}] ERROR: {result['error']}")
        return
    status = "blocked" if result["blocked"] else "ok"
    print(
        f"  [{mode}] listings={result['listings']} status={status} "
        f"url={result['url'][:80]}…"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Spike: bundled Chromium vs CDP Chrome")
    parser.add_argument(
        "--site",
        default="glassdoor",
        choices=["indeed", "linkedin", "glassdoor"],
    )
    parser.add_argument(
        "--cdp-url",
        default=None,
        help="Chrome DevTools URL (default: AGENTZERO_SCRAPE_CDP_URL or bundled only)",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run bundled profile then CDP (requires --cdp-url or env)",
    )
    args = parser.parse_args()

    from agentzero.config import get_settings

    settings = get_settings()
    cdp_url = args.cdp_url or settings.scrape_cdp_url

    print(f"Spike: {args.site} job search\n")

    if args.compare:
        print("Mode: bundled Chromium profile")
        _print_result(_probe_site(settings, site=args.site, cdp_url=None))
        if cdp_url:
            print(f"\nMode: CDP attach ({cdp_url})")
            _print_result(_probe_site(settings, site=args.site, cdp_url=cdp_url))
        else:
            print(
                "\nSkipping CDP — set --cdp-url or AGENTZERO_SCRAPE_CDP_URL.\n"
                "Start Chrome with:\n"
                '  chrome.exe --remote-debugging-port=9222 '
                '--user-data-dir="%LOCALAPPDATA%\\Google\\Chrome\\User Data"'
            )
    elif cdp_url:
        print(f"Mode: CDP attach ({cdp_url})")
        _print_result(_probe_site(settings, site=args.site, cdp_url=cdp_url))
    else:
        print("Mode: bundled Chromium profile")
        _print_result(_probe_site(settings, site=args.site, cdp_url=None))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
