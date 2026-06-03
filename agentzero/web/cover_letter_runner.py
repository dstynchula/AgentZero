"""Background cover letter generation from the job detail card."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentzero.generate.cover_letter import COVER_LETTER_DIR, generate_cover_letter
from agentzero.ingest.resume import RESUME_DIR, find_latest_resume, read_resume_text

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.storage.db import Database


@dataclass
class CoverLetterRunState:
    running: bool = False
    last_message: str = ""
    last_ok: bool | None = None
    job_id: str | None = None
    last_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "message": self.last_message,
            "ok": self.last_ok,
            "job_id": self.job_id,
            "errors": list(self.last_errors),
        }


class CoverLetterRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = CoverLetterRunState()

    def start(
        self,
        *,
        db: Database,
        settings: Settings,
        job_id: str,
        cover_letters_dir: Path | None = None,
    ) -> tuple[bool, str]:
        with self._lock:
            if self.state.running:
                return False, "Cover letter generation already in progress."
            self.state.running = True
            self.state.job_id = job_id
            self.state.last_message = "Generating cover letter…"
            self.state.last_ok = None
            self.state.last_errors = []

        thread = threading.Thread(
            target=self._run,
            args=(db, settings, job_id, cover_letters_dir),
            daemon=True,
            name="agentzero-web-cover-letter",
        )
        thread.start()
        return True, "Generating cover letter in the background. Refresh when finished."

    def _run(
        self,
        db: Database,
        settings: Settings,
        job_id: str,
        cover_letters_dir: Path | None,
    ) -> None:
        from agentzero.llm.provider import build_cover_letter_provider

        try:
            job = db.get_job(job_id)
            if job is None:
                raise LookupError("job not found")

            try:
                resume_path = find_latest_resume(RESUME_DIR)
            except FileNotFoundError as exc:
                raise ValueError(
                    f"No résumé in {RESUME_DIR}/ — add a .pdf, .docx, .txt, or .md file."
                ) from exc

            resume_text = read_resume_text(resume_path)
            llm = build_cover_letter_provider(settings)
            base_dir = cover_letters_dir or COVER_LETTER_DIR

            generate_cover_letter(
                job,
                resume_text,
                llm=llm,
                base_dir=base_dir,
            )
            with self._lock:
                self.state.last_message = "Cover letter ready."
                self.state.last_ok = True
        except Exception as exc:  # noqa: BLE001 — surface in UI
            with self._lock:
                self.state.last_message = str(exc)
                self.state.last_ok = False
                self.state.last_errors = [str(exc)]
        finally:
            with self._lock:
                self.state.running = False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.state.to_dict()
