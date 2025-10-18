"""Interfaces for application layer services."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

from firecrawl_demo.domain.models import EvidenceRecord, PipelineReport
from firecrawl_demo.integrations.telemetry.lineage import LineageContext

from .progress import PipelineProgressListener


class EvidenceSink(Protocol):
    """Protocol for recording evidence entries."""

    def record(
        self, entries: Iterable[EvidenceRecord]
    ) -> None:  # pragma: no cover - interface
        """Persist a batch of evidence entries."""


class PipelineService(ABC):
    """Abstract interface for enrichment pipeline orchestration."""

    @abstractmethod
    def run_dataframe(
        self,
        frame: Any,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
    ) -> PipelineReport:
        """Synchronously run the enrichment pipeline for a dataframe."""

    @abstractmethod
    async def run_dataframe_async(
        self,
        frame: Any,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
    ) -> PipelineReport:
        """Asynchronously run the enrichment pipeline for a dataframe."""

    @abstractmethod
    def run_file(
        self,
        input_path: Path,
        output_path: Path | None = None,
        *,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
    ) -> PipelineReport:
        """Synchronously process a dataset file through the pipeline."""

    @abstractmethod
    async def run_file_async(
        self,
        input_path: Path,
        output_path: Path | None = None,
        *,
        progress: PipelineProgressListener | None = None,
        lineage_context: LineageContext | None = None,
    ) -> PipelineReport:
        """Asynchronously process a dataset file through the pipeline."""

    @abstractmethod
    def available_tasks(self) -> dict[str, str]:
        """Describe the tasks supported by the pipeline orchestrator."""

    @abstractmethod
    def run_task(self, task: str, payload: dict[str, object]) -> dict[str, object]:
        """Execute a named pipeline task and return a serialisable payload."""

    @property
    @abstractmethod
    def last_report(self) -> PipelineReport | None:
        """Return the most recent pipeline report, if any."""
