import csv
from pathlib import Path
from typing import cast

import pytest
from structlog.typing import FilteringBoundLogger

from firecrawl_demo.core import config
from firecrawl_demo.domain.models import EvidenceRecord
from firecrawl_demo.infrastructure.evidence import (
    CompositeEvidenceSink,
    CSVEvidenceSink,
    StreamingEvidenceSink,
    build_evidence_sink,
)


def test_csv_evidence_sink_appends(tmp_path: Path) -> None:
    path = tmp_path / "evidence.csv"
    sink = CSVEvidenceSink(path=path)

    # Should not create file when no entries are provided.
    sink.record([])
    assert not path.exists()

    entries = [
        EvidenceRecord(
            row_id=2,
            organisation="Test Org",
            changes="Website URL -> https://example.org",
            sources=["https://example.org", "https://regulator.gov.za"],
            notes="Sample note",
            confidence=80,
        ),
        EvidenceRecord(
            row_id=3,
            organisation="Another Org",
            changes="Contact Person -> Jane",
            sources=["https://another.org", "https://caa.co.za"],
            notes="",  # empty notes should serialize as blank string
            confidence=70,
        ),
    ]

    sink.record(entries)

    assert path.exists()
    with path.open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 2
    first, second = rows
    assert first["RowID"] == "2"
    assert first["Organisation"] == "Test Org"
    assert first["Sources"].count("https://") == 2
    assert second["RowID"] == "3"
    assert second["Notes"] == ""
    assert second["Sources"].endswith("caa.co.za")


class _RecordingLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **payload: object) -> None:
        self.events.append((event, payload))


def _sample_evidence() -> EvidenceRecord:
    return EvidenceRecord(
        row_id=1,
        organisation="Example Org",
        changes="Contact Person -> Jane",
        sources=["https://regulator.example.za"],
        notes="",
        confidence=90,
    )


def test_streaming_evidence_sink_emits_rest_payloads() -> None:
    logger = _RecordingLogger()
    sink = StreamingEvidenceSink(
        enabled=True,
        endpoint="https://audit.example/api",
        logger=cast(FilteringBoundLogger, logger),
    )

    record = _sample_evidence()
    sink.record([record])

    assert logger.events == [
        (
            "evidence_sink.rest_publish",
            {
                "endpoint": "https://audit.example/api",
                "payload": record.as_dict(),
            },
        )
    ]


def test_streaming_evidence_sink_emits_kafka_payloads() -> None:
    logger = _RecordingLogger()
    sink = StreamingEvidenceSink(
        transport="kafka",
        topic="audit.events",
        enabled=True,
        logger=cast(FilteringBoundLogger, logger),
    )

    record = _sample_evidence()
    sink.record([record])

    assert logger.events == [
        (
            "evidence_sink.kafka_publish",
            {
                "topic": "audit.events",
                "payload": record.as_dict(),
            },
        )
    ]


def test_streaming_sink_is_noop_when_disabled() -> None:
    logger = _RecordingLogger()
    sink = StreamingEvidenceSink(
        enabled=False, logger=cast(FilteringBoundLogger, logger)
    )

    sink.record([_sample_evidence()])

    assert logger.events == []


def test_composite_sink_broadcasts_records() -> None:
    class _StubSink:
        def __init__(self) -> None:
            self.received: list[list[EvidenceRecord]] = []

        def record(self, entries) -> None:
            self.received.append(list(entries))

    first = _StubSink()
    second = _StubSink()
    composite = CompositeEvidenceSink((first, second))

    record = _sample_evidence()
    composite.record([record])

    assert first.received == [[record]]
    assert second.received == [[record]]


def test_build_evidence_sink_supports_composite_configs() -> None:
    settings = config.EvidenceSinkSettings(
        backend="csv+stream+csv", stream_enabled=True
    )
    sink = build_evidence_sink(settings)

    assert isinstance(sink, CompositeEvidenceSink)
    assert isinstance(sink.sinks[0], CSVEvidenceSink)
    assert isinstance(sink.sinks[1], StreamingEvidenceSink)


def test_build_evidence_sink_defaults_to_csv_for_empty_backend() -> None:
    settings = config.EvidenceSinkSettings(backend="   ")
    sink = build_evidence_sink(settings)

    assert isinstance(sink, CSVEvidenceSink)


def test_build_evidence_sink_raises_for_unknown_backend() -> None:
    settings = config.EvidenceSinkSettings(backend="csv+unknown")

    with pytest.raises(ValueError, match="unknown"):
        build_evidence_sink(settings)


def test_build_evidence_sink_returns_csv_when_backend_empty() -> None:
    settings = config.EvidenceSinkSettings(backend="", stream_enabled=False)
    sink = build_evidence_sink(settings)

    assert isinstance(sink, CSVEvidenceSink)
