"""Tests for LLM JSON parsing helpers."""

import pytest

from agentzero.llm.json_util import (
    parse_llm_json_object,
    parse_llm_json_object_loose,
    strip_json_fences,
)


def test_strip_json_fences():
    assert strip_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_parse_llm_json_object():
    assert parse_llm_json_object('{"match_score": 0.5, "rationale": "ok"}') == {
        "match_score": 0.5,
        "rationale": "ok",
    }


def test_parse_llm_json_object_with_fence():
    text = '```json\n{"title": "Engineer"}\n```'
    assert parse_llm_json_object(text)["title"] == "Engineer"


def test_parse_llm_json_object_rejects_non_object():
    with pytest.raises(TypeError, match="JSON object"):
        parse_llm_json_object("[1, 2]")


def test_parse_llm_json_object_loose_regex_fence():
    text = "```json\n{\"ok\": true}\n```"
    assert parse_llm_json_object_loose(text) == {"ok": True}
