"""Abstract interface for all job-board scrapers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from agentzero.models import RawRecord


class JobSource(ABC):
    """Fetch raw job records from a single board before validation."""

    name: str

    @abstractmethod
    def fetch(self) -> Sequence[RawRecord]:
        """Return unvalidated records as plain dicts (see ``RawRecord``)."""
