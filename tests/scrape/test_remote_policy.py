"""Tests for remote-only scrape policy."""

from __future__ import annotations

from agentzero.config import Settings
from agentzero.models import JobPosting
from agentzero.scrape.remote_policy import (
    apply_remote_only_settings,
    apply_remote_search_trust_to_record,
    filter_remote_jobs,
    format_remote_filter_skips,
    job_is_remote,
    location_is_explicitly_non_remote,
    parse_locations_for_scrape_remote_aware,
    trust_remote_search_listing,
)


def _job(**kwargs) -> JobPosting:
    base = dict(title="Eng", company="Acme", url="https://x.com/1", source="indeed")
    base.update(kwargs)
    return JobPosting(**base)


def test_apply_remote_only_settings():
    s = Settings(_env_file=None, locations=["Woodland Hills, CA"], remote_only=True)
    effective = apply_remote_only_settings(s)
    assert effective.locations == ["remote - usa"]
    assert effective.remote_preferred is True


def test_parse_locations_remote_only_drops_office():
    s = Settings(
        _env_file=None,
        locations=["Woodland Hills, CA", "Remote"],
        remote_only=True,
    )
    parsed = parse_locations_for_scrape_remote_aware(s)
    assert len(parsed) == 1
    assert parsed[0].is_remote is True


def test_job_is_remote_flags():
    assert job_is_remote(_job(remote=True))
    assert not job_is_remote(_job(remote=False))
    assert job_is_remote(_job(location="Remote - US"))
    assert job_is_remote(_job(location="United States"))
    assert job_is_remote(_job(location="TX"))
    assert not job_is_remote(_job(location="Woodland Hills, CA"))
    assert not job_is_remote(_job(location="Hybrid - Los Angeles, CA"))


def test_filter_remote_jobs():
    jobs = [
        _job(remote=True),
        _job(location="Beverly Hills, CA"),
    ]
    kept, rejected = filter_remote_jobs(jobs)
    assert len(kept) == 1
    assert len(rejected) == 1


def test_trust_remote_search_listing():
    assert trust_remote_search_listing("New York, NY", remote=None, remote_search=True) is True
    assert trust_remote_search_listing(
        "Hybrid - Los Angeles, CA", remote=None, remote_search=True
    ) is False
    assert trust_remote_search_listing("New York, NY", remote=None, remote_search=False) is None


def test_apply_remote_search_trust_to_record():
    record = {"location": "Dallas, TX"}
    apply_remote_search_trust_to_record(record, remote_search=True)
    assert record["remote"] is True

    hybrid = {"location": "Hybrid remote in Austin, TX"}
    apply_remote_search_trust_to_record(hybrid, remote_search=True)
    assert hybrid["remote"] is False


def test_format_remote_filter_skips():
    jobs = [_job(title="Sec Eng", company="Garner Health", location="New York, NY")]
    lines = format_remote_filter_skips(jobs)
    assert len(lines) == 1
    assert "Garner Health" in lines[0]
    assert "New York, NY" in lines[0]


def test_location_is_explicitly_non_remote():
    assert location_is_explicitly_non_remote("Hybrid - Boston, MA")
    assert not location_is_explicitly_non_remote("New York, NY")
