"""FastAPI application for the Docker operator job tracker."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi import Path as FPath
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from agentzero.config import Settings, get_settings
from agentzero.generate.cover_letter import COVER_LETTER_DIR, save_cover_letter
from agentzero.models import ApplicationStatus, JobPosting
from agentzero.storage.db import Database
from agentzero.web.cdp_status import cdp_status_payload, retry_cdp_connection
from agentzero.web.chat.agent import run_agent_turn
from agentzero.web.chat.hitl import confirm_pending, reject_pending
from agentzero.web.chat.store import ChatStore
from agentzero.web.cover_letter_io import (
    cover_letter_download_filename,
    cover_letters_dir,
    load_cover_letter_text,
)
from agentzero.web.cover_letter_runner import CoverLetterRunner
from agentzero.web.display import build_list_query
from agentzero.web.jobs import (
    LIST_VIEW_DEFAULT_COLUMNS,
    UI_COLUMNS,
    job_detail_for_ui,
    jobs_for_table,
    list_context,
    list_jobs_for_ui,
)
from agentzero.web.legacy_redirect import (
    legacy_api_scraper_redirect_url,
    legacy_scraper_redirect_base,
    legacy_scraper_redirect_url,
    safe_flash_query,
)
from agentzero.web.mutations import (
    JobNotFoundError,
    reject_job,
    update_job_notes,
    update_job_status,
)
from agentzero.web.operator_config import (
    load_operator_config,
    normalize_source_selection,
    operator_config_path,
    patch_operator_config,
)
from agentzero.web.resume_loader import ResumeLoader, latest_resume_info
from agentzero.web.scrape_runner import ScrapeRunner
from agentzero.web.search_titles import (
    add_operator_title,
    merge_title_selection,
    remove_operator_title,
    search_profile_summary,
    title_rows,
)
from agentzero.web.sources import active_source_names, source_catalog

JobId = Annotated[str, FPath(pattern=r"^[a-f0-9]{16}$", min_length=16, max_length=16)]
ChatSessionId = Annotated[str, FPath(pattern=r"^[a-f0-9]{32}$", min_length=32, max_length=32)]

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
_STATUS_CHOICES = [status.value for status in ApplicationStatus]
_JOB_DETAIL_FLASH_KEYS = frozenset(
    {
        "cover_saved",
        "cover_started",
        "cover_ready",
        "cover_busy",
        "cover_fail",
        "status_saved",
        "notes_saved",
        "rejected",
    }
)


def create_app(
    *,
    db_path: Path | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Build the web app; inject *db_path* in tests."""
    cfg = settings or get_settings()
    path = db_path or cfg.db_path

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(path)
        app.state.db = database
        try:
            yield
        finally:
            database.close()

    app = FastAPI(title="AgentZero Job Tracker", lifespan=lifespan)
    app.state.settings = cfg
    app.state.operator_config_path = operator_config_path(path)
    app.state.scrape_runner = ScrapeRunner()
    app.state.resume_loader = ResumeLoader()
    app.state.cover_letter_runner = CoverLetterRunner()
    app.state.cover_letters_dir = COVER_LETTER_DIR

    def _db(request: Request) -> Database:
        return request.app.state.db

    def _chat(request: Request) -> ChatStore:
        return ChatStore(_db(request))

    def _operator(request: Request):
        return load_operator_config(request.app.state.operator_config_path)

    def _config_context(request: Request, *, flash: str = "", flash_ok: bool = True) -> dict:
        from agentzero.ingest.search_profile import load_search_profile

        settings: Settings = request.app.state.settings
        operator = _operator(request)
        snapshot = load_search_profile()
        profile_terms = list(snapshot.search_terms) if snapshot else []
        return {
            "nav_active": "scraper",
            "sources": source_catalog(settings, operator),
            "active_sources": active_source_names(settings, operator),
            "cdp": cdp_status_payload(settings, operator),
            "scrape": request.app.state.scrape_runner.snapshot(),
            "search_profile": search_profile_summary(snapshot),
            "title_rows": title_rows(profile_terms, operator),
            "resume": latest_resume_info(),
            "resume_load": request.app.state.resume_loader.snapshot(),
            "flash": flash,
            "flash_ok": flash_ok,
        }

    def _letters_dir(request: Request) -> Path:
        return cover_letters_dir(getattr(request.app.state, "cover_letters_dir", None))

    def _require_job(request: Request, job_id: JobId) -> JobPosting:
        job = _db(request).get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    def _redirect_job_detail(
        request: Request,
        job: JobPosting,
        show_rejected: bool,
        sort: str | None = None,
        order: str | None = None,
        *,
        flag: str | None = None,
        msg: str | None = None,
    ) -> RedirectResponse:
        from urllib.parse import parse_qsl, urlencode

        query_items: list[tuple[str, str]] = list(
            parse_qsl(build_list_query(show_rejected=show_rejected, sort=sort, order=order).lstrip("?"))
        )
        if flag:
            key, _, value = flag.partition("=")
            if key in _JOB_DETAIL_FLASH_KEYS:
                query_items.append((key, value or "1"))
        if msg:
            query_items.append(("msg", msg[:500]))
        url = str(request.url_for("job_detail", job_id=job.job_id))
        if query_items:
            url = f"{url}?{urlencode(query_items)}"
        return RedirectResponse(url=url, status_code=303)

    def _job_detail_flash(request: Request) -> tuple[str, bool]:
        params = request.query_params
        if params.get("cover_saved") == "1":
            return "Cover letter saved.", True
        if params.get("cover_started") == "1":
            return "Generating cover letter — refresh when finished.", True
        if params.get("cover_ready") == "1":
            return "Cover letter ready.", True
        if params.get("cover_busy") == "1":
            return "Cover letter generation already in progress.", False
        if params.get("cover_fail") == "1":
            return params.get("msg") or "Cover letter generation failed.", False
        if params.get("status_saved") == "1":
            return "Status updated.", True
        if params.get("notes_saved") == "1":
            return "Notes saved.", True
        if params.get("rejected") == "1":
            return "Marked as rejected.", True
        return "", True

    def _job_detail_context(
        request: Request,
        job: JobPosting,
        *,
        show_rejected: bool,
        sort: str | None,
        order: str | None,
    ) -> dict:
        flash, flash_ok = _job_detail_flash(request)
        letter_text = load_cover_letter_text(job, base_dir=_letters_dir(request))
        runner = request.app.state.cover_letter_runner.snapshot()
        return {
            **list_context(show_rejected=show_rejected, sort=sort, order=order),
            "flash": flash,
            "flash_ok": flash_ok,
            "status_choices": _STATUS_CHOICES,
            "cover_letter_text": letter_text or "",
            "has_cover_letter": letter_text is not None,
            "cover_letter_running": runner.get("running") and runner.get("job_id") == job.job_id,
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/chat/sessions")
    def api_chat_sessions(request: Request) -> list[dict[str, object]]:
        return [row.to_dict() for row in _chat(request).list_sessions()]

    @app.post("/api/chat/sessions")
    async def api_chat_create_session(request: Request) -> JSONResponse:
        body: dict[str, object] = {}
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                body = await request.json()
            except json.JSONDecodeError:
                body = {}
        title = str(body.get("title", "") or "")
        session_id = _chat(request).create_session(title=title)
        session = _chat(request).get_session(session_id)
        assert session is not None
        return JSONResponse(session.to_dict(), status_code=201)

    @app.get("/api/chat/sessions/{session_id}")
    def api_chat_session(request: Request, session_id: ChatSessionId) -> JSONResponse:
        store = _chat(request)
        session = store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        pending = store.get_pending_action(session_id)
        return JSONResponse(
            {
                **session.to_dict(),
                "messages": [msg.to_dict() for msg in store.list_messages(session_id)],
                "pending_action": pending.to_dict() if pending else None,
            }
        )

    @app.delete("/api/chat/sessions/{session_id}")
    def api_chat_delete_session(request: Request, session_id: ChatSessionId) -> JSONResponse:
        store = _chat(request)
        archived = store.archive_session(session_id)
        if not archived and not store.delete_session(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        return JSONResponse({"session_id": session_id, "archived": archived})

    @app.post("/api/chat/sessions/{session_id}/messages")
    async def api_chat_post_message(
        request: Request,
        session_id: ChatSessionId,
    ) -> JSONResponse:
        store = _chat(request)
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        if store.get_pending_action(session_id) is not None:
            raise HTTPException(
                status_code=409,
                detail="Resolve the pending action before sending another message.",
            )
        try:
            body = await request.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON body") from exc
        content = str(body.get("content", "") or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="content required")
        try:
            turn = run_agent_turn(
                store,
                session_id,
                content,
                db=_db(request),
                scrape_snapshot=request.app.state.scrape_runner.snapshot(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        pending = turn.pending_action or store.get_pending_action(session_id)
        return JSONResponse(
            {
                "assistant_text": turn.assistant_text,
                "pending_action": pending.to_dict() if pending else None,
            }
        )

    @app.post("/api/chat/sessions/{session_id}/confirm")
    def api_chat_confirm(request: Request, session_id: ChatSessionId) -> JSONResponse:
        store = _chat(request)
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        try:
            result = confirm_pending(
                store,
                session_id,
                db=_db(request),
                settings=request.app.state.settings,
                scrape_runner=request.app.state.scrape_runner,
                cover_letter_runner=request.app.state.cover_letter_runner,
                operator_config_path=request.app.state.operator_config_path,
                cover_letters_dir=_letters_dir(request),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (JobNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.post("/api/chat/sessions/{session_id}/reject")
    def api_chat_reject_pending(request: Request, session_id: ChatSessionId) -> JSONResponse:
        store = _chat(request)
        if store.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        try:
            result = reject_pending(store, session_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return JSONResponse(result)

    @app.get("/", response_class=HTMLResponse)
    def chat_page(request: Request) -> HTMLResponse:
        return _TEMPLATES.TemplateResponse(
            request,
            "chat.html",
            {"nav_active": "chat"},
        )

    @app.get("/api/jobs")
    def api_jobs(
        request: Request,
        include_rejected: bool = Query(default=False),
        sort: str | None = Query(default=None),
        order: str | None = Query(default=None),
    ) -> list[dict[str, object]]:
        return list_jobs_for_ui(
            _db(request),
            include_rejected=include_rejected,
            sort=sort,
            order=order,
        )

    @app.get("/jobs", response_class=HTMLResponse, name="jobs_list")
    def jobs_list(
        request: Request,
        show_rejected: bool = Query(default=False),
        sort: str | None = Query(default=None),
        order: str | None = Query(default=None),
    ) -> HTMLResponse:
        ctx = list_context(show_rejected=show_rejected, sort=sort, order=order)
        jobs = jobs_for_table(
            _db(request),
            include_rejected=show_rejected,
            sort=sort,
            order=order,
        )
        return _TEMPLATES.TemplateResponse(
            request,
            "jobs.html",
            {
                "nav_active": "jobs",
                "jobs": jobs,
                "columns": UI_COLUMNS,
                "default_columns": LIST_VIEW_DEFAULT_COLUMNS,
                "tracker_column_config_json": json.dumps(
                    {
                        "all": list(UI_COLUMNS),
                        "default": list(LIST_VIEW_DEFAULT_COLUMNS),
                    }
                ),
                "status_choices": _STATUS_CHOICES,
                "show_rejected": show_rejected,
                **ctx,
            },
        )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse, name="job_detail")
    def job_detail(
        request: Request,
        job_id: JobId,
        show_rejected: bool = Query(default=False),
        sort: str | None = Query(default=None),
        order: str | None = Query(default=None),
    ) -> HTMLResponse:
        job = _require_job(request, job_id)
        detail = job_detail_for_ui(_db(request), job_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="job not found")
        return _TEMPLATES.TemplateResponse(
            request,
            "job_card.html",
            {
                "nav_active": "jobs",
                "job": detail,
                "job_id": job.job_id,
                "show_rejected": show_rejected,
                **_job_detail_context(
                    request,
                    job,
                    show_rejected=show_rejected,
                    sort=sort,
                    order=order,
                ),
            },
        )

    @app.get("/scraper", response_class=HTMLResponse)
    def scraper_page(request: Request) -> HTMLResponse:
        flash = ""
        flash_ok = True
        params = request.query_params
        if params.get("saved") == "1":
            flash = "Sources saved."
        elif params.get("titles_saved") == "1":
            flash = "Search titles saved."
        elif params.get("title_added") == "1":
            flash = "Search title added."
        elif params.get("title_removed") == "1":
            flash = "Search title removed."
        elif params.get("cdp_ok") == "1":
            flash = params.get("msg") or "Chrome CDP connected."
        elif params.get("cdp_fail") == "1":
            flash = params.get("msg") or "Could not connect to Chrome CDP."
            flash_ok = False
        elif params.get("scrape_started") == "1":
            flash = "Background scrape started."
        elif params.get("scrape_busy") == "1":
            flash = "A scrape is already running."
            flash_ok = False
        elif params.get("resume_loading") == "1":
            flash = "Loading résumé in the background. Refresh when complete."
        elif params.get("resume_busy") == "1":
            flash = "A résumé load is already in progress."
            flash_ok = False
        return _TEMPLATES.TemplateResponse(
            request,
            "config.html",
            _config_context(request, flash=flash, flash_ok=flash_ok),
        )

    @app.get("/api/scraper")
    def api_scraper(request: Request) -> dict[str, object]:
        ctx = _config_context(request)
        return {
            "sources": [row.to_dict() for row in ctx["sources"]],
            "active_sources": ctx["active_sources"],
            "cdp": ctx["cdp"],
            "launch_commands": ctx["cdp"]["launch_commands"],
            "scrape": ctx["scrape"],
            "search_profile": ctx["search_profile"],
        }

    @app.post("/scraper/sources", response_model=None)
    def post_scraper_sources(
        request: Request,
        browser_sites: Annotated[list[str] | None, Form()] = None,
        jobspy_sites: Annotated[list[str] | None, Form()] = None,
    ):
        cfg_path = request.app.state.operator_config_path
        normalized = normalize_source_selection(
            browser_sites or [],
            jobspy_sites or [],
        )
        if not normalized.scrape_browser_sites and not normalized.scrape_sites:
            return _TEMPLATES.TemplateResponse(
                request,
                "config.html",
                _config_context(
                    request,
                    flash="Enable at least one source.",
                    flash_ok=False,
                ),
                status_code=400,
            )
        patch_operator_config(
            cfg_path,
            scrape_browser_sites=normalized.scrape_browser_sites,
            scrape_sites=normalized.scrape_sites,
        )
        return RedirectResponse(url="/scraper?saved=1", status_code=303)

    @app.post("/scraper/resume/load", response_model=None)
    def post_scraper_resume_load(request: Request) -> RedirectResponse:
        ok, _message = request.app.state.resume_loader.start(
            request.app.state.operator_config_path,
            force_refresh=True,
        )
        query = "resume_loading=1" if ok else "resume_busy=1"
        return RedirectResponse(url=f"/scraper?{query}", status_code=303)

    @app.post("/scraper/search-titles", response_model=None)
    def post_scraper_search_titles(
        request: Request,
        search_terms: Annotated[list[str] | None, Form()] = None,
    ):
        from agentzero.ingest.search_profile import load_search_profile

        cfg_path = request.app.state.operator_config_path
        snapshot = load_search_profile()
        if snapshot is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "config.html",
                _config_context(
                    request,
                    flash="Load a résumé first (Search titles → Load résumé).",
                    flash_ok=False,
                ),
                status_code=400,
            )
        profile_terms = list(snapshot.search_terms)
        operator = _operator(request)
        terms = merge_title_selection(
            search_terms or [],
            profile_terms,
            operator,
        )
        if not terms:
            return _TEMPLATES.TemplateResponse(
                request,
                "config.html",
                _config_context(
                    request,
                    flash="Select at least one search title.",
                    flash_ok=False,
                ),
                status_code=400,
            )
        patch_operator_config(cfg_path, search_terms=terms)
        return RedirectResponse(url="/scraper?titles_saved=1", status_code=303)

    @app.post("/scraper/search-titles/add", response_model=None)
    def post_scraper_search_titles_add(
        request: Request,
        term: Annotated[str, Form()] = "",
    ) -> RedirectResponse | HTMLResponse:
        from agentzero.ingest.search_profile import load_search_profile

        cfg_path = request.app.state.operator_config_path
        snapshot = load_search_profile()
        if snapshot is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "config.html",
                _config_context(
                    request,
                    flash="Load a résumé first (Search titles → Load résumé).",
                    flash_ok=False,
                ),
                status_code=400,
            )
        try:
            add_operator_title(
                cfg_path,
                term,
                profile_terms=list(snapshot.search_terms),
            )
        except ValueError:
            return _TEMPLATES.TemplateResponse(
                request,
                "config.html",
                _config_context(
                    request,
                    flash="Enter a title to add.",
                    flash_ok=False,
                ),
                status_code=400,
            )
        return RedirectResponse(url="/scraper?title_added=1", status_code=303)

    @app.post("/scraper/search-titles/remove", response_model=None)
    def post_scraper_search_titles_remove(
        request: Request,
        term: Annotated[str, Form()] = "",
    ) -> RedirectResponse | HTMLResponse:
        from agentzero.ingest.search_profile import load_search_profile

        cfg_path = request.app.state.operator_config_path
        snapshot = load_search_profile()
        if snapshot is None:
            return _TEMPLATES.TemplateResponse(
                request,
                "config.html",
                _config_context(
                    request,
                    flash="Load a résumé first.",
                    flash_ok=False,
                ),
                status_code=400,
            )
        try:
            remove_operator_title(
                cfg_path,
                term,
                profile_terms=list(snapshot.search_terms),
            )
        except ValueError:
            return _TEMPLATES.TemplateResponse(
                request,
                "config.html",
                _config_context(
                    request,
                    flash="Missing title to remove.",
                    flash_ok=False,
                ),
                status_code=400,
            )
        return RedirectResponse(url="/scraper?title_removed=1", status_code=303)

    @app.post("/scraper/cdp/connect", response_model=None)
    def post_scraper_cdp_connect(request: Request) -> RedirectResponse:
        settings: Settings = request.app.state.settings
        ok, message = retry_cdp_connection(settings, _operator(request))
        from urllib.parse import quote

        q = "cdp_ok=1" if ok else "cdp_fail=1"
        return RedirectResponse(
            url=f"/scraper?{q}&msg={quote(message)}",
            status_code=303,
        )

    @app.post("/scraper/scrape", response_model=None)
    def post_scraper_scrape(request: Request) -> RedirectResponse:
        ok, _message = request.app.state.scrape_runner.start(
            db=_db(request),
            settings=request.app.state.settings,
            operator=_operator(request),
        )
        query = "scrape_started=1" if ok else "scrape_busy=1"
        return RedirectResponse(url=f"/scraper?{query}", status_code=303)

    @app.get("/config", include_in_schema=False)
    @app.get("/config/", include_in_schema=False)
    def redirect_config_root(request: Request) -> RedirectResponse:
        return RedirectResponse(
            url=legacy_scraper_redirect_url(request),
            status_code=307,
        )

    @app.get("/config/{path:path}", include_in_schema=False)
    def redirect_config_get(request: Request, path: str) -> RedirectResponse:
        base = legacy_scraper_redirect_base(path)
        return RedirectResponse(url=base + safe_flash_query(request), status_code=307)

    @app.post("/config/{path:path}", include_in_schema=False)
    def redirect_config_post(request: Request, path: str) -> RedirectResponse:
        base = legacy_scraper_redirect_base(path)
        return RedirectResponse(url=base + safe_flash_query(request), status_code=307)

    @app.get("/api/config", include_in_schema=False)
    def redirect_api_config(request: Request) -> RedirectResponse:
        return RedirectResponse(
            url=legacy_api_scraper_redirect_url(request),
            status_code=307,
        )

    def _redirect_index(
        show_rejected: bool,
        sort: str | None = None,
        order: str | None = None,
    ) -> RedirectResponse:
        query = build_list_query(show_rejected=show_rejected, sort=sort, order=order)
        return RedirectResponse(url=f"/jobs{query}", status_code=303)

    def _apply_status(request: Request, job_id: JobId, status: str) -> JobPosting:
        try:
            return update_job_status(_db(request), job_id, status)
        except JobNotFoundError:
            raise HTTPException(status_code=404, detail="job not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/jobs/{job_id}/status", response_model=None)
    def post_status_html(
        request: Request,
        job_id: JobId,
        status: Annotated[str, Form()],
        show_rejected: Annotated[bool, Form()] = False,
        sort: Annotated[str, Form()] = "",
        order: Annotated[str, Form()] = "",
        return_to: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        job = _apply_status(request, job_id, status)
        if return_to == "detail":
            return _redirect_job_detail(
                request,
                job,
                show_rejected,
                sort=sort or None,
                order=order or None,
                flag="status_saved=1",
            )
        return _redirect_index(show_rejected, sort=sort or None, order=order or None)

    @app.post("/api/jobs/{job_id}/status", response_model=None)
    def post_status_api(
        request: Request,
        job_id: JobId,
        status: Annotated[str, Form()],
    ) -> JSONResponse:
        _apply_status(request, job_id, status)
        return JSONResponse({"job_id": job_id, "status": status})

    def _apply_notes(request: Request, job_id: JobId, notes: str) -> str:
        try:
            update_job_notes(_db(request), job_id, notes)
        except JobNotFoundError:
            raise HTTPException(status_code=404, detail="job not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return notes.strip()

    @app.post("/jobs/{job_id}/notes", response_model=None)
    def post_notes_html(
        request: Request,
        job_id: JobId,
        notes: Annotated[str, Form()] = "",
        show_rejected: Annotated[bool, Form()] = False,
        sort: Annotated[str, Form()] = "",
        order: Annotated[str, Form()] = "",
        return_to: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        _apply_notes(request, job_id, notes)
        job = _require_job(request, job_id)
        if return_to == "detail":
            return _redirect_job_detail(
                request,
                job,
                show_rejected,
                sort=sort or None,
                order=order or None,
                flag="notes_saved=1",
            )
        return _redirect_index(show_rejected, sort=sort or None, order=order or None)

    @app.post("/api/jobs/{job_id}/notes", response_model=None)
    def post_notes_api(
        request: Request,
        job_id: JobId,
        notes: Annotated[str, Form()] = "",
    ) -> JSONResponse:
        cleaned = _apply_notes(request, job_id, notes)
        return JSONResponse({"job_id": job_id, "notes": cleaned})

    def _apply_reject(request: Request, job_id: JobId) -> JobPosting:
        try:
            return reject_job(_db(request), job_id)
        except JobNotFoundError:
            raise HTTPException(status_code=404, detail="job not found") from None

    @app.post("/jobs/{job_id}/reject", response_model=None)
    def post_reject_html(
        request: Request,
        job_id: JobId,
        show_rejected: Annotated[bool, Form()] = False,
        sort: Annotated[str, Form()] = "",
        order: Annotated[str, Form()] = "",
        return_to: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        job = _apply_reject(request, job_id)
        if return_to == "detail":
            return _redirect_job_detail(
                request,
                job,
                show_rejected,
                sort=sort or None,
                order=order or None,
                flag="rejected=1",
            )
        return _redirect_index(show_rejected, sort=sort or None, order=order or None)

    @app.post("/jobs/{job_id}/cover-letter/generate", response_model=None)
    def post_cover_letter_generate(
        request: Request,
        job_id: JobId,
        show_rejected: Annotated[bool, Form()] = False,
        sort: Annotated[str, Form()] = "",
        order: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        job = _require_job(request, job_id)
        ok, message = request.app.state.cover_letter_runner.start(
            db=_db(request),
            settings=request.app.state.settings,
            job_id=job.job_id,
            cover_letters_dir=_letters_dir(request),
        )
        if ok:
            return _redirect_job_detail(
                request,
                job,
                show_rejected,
                sort=sort or None,
                order=order or None,
                flag="cover_started=1",
            )
        return _redirect_job_detail(
            request,
            job,
            show_rejected,
            sort=sort or None,
            order=order or None,
            flag="cover_busy=1",
            msg=message,
        )

    @app.post("/jobs/{job_id}/cover-letter/save", response_model=None)
    def post_cover_letter_save(
        request: Request,
        job_id: JobId,
        text: Annotated[str, Form()] = "",
        show_rejected: Annotated[bool, Form()] = False,
        sort: Annotated[str, Form()] = "",
        order: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        job = _require_job(request, job_id)
        try:
            save_cover_letter(job, text, base_dir=_letters_dir(request))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _redirect_job_detail(
            request,
            job,
            show_rejected,
            sort=sort or None,
            order=order or None,
            flag="cover_saved=1",
        )

    @app.get("/jobs/{job_id}/cover-letter/download")
    def get_cover_letter_download(request: Request, job_id: JobId) -> FileResponse:
        from agentzero.generate.cover_letter import cover_letter_path

        job = _require_job(request, job_id)
        path = cover_letter_path(job, base_dir=_letters_dir(request))
        if not path.is_file():
            raise HTTPException(status_code=404, detail="cover letter not found")
        filename = cover_letter_download_filename(job)
        return FileResponse(
            path,
            media_type="text/plain; charset=utf-8",
            filename=filename,
        )

    @app.get("/api/jobs/{job_id}/cover-letter")
    def api_cover_letter_status(request: Request, job_id: JobId) -> JSONResponse:
        job = _require_job(request, job_id)
        runner = request.app.state.cover_letter_runner.snapshot()
        text = load_cover_letter_text(job, base_dir=_letters_dir(request))
        payload: dict[str, object] = {
            "job_id": job.job_id,
            "running": bool(runner.get("running") and runner.get("job_id") == job.job_id),
            "ok": runner.get("ok"),
            "message": runner.get("message") or "",
            "text": text,
        }
        return JSONResponse(payload)

    @app.post("/api/jobs/{job_id}/reject", response_model=None)
    def post_reject_api(request: Request, job_id: JobId) -> JSONResponse:
        _apply_reject(request, job_id)
        return JSONResponse({"job_id": job_id, "status": ApplicationStatus.REJECTED.value})

    return app
