"""Operational helpers for contract execution bookkeeping."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from firecrawl_demo.core import config
from firecrawl_demo.core.compliance import append_evidence_log

from .dbt_runner import DbtContractResult
from .great_expectations_runner import CuratedDatasetContractResult

_CONTRACTS_DIR_ENV = "CONTRACTS_ARTIFACT_DIR"


def _contracts_root() -> Path:
    root = Path(os.environ.get(_CONTRACTS_DIR_ENV, config.DATA_DIR / "contracts"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def persist_contract_artifacts(
    dataset_path: Path,
    ge_payload: dict[str, Any],
    dbt_result: DbtContractResult,
) -> Path:
    """Write contract run artefacts to a timestamped directory."""

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = _contracts_root() / timestamp
    target_dir.mkdir(parents=True, exist_ok=True)

    (target_dir / "dataset_path.txt").write_text(str(dataset_path))
    (target_dir / "great_expectations_result.json").write_text(
        json.dumps(ge_payload, indent=2, sort_keys=True)
    )

    if dbt_result.run_results_path and dbt_result.run_results_path.exists():
        shutil.copy2(
            dbt_result.run_results_path,
            target_dir / "dbt_run_results.json",
        )
    else:
        (target_dir / "dbt_run_results.json").write_text(
            json.dumps({"results": dbt_result.results}, indent=2, sort_keys=True)
        )

    return target_dir


def record_contracts_evidence(
    dataset_path: Path,
    ge_result: CuratedDatasetContractResult,
    dbt_result: DbtContractResult,
    artifact_dir: Path,
) -> None:
    """Append an evidence-log entry describing the contract run."""

    ge_stats = ge_result.statistics
    evaluated = int(ge_stats.get("evaluated_expectations", 0))
    successful = int(ge_stats.get("successful_expectations", 0))
    dbt_summary = f"dbt tests {dbt_result.passed}/{dbt_result.total}"
    ge_summary = f"Great Expectations {successful}/{evaluated}"

    sources = [
        str(
            config.PROJECT_ROOT
            / "great_expectations"
            / "expectations"
            / "curated_dataset.json"
        ),
        str(artifact_dir / "great_expectations_result.json"),
        str(artifact_dir / "dbt_run_results.json"),
    ]

    append_evidence_log(
        [
            {
                "RowID": "0",
                "Organisation": dataset_path.name,
                "What changed": "Contracts executed (Great Expectations + dbt)",
                "Sources": "; ".join(sources),
                "Notes": f"{ge_summary}; {dbt_summary}",
                "Timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "Confidence": "100",
            }
        ]
    )
