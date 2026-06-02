"""Thread-safe CLI progress for long-running parallel steps."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


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


def _format_duration(seconds: float) -> str:
    """Human-readable duration for build progress lines."""
    if seconds < 0:
        seconds = 0
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


@dataclass(slots=True)
class BuildStep:
    """One Docker build manifest step."""

    id: str
    label: str
    estimated_seconds: float


class BuildProgress:
    """Multi-step build progress with elapsed time and ETA."""

    def __init__(
        self,
        steps: list[BuildStep],
        *,
        stall_seconds: float = 180.0,
        heartbeat_seconds: float = 10.0,
    ) -> None:
        if not steps:
            raise ValueError("steps must not be empty")
        self.steps = steps
        self.stall_seconds = stall_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._started = time.monotonic()
        self._step_started = self._started
        self._index = 0
        self._estimates: list[float] = [s.estimated_seconds for s in self.steps]
        self._last_output = self._started
        self._lock = threading.Lock()

    @property
    def step_index(self) -> int:
        return self._index + 1

    @property
    def step_total(self) -> int:
        return len(self.steps)

    @property
    def current_step(self) -> BuildStep:
        return self.steps[self._index]

    @property
    def elapsed_sec(self) -> float:
        return time.monotonic() - self._started

    @property
    def step_elapsed_sec(self) -> float:
        return time.monotonic() - self._step_started

    def touch_output(self) -> None:
        with self._lock:
            self._last_output = time.monotonic()

    def seconds_since_output(self) -> float:
        with self._lock:
            return time.monotonic() - self._last_output

    def is_stalled(self) -> bool:
        return self.seconds_since_output() >= self.stall_seconds

    def eta_next_step_sec(self) -> float | None:
        if self._index >= len(self.steps):
            return 0.0
        est = self._estimates[self._index]
        remaining = est - self.step_elapsed_sec
        return max(0.0, remaining)

    def eta_total_sec(self) -> float:
        remaining = sum(self._estimates[i] for i in range(self._index, len(self.steps)))
        next_eta = self.eta_next_step_sec()
        if next_eta is not None and self._index < len(self.steps):
            remaining = remaining - self._estimates[self._index] + next_eta
        return remaining

    def blend_completed_estimate(self, observed_sec: float) -> None:
        """Update estimate for the step that just finished."""
        idx = self._index - 1
        if idx < 0:
            return
        manifest = self.steps[idx].estimated_seconds
        self._estimates[idx] = 0.7 * manifest + 0.3 * observed_sec

    def advance_to_step_id(self, step_id: str) -> bool:
        """Move to *step_id* if it is current or later; return True if index changed."""
        ids = [s.id for s in self.steps]
        if step_id not in ids:
            return False
        target = ids.index(step_id)
        if target < self._index:
            return False
        if target == self._index:
            self.touch_output()
            return False
        now = time.monotonic()
        with self._lock:
            if target > self._index:
                observed = now - self._step_started
                self.blend_completed_estimate(observed)
                self._index = target
                self._step_started = now
            self._last_output = now
        return True

    def finish_all(self) -> None:
        now = time.monotonic()
        with self._lock:
            if self._index < len(self.steps):
                observed = now - self._step_started
                self.blend_completed_estimate(observed)
                self._index = len(self.steps) - 1
            self._last_output = now

    def format_line(self, *, suffix: str = "") -> str:
        step = self.current_step if self._index < len(self.steps) else self.steps[-1]
        elapsed = _format_duration(self.elapsed_sec)
        eta_total = self.eta_total_sec()
        eta_next = self.eta_next_step_sec()
        eta_total_s = _format_duration(eta_total) if eta_total is not None else "?"
        eta_next_s = _format_duration(eta_next) if eta_next is not None else "?"
        flags: list[str] = []
        if self.is_stalled():
            flags.append("STALL?")
        elif self.step_elapsed_sec > 2 * self._estimates[self._index]:
            flags.append("SLOW")
        flag = f" {' '.join(flags)}" if flags else ""
        extra = f" {suffix}" if suffix else ""
        return (
            f"[build {self.step_index}/{self.step_total}] {step.label} | "
            f"elapsed {elapsed} | ETA total ~{eta_total_s} | next step ~{eta_next_s}{flag}{extra}"
        )

    def print_status(self, *, suffix: str = "") -> None:
        print(self.format_line(suffix=suffix), flush=True)

    def status_dict(self, *, stalled: bool | None = None) -> dict[str, object]:
        from datetime import UTC, datetime

        step = self.current_step if self._index < len(self.steps) else self.steps[-1]
        is_stalled = self.is_stalled() if stalled is None else stalled
        return {
            "phase": step.id,
            "step_index": self.step_index,
            "step_total": self.step_total,
            "elapsed_sec": round(self.elapsed_sec, 1),
            "eta_total_sec": round(self.eta_total_sec(), 1),
            "eta_next_step_sec": round(self.eta_next_step_sec() or 0, 1),
            "last_output_at": datetime.now(UTC).isoformat(),
            "stalled": is_stalled,
        }
