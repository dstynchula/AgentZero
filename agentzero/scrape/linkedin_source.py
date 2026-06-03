"""JobSource adapter delegating LinkedIn scrape to LinkedInJobsService."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from agentzero.scrape.base import JobSource
from agentzero.scrape.linkedin_jobs import LinkedInJobsService

if TYPE_CHECKING:
    from agentzero.config import Settings

log = logging.getLogger(__name__)


class LinkedInFetchError(RuntimeError):
    """LinkedIn browser fetch produced no rows (login, error, or empty parse)."""


class LinkedInJobSource(JobSource):
    """Single-board LinkedIn fetch via shared Playwright service."""

    name = "linkedin_browser"

    def __init__(
        self,
        settings: Settings,
        *,
        input_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._service = LinkedInJobsService(settings, input_fn=input_fn)

    def fetch(self, *, progress: object | None = None) -> Sequence[dict]:
        result = self._service.search(progress=progress)
        if result.parsed_raw and result.after_title_filter is not None:
            dropped = result.parsed_raw - result.after_title_filter
            if dropped:
                log.info(
                    "LinkedIn: dropped %d off-topic title(s) (parsed=%d kept=%d)",
                    dropped,
                    result.parsed_raw,
                    result.after_title_filter,
                )
        log.info(
            "LinkedIn: %d rows (parsed_raw=%s after_filter=%s markers=%s session=%s)",
            len(result.records),
            result.parsed_raw,
            result.after_title_filter,
            result.has_job_markers,
            result.session_state,
        )

        if result.records:
            return result.records

        if result.login_required:
            from agentzero.scrape.browser_session import SessionState, session_status_message

            msg = session_status_message("linkedin", SessionState.LOGIN_REQUIRED)
            print(msg, file=sys.stderr)
            raise LinkedInFetchError(msg)

        if result.error:
            msg = f"LinkedIn search failed: {result.error}"
            print(msg, file=sys.stderr)
            raise LinkedInFetchError(msg)

        msg = (
            "LinkedIn returned 0 listings after filters. "
            "Run: python scripts/debug_linkedin_search.py --live "
            "(see docs/SCRAPING.md). Check session with "
            "python scripts/verify_browser_session.py --site linkedin"
        )
        print(msg, file=sys.stderr)
        raise LinkedInFetchError(msg)
