"""Combine multiple job sources (JobSpy + Playwright, etc.)."""

from __future__ import annotations

from collections.abc import Sequence

from agentzero.models import RawRecord
from agentzero.scrape.base import JobSource


class MultiSource(JobSource):
    """Run several sources sequentially and merge raw records."""

    name = "multi"

    def __init__(self, sources: Sequence[JobSource]) -> None:
        if not sources:
            raise ValueError("MultiSource requires at least one JobSource")
        self._sources = list(sources)

    def fetch(self) -> Sequence[RawRecord]:
        records: list[RawRecord] = []
        total = len(self._sources)
        for index, source in enumerate(self._sources, start=1):
            print(
                f"Scrape [{index}/{total}] {source.name} — starting…",
                flush=True,
            )
            batch = list(source.fetch())
            print(
                f"Scrape [{index}/{total}] {source.name} — {len(batch)} listing(s)",
                flush=True,
            )
            records.extend(batch)
        return records
