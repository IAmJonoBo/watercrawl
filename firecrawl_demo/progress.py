"""Progress reporting utilities for pipeline execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .models import SchoolRecord


class PipelineProgressListener(Protocol):
    """Protocol for observing pipeline execution progress."""

    def on_start(self, total_rows: int) -> None: ...

    def on_row_processed(
        self, index: int, updated: bool, record: SchoolRecord
    ) -> None: ...

    def on_complete(self, metrics: Mapping[str, int]) -> None: ...

    def on_error(self, error: Exception, index: int | None = None) -> None: ...


@dataclass(slots=True)
class NullPipelineProgressListener(PipelineProgressListener):
    """No-op listener used when progress reporting is disabled."""

    def on_start(self, total_rows: int) -> None:  # pragma: no cover - trivial
        return

    def on_row_processed(
        self, index: int, updated: bool, record: SchoolRecord
    ) -> None:  # pragma: no cover - trivial
        return

    def on_complete(
        self, metrics: Mapping[str, int]
    ) -> None:  # pragma: no cover - trivial
        return

    def on_error(
        self, error: Exception, index: int | None = None
    ) -> None:  # pragma: no cover - trivial
        return
