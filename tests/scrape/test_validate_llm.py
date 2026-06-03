import json

import pytest

from agentzero.scrape.validate import (
    build_llm_repair_prompt,
    llm_repair_raw,
    validate_batch,
    validate_raw_with_llm,
)


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.response


def test_build_llm_repair_prompt_includes_schema_and_error():
    raw = {"job_title": "Engineer"}
    prompt = build_llm_repair_prompt(raw, "missing url", source="indeed")
    data = json.loads(prompt)
    assert data["raw_record"] == raw
    assert "missing url" in data["validation_error"]
    assert "title" in json.dumps(data["target_schema"])


def test_llm_repair_strips_markdown_fence():
    llm = FakeLLM(
        '```json\n{"title": "T", "company": "C", "url": "https://x.com/1", '
        '"source": "indeed", "location": "Remote"}\n```'
    )
    repaired = llm_repair_raw(
        {"broken": True}, source="indeed", error="err", llm=llm
    )
    assert repaired["title"] == "T"


def test_validate_raw_with_llm_repairs_broken_record():
    llm = FakeLLM(
        json.dumps(
            {
                "title": "Data Engineer",
                "company": "DataCo",
                "url": "https://jobs.example.com/9",
                "source": "indeed",
                "location": "Remote",
            }
        )
    )
    raw = {"job_title": "Data Engineer", "company_name": "DataCo"}
    outcome = validate_raw_with_llm(raw, source="indeed", llm=llm)
    assert outcome.ok
    assert outcome.repaired
    assert outcome.job is not None
    assert outcome.job.title == "Data Engineer"


def test_validate_raw_with_llm_quarantines_when_repair_fails():
    llm = FakeLLM('{"title": "still missing fields"}')
    outcome = validate_raw_with_llm({"x": 1}, source="indeed", llm=llm)
    assert not outcome.ok
    assert outcome.quarantined


def test_validate_raw_with_llm_skips_llm_when_none():
    raw = {
        "title": "A",
        "company": "C",
        "url": "https://x.com/a",
        "source": "indeed",
        "location": "Remote",
    }
    outcome = validate_raw_with_llm(raw, source="indeed", llm=None)
    assert outcome.ok


def test_validate_batch_with_llm_improves_valid_pct():
    records = [
        {
            "job_title": "A",
            "company_name": "C",
            "job_url": "https://x.com/a",
            "location": "Remote",
        },
        {"title": "broken"},
    ]
    llm = FakeLLM(
        json.dumps(
            {
                "title": "B",
                "company": "C",
                "url": "https://x.com/b",
                "source": "indeed",
                "location": "Remote",
            }
        )
    )
    jobs, quarantined, metrics = validate_batch(records, source="indeed", llm=llm)
    assert len(jobs) == 2
    assert len(quarantined) == 0
    assert metrics["valid_pct"] == 100.0


def test_llm_repair_rejects_non_object_response():
    llm = FakeLLM("[1, 2, 3]")
    with pytest.raises(TypeError, match="JSON object"):
        llm_repair_raw({}, source="indeed", error="e", llm=llm)


def test_validate_raw_with_llm_handles_invalid_json():
    llm = FakeLLM("not json at all")
    outcome = validate_raw_with_llm({"bad": True}, source="indeed", llm=llm)
    assert not outcome.ok
    assert outcome.quarantined
    assert "LLM repair failed" in (outcome.error or "")


def test_validate_raw_with_llm_when_second_validation_fails():
    llm = FakeLLM(json.dumps({"title": "Only title"}))
    outcome = validate_raw_with_llm({"x": 1}, source="indeed", llm=llm)
    assert not outcome.ok
    assert outcome.quarantined
