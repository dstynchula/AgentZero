"""Validate Chrome DevTools Protocol (CDP) endpoint URLs."""

from __future__ import annotations

from urllib.parse import urlparse

_ALLOWED_CDP_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class UnsafeCDPURLError(ValueError):
    """Raised when a CDP URL is not permitted."""


def validate_cdp_url(url: str) -> str:
    """Return *url* if it targets a local CDP listener; otherwise raise."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeCDPURLError(f"CDP URL must be http(s), got {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_CDP_HOSTS:
        raise UnsafeCDPURLError(
            f"CDP URL must target localhost (127.0.0.1 / localhost / ::1), got {host!r}"
        )
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise UnsafeCDPURLError(f"Invalid CDP port: {parsed.port}")
    return url.strip()
