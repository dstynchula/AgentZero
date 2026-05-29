import json
from pathlib import Path

from agentzero.ingest.voice import (
    VoiceProfile,
    extract_voice_profile,
    ingest_voice_samples,
    load_writing_samples,
)

FIXTURES = Path(__file__).parent / "fixtures"


class FakeLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete(self, *, system: str, user: str) -> str:
        return json.dumps(self.payload)


def test_load_writing_samples(tmp_path):
    dest = tmp_path / "coverletters" / "a.txt"
    dest.parent.mkdir(parents=True)
    dest.write_text("Hello hiring team", encoding="utf-8")
    combined, sources = load_writing_samples(tmp_path / "coverletters")
    assert "Hello hiring team" in combined
    assert sources[0].endswith("a.txt")


def test_extract_voice_profile():
    llm = FakeLLM(
        {
            "tone": "direct and warm",
            "sample_phrases": ["pragmatic tools"],
            "style_guide": "Use short sentences and concrete outcomes.",
        }
    )
    profile = extract_voice_profile("sample text", llm=llm)
    assert profile.tone == "direct and warm"
    assert "pragmatic" in profile.sample_phrases[0]


def test_ingest_voice_samples(tmp_path):
    dest = tmp_path / "coverletters" / "sample.txt"
    dest.parent.mkdir(parents=True)
    sample = (FIXTURES / "sample_coverletter.txt").read_text(encoding="utf-8")
    dest.write_text(sample, encoding="utf-8")
    llm = FakeLLM(
        {
            "tone": "direct",
            "sample_phrases": ["concrete outcomes"],
            "style_guide": "Clear prose.",
        }
    )
    profile = ingest_voice_samples(llm=llm, directory=tmp_path / "coverletters")
    assert isinstance(profile, VoiceProfile)
    assert profile.source_files
