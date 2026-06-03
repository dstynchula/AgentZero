"""Shared Playwright helpers for real-browser job boards."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from urllib.parse import urlparse

from agentzero.scrape.location import ParsedLocation
from agentzero.scrape.remote_policy import parse_locations_for_scrape_remote_aware
from agentzero.scrape.resilience import DEFAULT_USER_AGENT

if TYPE_CHECKING:
    from agentzero.config import Settings

log = logging.getLogger(__name__)

InputFn = Callable[[str], str]

# Playwright injects flags that system Chrome rejects (especially on Windows).
_SYSTEM_CHROME_IGNORE_ARGS = (
    "--enable-automation",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
)


def build_launch_args(settings: Settings, *, headless: bool) -> list[str]:
    """Chrome launch args. Skip anti-automation blink flags for installed Chrome (channel=)."""
    args: list[str] = []
    if not settings.scrape_browser_channel:
        args.append("--disable-blink-features=AutomationControlled")
    if not headless:
        args.append("--start-maximized")
    return args


def cdp_endpoint_reachable(cdp_url: str, *, timeout_sec: float = 2.0) -> bool:
    """Return True when Chrome is listening for CDP at *cdp_url*."""
    import urllib.error
    import urllib.request

    base = cdp_url.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/json/version", timeout=timeout_sec) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def fetch_cdp_version_json(cdp_url: str, *, timeout_sec: float = 5.0) -> dict | None:
    """Return parsed ``/json/version`` payload or None when unreachable."""
    import json
    import urllib.error
    import urllib.request

    base = cdp_url.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/json/version", timeout=timeout_sec) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


_LOCAL_WS_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DOCKER_CDP_HOSTS = frozenset({"host.docker.internal"})


def _is_loopback_host(host: str | None) -> bool:
    return (host or "").lower() in _LOCAL_WS_HOSTS


def rewrite_cdp_ws_url_for_client(
    ws_url: str,
    *,
    cdp_http_url: str,
    allow_docker_host: bool,
) -> str | None:
    """Rewrite loopback WS URLs so Docker clients attach via the HTTP proxy host/port."""
    from urllib.parse import urlparse, urlunparse

    from agentzero.net.cdp_safety import allowed_cdp_hosts

    if not allow_docker_host:
        return None
    http = urlparse(cdp_http_url.strip())
    http_host = (http.hostname or "").lower()
    if http_host not in _DOCKER_CDP_HOSTS:
        return None
    ws = urlparse(ws_url.strip())
    if ws.scheme not in ("ws", "wss") or not _is_loopback_host(ws.hostname):
        return None
    proxy_port = http.port or (443 if http.scheme == "https" else 80)
    rewritten = urlunparse(ws._replace(netloc=f"{http_host}:{proxy_port}"))
    ws_host = (urlparse(rewritten).hostname or "").lower()
    if ws_host not in allowed_cdp_hosts(allow_docker_host=True):
        return None
    return rewritten


def resolve_cdp_ws_endpoint(cdp_url: str, *, allow_docker_host: bool = False) -> str | None:
    """Return a Playwright ``ws_endpoint`` when Docker bridge rewrite is required."""
    version = fetch_cdp_version_json(cdp_url)
    if version is None:
        return None
    raw_ws = version.get("webSocketDebuggerUrl")
    if not isinstance(raw_ws, str) or not raw_ws.strip():
        return None
    return rewrite_cdp_ws_url_for_client(
        raw_ws,
        cdp_http_url=cdp_url,
        allow_docker_host=allow_docker_host,
    )


def connect_cdp_browser(playwright: object, cdp_url: str, *, allow_docker_host: bool):
    """Attach Chromium to CDP, rewriting the WS URL for Docker when needed."""
    ws = resolve_cdp_ws_endpoint(cdp_url, allow_docker_host=allow_docker_host)
    chromium = playwright.chromium  # type: ignore[union-attr]
    if ws is not None:
        log.info("Connecting to Chrome over CDP via %s", ws)
        return chromium.connect(ws_endpoint=ws)
    log.info("Connecting to Chrome over CDP at %s", cdp_url)
    return chromium.connect_over_cdp(cdp_url)


def cdp_setup_hint(settings: Settings) -> str:
    from agentzero.scrape.cdp_launch import build_launch_commands

    port = cdp_port(settings.scrape_cdp_url) if settings.scrape_cdp_url else 9222
    auto = (
        "CDP Chrome auto-launches when AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH=true (default).\n"
        if settings.scrape_cdp_auto_launch
        else "Set AGENTZERO_SCRAPE_CDP_AUTO_LAUNCH=true or start Chrome manually.\n"
    )
    lines = [
        "Indeed and Glassdoor need your real Chrome profile (MFA / Cloudflare).",
        auto.rstrip(),
        "Start Chrome on the host:",
    ]
    for entry in build_launch_commands(port=port):
        lines.append(f"  {entry['platform']}: {entry['command']}")
    lines.append(f"  Set AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:{port} in .env")
    lines.append("LinkedIn continues to use the Playwright profile (no CDP required).")
    return "\n".join(lines) + "\n"


_CDP_LAUNCH_WAIT_SEC = 30.0
_CDP_POLL_INTERVAL_SEC = 0.5


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def cdp_port(cdp_url: str) -> int:
    parsed = urlparse(cdp_url)
    if parsed.port is not None:
        return parsed.port
    return 443 if parsed.scheme == "https" else 9222


def launch_cdp_chrome(settings: Settings) -> None:
    """Start dedicated Chrome with remote debugging (non-blocking)."""
    from agentzero.scrape.cdp_launch import default_cdp_profile_dir, launch_cdp_chrome_process

    cdp_url = settings.scrape_cdp_url
    if not cdp_url:
        raise ValueError("scrape_cdp_url is required to launch CDP Chrome")
    from agentzero.net.cdp_safety import validate_cdp_url

    validate_cdp_url(cdp_url)
    launch_cdp_chrome_process(
        port=cdp_port(cdp_url),
        user_data_dir=default_cdp_profile_dir(_repo_root()),
        quiet=True,
    )


def ensure_cdp_ready(settings: Settings, *, site: str) -> None:
    """Ensure CDP Chrome is listening before Playwright attaches."""
    if not settings.use_cdp_for_site(site):
        return
    cdp_url = settings.scrape_cdp_url
    if not cdp_url:
        raise ValueError(
            f"{site} requires AGENTZERO_SCRAPE_CDP_URL (see scripts/launch_chrome_cdp.py)"
        )
    if cdp_endpoint_reachable(cdp_url):
        return
    if not settings.scrape_cdp_auto_launch:
        raise RuntimeError(
            f"CDP not reachable at {cdp_url}. {cdp_setup_hint(settings)}"
        )
    log.info("CDP not reachable — auto-launching Chrome for %s", site)
    launch_cdp_chrome(settings)
    deadline = time.time() + _CDP_LAUNCH_WAIT_SEC
    while time.time() < deadline:
        if cdp_endpoint_reachable(cdp_url, timeout_sec=1.0):
            log.info("CDP ready at %s", cdp_url)
            return
        time.sleep(_CDP_POLL_INTERVAL_SEC)
    raise RuntimeError(
        f"CDP still not reachable at {cdp_url} after auto-launch. {cdp_setup_hint(settings)}"
    )


def ensure_cdp_for_sites(settings: Settings) -> None:
    """Auto-launch CDP Chrome for every configured CDP site before a browser batch."""
    if not settings.scrape_cdp_url:
        return
    raw = settings.scrape_cdp_sites
    if isinstance(raw, str):
        sites = [s.strip().lower() for s in raw.split(",") if s.strip()]
    else:
        sites = [s.strip().lower() for s in raw if s.strip()]
    if any(s in ("*", "all") for s in sites):
        sites = ["indeed", "glassdoor", "linkedin"]
    for site in sites:
        if settings.use_cdp_for_site(site):
            ensure_cdp_ready(settings, site=site)
            return


@runtime_checkable
class BrowserPage(Protocol):
    """Minimal Playwright ``Page`` surface used by scrape/enrich helpers."""

    @property
    def url(self) -> str: ...

    def content(self) -> str: ...

    def wait_for_load_state(self, state: str, *, timeout: float) -> None: ...

    def wait_for_timeout(self, ms: float) -> None: ...

    def locator(self, selector: str) -> object: ...


def browser_profile_dir(settings: Settings, site: str) -> Path:
    """Per-site persistent Chromium profile under ``data/browser_profiles/<site>``."""
    legacy = settings.scrape_browser_profile_dir
    if legacy.name == "indeed_browser_profile" and site == "indeed":
        return legacy
    root = legacy.parent / "browser_profiles"
    return root / site


def primary_scrape_query(settings: Settings) -> tuple[str, ParsedLocation]:
    """One term + one location for a quick browser search (first of each)."""
    if not settings.search_terms:
        raise ValueError("At least one search term is required")
    parsed_locations = parse_locations_for_scrape_remote_aware(settings)
    if not parsed_locations:
        raise ValueError("At least one location is required")
    return settings.search_terms[0], parsed_locations[0]


def persistent_context_kwargs(
    settings: Settings,
    *,
    headless: bool,
    launch_args: list[str],
    context_kwargs: dict | None = None,
) -> dict:
    """Build kwargs for ``launch_persistent_context`` (channel + Windows Chrome fixes)."""
    opts: dict = {
        "headless": headless,
        "args": launch_args,
        **(context_kwargs or {}),
    }
    channel = settings.scrape_browser_channel
    if channel:
        opts["channel"] = channel
        opts["ignore_default_args"] = list(_SYSTEM_CHROME_IGNORE_ARGS)
        if sys.platform == "win32":
            opts["chromium_sandbox"] = True
    return opts


def validate_browser_page_url(page: BrowserPage) -> bool:
    """Return False when the browser landed on a blocked URL (SSRF guard)."""
    from agentzero.net.url_safety import UnsafeURLError, validate_fetch_url

    try:
        validate_fetch_url(page.url)
    except UnsafeURLError as exc:
        log.warning("Blocked browser URL %s: %s", page.url, exc)
        return False
    return True


def launch_browser_page(settings: Settings, *, site: str, headless: bool | None = None):
    """Return (playwright, context, page) — caller must close context."""
    from playwright.sync_api import sync_playwright

    from agentzero.scrape.browser_session import (
        apply_storage_state,
        load_storage_state,
        storage_state_path,
    )

    user_agent = settings.scrape_user_agent or DEFAULT_USER_AGENT
    headless_val = headless if headless is not None else settings.scrape_browser_headless
    profile_dir = browser_profile_dir(settings, site)
    profile_dir.mkdir(parents=True, exist_ok=True)

    playwright = sync_playwright().start()
    launch_args = build_launch_args(settings, headless=headless_val)
    context_kwargs: dict = {
        "user_agent": user_agent,
        "viewport": {"width": 1366, "height": 768},
        "locale": "en-US",
    }

    if settings.use_cdp_for_site(site):
        cdp_url = settings.scrape_cdp_url
        assert cdp_url is not None
        ensure_cdp_ready(settings, site=site)
        browser = connect_cdp_browser(
            playwright,
            cdp_url,
            allow_docker_host=settings.cdp_allow_docker_host,
        )
        context = browser.contexts[0] if browser.contexts else browser.new_context(**context_kwargs)
        page = context.new_page()
        state = load_storage_state(storage_state_path(settings, site))
        if state:
            apply_storage_state(context, state)
        return playwright, context, page

    persistent_kwargs = persistent_context_kwargs(
        settings,
        headless=headless_val,
        launch_args=launch_args,
        context_kwargs=context_kwargs,
    )
    if settings.scrape_browser_channel:
        log.info(
            "Launching browser channel=%s profile=%s",
            settings.scrape_browser_channel,
            profile_dir,
        )

    context = playwright.chromium.launch_persistent_context(
        str(profile_dir),
        **persistent_kwargs,
    )
    state = load_storage_state(storage_state_path(settings, site))
    if state:
        apply_storage_state(context, state)

    page = context.pages[0] if context.pages else context.new_page()
    return playwright, context, page


def close_browser_session(
    playwright: object | None,
    context: object | None,
    settings: Settings,
    *,
    site: str | None = None,
) -> None:
    """Close Playwright resources; CDP attach disconnects without closing user Chrome."""
    if site is not None and settings.use_cdp_for_site(site):
        if playwright is not None:
            playwright.stop()  # type: ignore[union-attr]
        return
    if context is not None:
        context.close()  # type: ignore[union-attr]
    if playwright is not None:
        playwright.stop()  # type: ignore[union-attr]


def wait_for_html(
    page: BrowserPage,
    *,
    predicate: Callable[[str], bool],
    timeout_ms: int = 30_000,
) -> str:
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15_000))
    except Exception:
        pass
    deadline = time.time() + (timeout_ms / 1000)
    last_html = ""
    while time.time() < deadline:
        try:
            last_html = page.content()
        except Exception as exc:
            log.warning("Browser page closed while waiting for results (%s)", exc)
            return last_html
        if predicate(last_html):
            return last_html
        try:
            page.wait_for_timeout(750)
        except Exception as exc:
            log.warning("Browser closed during wait (%s)", exc)
            return last_html
    try:
        return last_html or page.content()
    except Exception:
        return last_html


def click_consent_buttons(page: BrowserPage, selectors: Sequence[str]) -> None:
    for selector in selectors:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=2_000):
                btn.click()
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


def prompt_for_browser_verification(
    *,
    site: str,
    reason: str,
    input_fn: InputFn,
    pause_enabled: bool,
    will_reload: bool = False,
) -> None:
    if not pause_enabled:
        return
    print("\n" + "=" * 60)
    print(f"{site} browser — action needed")
    print("=" * 60)
    print(reason)
    print("Complete any block/consent in the Chromium window.")
    if will_reload:
        print(
            "If you still see a Ray ID or blank/sorry page after solving CAPTCHA, "
            "press Enter here — the search will reload automatically."
        )
    else:
        print("When listings appear (or the block is gone), press Enter here.")
    print("=" * 60)
    input_fn("Press Enter when ready… ")


MAX_HUMAN_PROMPTS = 3
POLL_INTERVAL_SEC = 1.5
AUTO_VERIFY_WAIT_SEC = 300.0


def _enter_pressed() -> bool:
    """Non-blocking check for Enter in an interactive terminal."""
    if not sys.stdin.isatty():
        return False
    if sys.platform == "win32":
        try:
            import msvcrt

            return msvcrt.kbhit()
        except ImportError:
            return False
    try:
        import select

        return bool(select.select([sys.stdin], [], [], 0)[0])
    except Exception:
        return False


def _consume_enter() -> None:
    if sys.platform == "win32":
        try:
            import msvcrt

            while msvcrt.kbhit():
                msvcrt.getwch()
        except ImportError:
            return
        return
    try:
        import select

        if select.select([sys.stdin], [], [], 0)[0]:
            sys.stdin.readline()
    except Exception:
        pass


def maybe_wait_for_human(
    page: BrowserPage,
    *,
    site: str,
    html: str,
    needs_human: Callable[[str, str], bool],
    input_fn: InputFn,
    pause_enabled: bool,
    has_results: Callable[[str], bool] | None = None,
    max_attempts: int = MAX_HUMAN_PROMPTS,
    after_prompt: Callable[[BrowserPage], None] | None = None,
) -> None:
    if not pause_enabled:
        return
    url = page.url
    if has_results and has_results(html):
        return
    if not needs_human(html, url):
        return

    attempts = 0
    announced = False
    deadline = time.time() + AUTO_VERIFY_WAIT_SEC

    while attempts < max_attempts and time.time() < deadline:
        try:
            current_html = page.content()
            current_url = page.url
        except Exception as exc:
            log.warning("%s browser: page closed during CAPTCHA wait (%s)", site, exc)
            return

        if has_results and has_results(current_html):
            log.info("%s browser: listings detected — continuing scrape", site)
            return
        if not needs_human(current_html, current_url):
            return

        if not announced:
            print("\n" + "=" * 60)
            print(f"{site} browser — verification")
            print("=" * 60)
            print("Complete CAPTCHA/consent in Chromium.")
            print(
                "The scrape continues automatically when job listings appear. "
                "If you still see a Ray ID / sorry page, press Enter to reload the search."
            )
            print("=" * 60, flush=True)
            announced = True

        if _enter_pressed():
            _consume_enter()
            attempts += 1
            if after_prompt is not None:
                try:
                    log.info("%s browser: reloading search after Enter", site)
                    after_prompt(page)
                except Exception as exc:
                    log.warning("%s browser: reload after CAPTCHA failed (%s)", site, exc)
                    return
            continue

        try:
            page.wait_for_timeout(int(POLL_INTERVAL_SEC * 1000))
        except Exception as exc:
            log.warning("%s browser: page closed during CAPTCHA wait (%s)", site, exc)
            return

    log.warning(
        "%s browser: still blocked after %d reload(s) / %.0fs wait — continuing with partial results",
        site,
        attempts,
        AUTO_VERIFY_WAIT_SEC,
    )
