"""Combine multiple job sources (JobSpy + Playwright, etc.)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from agentzero.models import RawRecord
from agentzero.scrape.base import JobSource
from agentzero.scrape.browser_board import BrowserJobBoardSource

if TYPE_CHECKING:
    from agentzero.loops.run_progress import RunProgress


class MultiSource(JobSource):
    """Run several sources sequentially and merge raw records."""

    name = "multi"

    def __init__(self, sources: Sequence[JobSource]) -> None:
        if not sources:
            raise ValueError("MultiSource requires at least one JobSource")
        self._sources = list(sources)

    def fetch(self, *, progress: RunProgress | None = None) -> Sequence[RawRecord]:
        if all(isinstance(s, BrowserJobBoardSource) for s in self._sources):
            return self._fetch_browser_sources(progress=progress)
        return self._fetch_sources_sequential(progress=progress)

    def _fetch_browser_sources(self, *, progress: RunProgress | None) -> Sequence[RawRecord]:
        from playwright.sync_api import sync_playwright

        records: list[RawRecord] = []
        total = len(self._sources)
        if progress is not None:
            progress.enter_step(
                "scrape.boards",
                phase="scrape",
                label="Scrape job boards",
                total=total,
                done=0,
                next_step_id=f"scrape.{self._sources[0].name}" if self._sources else "",
                next_step_label=self._sources[0].name if self._sources else "",
            )
        with sync_playwright() as pw:
            for index, source in enumerate(self._sources, start=1):
                assert isinstance(source, BrowserJobBoardSource)
                if progress is not None:
                    next_src = (
                        self._sources[index].name if index < total else "validate.batch"
                    )
                    progress.enter_step(
                        f"scrape.{source.name}",
                        phase="scrape",
                        label=f"Scrape {source.name} ({index}/{total})",
                        total=total,
                        done=index - 1,
                        detail=source.name,
                        step_index=index,
                        next_step_id=f"scrape.{next_src}"
                        if index < total
                        else "validate.batch",
                        next_step_label=next_src if index < total else "Validate listings",
                        extra={"board": source.name, "board_index": index, "board_total": total},
                    )
                print(
                    f"Scrape [{index}/{total}] {source.name} — starting…",
                    flush=True,
                )
                batch = list(source.fetch_with_playwright(pw, progress=progress))
                if progress is not None:
                    progress.step(
                        detail=f"{source.name}: {len(batch)} listing(s)",
                        done=index,
                    )
                print(
                    f"Scrape [{index}/{total}] {source.name} — {len(batch)} listing(s)",
                    flush=True,
                )
                records.extend(batch)
        return records

    def _fetch_sources_sequential(self, *, progress: RunProgress | None) -> Sequence[RawRecord]:
        records: list[RawRecord] = []
        total = len(self._sources)
        if progress is not None:
            progress.enter_step(
                "scrape.boards",
                phase="scrape",
                label="Scrape job boards",
                total=total,
                done=0,
            )
        for index, source in enumerate(self._sources, start=1):
            if progress is not None:
                next_src = self._sources[index].name if index < total else "validate.batch"
                progress.enter_step(
                    f"scrape.{source.name}",
                    phase="scrape",
                    label=f"Scrape {source.name} ({index}/{total})",
                    total=total,
                    done=index - 1,
                    detail=source.name,
                    step_index=index,
                    next_step_id=f"scrape.{next_src}" if index < total else "validate.batch",
                    next_step_label=next_src if index < total else "Validate listings",
                    extra={"board": source.name, "board_index": index, "board_total": total},
                )
            print(
                f"Scrape [{index}/{total}] {source.name} — starting…",
                flush=True,
            )
            batch = list(source.fetch(progress=progress))
            if progress is not None:
                progress.step(
                    detail=f"{source.name}: {len(batch)} listing(s)",
                    done=index,
                )
            print(
                f"Scrape [{index}/{total}] {source.name} — {len(batch)} listing(s)",
                flush=True,
            )
            records.extend(batch)
        return records
