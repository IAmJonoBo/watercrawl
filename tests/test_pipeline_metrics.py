from __future__ import annotations

from watercrawl.application.pipeline import _LookupMetrics
from watercrawl.integrations.adapters.research.connectors import ConnectorEvidence
from watercrawl.integrations.adapters.research.core import ResearchFinding
from watercrawl.integrations.adapters.research.validators import ValidationReport


def test_lookup_metrics_tracks_connector_details() -> None:
    metrics = _LookupMetrics()
    finding = ResearchFinding(
        confidence=70,
        evidence_by_connector={
            "regulator": ConnectorEvidence(
                connector="regulator",
                sources=["https://regulator.gov.za/sky-high"],
                notes=["Regulator registry corroboration"],
                latency_seconds=0.2,
                success=True,
            ),
            "press": ConnectorEvidence(
                connector="press",
                sources=["https://press.example/article"],
                notes=["Press coverage located"],
                latency_seconds=0.3,
                success=False,
            ),
        },
        validation=ValidationReport(
            base_confidence=60,
            confidence_adjustment=10,
            final_confidence=70,
            checks=(),
            contradictions=(),
        ),
    )

    metrics.record_connector_metrics(finding)

    assert metrics.connector_latency["regulator"] == [0.2]
    assert metrics.connector_success["press"] == [False]
    assert metrics.confidence_deltas == [(60, 10, 70)]
