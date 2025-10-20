"""Utility for seeding drift baselines and metadata artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]

try:  # pragma: no cover - fallback for direct execution
    from firecrawl_demo.core import config
    from firecrawl_demo.integrations.telemetry.drift import (
        DriftBaseline,
        log_whylogs_profile,
        save_baseline,
    )
except ModuleNotFoundError:  # pragma: no cover - allows `python seed_drift_baseline.py`
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from firecrawl_demo.core import config
    from firecrawl_demo.integrations.telemetry.drift import (
        DriftBaseline,
        log_whylogs_profile,
        save_baseline,
    )


def _default_baseline_path() -> Path:
    return config.DATA_DIR / "observability" / "whylogs" / "baseline.json"


def _default_metadata_path() -> Path:
    return config.DATA_DIR / "observability" / "whylogs" / "baseline_profile.bin"


def _build_baseline(frame: pd.DataFrame) -> DriftBaseline:
    status_counts = (
        frame["Status"].fillna("Unknown").value_counts(dropna=False).to_dict()
    )
    province_counts = (
        frame["Province"].fillna("Unknown").value_counts(dropna=False).to_dict()
    )
    return DriftBaseline(
        status_counts=status_counts,
        province_counts=province_counts,
        total_rows=int(frame.shape[0]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed drift baseline JSON and whylogs metadata artifacts."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=config.DATA_DIR / "sample.csv",
        help="Input dataset used to derive the baseline (default: data/sample.csv).",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=_default_baseline_path(),
        help="Path to the baseline JSON artifact (default: data/observability/whylogs/baseline.json).",
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=_default_metadata_path(),
        help="Output path (without .json extension) for whylogs profile metadata (default: data/observability/whylogs/baseline_profile.bin).",
    )
    args = parser.parse_args()

    frame = pd.read_csv(args.dataset)
    baseline = _build_baseline(frame)

    save_baseline(baseline, args.baseline)
    profile_info = log_whylogs_profile(frame, args.metadata_output)
    metadata_payload = json.loads(profile_info.metadata_path.read_text())
    try:
        metadata_payload["profile_path"] = str(
            profile_info.profile_path.relative_to(REPO_ROOT)
        )
    except ValueError:
        metadata_payload["profile_path"] = str(profile_info.profile_path)
    profile_info.metadata_path.write_text(
        json.dumps(metadata_payload, indent=2, sort_keys=True)
    )

    print(f"Baseline written to {args.baseline}")
    print(f"Whylogs metadata written to {profile_info.metadata_path}")


if __name__ == "__main__":
    main()
