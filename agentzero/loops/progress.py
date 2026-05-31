"""Thread-safe CLI progress for long-running parallel steps."""

from __future__ import annotations

import threading
import time


class Progress:
    """Print ``[n/total] detail`` lines as work completes (safe across threads)."""

    def __init__(self, total: int, *, label: str) -> None:
        if total < 0:
            raise ValueError("total must be non-negative")
        self.total = total
        self.label = label
        self._done = 0
        self._lock = threading.Lock()
        self._started = time.monotonic()

    def announce(self, extra: str = "") -> None:
        """Print that a multi-item step is starting."""
        suffix = f" ({extra})" if extra else ""
        print(f"{self.label}: 0/{self.total}{suffix}", flush=True)

    def step(self, detail: str = "") -> None:
        with self._lock:
            self._done += 1
            n, t = self._done, self.total
        elapsed = time.monotonic() - self._started
        line = f"{self.label} [{n}/{t}]"
        if detail:
            line += f" {detail}"
        line += f" ({elapsed:.0f}s)"
        print(line, flush=True)

    def finish(self, summary: str = "") -> None:
        elapsed = time.monotonic() - self._started
        msg = f"{self.label}: done {self._done}/{self.total} in {elapsed:.0f}s"
        if summary:
            msg += f" — {summary}"
        print(msg, flush=True)
