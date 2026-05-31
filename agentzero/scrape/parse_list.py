"""Parse list-style job board HTML using configurable CSS selectors.

Example-only — used by tests and ``sources_config`` reference JSON, not the live scrape stack.
"""

from __future__ import annotations

from urllib.parse import urljoin

from agentzero.models import RawRecord
from agentzero.scrape.sources_config import JobSourceEntry


def parse_list_page_html(
    html: str,
    *,
    entry: JobSourceEntry,
    page_url: str,
) -> list[RawRecord]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise ImportError(
            "List-page parsing requires beautifulsoup4. pip install -e '.[scrape]'"
        ) from exc

    soup = BeautifulSoup(html, "html.parser")
    selectors = entry.selectors
    records: list[RawRecord] = []
    seen_urls: set[str] = set()

    cards = soup.select(selectors.job_card)
    if not cards:
        cards = soup.select("a[href*='job']")

    for card in cards:
        link = card.select_one(selectors.title_link) if card.name != "a" else card
        if link is None:
            link = card.find("a", href=True)
        if link is None:
            continue

        title = link.get_text(strip=True)
        href = link.get("href", "").strip()
        if not title or len(title) < 3 or not href:
            continue
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue

        url = urljoin(page_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        company_el = card.select_one(selectors.company)
        location_el = card.select_one(selectors.location)
        company = company_el.get_text(strip=True) if company_el else entry.name
        location = location_el.get_text(strip=True) if location_el else None

        record: RawRecord = {
            "title": title,
            "company": company or entry.name,
            "url": url,
            "source": entry.slug,
        }
        if location:
            record["location"] = location
        records.append(record)

    return records
