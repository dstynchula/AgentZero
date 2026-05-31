from agentzero.config import Settings
from agentzero.ingest.resume import ResumeProfile
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

    failures = run_parallel(["a", "b"], worker, max_workers=2)
    assert sorted(seen) == ["a", "b"]
    assert failures == []


def test_run_parallel_collects_failures():
    def worker(item: str) -> None:
        if item == "bad":
            raise ValueError("nope")

    failures = run_parallel(["ok", "bad"], worker, max_workers=2)
    assert len(failures) == 1
    assert "bad" in failures[0]


def test_pipeline_idempotent_scrape(tmp_path):
    db = Database(tmp_path / "jobs.db")
    raw = {
        "title": "Software Engineer",
        "company": "Acme",
        "url": "https://x.com/1",
        "source": "fake",
        "remote": True,
    }
    source = FakeSource([raw])
    pipeline = Pipeline(db, source, settings=Settings(_env_file=None, remote_only=False), llm=None)
    r1 = pipeline.run()
    assert r1.scraped == 1
    r2 = pipeline.run()
    assert r2.scraped == 1
    assert db.count_jobs() == 1
    assert source.fetch_count == 2
    db.close()


def test_pipeline_enrich_rank(tmp_path):
    db = Database(tmp_path / "jobs.db")
    raw = {
        "title": "Software Engineer",
        "company": "Acme",
        "url": "https://x.com/1",
        "source": "fake",
        "remote": True,
    }
    source = FakeSource([raw])
    llm = FakeLLM()
    profile = ResumeProfile(raw_text="x", skills=["Python"], experience=[], source_path="")
    pipeline = Pipeline(db, source, settings=Settings(_env_file=None, remote_only=False), llm=llm)
    result = pipeline.run(profile=profile)
    assert result.enriched >= 1
    assert result.ranked >= 1
    job = db.list_jobs()[0]
    assert job.match_score == 0.75
    db.close()


def test_pipeline_comp_filter_uses_run_settings(tmp_path):
    db = Database(tmp_path / "jobs.db")
    raw_low = {
        "title": "Junior Software Engineer",
        "company": "CheapCo",
        "url": "https://example.com/low",
        "source": "fake",
        "comp_min": 100_000,
        "comp_max": 150_000,
    }
    raw_ok = {
        "title": "Staff Software Engineer",
        "company": "GoodCo",
        "url": "https://example.com/high",
        "source": "fake",
        "comp_min": 200_000,
        "comp_max": 250_000,
        "remote": True,
    }
    source = FakeSource([raw_low, raw_ok])
    settings = Settings(_env_file=None, salary_min=230_000, remote_only=False)
    pipeline = Pipeline(db, source, settings=settings, llm=None)
    result = pipeline.run()
    assert result.scraped == 1
    assert result.comp_filtered == 1
    job = db.list_jobs()[0]
    assert job.company == "GoodCo"
    db.close()
