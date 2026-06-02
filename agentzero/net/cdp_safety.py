"""Validate Chrome DevTools Protocol (CDP) endpoint URLs."""

from __future__ import annotations

import os
from urllib.parse import urlparse

_LOCAL_CDP_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DOCKER_CDP_HOSTS = frozenset({"host.docker.internal"})


class UnsafeCDPURLError(ValueError):
    """Raised when a CDP URL is not permitted."""


def _docker_host_allowed() -> bool:
    raw = os.environ.get("AGENTZERO_CDP_ALLOW_DOCKER_HOST", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def allowed_cdp_hosts(*, allow_docker_host: bool | None = None) -> frozenset[str]:
    """Return permitted CDP hostname set for the current environment."""
    if allow_docker_host is None:
        allow_docker_host = _docker_host_allowed()
    hosts = set(_LOCAL_CDP_HOSTS)
    if allow_docker_host:
        hosts |= _DOCKER_CDP_HOSTS
    return frozenset(hosts)


def validate_cdp_url(url: str, *, allow_docker_host: bool | None = None) -> str:
    """Return *url* if it targets a permitted CDP listener; otherwise raise."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeCDPURLError(f"CDP URL must be http(s), got {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    permitted = allowed_cdp_hosts(allow_docker_host=allow_docker_host)
    if host not in permitted:
        hint = "127.0.0.1 / localhost / ::1"
        if allow_docker_host or _docker_host_allowed():
            hint += " / host.docker.internal (when AGENTZERO_CDP_ALLOW_DOCKER_HOST=true)"
        raise UnsafeCDPURLError(f"CDP URL must target {hint}, got {host!r}")
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise UnsafeCDPURLError(f"Invalid CDP port: {parsed.port}")
    return url.strip()


# Backward-compatible alias for tests importing private name
_ALLOWED_CDP_HOSTS = _LOCAL_CDP_HOSTS
