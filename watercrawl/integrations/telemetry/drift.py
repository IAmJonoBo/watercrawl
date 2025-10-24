from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import pandas as pd

    _PANDAS_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    _PANDAS_AVAILABLE = False

try:  # pragma: no cover - optional dependency
    import whylogs as why

    _WHYLOGS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    why = None  # type: ignore
    _WHYLOGS_AVAILABLE = False

from watercrawl.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    register_plugin,
)


@dataclass(frozen=True)
class DriftMetric:
    baseline_count: int
    observed_count: int
    baseline_ratio: float
    observed_ratio: float
    difference: float


@dataclass(frozen=True)
class DriftBaseline:
    status_counts: Mapping[str, int]
    province_counts: Mapping[str, int]
    total_rows: int


@dataclass
class WhylogsAlert:
    column: str
    category: str
    baseline_ratio: float
    observed_ratio: float
    difference: float


@dataclass
class WhylogsProfileInfo:
    profile_path: Path
    metadata_path: Path
    backend: str
    status_counts: Mapping[str, int]
    province_counts: Mapping[str, int]
    total_rows: int
    generated_at: datetime


@dataclass
class DriftReport:
    status_drift: dict[str, DriftMetric]
    province_drift: dict[str, DriftMetric]
    exceeded_threshold: bool
    threshold: float
    whylogs_profile: WhylogsProfileInfo | None = None
    whylogs_alerts: list[WhylogsAlert] = field(default_factory=list)


def _calculate_ratios(counts: Mapping[str, int], total: int) -> dict[str, float]:
    if total == 0:
        return {key: 0.0 for key in counts}
    return {key: value / total for key, value in counts.items()}


def _merge_categories(*mappings: Mapping[str, int]) -> set[str]:
    categories: set[str] = set()
    for mapping in mappings:
        categories.update(mapping.keys())
    return categories


def _value_counts(frame: Any, column: str) -> dict[str, int]:
    if _PANDAS_AVAILABLE and column in getattr(frame, "columns", []):
        series = frame[column]
        return series.value_counts(dropna=False).to_dict()
    counts: dict[str, int] = {}
    for row in frame:
        if not isinstance(row, Mapping):
            continue
        value = row.get(column)
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def compare_to_baseline(
    frame: Any, baseline: DriftBaseline, threshold: float
) -> DriftReport:
    """Compare observed distributions to a stored baseline and flag drift."""

    observed_status_counts = _value_counts(frame, "Status")
    observed_province_counts = _value_counts(frame, "Province")
    observed_total = int(frame.shape[0]) or 1

    baseline_status_ratios = _calculate_ratios(
        baseline.status_counts, baseline.total_rows
    )
    baseline_province_ratios = _calculate_ratios(
        baseline.province_counts, baseline.total_rows
    )
    observed_status_ratios = _calculate_ratios(observed_status_counts, observed_total)
    observed_province_ratios = _calculate_ratios(
        observed_province_counts, observed_total
    )

    status_metrics: dict[str, DriftMetric] = {}
    exceeded = False
    for category in _merge_categories(baseline.status_counts, observed_status_counts):
        baseline_ratio = baseline_status_ratios.get(category, 0.0)
        observed_ratio = observed_status_ratios.get(category, 0.0)
        difference = abs(observed_ratio - baseline_ratio)
        status_metrics[category] = DriftMetric(
            baseline_count=baseline.status_counts.get(category, 0),
            observed_count=observed_status_counts.get(category, 0),
            baseline_ratio=baseline_ratio,
            observed_ratio=observed_ratio,
            difference=difference,
        )
        if difference > threshold:
            exceeded = True

    province_metrics: dict[str, DriftMetric] = {}
    for category in _merge_categories(
        baseline.province_counts, observed_province_counts
    ):
        baseline_ratio = baseline_province_ratios.get(category, 0.0)
        observed_ratio = observed_province_ratios.get(category, 0.0)
        difference = abs(observed_ratio - baseline_ratio)
        province_metrics[category] = DriftMetric(
            baseline_count=baseline.province_counts.get(category, 0),
            observed_count=observed_province_counts.get(category, 0),
            baseline_ratio=baseline_ratio,
            observed_ratio=observed_ratio,
            difference=difference,
        )
        if difference > threshold:
            exceeded = True

    return DriftReport(
        status_drift=status_metrics,
        province_drift=province_metrics,
        exceeded_threshold=exceeded,
        threshold=threshold,
    )


