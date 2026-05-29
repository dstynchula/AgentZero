

from agentzero.enrich.comp import enrich_comp, parse_comp_from_description, parse_employee_count
from agentzero.enrich.company import bucket_employee_count, enrich_company_size
from agentzero.enrich.glassdoor_rating import enrich_glassdoor, parse_rating_from_description
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


def test_parse_comp_from_description_range():
    low, high, currency = parse_comp_from_description("$100,000 - $130,000")
    assert low == 100_000
    assert high == 130_000
    assert currency == "USD"


def test_enrich_comp_from_description():
    job = _job(description="Salary: $90k - $110k per year")
    enriched = enrich_comp(job)
    assert enriched.comp_min == 90_000
    assert enriched.comp_max == 110_000
    assert enriched.comp_is_estimate is True


def test_enrich_comp_skips_when_already_set():
    job = _job(comp_min=100_000, description="$50k")
    assert enrich_comp(job).comp_min == 100_000


def test_enrich_comp_no_description():
    job = _job()
    assert enrich_comp(job) is job


def test_enrich_comp_no_parseable_salary():
    job = _job(description="Excellent benefits and remote work")
    assert enrich_comp(job) is job


def test_enrich_comp_handles_parse_error():
    job = _job(description="Listed, no valid salary")
    result = enrich_comp(job)
    assert result.comp_min is None


def test_parse_employee_count():
    assert parse_employee_count("We have 250 employees worldwide") == 250
    assert parse_employee_count("no size here") is None


def test_bucket_employee_count():
    assert bucket_employee_count(5) == "1-10"
    assert bucket_employee_count(10_000) == "5000+"


def test_enrich_company_size():
    job = _job(description="Growing team of 75 employees")
    enriched = enrich_company_size(job)
    assert enriched.company_size == "51-200"


def test_parse_rating_from_description():
    assert parse_rating_from_description("Glassdoor rating: 4.2 stars") == 4.2


def test_enrich_glassdoor_from_description():
    job = _job(description="Glassdoor rating: 3.8")
    enriched = enrich_glassdoor(job)
    assert enriched.glassdoor_rating == 3.8


def test_enrich_job_runs_all_steps():
    job = _job(
        description="Salary $120k-150k. 120 employees. Glassdoor rating: 4.1",
    )
    enriched = enrich_job(job)
    assert enriched.comp_min == 120_000
    assert enriched.company_size == "51-200"
    assert enriched.glassdoor_rating == 4.1
