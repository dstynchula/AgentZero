from agentzero.ingest.resume import ResumeProfile
from agentzero.loops.pipeline import Pipeline, PipelineResult
from agentzero.loops.ralph import run_parallel
from agentzero.models import JobPosting, RawRecord
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
                "location": "Remote",
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


def test_pipeline_idempotent_scrape(tmp_path, pipeline_test_settings):
    db = Database(tmp_path / "jobs.db")
    raw = {
        "title": "Software Engineer",
        "company": "Acme",
        "url": "https://x.com/1",
        "source": "fake",
        "remote": True,
        "location": "Remote",
    }
    source = FakeSource([raw])
    pipeline = Pipeline(db, source, settings=pipeline_test_settings(), llm=None)
    r1 = pipeline.run()
    assert r1.scraped == 1
    r2 = pipeline.run()
    assert r2.scraped == 1
    assert db.count_jobs() == 1
    assert source.fetch_count == 2
    db.close()


def test_pipeline_enrich_rank(tmp_path, pipeline_test_settings):
    db = Database(tmp_path / "jobs.db")
    raw = {
        "title": "Software Engineer",
        "company": "Acme",
        "url": "https://x.com/1",
        "source": "fake",
        "remote": True,
        "location": "Remote",
    }
    source = FakeSource([raw])
    llm = FakeLLM()
    profile = ResumeProfile(raw_text="x", skills=["Python"], experience=[], source_path="")
    pipeline = Pipeline(db, source, settings=pipeline_test_settings(), llm=llm)
    result = pipeline.run(profile=profile)
    assert result.enriched >= 1
    assert result.ranked >= 1
    job = db.list_jobs()[0]
    assert job.match_score == 0.75
    db.close()


def test_pipeline_comp_filter_uses_run_settings(tmp_path, pipeline_test_settings):
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
    settings = pipeline_test_settings(salary_min=230_000)
    pipeline = Pipeline(db, source, settings=settings, llm=None)
    result = pipeline.run()
    assert result.scraped == 1
    assert result.comp_filtered == 1
    job = db.list_jobs()[0]
    assert job.company == "GoodCo"
    db.close()


def test_pipeline_result_ok():
    assert PipelineResult().ok
    assert not PipelineResult(errors=["Source health check failed"]).ok


def test_pipeline_unhealthy_source_skips_upserts(tmp_path, monkeypatch, pipeline_test_settings):
    db = Database(tmp_path / "jobs.db")
    raw_valid = {
        "title": "Software Engineer",
        "company": "Acme",
        "url": "https://x.com/1",
        "source": "fake",
        "remote": True,
        "location": "Remote",
    }
    raw_invalid = {"title": "", "company": "Bad", "url": "https://x.com/bad", "source": "fake"}
    source = FakeSource([raw_valid, raw_invalid])

    def _unhealthy(metrics, *, min_valid_pct=80.0):
        raise RuntimeError("Source health check failed: valid_pct=50.0 (minimum 80.0)")

    monkeypatch.setattr("agentzero.loops.pipeline.assert_source_healthy", _unhealthy)
    pipeline = Pipeline(db, source, settings=pipeline_test_settings(), llm=None)
    result = pipeline.run()
    assert not result.ok
    assert any("Source health check failed" in err for err in result.errors)
    assert result.quarantined == 1
    assert result.scraped == 0
    assert db.count_jobs() == 0
    db.close()


def test_pipeline_remote_only_filter(tmp_path, pipeline_test_settings):
    db = Database(tmp_path / "jobs.db")
    raw_remote = {
        "title": "Software Engineer",
        "company": "RemoteCo",
        "url": "https://x.com/remote",
        "source": "fake",
        "remote": True,
        "location": "Remote",
    }
    raw_onsite = {
        "title": "Software Engineer",
        "company": "OfficeCo",
        "url": "https://x.com/onsite",
        "source": "fake",
        "remote": False,
        "location": "San Francisco, CA",
    }
    source = FakeSource([raw_remote, raw_onsite])
    settings = pipeline_test_settings(
        remote_only=True,
        search_terms=[],
        salary_min=None,
    )
    pipeline = Pipeline(db, source, settings=settings, llm=None)
    result = pipeline.run()
    assert result.scraped == 1
    assert db.count_jobs() == 1
    assert db.list_jobs()[0].company == "RemoteCo"
    db.close()


