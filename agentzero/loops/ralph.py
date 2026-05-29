"""Idempotent loop runner with bounded parallelism."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


def run_parallel(
    items: list[str],
    worker: Callable[[str], None],
    *,
    max_workers: int = 4,
) -> None:
    """Process ``items`` in parallel; safe when ``worker`` is idempotent per item."""
    if not items:
        return
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
        list(pool.map(worker, items))
