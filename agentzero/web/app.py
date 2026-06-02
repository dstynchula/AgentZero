"""FastAPI application for the Docker operator job tracker."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from agentzero.config import Settings, get_settings
from agentzero.models import ApplicationStatus
from agentzero.storage.db import Database
from agentzero.web.cdp_status import cdp_status_payload, retry_cdp_connection
from agentzero.web.display import build_list_query
from agentzero.web.jobs import (
    UI_COLUMNS,
    job_detail_for_ui,
    jobs_for_table,
    list_context,
    list_jobs_for_ui,
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
    normalize_title_selection,
    search_profile_summary,
    title_rows,
)
from agentzero.web.sources import active_source_names, source_catalog

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
_STATUS_CHOICES = [status.value for status in ApplicationStatus]


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

    def _db(request: Request) -> Database:
        return request.app.state.db

    def _operator(request: Request):
        return load_operator_config(request.app.state.operator_config_path)

    def _config_context(request: Request, *, flash: str = "", flash_ok: bool = True) -> dict:
        from agentzero.ingest.search_profile import load_search_profile

        settings: Settings = request.app.state.settings
        operator = _operator(request)
        snapshot = load_search_profile()
        profile_terms = list(snapshot.search_terms) if snapshot else []
        return {
            "nav_active": "config",
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

    @app.get("/", response_class=HTMLResponse)
    def index(
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
                "status_choices": _STATUS_CHOICES,
                "show_rejected": show_rejected,
                **ctx,
            },
        )

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_detail(
        request: Request,
        job_id: str,
        show_rejected: bool = Query(default=False),
        sort: str | None = Query(default=None),
        order: str | None = Query(default=None),
    ) -> HTMLResponse:
        detail = job_detail_for_ui(_db(request), job_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="job not found")
        ctx = list_context(show_rejected=show_rejected, sort=sort, order=order)
        return _TEMPLATES.TemplateResponse(
            request,
            "job_card.html",
            {
                "nav_active": "jobs",
                "job": detail,
                "job_id": job_id,
                "show_rejected": show_rejected,
                **ctx,
            },
        )

    @app.get("/config", response_class=HTMLResponse)
    def config_page(request: Request) -> HTMLResponse:
        flash = ""
        flash_ok = True
        params = request.query_params
        if params.get("saved") == "1":
            flash = "Sources saved."
        elif params.get("titles_saved") == "1":
            flash = "Search titles saved."
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

    @app.get("/api/config")
    def api_config(request: Request) -> dict[str, object]:
        ctx = _config_context(request)
        return {
            "sources": [row.to_dict() for row in ctx["sources"]],
            "active_sources": ctx["active_sources"],
            "cdp": ctx["cdp"],
            "launch_commands": ctx["cdp"]["launch_commands"],
            "scrape": ctx["scrape"],
            "search_profile": ctx["search_profile"],
        }

    @app.post("/config/sources", response_model=None)
    def post_config_sources(
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
        return RedirectResponse(url="/config?saved=1", status_code=303)

    @app.post("/config/resume/load", response_model=None)
    def post_config_resume_load(request: Request) -> RedirectResponse:
        ok, _message = request.app.state.resume_loader.start(
            request.app.state.operator_config_path,
            force_refresh=True,
        )
        query = "resume_loading=1" if ok else "resume_busy=1"
        return RedirectResponse(url=f"/config?{query}", status_code=303)

    @app.post("/config/search-titles", response_model=None)
    def post_config_search_titles(
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
        terms = normalize_title_selection(
            search_terms or [],
            list(snapshot.search_terms),
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
        return RedirectResponse(url="/config?titles_saved=1", status_code=303)

    @app.post("/config/cdp/connect", response_model=None)
    def post_config_cdp_connect(request: Request) -> RedirectResponse:
        settings: Settings = request.app.state.settings
        ok, message = retry_cdp_connection(settings, _operator(request))
        from urllib.parse import quote

        q = "cdp_ok=1" if ok else "cdp_fail=1"
        return RedirectResponse(
            url=f"/config?{q}&msg={quote(message)}",
            status_code=303,
        )

    @app.post("/config/scrape", response_model=None)
    def post_config_scrape(request: Request) -> RedirectResponse:
        ok, _message = request.app.state.scrape_runner.start(
            db=_db(request),
            settings=request.app.state.settings,
            operator=_operator(request),
        )
        query = "scrape_started=1" if ok else "scrape_busy=1"
        return RedirectResponse(url=f"/config?{query}", status_code=303)

    def _redirect_index(
        show_rejected: bool,
        sort: str | None = None,
        order: str | None = None,
    ) -> RedirectResponse:
        query = build_list_query(show_rejected=show_rejected, sort=sort, order=order)
        return RedirectResponse(url=f"/{query}", status_code=303)

    def _apply_status(request: Request, job_id: str, status: str) -> None:
        try:
            update_job_status(_db(request), job_id, status)
        except JobNotFoundError:
            raise HTTPException(status_code=404, detail="job not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/jobs/{job_id}/status", response_model=None)
    def post_status_html(
        request: Request,
        job_id: str,
        status: Annotated[str, Form()],
        show_rejected: Annotated[bool, Form()] = False,
        sort: Annotated[str, Form()] = "",
        order: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        _apply_status(request, job_id, status)
        return _redirect_index(show_rejected, sort=sort or None, order=order or None)

    @app.post("/api/jobs/{job_id}/status", response_model=None)
    def post_status_api(
        request: Request,
        job_id: str,
        status: Annotated[str, Form()],
    ) -> JSONResponse:
        _apply_status(request, job_id, status)
        return JSONResponse({"job_id": job_id, "status": status})

    def _apply_notes(request: Request, job_id: str, notes: str) -> str:
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
        job_id: str,
        notes: Annotated[str, Form()] = "",
        show_rejected: Annotated[bool, Form()] = False,
        sort: Annotated[str, Form()] = "",
        order: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        _apply_notes(request, job_id, notes)
        return _redirect_index(show_rejected, sort=sort or None, order=order or None)

    @app.post("/api/jobs/{job_id}/notes", response_model=None)
    def post_notes_api(
        request: Request,
        job_id: str,
        notes: Annotated[str, Form()] = "",
    ) -> JSONResponse:
        cleaned = _apply_notes(request, job_id, notes)
        return JSONResponse({"job_id": job_id, "notes": cleaned})

    def _apply_reject(request: Request, job_id: str) -> None:
        try:
            reject_job(_db(request), job_id)
        except JobNotFoundError:
            raise HTTPException(status_code=404, detail="job not found") from None

    @app.post("/jobs/{job_id}/reject", response_model=None)
    def post_reject_html(
        request: Request,
        job_id: str,
        show_rejected: Annotated[bool, Form()] = False,
        sort: Annotated[str, Form()] = "",
        order: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        _apply_reject(request, job_id)
        return _redirect_index(show_rejected, sort=sort or None, order=order or None)

    @app.post("/api/jobs/{job_id}/reject", response_model=None)
    def post_reject_api(request: Request, job_id: str) -> JSONResponse:
        _apply_reject(request, job_id)
        return JSONResponse({"job_id": job_id, "status": ApplicationStatus.REJECTED.value})

    return app