def log_whylogs_profile(frame: Any, output_path: Path) -> WhylogsProfileInfo:
    """Persist a whylogs profile (or fallback metadata) for the observed frame."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path.with_suffix(output_path.suffix + ".json")
    status_counts = _value_counts(frame, "Status")
    province_counts = _value_counts(frame, "Province")
    total_rows = int(frame.shape[0])

    backend = "fallback"
    if _WHYLOGS_AVAILABLE and why is not None:
        try:  # pragma: no cover - exercised when whylogs installed
            profile = why.log(pandas=frame).profile
            profile.write(str(output_path))
            backend = "whylogs"
        except Exception:  # pragma: no cover - defensive fallback
            output_path.write_text("")

    generated_at = datetime.now(UTC)
    metadata_payload = {
        "generated_at": generated_at.isoformat(),
        "backend": backend,
        "status_counts": status_counts,
        "province_counts": province_counts,
        "total_rows": total_rows,
        "profile_path": str(output_path),
    }
    metadata_path.write_text(json.dumps(metadata_payload, indent=2, sort_keys=True))

    return WhylogsProfileInfo(
        profile_path=output_path,
        metadata_path=metadata_path,
        backend=backend,
        status_counts=status_counts,
        province_counts=province_counts,
        total_rows=total_rows,
        generated_at=generated_at,
    )


def load_whylogs_metadata(path: Path) -> WhylogsProfileInfo:
    payload = json.loads(Path(path).read_text())
    generated_at_raw = payload.get("generated_at")
    generated_at = (
        datetime.fromisoformat(generated_at_raw)
        if isinstance(generated_at_raw, str)
        else datetime.now(UTC)
    )
    profile_path_raw = payload.get("profile_path")
    profile_path = (
        Path(profile_path_raw)
        if isinstance(profile_path_raw, str)
        else path.with_suffix("")
    )
    return WhylogsProfileInfo(
        profile_path=profile_path,
        metadata_path=path,
        backend=payload.get("backend", "fallback"),
        status_counts=payload.get("status_counts", {}),
        province_counts=payload.get("province_counts", {}),
        total_rows=int(payload.get("total_rows", 0)),
        generated_at=generated_at,
    )


def compare_whylogs_metadata(
    baseline: WhylogsProfileInfo,
    observed: WhylogsProfileInfo,
    threshold: float,
) -> list[WhylogsAlert]:
    alerts: list[WhylogsAlert] = []

    baseline_status_ratios = _calculate_ratios(
        baseline.status_counts, baseline.total_rows or 1
    )
    observed_status_ratios = _calculate_ratios(
        observed.status_counts, observed.total_rows or 1
    )
    for category in _merge_categories(baseline.status_counts, observed.status_counts):
        baseline_ratio = baseline_status_ratios.get(category, 0.0)
        observed_ratio = observed_status_ratios.get(category, 0.0)
        difference = abs(observed_ratio - baseline_ratio)
        if difference > threshold:
            alerts.append(
                WhylogsAlert(
                    column="Status",
                    category=category,
                    baseline_ratio=baseline_ratio,
                    observed_ratio=observed_ratio,
                    difference=difference,
                )
            )

    baseline_province_ratios = _calculate_ratios(
        baseline.province_counts, baseline.total_rows or 1
    )
    observed_province_ratios = _calculate_ratios(
        observed.province_counts, observed.total_rows or 1
    )
    for category in _merge_categories(
        baseline.province_counts, observed.province_counts
    ):
        baseline_ratio = baseline_province_ratios.get(category, 0.0)
        observed_ratio = observed_province_ratios.get(category, 0.0)
        difference = abs(observed_ratio - baseline_ratio)
        if difference > threshold:
            alerts.append(
                WhylogsAlert(
                    column="Province",
                    category=category,
                    baseline_ratio=baseline_ratio,
                    observed_ratio=observed_ratio,
                    difference=difference,
                )
            )

    return alerts


def save_baseline(baseline: DriftBaseline, path: Path) -> None:
    payload = {
        "status_counts": dict(baseline.status_counts),
        "province_counts": dict(baseline.province_counts),
        "total_rows": baseline.total_rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def load_baseline(path: Path) -> DriftBaseline:
    payload = json.loads(Path(path).read_text())
    return DriftBaseline(
        status_counts=payload.get("status_counts", {}),
        province_counts=payload.get("province_counts", {}),
        total_rows=int(payload.get("total_rows", 0)),
    )


__all__ = [
    "DriftBaseline",
    "DriftMetric",
    "DriftReport",
    "WhylogsAlert",
    "WhylogsProfileInfo",
    "compare_to_baseline",
    "log_whylogs_profile",
    "compare_whylogs_metadata",
    "save_baseline",
    "load_baseline",
]


def _drift_health_probe(context: PluginContext) -> PluginHealthStatus:
    details = {
        "requires_baseline": True,
        "optional_dependencies": ["pandas"],
    }
    return PluginHealthStatus(
        healthy=True,
        reason="Drift module requires external baseline input",
        details=details,
    )


register_plugin(
    IntegrationPlugin(
        name="drift",
        category="telemetry",
        factory=lambda ctx: {
            "compare_to_baseline": compare_to_baseline,
            "log_whylogs_profile": log_whylogs_profile,
            "compare_whylogs_metadata": compare_whylogs_metadata,
            "load_baseline": load_baseline,
            "save_baseline": save_baseline,
            "load_whylogs_metadata": load_whylogs_metadata,
        },
        config_schema=PluginConfigSchema(
            optional_dependencies=("pandas", "whylogs"),
            description="Detect distribution drift across provincial and status metrics.",
        ),
        health_probe=_drift_health_probe,
        summary="Status and province drift calculations",
    )
)
