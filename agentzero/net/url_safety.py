"""Validate outbound fetch URLs to reduce SSRF risk."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Cloud provider link-local metadata endpoints.
_METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.goog",
    }
)

_BLOCKED_HOSTNAMES = frozenset({"localhost", "0.0.0.0"})


class UnsafeURLError(ValueError):
    """Raised when a URL must not be fetched over the network."""


def _hostname_blocked(host: str) -> bool:
    lowered = host.strip().lower().rstrip(".")
    if lowered in _BLOCKED_HOSTNAMES:
        return True
    if lowered.endswith(".localhost") or lowered.endswith(".local"):
        return True
    return lowered in _METADATA_HOSTS


def _ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    if ip.is_multicast or ip.is_unspecified:
        return True
    return str(ip) in _METADATA_HOSTS


def _resolve_host_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Cannot resolve host for URL fetch: {host!r}") from exc
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            ips.append(ipaddress.ip_address(ip_str))
        except ValueError:
            continue
    if not ips:
        raise UnsafeURLError(f"No usable addresses for host: {host!r}")
    return ips


def url_host_matches(url: str, domain: str) -> bool:
    """Return True when ``url``'s host equals ``domain`` or is a subdomain of it.

    Uses the parsed hostname rather than a substring check so hostile values
    like ``indeed.com.evil.example`` (or ``notindeed.com``) do not match.
    """
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def is_safe_public_url(url: str) -> bool:
    """Return True when ``url`` is an http(s) URL targeting a public host."""
    try:
        validate_fetch_url(url)
    except UnsafeURLError:
        return False
    return True


def validate_fetch_url(url: str) -> str:
    """Return ``url`` if safe to fetch; otherwise raise ``UnsafeURLError``."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Only http(s) URLs may be fetched, got {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError(f"URL missing hostname: {url!r}")
    if _hostname_blocked(host):
        raise UnsafeURLError(f"Refusing blocked hostname: {host!r}")
    if host in _METADATA_HOSTS:
        raise UnsafeURLError(f"Refusing metadata host: {host!r}")

    # Literal IP in URL — validate directly.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _ip_blocked(literal):
            raise UnsafeURLError(f"Refusing non-public IP: {host!r}")
        return url

    for ip in _resolve_host_ips(host):
        if _ip_blocked(ip):
            raise UnsafeURLError(
                f"Refusing host {host!r} (resolves to non-public address {ip})"
            )
    return url
