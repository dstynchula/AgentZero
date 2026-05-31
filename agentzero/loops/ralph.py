"""Idempotent loop runner with bounded parallelism."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentzero.loops.progress import Progress

log = logging.getLogger(__name__)


def run_parallel(
    items: list[str],
    worker: Callable[[str], None],
    *,
    max_workers: int = 4,
    progress: Progress | None = None,
    item_label: Callable[[str], str] | None = None,
) -> list[str]:
    """Process ``items`` in parallel.

    Returns human-readable error strings for failed workers (empty when all succeed).
    """
    if not items:
        return []

    failures: list[str] = []

    def wrapped(item: str) -> None:
        label = item_label(item) if item_label else item
        try:
            worker(item)
        except Exception as exc:
            log.exception("Parallel worker failed for %s", label)
            failures.append(f"{label}: {exc}")
            if progress is not None:
                progress.step(f"FAILED {label}")
            return
        if progress is not None:
            progress.step(label)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
        list(pool.map(wrapped, items))
    return failures
