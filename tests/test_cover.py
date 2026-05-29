
from agentzero.generate.cover_letter import cover_letter_path, generate_cover_letter
from agentzero.ingest.resume import ResumeProfile
from agentzero.ingest.voice import VoiceProfile
from agentzero.models import JobPosting


class FakeLLM:
    def complete(self, *, system: str, user: str) -> str:
        return "# Cover Letter\n\nDear team,\n\nI am a great fit.\n"


def test_cover_letter_path_is_stable():
    job = JobPosting(title="T", company="Acme Inc", url="https://x.com/1", source="indeed")
    p1 = cover_letter_path(job)
    p2 = cover_letter_path(job)
    assert p1 == p2
    assert p1.name.startswith(job.job_id)


def test_generate_cover_letter_writes_file(tmp_path):
    job = JobPosting(title="Engineer", company="Acme", url="https://x.com/1", source="indeed")
    profile = ResumeProfile(raw_text="resume", skills=[], experience=[], source_path="")
    voice = VoiceProfile(style_guide="Be direct.", sample_phrases=["pragmatic"])
    path = generate_cover_letter(
        job, profile, voice, llm=FakeLLM(), output_dir=tmp_path / "letters"
    )
    assert path.is_file()
    assert "Cover Letter" in path.read_text(encoding="utf-8")
