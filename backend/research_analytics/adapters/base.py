"""Standard source adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable


class SourceAdapter(ABC):
    """Collect, transform, and validate records from one source."""

    @abstractmethod
    def connect(self) -> None:
        """Check whether the source is accessible."""
        raise NotImplementedError

    @abstractmethod
    def collect(self) -> Iterable[dict]:
        """Collect raw source records."""
        raise NotImplementedError

    @abstractmethod
    def transform(self, record: dict) -> dict:
        """Convert a raw record to the common schema."""
        raise NotImplementedError

    @abstractmethod
    def validate(self, record: dict) -> list[str]:
        """Return validation errors for the transformed record."""
        raise NotImplementedError

    def preview(self, limit: int = 5) -> list[dict]:
        """Collect and transform a small sample for mapping confirmation."""

        preview_records = []
        for raw_record in self.collect():
            preview_records.append(self.transform(raw_record))
            if len(preview_records) >= limit:
                break
        return preview_records
