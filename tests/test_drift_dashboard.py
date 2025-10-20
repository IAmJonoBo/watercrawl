from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from firecrawl_demo.integrations.telemetry.drift import DriftMetric, DriftReport
from firecrawl_demo.integrations.telemetry.drift_dashboard import (
    append_alert_report,
    write_prometheus_metrics,
)


def _sample_report() -> DriftReport:
    metric = DriftMetric(
        baseline_count=10,
        observed_count=8,
        baseline_ratio=0.5,
        observed_ratio=0.4,
        difference=0.1,
    )
    return DriftReport(
        status_drift={"Verified": metric},
        province_drift={"Gauteng": metric},
        exceeded_threshold=False,
        threshold=0.15,
        whylogs_alerts=[],
    )


def test_append_alert_report_appends_entries(tmp_path: Path) -> None:
    output_path = tmp_path / "alerts.json"
    report = _sample_report()
    recorded_at = datetime(2025, 10, 21, 9, 30, tzinfo=UTC)

    append_alert_report(
        report=report,
        output_path=output_path,
        run_id="run-001",
        dataset_name="flight-schools",
        timestamp=recorded_at,
    )
    append_alert_report(
        report=report,
        output_path=output_path,
        run_id="run-002",
        dataset_name="flight-schools",
        timestamp=recorded_at,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(payload) == 2
    latest = payload[-1]
    assert latest["run_id"] == "run-002"
    assert latest["dataset"] == "flight-schools"
    assert latest["status_drift"][0]["category"] == "Verified"


def test_write_prometheus_metrics_emits_lines(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.prom"
    report = _sample_report()

    write_prometheus_metrics(
        report=report,
        metrics_path=metrics_path,
        run_id="run-123",
        dataset_name="flight-schools",
        timestamp=datetime(2025, 10, 21, 9, 31, tzinfo=UTC),
    )

    content = metrics_path.read_text(encoding="utf-8")
    assert (
        'whylogs_drift_alerts_total{run_id="run-123",dataset="flight-schools"} 0'
        in content
    )
    assert (
        'whylogs_drift_ratio_difference{run_id="run-123",dataset="flight-schools",dimension="status",category="Verified"} 0.1'
        in content
    )
