"""Sync SQLite jobs to Google Sheets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentzero.google.auth import SHEETS_SCOPES, load_credentials
from agentzero.google.client import authorize_gspread
from agentzero.google.sheets import SheetsSync

if TYPE_CHECKING:
    from agentzero.config import Settings
    from agentzero.storage.db import Database


@dataclass(frozen=True, slots=True)
class PrunePlan:
    spreadsheet_title: str
    sheet_job_count: int
    db_job_count: int
    to_delete: list[str]
    missing_in_db: list[str]


def _sheets_sync(settings: Settings, scopes: list[str] | None = None) -> tuple:
    from agentzero.google.client import open_spreadsheet

    creds = load_credentials(
        client_secret_path=settings.google_client_secret,
        token_path=settings.google_token_path,
        scopes=scopes or SHEETS_SCOPES,
    )
    client = authorize_gspread(creds)
    spreadsheet = open_spreadsheet(creds, settings.sheet_id)
    sync = SheetsSync(client, settings.sheet_id)
    return sync, spreadsheet


@dataclass(frozen=True, slots=True)
class SheetSyncResult:
    row_count: int
    spreadsheet_title: str
    imported: int
    created: int
    skipped_unknown_job_id: int


def sync_jobs_to_sheet(
    *,
    db: Database,
    settings: Settings | None = None,
    scopes: list[str] | None = None,
    import_user_fields: bool = True,
) -> SheetSyncResult:
    """Push all jobs from ``db`` to the configured Google Sheet.

    When ``import_user_fields`` is true (default), human-edited columns
    (``date_applied``, ``status``, etc.) are read from the sheet into SQLite
    before the worksheet is rewritten.
    """
    from agentzero.config import get_settings

    cfg = settings or get_settings()
    if not cfg.sheet_id:
        raise ValueError(
            "AGENTZERO_SHEET_ID is not set. Add your spreadsheet ID to .env."
        )

    sync, spreadsheet = _sheets_sync(cfg, scopes)
    count, import_result = sync.sync(
        db,
        import_user_fields=import_user_fields,
        search_terms=cfg.search_terms,
        min_match_score=cfg.min_match_score,
    )
    return SheetSyncResult(
        row_count=count,
        spreadsheet_title=spreadsheet.title,
        imported=import_result.updated + import_result.created,
        created=import_result.created,
        skipped_unknown_job_id=import_result.skipped_unknown_job_id,
    )


def plan_prune_db_to_sheet(
    *,
    db: Database,
    settings: Settings | None = None,
    scopes: list[str] | None = None,
) -> PrunePlan:
    """Return DB job IDs that would be removed to match the sheet."""
    from agentzero.config import get_settings

    cfg = settings or get_settings()
    if not cfg.sheet_id:
        raise ValueError(
            "AGENTZERO_SHEET_ID is not set. Add your spreadsheet ID to .env."
        )

    sync, spreadsheet = _sheets_sync(cfg, scopes)
    sheet_ids = sync.read_job_ids()
    db_ids = set(db.list_job_ids())
    to_delete = sorted(db_ids - sheet_ids)
    missing_in_db = sorted(sheet_ids - db_ids)
    return PrunePlan(
        spreadsheet_title=spreadsheet.title,
        sheet_job_count=len(sheet_ids),
        db_job_count=len(db_ids),
        to_delete=to_delete,
        missing_in_db=missing_in_db,
    )


def prune_db_to_sheet(
    *,
    db: Database,
    settings: Settings | None = None,
    scopes: list[str] | None = None,
) -> tuple[int, int, str]:
    """Delete DB jobs that are not present in the Google Sheet.

    Returns ``(kept_count, deleted_count, spreadsheet_title)``.
    """
    plan = plan_prune_db_to_sheet(db=db, settings=settings, scopes=scopes)
    deleted = db.delete_jobs(plan.to_delete)
    kept = plan.sheet_job_count - len(plan.missing_in_db)
    return kept, deleted, plan.spreadsheet_title
