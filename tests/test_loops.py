from agentzero.ingest.resume import ResumeProfile
from agentzero.ingest.voice import VoiceProfile
from agentzero.loops.pipeline import Pipeline
from agentzero.loops.ralph import run_parallel
from agentzero.models import RawRecord
from agentzero.scrape.base import JobSource
from agentzero.storage.db import Database


class FakeSource(JobSource):
    name = "fake"

    def __init__(self, records: list[RawRecord]) -> None:
        self._records = records
        self.fetch_count = 0

    def fetch(self):
        self.fetch_count += 1
        return list(self._records)


class FakeLLM:
    def complete(self, *, system: str, user: str) -> str:
        import json

        if "match_score" in system:
            return json.dumps({"match_score": 0.75, "rationale": "ok"})
        if "cover letter" in system.lower():
            return "# Draft\n\nHello\n"
        return json.dumps(
            {
                "title": "Engineer",
                "company": "Acme",
                "url": "https://x.com/1",
                "source": "fake",
            }
        )


def test_run_parallel_invokes_workers():
    seen: list[str] = []

    def worker(item: str) -> None:
        seen.append(item)

    run_parallel(["a", "b"], worker, max_workers=2)
    assert sorted(seen) == ["a", "b"]


def test_pipeline_idempotent_scrape(tmp_path):
    db = Database(tmp_path / "jobs.db")
    raw = {"title": "Eng", "company": "Acme", "url": "https://x.com/1", "source": "fake"}
    source = FakeSource([raw])
    pipeline = Pipeline(db, source, llm=None)
    r1 = pipeline.run()
    assert r1.scraped == 1
    r2 = pipeline.run()
    assert r2.scraped == 1
    assert db.count_jobs() == 1
    assert source.fetch_count == 2
    db.close()


def test_pipeline_enrich_rank_draft(tmp_path):
    db = Database(tmp_path / "jobs.db")
    raw = {"title": "Eng", "company": "Acme", "url": "https://x.com/1", "source": "fake"}
    source = FakeSource([raw])
    llm = FakeLLM()
    profile = ResumeProfile(raw_text="x", skills=["Python"], experience=[], source_path="")
    voice = VoiceProfile(style_guide="Direct", sample_phrases=[])
    pipeline = Pipeline(db, source, llm=llm)
    result = pipeline.run(profile=profile, voice=voice)
    assert result.enriched >= 1
    assert result.ranked >= 1
    assert result.drafted >= 1
    job = db.list_jobs()[0]
    assert job.match_score == 0.75
    db.close()
