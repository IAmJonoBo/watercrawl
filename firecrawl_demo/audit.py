from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import structlog
from structlog.typing import FilteringBoundLogger

from . import config
from .models import EvidenceRecord


class EvidenceSink(Protocol):
    """Protocol for recording evidence records to an audit sink."""

    def record(
        self, entries: Iterable[EvidenceRecord]
    ) -> None:  # pragma: no cover - interface
        """Persist a batch of evidence entries."""


class NullEvidenceSink:
    """No-op sink used for tests or scenarios where persistence is disabled."""

    def record(
        self, entries: Iterable[EvidenceRecord]
    ) -> None:  # pragma: no cover - no-op
        return


@dataclass(slots=True)
class CSVEvidenceSink:
    """Append evidence rows to a CSV file, preserving legacy behaviour."""

    path: Path = field(default_factory=lambda: config.EVIDENCE_LOG)

    _FIELDNAMES = (
        "RowID",
        "Organisation",
        "What changed",
        "Sources",
        "Notes",
        "Timestamp",
        "Confidence",
    )

    def record(self, entries: Iterable[EvidenceRecord]) -> None:
        records = list(entries)
        if not records:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.path.exists()

        with self.path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=self._FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            for record in records:
                writer.writerow(record.as_dict())


@dataclass(slots=True)
class StreamingEvidenceSink:
    """Stub sink for Kafka/REST streaming integrations."""

    transport: str = "rest"
    endpoint: str | None = None
    topic: str | None = None
    enabled: bool = False
    logger: FilteringBoundLogger = field(
        default_factory=lambda: structlog.get_logger(__name__)
    )

    def record(self, entries: Iterable[EvidenceRecord]) -> None:
        records = list(entries)
        if not records or not self.enabled:
            return

        for record in records:
            payload = record.as_dict()
            if self.transport == "kafka":
                self.logger.info(
                    "evidence_sink.kafka_publish",
                    topic=self.topic,
                    payload=payload,
                )
            else:
                self.logger.info(
                    "evidence_sink.rest_publish",
                    endpoint=self.endpoint,
                    payload=payload,
                )


@dataclass(slots=True)
class CompositeEvidenceSink:
    """Dispatch evidence batches to multiple sinks."""

    sinks: Sequence[EvidenceSink]

    def record(self, entries: Iterable[EvidenceRecord]) -> None:
        records = list(entries)
        if not records:
            return
        for sink in self.sinks:
            sink.record(records)


def build_evidence_sink(
    settings: config.EvidenceSinkSettings | None = None,
) -> EvidenceSink:
    """Construct an evidence sink based on configuration settings."""

    resolved = settings or config.EVIDENCE_SINK
    backend_parts = [
        part.strip().lower() for part in resolved.backend.split("+") if part.strip()
    ]

    sinks: list[EvidenceSink] = []
    for backend in backend_parts or ["csv"]:
        if backend == "csv":
            sinks.append(CSVEvidenceSink())
        elif backend == "stream":
            sinks.append(
                StreamingEvidenceSink(
                    transport=resolved.stream_transport,
                    endpoint=resolved.rest_endpoint,
                    topic=resolved.kafka_topic,
                    enabled=resolved.stream_enabled,
                )
            )

    if not sinks:
        return NullEvidenceSink()
    if len(sinks) == 1:
        return sinks[0]
    return CompositeEvidenceSink(tuple(sinks))
