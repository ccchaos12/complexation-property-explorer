"""Common contract implemented by every future data-source adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class SourceAdapter(ABC):
    """Transform one immutable staging source into canonical candidate records."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Return a stable identifier for the source family."""

    @abstractmethod
    def load(self, staging_path: Path, canonical_path: Path) -> dict:
        """Load source data and return a validation summary."""
