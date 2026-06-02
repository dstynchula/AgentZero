"""Load résumé + search profile from the web settings UI."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentzero.ingest.resume import RESUME_DIR, find_latest_resume
from agentzero.ingest.search_profile import (
    clear_search_profile_session_cache,
    resolve_search_from_resume,
)
from agentzero.web.search_titles import sync_operator_titles_after_resume_load


@dataclass
class ResumeLoadState:
    running: bool = False
    last_message: str = ""
    last_ok: bool | None = None
    resume_file: str | None = None
    title_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "message": self.last_message,
            "ok": self.last_ok,
            "resume_file": self.resume_file,
            "title_count": self.title_count,
        }


def latest_resume_info(resume_dir: Path = RESUME_DIR) -> dict[str, Any]:
    try:
        path = find_latest_resume(resume_dir)
    except FileNotFoundError:
        return {"available": False, "filename": None, "path": str(resume_dir)}
    return {"available": True, "filename": path.name, "path": str(path)}


def load_resume_search_profile(*, force_refresh: bool = True) -> tuple[bool, str, list[str]]:
    """Parse latest résumé and write ``data/search_profile.json`` via LLM."""
    from agentzero.llm.provider import build_llm_provider

    try:
        path = find_latest_resume()
    except FileNotFoundError:
        return (
            False,
            f"No résumé in {RESUME_DIR}/ — add a .pdf, .docx, .txt, or .md file.",
            [],
        )

    try:
        llm = build_llm_provider()
    except ValueError as exc:
        if "Missing API key" in str(exc):
            return (
                False,
                "Missing LLM API key (OPENAI_API_KEY or ANTHROPIC_API_KEY).",
                [],
            )
        raise

    clear_search_profile_session_cache()
    profile = resolve_search_from_resume(
        llm=llm,
        force_refresh=force_refresh,
        prefer_snapshot=not force_refresh,
    )
    terms = list(profile.search_terms)
    msg = (
        f"Loaded {path.name}: {len(terms)} title(s), "
        f"{len(profile.locations)} location(s)."
    )
    return True, msg, terms


class ResumeLoader:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = ResumeLoadState()

    def start(self, operator_config_path: Path, *, force_refresh: bool = True) -> tuple[bool, str]:
        with self._lock:
            if self.state.running:
                return False, "Résumé load already in progress. Refresh shortly."
            self.state.running = True
            self.state.last_message = "Loading résumé and extracting search titles…"
            self.state.last_ok = None

        thread = threading.Thread(
            target=self._run,
            args=(operator_config_path, force_refresh),
            daemon=True,
            name="agentzero-web-resume-load",
        )
        thread.start()
        return True, "Loading résumé in the background. Refresh this page when finished."

    def _run(self, operator_config_path: Path, force_refresh: bool) -> None:
        try:
            ok, message, terms = load_resume_search_profile(force_refresh=force_refresh)
            if ok and terms:
                sync_operator_titles_after_resume_load(operator_config_path, terms)
            with self._lock:
                self.state.last_message = message
                self.state.last_ok = ok
                if ok:
                    info = latest_resume_info()
                    self.state.resume_file = info.get("filename")
                    self.state.title_count = len(terms)
        except Exception as exc:  # noqa: BLE001 — show in UI
            with self._lock:
                self.state.last_message = f"Résumé load failed: {exc}"
                self.state.last_ok = False
        finally:
            with self._lock:
                self.state.running = False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.state.to_dict()
