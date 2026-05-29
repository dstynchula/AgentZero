"""Resume and writing-sample ingestion."""

from agentzero.ingest.resume import ResumeProfile, ingest_resume
from agentzero.ingest.voice import VoiceProfile, ingest_voice_samples

__all__ = [
    "ResumeProfile",
    "ingest_resume",
    "VoiceProfile",
    "ingest_voice_samples",
]
