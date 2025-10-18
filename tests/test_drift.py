from __future__ import annotations

import pandas as pd

from firecrawl_demo.integrations.telemetry.drift import (
    DriftBaseline,
    DriftReport,
    compare_to_baseline,
)


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Name of Organisation": "Aero Academy",
                "Province": "Gauteng",
                "Status": "Verified",
            },
            {
                "Name of Organisation": "Cape Flight",
                "Province": "Western Cape",
                "Status": "Candidate",
            },
        ]
    )


def test_compare_to_baseline_flags_large_shift() -> None:
    baseline = DriftBaseline(
        status_counts={"Verified": 20, "Candidate": 0},
        province_counts={"Gauteng": 10, "Western Cape": 10},
        total_rows=20,
    )
    frame = _sample_frame()

    report = compare_to_baseline(frame, baseline, threshold=0.15)

    assert isinstance(report, DriftReport)
    assert report.exceeded_threshold is True
    assert "Verified" in report.status_drift
    assert (
        report.status_drift["Verified"].observed_ratio
        != report.status_drift["Verified"].baseline_ratio
    )
