"""Infrastructure-backed implementations of evidence sinks."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import structlog
from structlog.typing import FilteringBoundLogger

from watercrawl.core import config
from watercrawl.domain.contracts import EvidenceRecordContract
from watercrawl.domain.models import (
    EvidenceRecord,
    evidence_record_from_contract,
    evidence_record_to_contract,
)

if TYPE_CHECKING:
    from watercrawl.application.interfaces import EvidenceSink
else:  # pragma: no cover - runtime protocol for loose coupling

    class EvidenceSink(Protocol):
        def record(
            self, entries: Iterable[EvidenceRecord | EvidenceRecordContract]
        ) -> None: ...


def _ensure_contract_records(
    entries: Iterable[EvidenceRecord | EvidenceRecordContract],
) -> list[EvidenceRecordContract]:
    """Normalise evidence entries into validated contract instances."""

    contracts: list[EvidenceRecordContract] = []
    for entry in entries:
        if isinstance(entry, EvidenceRecordContract):
            # Always round-trip through validation to catch model_construct shortcuts.
            validated = EvidenceRecordContract.model_validate(entry.model_dump())
        elif isinstance(entry, EvidenceRecord):
            validated = evidence_record_to_contract(entry)
        elif isinstance(entry, Mapping):
            validated = EvidenceRecordContract.model_validate(dict(entry))
        else:
            raise TypeError(
                "Evidence sinks accept EvidenceRecord dataclasses, EvidenceRecordContract instances, or mappings"
            )
        contracts.append(validated)
    return contracts


class NullEvidenceSink:
    """No-op sink used for tests or scenarios where persistence is disabled."""

    def record(
        self, entries: Iterable[EvidenceRecord | EvidenceRecordContract]
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

    def record(
        self, entries: Iterable[EvidenceRecord | EvidenceRecordContract]
    ) -> None:
        contracts = _ensure_contract_records(entries)
        if not contracts:
            return

        records = [evidence_record_from_contract(contract) for contract in contracts]

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

    def record(
        self, entries: Iterable[EvidenceRecord | EvidenceRecordContract]
    ) -> None:
        contracts = _ensure_contract_records(entries)
        if not contracts or not self.enabled:
            return

        for contract in contracts:
            payload = contract.model_dump()
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

    def record(
        self, entries: Iterable[EvidenceRecord | EvidenceRecordContract]
    ) -> None:
        contracts = _ensure_contract_records(entries)
        if not contracts:
            return
        for sink in self.sinks:
            sink.record(contracts)


def build_evidence_sink(
    settings: config.EvidenceSinkSettings | None = None,
) -> EvidenceSink:
    """Construct an evidence sink based on configuration settings."""

    resolved = settings or config.EVIDENCE_SINK
    backend_parts = [
        part.strip().lower() for part in resolved.backend.split("+") if part.strip()
    ]
    backend_parts = list(dict.fromkeys(backend_parts))

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
        else:
            raise ValueError(f"Unknown evidence sink backend '{backend}'")

    if not sinks:
        return NullEvidenceSink()
    if len(sinks) == 1:
        return sinks[0]
    return CompositeEvidenceSink(tuple(sinks))
