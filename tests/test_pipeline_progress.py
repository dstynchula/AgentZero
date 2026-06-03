"""Pipeline progress reporting during scrape runs."""

from __future__ import annotations

from agentzero.loops.pipeline import Pipeline
from agentzero.loops.run_progress import RunProgress
from agentzero.models import RawRecord
from agentzero.scrape.base import JobSource
from agentzero.scrape.multi import MultiSource
from agentzero.storage.db import Database
from tests.test_loops import FakeSource


class StubBoard(JobSource):
    def __init__(self, board_name: str) -> None:
        self._board_name = board_name

    @property
    def name(self) -> str:
        return self._board_name

    def fetch(self, *, progress=None):
        return [
            RawRecord(
                title="Engineer",
                company="Acme",
                url=f"https://example.com/{self._board_name}",
                source=self._board_name,
            )
        ]


def test_multisource_updates_scrape_progress():
    progress = RunProgress(running=True)
    multi = MultiSource([StubBoard("indeed"), StubBoard("glassdoor")])
    multi.fetch(progress=progress)
    snap = progress.snapshot()
    assert snap.phase == "scrape"
    assert snap.done == 2
    assert snap.total == 2


def test_pipeline_finishes_with_done_phase(tmp_path, pipeline_test_settings):
    db = Database(tmp_path / "t.db")
    raw: RawRecord = {
        "title": "Software Engineer",
        "company": "Acme",
        "url": "https://example.com/1",
        "source": "fake",
        "location": "Remote",
    }
    source = FakeSource([raw])
    progress = RunProgress(running=True)
    pipeline = Pipeline(db, source, settings=pipeline_test_settings(), llm=None)
    pipeline.run(progress=progress)
    snap = progress.snapshot()
    assert snap.phase == "done"
    step_ids = [step["step_id"] for step in snap.plan]
    assert "filter.enrich_comp" not in step_ids
    db.close()
