"""Parse Greenhouse job board HTML fixtures."""

from __future__ import annotations

from agentzero.models import RawRecord

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[misc, assignment]


def parse_greenhouse_html(html: str, *, source: str = "greenhouse") -> list[RawRecord]:
    if BeautifulSoup is None:
        raise ImportError("HTML parsing requires beautifulsoup4. pip install -e '.[scrape]'")
    soup = BeautifulSoup(html, "html.parser")
    records: list[RawRecord] = []
    for opening in soup.select("div.opening"):
        link = opening.select_one("a")
        if link is None:
            continue
        title = link.get_text(strip=True)
        url = link.get("href", "")
        company_node = opening.select_one(".company")
        company = company_node.get_text(strip=True) if company_node else "Unknown"
        records.append(
            {
                "title": title,
                "company": company,
                "url": url,
                "source": source,
            }
        )
    return records
