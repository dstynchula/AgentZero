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

    def _db(request: Request) -> Database:
        return request.app.state.db

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
                "job": detail,
                "job_id": job_id,
                "show_rejected": show_rejected,
                **ctx,
            },
        )

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
