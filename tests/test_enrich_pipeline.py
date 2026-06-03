from agentzero.enrich.pipeline import enrich_job
from agentzero.models import JobPosting


def _job(**kwargs) -> JobPosting:
    base = dict(
        title="Engineer",
        company="Acme",
        url="https://jobs.example.com/1",
        source="indeed",
    )
    base.update(kwargs)
    return JobPosting(**base)


def test_shallow_enrich_sets_company_website_when_research_finds(monkeypatch):
    from agentzero.config import Settings

    def fake_web(job, *, settings, cache=None, user_agent=None):
        return job.model_copy(
            update={
                "company_website": "https://www.acme.com/",
                "is_public_company": True,
                "stock_ticker": "ACME",
            }
        )

    monkeypatch.setattr(
        "agentzero.enrich.pipeline.enrich_job_web_research",
        fake_web,
    )
    cfg = Settings(_env_file=None, enrich_web_search=True)
    enriched = enrich_job(_job(), settings=cfg)
    assert enriched.company_website == "https://www.acme.com/"
    assert enriched.is_public_company is True
    assert enriched.stock_ticker == "ACME"
