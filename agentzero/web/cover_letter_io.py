"""Cover letter file helpers for the web UI."""

from __future__ import annotations

import re
from pathlib import Path

from agentzero.generate.cover_letter import COVER_LETTER_DIR, read_cover_letter
from agentzero.models import JobPosting

_FILENAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def cover_letters_dir(base: Path | None = None) -> Path:
    return base or COVER_LETTER_DIR


def cover_letter_download_filename(job: JobPosting) -> str:
    company = _FILENAME_UNSAFE.sub("-", job.company.strip())[:40].strip("-") or "company"
    title = _FILENAME_UNSAFE.sub("-", job.title.strip())[:50].strip("-") or "role"
    return f"{company}-{title}-cover-letter.txt"


def load_cover_letter_text(job_id: str, *, base_dir: Path | None = None) -> str | None:
    return read_cover_letter(job_id, base_dir=cover_letters_dir(base_dir))
