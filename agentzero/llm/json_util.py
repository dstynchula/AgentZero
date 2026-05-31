"""Parse JSON objects from LLM responses (with optional markdown fences)."""

from __future__ import annotations

import json
import re


def strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return cleaned


def parse_llm_json_object(text: str) -> dict:
    """Return a dict parsed from an LLM response string."""
    cleaned = strip_json_fences(text)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise TypeError("LLM response must be a JSON object")
    return data


def parse_llm_json_object_loose(text: str) -> dict:
    """Like ``parse_llm_json_object`` but also strips regex fence wrappers."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise TypeError("LLM response must be a JSON object")
    return data
