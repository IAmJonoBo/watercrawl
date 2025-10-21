"""Helpers for persisting whylogs drift reports to dashboards and metrics."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from firecrawl_demo.integrations.telemetry.drift import DriftMetric, DriftReport


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _metric_entries(
    metrics: Iterable[tuple[str, DriftMetric]],
) -> list[dict[str, float | str]]:
    formatted: list[dict[str, float | str]] = []
    for category, metric in metrics:
        formatted.append(
            {
                "category": category,
                "baseline_ratio": metric.baseline_ratio,
                "observed_ratio": metric.observed_ratio,
                "difference": metric.difference,
            }
        )
    return formatted


def append_alert_report(
    *,
    report: DriftReport,
    output_path: Path,
    run_id: str,
    dataset_name: str,
    timestamp: datetime | None = None,
) -> Path:
    """Append the drift report to a JSON log consumable by dashboards."""

    _ensure_parent(output_path)
    entries: list[dict[str, object]] = []
    if output_path.exists():
        try:
            entries = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []

    recorded_at = timestamp or datetime.now(UTC)

    entry = {
        "timestamp": recorded_at.isoformat(),
        "run_id": run_id,
        "dataset": dataset_name,
        "exceeded_threshold": report.exceeded_threshold,
        "threshold": report.threshold,
        "status_drift": _metric_entries(report.status_drift.items()),
        "province_drift": _metric_entries(report.province_drift.items()),
        "whylogs_alerts": [
            {
                "column": alert.column,
                "category": alert.category,
                "difference": alert.difference,
                "baseline_ratio": alert.baseline_ratio,
                "observed_ratio": alert.observed_ratio,
            }
            for alert in report.whylogs_alerts
        ],
    }

    entries.append(entry)
    output_path.write_text(
        json.dumps(entries, indent=2, sort_keys=True), encoding="utf-8"
    )
    return output_path


def write_prometheus_metrics(
    *,
    report: DriftReport,
    metrics_path: Path,
    run_id: str,
    dataset_name: str,
    timestamp: datetime | None = None,
) -> Path:
    """Emit a Prometheus exposition file with drift metrics."""

    _ensure_parent(metrics_path)
    recorded_at = timestamp or datetime.now(UTC)
    alert_total = len(report.whylogs_alerts) if report.whylogs_alerts else 0

    lines = [
        "# HELP whylogs_drift_alerts_total Total number of whylogs alerts for the run",
        "# TYPE whylogs_drift_alerts_total gauge",
        f'whylogs_drift_alerts_total{{run_id="{run_id}",dataset="{dataset_name}"}} {alert_total}',
        "# HELP whylogs_drift_exceeded_threshold Whether drift threshold was exceeded (1=yes)",
        "# TYPE whylogs_drift_exceeded_threshold gauge",
        f'whylogs_drift_exceeded_threshold{{run_id="{run_id}",dataset="{dataset_name}"}} {1 if report.exceeded_threshold else 0}',
    ]

    def _ratio_line(metric: DriftMetric, *, label: str, category: str) -> str:
        return (
            f'whylogs_drift_ratio_difference{{run_id="{run_id}",dataset="{dataset_name}",'
            f'dimension="{label}",category="{category}"}} {metric.difference}'
        )

    for label, collection in ("status", report.status_drift.items()), (
        "province",
        report.province_drift.items(),
    ):
        for category, metric in collection:
            lines.append(_ratio_line(metric, label=label, category=category))

    lines.append(
        f"# HELP whylogs_drift_report_generated_at Unix timestamp of latest drift report\n"
        f"# TYPE whylogs_drift_report_generated_at gauge\n"
        f'whylogs_drift_report_generated_at{{dataset="{dataset_name}"}} {recorded_at.timestamp()}'
    )

    metrics_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return metrics_path
