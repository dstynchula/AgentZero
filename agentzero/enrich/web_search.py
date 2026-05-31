"""Web search via the ``ddgs`` package (DuckDuckGo backend; HTML fallback)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

log = logging.getLogger(__name__)

DDG_HTML_URL = "https://html.duckduckgo.com/html/"


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


def _unwrap_ddg_redirect(href: str) -> str:
    if "uddg=" in href:
        parsed = parse_qs(urlparse(href).query)
        if "uddg" in parsed:
            return unquote(parsed["uddg"][0])
    return href


def parse_duckduckgo_html(html: str, *, max_results: int) -> list[SearchHit]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    hits: list[SearchHit] = []
    for block in soup.select("div.result"):
        link = block.select_one("a.result__a")
        if link is None or not link.get("href"):
            continue
        snippet_el = block.select_one("a.result__snippet") or block.select_one(
            ".result__snippet"
        )
        title = link.get_text(" ", strip=True)
        url = _unwrap_ddg_redirect(link["href"])
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        hits.append(SearchHit(title=title, url=url, snippet=snippet))
        if len(hits) >= max_results:
            break
    return hits


def _search_ddgs(query: str, *, max_results: int) -> list[SearchHit]:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # noqa: PLC0415 — legacy package name
        except ImportError:
            return []

    try:
        with DDGS() as ddgs:
            rows = list(ddgs.text(query, max_results=max_results))
    except Exception as exc:
        log.debug("DDGS search failed for %r: %s", query, exc)
        return []

    hits: list[SearchHit] = []
    for row in rows:
        href = row.get("href") or row.get("url") or ""
        if not href:
            continue
        hits.append(
            SearchHit(
                title=str(row.get("title") or ""),
                url=href,
                snippet=str(row.get("body") or row.get("snippet") or ""),
            )
        )
    return hits


def _search_ddg_html(query: str, *, max_results: int, user_agent: str) -> list[SearchHit]:
    try:
        import httpx
    except ImportError:
        return []

    try:
        response = httpx.post(
            DDG_HTML_URL,
            data={"q": query, "b": "", "kl": "us-en"},
            headers={
                "User-Agent": user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            follow_redirects=True,
            timeout=25.0,
        )
        if response.status_code >= 400:
            log.debug("DDG HTML HTTP %s for %r", response.status_code, query)
            return []
        return parse_duckduckgo_html(response.text, max_results=max_results)
    except Exception as exc:
        log.debug("DDG HTML search failed for %r: %s", query, exc)
        return []


def search_web(
    query: str,
    *,
    max_results: int = 8,
    user_agent: str,
    delay_seconds: float = 0.0,
) -> list[SearchHit]:
    """Run a web search and return normalized hits (DDGS first, HTML fallback)."""
    if delay_seconds > 0:
        time.sleep(delay_seconds)

    hits = _search_ddgs(query, max_results=max_results)
    if hits:
        return hits
    return _search_ddg_html(query, max_results=max_results, user_agent=user_agent)
