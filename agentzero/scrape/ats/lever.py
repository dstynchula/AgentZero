"""Parse Lever job board HTML fixtures."""

from __future__ import annotations

from agentzero.models import RawRecord

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[misc, assignment]


def parse_lever_html(html: str, *, source: str = "lever") -> list[RawRecord]:
    if BeautifulSoup is None:
        raise ImportError("HTML parsing requires beautifulsoup4. pip install -e '.[scrape]'")
    soup = BeautifulSoup(html, "html.parser")
    records: list[RawRecord] = []
    for posting in soup.select("div.posting"):
        title_node = posting.select_one("h5")
        link = posting.select_one("a.posting-title")
        if title_node is None or link is None:
            continue
        records.append(
            {
                "title": title_node.get_text(strip=True),
                "company": posting.get("data-company", "Unknown"),
                "url": link.get("href", ""),
                "source": source,
            }
        )
    return records
