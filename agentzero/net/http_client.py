"""Shared HTTP GET with SSRF validation (including redirect hops)."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

from agentzero.net.url_safety import UnsafeURLError, validate_fetch_url

log = logging.getLogger(__name__)

_REDIRECT_STATUS = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 5
# Cap response bodies to limit memory use on hostile or oversized pages.
_DEFAULT_MAX_BYTES = 2_000_000


def safe_get_text(
    url: str,
    *,
    user_agent: str,
    timeout: float = 20.0,
    max_bytes: int | None = _DEFAULT_MAX_BYTES,
    max_chars: int | None = None,
) -> str | None:
    """Fetch a public http(s) URL; return response text or None on failure."""
    try:
        import httpx
    except ImportError:
        return None

    current = url.strip()
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=timeout,
            headers={"User-Agent": user_agent},
        ) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                try:
                    validate_fetch_url(current)
                except UnsafeURLError as exc:
                    log.debug("Blocked URL fetch %s: %s", current, exc)
                    return None
                with client.stream("GET", current) as response:
                    if response.status_code in _REDIRECT_STATUS:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current = urljoin(str(response.url), location)
                        continue
                    if response.status_code >= 400:
                        return None
                    chunks: list[bytes] = []
                    total = 0
                    limit = max_bytes
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        if limit is not None and total + len(chunk) > limit:
                            remaining = limit - total
                            if remaining > 0:
                                chunks.append(chunk[:remaining])
                            break
                        chunks.append(chunk)
                        total += len(chunk)
                    text = b"".join(chunks).decode(
                        response.encoding or "utf-8",
                        errors="replace",
                    )
                    if max_chars is not None:
                        text = text[:max_chars]
                    return text
    except Exception as exc:
        log.debug("HTTP GET failed %s: %s", url, exc)
        return None
    log.debug("Too many redirects for %s", url)
    return None
