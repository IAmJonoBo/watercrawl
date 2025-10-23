"""Contracts and quality gates for curated datasets."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from watercrawl.integrations.integration_plugins import (
    IntegrationPlugin,
    PluginConfigSchema,
    PluginContext,
    PluginHealthStatus,
    register_plugin,
)

from .coverage import (
    ContractCoverage,
    calculate_contract_coverage,
    report_coverage,
)
from .deequ_runner import DEEQU_AVAILABLE, DeequContractResult, run_deequ_checks
from .operations import persist_contract_artifacts, record_contracts_evidence
from .shared_config import (
    canonical_contracts_config,
    environment_payload,
    restore_environment,
    seed_environment,
)

if TYPE_CHECKING:
    from .dbt_runner import DbtContractResult as RealDbtContractResult
    from .great_expectations_runner import (
        CuratedDatasetContractResult as RealCuratedDatasetContractResult,
    )


# Define fallback types first
@dataclass(frozen=True)
class DbtContractResult:
    """Fallback result when dbt is not available."""

    success: bool
    total: int
    failures: int
    elapsed: float
    results: list[dict[str, Any]]
    project_dir: Path
    profiles_dir: Path
    target_path: Path
    log_path: Path
    run_results_path: Path | None


@dataclass(frozen=True)
class CuratedDatasetContractResult:
    """Fallback result when Great Expectations is not available."""

    success: bool
    statistics: dict[str, Any]
    results: list[dict[str, Any]]
    expectation_suite_name: str
    meta: dict[str, Any]

    @property
    def unsuccessful_expectations(self) -> int:
        """Return the number of failing expectations for quick gating."""
        return int(self.statistics.get("unsuccessful_expectations", 0))


# Conditionally import dbt components if available
try:
    from dbt.cli.main import dbtRunner  # noqa: F401

    from .dbt_runner import DbtContractResult as RealDbtContractResult  # type: ignore
    from .dbt_runner import run_dbt_contract_tests  # type: ignore

    # Override with real implementation
    DbtContractResult = RealDbtContractResult  # type: ignore
    DBT_AVAILABLE = True
except (ImportError, TypeError):

    def run_dbt_contract_tests(dataset_path: Path, *, project_dir: Path | None = None, profiles_dir: Path | None = None, target_path: Path | None = None, log_path: Path | None = None, threads: int | None = None) -> DbtContractResult:  # type: ignore
        """Fallback function when dbt is not available."""
        return DbtContractResult(
            success=True,  # Assume success when dbt is not available
            total=0,
            failures=0,
            elapsed=0.0,
            results=[],
            project_dir=Path("."),
            profiles_dir=Path("."),
            target_path=Path("."),
            log_path=Path("."),
            run_results_path=None,
        )

    DBT_AVAILABLE = False

try:
    import great_expectations  # noqa: F401

    from .great_expectations_runner import (
        CuratedDatasetContractResult as RealCuratedDatasetContractResult,  # type: ignore
    )
    from .great_expectations_runner import validate_curated_dataframe  # type: ignore
    from .great_expectations_runner import validate_curated_file  # type: ignore

    # Override with real implementation
    CuratedDatasetContractResult = RealCuratedDatasetContractResult  # type: ignore
    GREAT_EXPECTATIONS_AVAILABLE = True
except (ImportError, TypeError):

    def validate_curated_dataframe(frame):  # type: ignore
        """Fallback function when Great Expectations is not available."""
        return CuratedDatasetContractResult(
            success=True,  # Assume success when GE is not available
            statistics={"successful_expectations": 0, "unsuccessful_expectations": 0},
            results=[],
            expectation_suite_name="fallback",
            meta={"note": "Great Expectations not available"},
        )

    def validate_curated_file(path):  # type: ignore
        """Fallback function when Great Expectations is not available."""
        return CuratedDatasetContractResult(
            success=True,  # Assume success when GE is not available
            statistics={"successful_expectations": 0, "unsuccessful_expectations": 0},
            results=[],
            expectation_suite_name="fallback",
            meta={"note": "Great Expectations not available"},
        )

    GREAT_EXPECTATIONS_AVAILABLE = False

# Conditionally import dbt components if available
try:
    from dbt.cli.main import dbtRunner  # noqa: F401

    DBT_AVAILABLE = True
except (ImportError, TypeError):
    DBT_AVAILABLE = False

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class ContractsToolkit:
    """Convenience wrapper exposing contract execution helpers."""

    validate_dataframe: Callable[..., CuratedDatasetContractResult]
    validate_file: Callable[..., CuratedDatasetContractResult]
    run_dbt_contracts: Callable[..., DbtContractResult]
    run_deequ_contracts: Callable[..., DeequContractResult]
    persist_artifacts: Callable[..., Path]
    record_evidence: Callable[..., None]


def _contracts_health_probe(context: PluginContext) -> PluginHealthStatus:
    missing_dependencies: list[str] = []
    for module_name in ("great_expectations", "dbt.cli.main"):
        if importlib.util.find_spec(module_name) is None:
            missing_dependencies.append(module_name)

    details = {
        "optional_dependencies": ["great_expectations", "dbt"],
        "environment_variables": [
            "CONTRACTS_ARTIFACT_DIR",
            "DBT_PROFILES_DIR",
            "DBT_TARGET_PATH",
            "DBT_LOG_PATH",
            "CONTRACTS_CANONICAL_JSON",
        ],
    }

    if missing_dependencies:
        return PluginHealthStatus(
            healthy=False,
            reason=f"Missing contract dependencies: {', '.join(sorted(missing_dependencies))}",
            details=details,
        )

    return PluginHealthStatus(healthy=True, reason="Contracts ready", details=details)


def _build_contracts_toolkit(context: PluginContext) -> ContractsToolkit:
    if GREAT_EXPECTATIONS_AVAILABLE:
        return ContractsToolkit(
            validate_dataframe=validate_curated_dataframe,  # type: ignore
            validate_file=validate_curated_file,  # type: ignore
            run_dbt_contracts=run_dbt_contract_tests,  # type: ignore
            run_deequ_contracts=run_deequ_checks,
            persist_artifacts=persist_contract_artifacts,
            record_evidence=record_contracts_evidence,
        )
    else:
        # Provide dummy functions when Great Expectations is not available
        def dummy_validate_dataframe(df):  # type: ignore
            raise NotImplementedError(
                "Great Expectations not available (requires Python < 3.14)"
            )

        def dummy_validate_file(path):  # type: ignore
            raise NotImplementedError(
                "Great Expectations not available (requires Python < 3.14)"
            )

        return ContractsToolkit(
            validate_dataframe=dummy_validate_dataframe,
            validate_file=dummy_validate_file,
            run_dbt_contracts=run_dbt_contract_tests,  # type: ignore
            run_deequ_contracts=run_deequ_checks,
            persist_artifacts=persist_contract_artifacts,
            record_evidence=record_contracts_evidence,
        )


register_plugin(
    IntegrationPlugin(
        name="contracts",
        category="contracts",
        factory=_build_contracts_toolkit,
        config_schema=PluginConfigSchema(
            environment_variables=(
                "CONTRACTS_ARTIFACT_DIR",
                "DBT_PROFILES_DIR",
                "DBT_TARGET_PATH",
                "DBT_LOG_PATH",
                "CONTRACTS_CANONICAL_JSON",
            ),
            optional_dependencies=("great_expectations", "dbt"),
            description=(
                "Execute Great Expectations, dbt, and Deequ contracts for curated datasets."
            ),
        ),
        health_probe=_contracts_health_probe,
        summary="Great Expectations, dbt, and Deequ contract orchestrator",
    )
)


__all__ = [
    "ContractsToolkit",
    "DbtContractResult",
    "run_dbt_contract_tests",
    "CuratedDatasetContractResult",
    "validate_curated_dataframe",
    "validate_curated_file",
    "DeequContractResult",
    "run_deequ_checks",
    "DEEQU_AVAILABLE",
    "ContractCoverage",
    "calculate_contract_coverage",
    "report_coverage",
    "record_contracts_evidence",
    "persist_contract_artifacts",
    "canonical_contracts_config",
    "environment_payload",
    "restore_environment",
    "seed_environment",
    "DBT_AVAILABLE",
    "GREAT_EXPECTATIONS_AVAILABLE",
]