def test_pipeline_title_filter_rejects_non_matching(tmp_path, pipeline_test_settings):
    db = Database(tmp_path / "jobs.db")
    raw_match = {
        "title": "Staff Security Engineer",
        "company": "SecureCo",
        "url": "https://x.com/security",
        "source": "fake",
        "remote": True,
        "location": "Remote",
    }
    raw_reject = {
        "title": "Account Executive",
        "company": "SalesCo",
        "url": "https://x.com/sales",
        "source": "fake",
        "remote": True,
        "location": "Remote",
    }
    source = FakeSource([raw_match, raw_reject])
    settings = pipeline_test_settings(
        search_terms=["security engineer"],
        salary_min=None,
    )
    pipeline = Pipeline(db, source, settings=settings, llm=None)
    result = pipeline.run()
    assert result.title_filtered == 1
    assert result.scraped == 1
    assert db.list_jobs()[0].company == "SecureCo"
    db.close()


def test_pipeline_backfill_enrich_uses_run_settings(tmp_path, pipeline_test_settings, monkeypatch):
    db = Database(tmp_path / "jobs.db")
    job = JobPosting(
        title="Backfill Role",
        company="StaleCo",
        url="https://example.com/backfill",
        source="fake",
        description="Build reliable systems.",
    )
    db.upsert_job(job)
    settings = pipeline_test_settings()
    seen: list[object] = []

    def _track_enrich(job, *, settings=None):
        seen.append(settings)
        return job

    monkeypatch.setattr("agentzero.loops.pipeline.enrich_job", _track_enrich)
    pipeline = Pipeline(db, FakeSource([]), settings=settings, llm=None)
    pipeline.run()
    assert seen
    assert all(s is settings for s in seen)
    db.close()


def test_pipeline_pending_enrich_backfill(tmp_path, pipeline_test_settings):
    db = Database(tmp_path / "jobs.db")
    job = JobPosting(
        title="Backfill Role",
        company="StaleCo",
        url="https://example.com/backfill",
        source="fake",
        description="Build reliable systems.",
    )
    db.upsert_job(job)
    assert db.list_pending("enrich_status") == [job.job_id]

    source = FakeSource([])
    pipeline = Pipeline(db, source, settings=pipeline_test_settings(), llm=None)
    result = pipeline.run()
    assert result.enriched >= 1
    assert db.list_pending("enrich_status") == []
    db.close()


def test_pipeline_rank_failures_in_errors(tmp_path, monkeypatch, pipeline_test_settings):
    db = Database(tmp_path / "jobs.db")
    raw_ok = {
        "title": "Software Engineer",
        "company": "GoodCo",
        "url": "https://x.com/good",
        "source": "fake",
        "remote": True,
        "location": "Remote",
    }
    raw_bad = {
        "title": "Software Engineer",
        "company": "BadCo",
        "url": "https://x.com/bad",
        "source": "fake",
        "remote": True,
        "location": "Remote",
    }
    source = FakeSource([raw_ok, raw_bad])
    llm = FakeLLM()
    profile = ResumeProfile(raw_text="x", skills=["Python"], experience=[], source_path="")

    def _rank(job, profile, *, llm, max_description_chars):
        if job.company == "BadCo":
            raise ValueError("rank failed")
        from types import SimpleNamespace

        return SimpleNamespace(match_score=0.8, rationale="good fit")

    monkeypatch.setattr("agentzero.loops.pipeline.rank_job", _rank)
    pipeline = Pipeline(db, source, settings=pipeline_test_settings(), llm=llm)
    result = pipeline.run(profile=profile)
    assert result.ranked == 1
    assert len(result.errors) == 1
    assert "BadCo" in result.errors[0]
    assert not result.ok
    db.close()


def test_pipeline_enrich_scraped_job_linkedin_detail(tmp_path, monkeypatch, pipeline_test_settings):
    db = Database(tmp_path / "jobs.db")
    settings = pipeline_test_settings()
    pipeline = Pipeline(
        db,
        FakeSource([]),
        settings=settings,
        llm=None,
    )
    job = JobPosting(
        title="Platform Engineer",
        company="LinkedCo",
        url="https://www.linkedin.com/jobs/view/123",
        source="linkedin",
        description="Design distributed services.",
    )

    def _fetch_detail(j, *, settings, allow_browser):
        assert allow_browser is True
        return j.model_copy(update={"comp_min": 180_000, "comp_max": 220_000})

    monkeypatch.setattr(
        "agentzero.enrich.detail_fetch.fetch_and_merge_detail",
        _fetch_detail,
    )
    enriched = pipeline._enrich_scraped_job(job, settings)
    assert enriched.comp_min == 180_000
    assert enriched.comp_max == 220_000
    db.close()
