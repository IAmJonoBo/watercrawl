from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd


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


@dataclass(frozen=True)
class DriftReport:
    status_drift: dict[str, DriftMetric]
    province_drift: dict[str, DriftMetric]
    exceeded_threshold: bool
    threshold: float


def _calculate_ratios(counts: Mapping[str, int], total: int) -> dict[str, float]:
    if total == 0:
        return {key: 0.0 for key in counts}
    return {key: value / total for key, value in counts.items()}


def _merge_categories(*mappings: Mapping[str, int]) -> set[str]:
    categories: set[str] = set()
    for mapping in mappings:
        categories.update(mapping.keys())
    return categories


def compare_to_baseline(
    frame: pd.DataFrame, baseline: DriftBaseline, threshold: float
) -> DriftReport:
    """Compare observed distributions to a stored baseline and flag drift."""

    observed_status_counts = frame["Status"].value_counts(dropna=False).to_dict()
    observed_province_counts = frame["Province"].value_counts(dropna=False).to_dict()
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


__all__ = ["DriftBaseline", "DriftMetric", "DriftReport", "compare_to_baseline"]
