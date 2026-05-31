"""Interactive search targeting before each scrape run."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from agentzero.config import Settings
from agentzero.ingest.search_profile import (
    ResumeSearchProfile,
    apply_search_profile,
    resolve_search_from_resume,
    save_search_profile,
)
from agentzero.ingest.work_mode import (
    apply_work_mode_selection,
    format_work_mode_summary,
    infer_default_work_mode,
    parse_work_mode,
    selection_from_work_mode,
)

if TYPE_CHECKING:
    from agentzero.llm.provider import LLMProvider

InputFn = Callable[[str], str]

_CONFIRM_WORD = "yes"


def stdin_is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def require_interactive_terminal() -> None:
    """Raise when search prompts cannot read from a real terminal."""
    if stdin_is_interactive():
        return
    raise RuntimeError(
        "Interactive search prompt requires a real terminal (stdin/stdout TTY).\n"
        "Open the Cursor terminal (Terminal → New Terminal) and run:\n"
        "  python scripts/run_scrape.py --limit 25"
    )


def await_search_prompt_ack(*, input_fn: InputFn | None = None) -> None:
    """Block until the user explicitly acknowledges the search review step."""
    banner = "!" * 60
    print(f"\n{banner}", flush=True)
    print("STOP — review search targets before scraping begins.", flush=True)
    print(banner, flush=True)

    if input_fn is not None:
        input_fn("Press Enter to open search prompts… ")
        return

    require_interactive_terminal()

    if sys.platform == "win32":
        try:
            import msvcrt
        except ImportError as exc:
            raise RuntimeError("Could not load msvcrt for interactive prompt on Windows.") from exc
        print("Press any key to open search prompts… ", flush=True)
        msvcrt.getwch()
        print(flush=True)
        return

    _read_with_eof_guard("Press Enter to open search prompts… ", input_fn=_default_input)


def _read_with_eof_guard(prompt: str, *, input_fn: InputFn) -> str:
    started = time.monotonic()
    try:
        value = input_fn(prompt)
    except EOFError as exc:
        raise RuntimeError(
            "Could not read input for the search prompt. "
            "Run scripts/run_scrape.py from an interactive terminal."
        ) from exc
    if value == "" and (time.monotonic() - started) < 0.05:
        raise RuntimeError(
            "Search prompt skipped — stdin is not interactive (empty read). "
            "Run from a real terminal: python scripts/run_scrape.py"
        )
    return value


def _default_input(prompt: str) -> str:
    require_interactive_terminal()
    sys.stdout.write(prompt)
    sys.stdout.flush()
    started = time.monotonic()
    try:
        line = sys.stdin.readline()
    except EOFError as exc:
        raise RuntimeError(
            "Could not read input for the search prompt. "
            "Run scripts/run_scrape.py from an interactive terminal."
        ) from exc
    if line == "" and (time.monotonic() - started) < 0.05:
        raise RuntimeError(
            "Search prompt skipped — stdin is not interactive (empty read). "
            "Run from a real terminal: python scripts/run_scrape.py"
        )
    return line.rstrip("\n\r")


def _split_csv(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _parse_optional_float(text: str) -> float | None:
    cleaned = text.strip().replace(",", "").replace("$", "")
    if not cleaned:
        return None
    value = float(cleaned)
    if value < 0:
        raise ValueError("salary must be non-negative")
    return value


def format_search_summary(profile: ResumeSearchProfile) -> str:
    """Human-readable summary of search targets."""
    lines = [
        "Suggested from your résumé:",
        f"  Titles:    {', '.join(profile.search_terms)}",
    ]
    if profile.remote_preferred or (
        profile.locations and all("remote" in loc.lower() for loc in profile.locations)
    ):
        lines.append("  Work mode: Remote (USA)")
    elif profile.locations:
        lines.append(f"  Work mode: In-office - {', '.join(profile.locations)}")
    else:
        lines.append("  Work mode: (not set)")
    if profile.salary_min is not None:
        lines.append(
            f"  Comp floor: ${profile.salary_min:,.0f} USD/year "
            f"(keep roles whose posted range reaches at least this)"
        )
    else:
        lines.append("  Comp floor: (not set — all comp ranges kept)")
    if profile.remote_preferred:
        lines.append("  Remote:    preferred")
    return "\n".join(lines)


def _require_scrape_confirmation(read: InputFn) -> None:
    """Require explicit YES — empty Enter is not enough to start scraping."""
    while True:
        answer = read(f"\nType {_CONFIRM_WORD.upper()} to start scraping (or n to cancel): ").strip().lower()
        if answer == _CONFIRM_WORD:
            return
        if answer in {"n", "no"}:
            raise KeyboardInterrupt("Search run cancelled by user")
        print(f"Please type {_CONFIRM_WORD.upper()} to confirm, or n to cancel.", flush=True)


def interactive_refine_search_profile(
    profile: ResumeSearchProfile,
    *,
    interactive: bool = True,
    input_fn: InputFn | None = None,
    save_snapshot: bool = True,
    resume_dir=None,
    remote_only: bool = False,
) -> ResumeSearchProfile:
    """Let the user confirm or edit titles, locations, and salary for this run."""
    if not interactive:
        if remote_only:
            return apply_work_mode_selection(profile, selection_from_work_mode("remote"))
        return profile

    from agentzero.ingest.resume import RESUME_DIR

    read = input_fn or _default_input
    await_search_prompt_ack(input_fn=input_fn)

    print("\n" + "=" * 60, flush=True)
    print("Target this search run", flush=True)
    print("=" * 60, flush=True)
    print(format_search_summary(profile), flush=True)
    print(flush=True)
    print("Press Enter to keep a suggestion, or type new values.", flush=True)
    print("Examples: titles=Staff Security Engineer, Principal Security Engineer", flush=True)
    print("          work mode: R=Remote USA, I=In-office then enter cities", flush=True)
    print(flush=True)

    titles_raw = read(
        f"Job titles [{', '.join(profile.search_terms)}]: "
    ).strip()

    default_mode = "remote" if remote_only else infer_default_work_mode(profile)
    default_label = "Remote (USA)" if default_mode == "remote" else "In-office"
    if remote_only:
        mode = "remote"
        selection = selection_from_work_mode("remote")
        print(format_work_mode_summary(selection), flush=True)
    else:
        mode_raw = read(f"Remote or In-office? [R/i] (default {default_label}): ").strip()
        mode = parse_work_mode(mode_raw, default=default_mode)

        if mode == "remote":
            selection = selection_from_work_mode("remote")
        else:
            default_locs = ", ".join(
                loc for loc in profile.locations if "remote" not in loc.lower()
            ) or "Los Angeles, CA"
            office_raw = read(f"Office locations (comma-separated) [{default_locs}]: ").strip()
            office = _split_csv(office_raw) if office_raw else _split_csv(default_locs)
            selection = selection_from_work_mode("in_office", office_locations=office)

        print(format_work_mode_summary(selection), flush=True)

    floor_default = (
        f"{int(profile.salary_min):,}" if profile.salary_min is not None else "(none)"
    )
    floor_raw = read(
        f"Minimum acceptable salary USD/year "
        f"(posted range top must reach this; none=off) [{floor_default}]: "
    ).strip()

    search_terms = _split_csv(titles_raw) if titles_raw else profile.search_terms
    if not search_terms:
        raise ValueError("At least one job title is required")

    locations = selection.locations
    remote_preferred = selection.remote_preferred
    country_indeed = selection.country_indeed

    salary_min = profile.salary_min
    if floor_raw and floor_raw not in {"(none)", "none"}:
        salary_min = _parse_optional_float(floor_raw)
    elif floor_raw in {"none", "(none)"}:
        salary_min = None

    _require_scrape_confirmation(read)

    primary = search_terms[0]
    if remote_preferred:
        print(
            f"\nPrimary scrape query: {primary!r} @ United States (remote)",
            flush=True,
        )
    else:
        print(
            f"\nPrimary scrape query: {primary!r} @ {', '.join(locations)}",
            flush=True,
        )
    print(
        "Boards (sequential): Indeed -> LinkedIn -> Glassdoor -> Google -> ZipRecruiter",
        flush=True,
    )

    refined = profile.model_copy(
        update={
            "search_terms": search_terms,
            "locations": locations,
            "remote_preferred": remote_preferred,
            "country_indeed": country_indeed,
            "salary_min": salary_min,
            "salary_max": None,
            "updated_at": datetime.now(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }
    )

    print("\nSearching with:", flush=True)
    print(format_search_summary(refined), flush=True)

    if save_snapshot:
        save_search_profile(refined, resume_dir or RESUME_DIR)

    return refined


def prepare_run_search(
    settings: Settings | None = None,
    *,
    llm: LLMProvider | None = None,
    interactive: bool = True,
    input_fn: InputFn | None = None,
    force_refresh: bool = False,
) -> tuple[Settings, ResumeSearchProfile]:
    """LLM résumé inference + optional user refinement → settings for this run."""
    from agentzero.config import get_settings
    from agentzero.ingest.search_profile import load_matching_search_profile

    base = settings or get_settings()
    if llm is None:
        raise ValueError("prepare_run_search requires an LLM to infer search targets")

    cached = None if force_refresh else load_matching_search_profile()
    if cached is not None:
        print("Loaded resume/search_profile.json (same résumé).", flush=True)
        profile = cached
    else:
        print("Inferring search terms from résumé via LLM (~15–30s)…", flush=True)
        profile = resolve_search_from_resume(
            llm=llm,
            save_snapshot=False,
            force_refresh=force_refresh,
            prefer_snapshot=False,
        )

    profile = interactive_refine_search_profile(
        profile,
        interactive=interactive,
        input_fn=input_fn,
        save_snapshot=True,
        remote_only=base.remote_only,
    )
    from agentzero.scrape.remote_policy import apply_remote_only_settings

    effective = apply_remote_only_settings(apply_search_profile(base, profile))
    return effective, profile
