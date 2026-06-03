import pytest

from agentzero.models import RawRecord
from agentzero.scrape.base import JobSource


class FakeSource(JobSource):
    name = "fake"

    def __init__(self, records: list[RawRecord]) -> None:
        self._records = records

    def fetch(self, *, progress=None) -> list[RawRecord]:
        return list(self._records)


def test_job_source_fetch_returns_raw_records():
    raw: RawRecord = {"title": "Engineer", "company": "Acme", "url": "https://x.com/1"}
    source = FakeSource([raw])
    assert source.fetch() == [raw]


def test_job_source_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        JobSource()  # type: ignore[abstract]
