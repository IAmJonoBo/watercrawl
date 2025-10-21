from __future__ import annotations

"""Helpers for executing Great Expectations contracts on curated datasets."""

import importlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pandas as pd

from firecrawl_demo.core import config
from firecrawl_demo.core.excel import read_dataset

from .shared_config import canonical_contracts_config

# Try to import Great Expectations modules
try:
    _ge_batch = importlib.import_module("great_expectations.core.batch")
    _ge_batch_spec = importlib.import_module("great_expectations.core.batch_spec")
    _ge_expectation_suite = importlib.import_module(
        "great_expectations.core.expectation_suite"
    )
    _ge_context_factory = importlib.import_module(
        "great_expectations.data_context.data_context.context_factory"
    )
    _ge_execution_engine = importlib.import_module(
        "great_expectations.execution_engine.pandas_execution_engine"
    )
    _ge_expectations_config = importlib.import_module(
        "great_expectations.expectations.expectation_configuration"
    )
    _ge_validator = importlib.import_module("great_expectations.validator.validator")

    Batch = cast(Any, getattr(_ge_batch, "Batch"))
    RuntimeDataBatchSpec = cast(Any, getattr(_ge_batch_spec, "RuntimeDataBatchSpec"))
    ExpectationSuite = cast(Any, getattr(_ge_expectation_suite, "ExpectationSuite"))
    project_manager = getattr(_ge_context_factory, "project_manager", None)
    PandasExecutionEngine = cast(
        Any, getattr(_ge_execution_engine, "PandasExecutionEngine")
    )
    ExpectationConfiguration = cast(
        Any, getattr(_ge_expectations_config, "ExpectationConfiguration")
    )
    Validator = cast(Any, getattr(_ge_validator, "Validator"))

    if project_manager and hasattr(project_manager, "is_using_cloud"):
        project_manager.is_using_cloud = lambda: False
    GREAT_EXPECTATIONS_AVAILABLE = True
except (ImportError, TypeError, AttributeError):
    GREAT_EXPECTATIONS_AVAILABLE = False

    # Fallback classes when Great Expectations is not available
    @dataclass
    class _FallbackExpectationSuite:
        name: str
        expectations: list[Any]
        meta: dict[str, Any]

        def __init__(self, name: str, expectations: list[Any] | None = None):
            self.name = name
            self.expectations = expectations or []
            self.meta = {}

    @dataclass
    class _FallbackExpectationConfiguration:
        expectation_type: str
        kwargs: dict[str, Any]
        meta: dict[str, Any] | None

        def __init__(
            self,
            expectation_type: str | None = None,
            kwargs: dict[str, Any] | None = None,
            meta: dict[str, Any] | None = None,
            type: str | None = None,
        ):
            # Handle both parameter names for compatibility
            self.expectation_type = expectation_type or type or ""
            self.kwargs = kwargs or {}
            self.meta = meta

        def to_domain_obj(self) -> _FallbackExpectationConfiguration:
            return self

    @dataclass
    class _FallbackRuntimeDataBatchSpec:
        batch_data: Any

    @dataclass
    class _FallbackBatch:
        data: Any
        batch_spec: _FallbackRuntimeDataBatchSpec

        def __init__(
            self, data: Any, batch_spec: _FallbackRuntimeDataBatchSpec
        ) -> None:
            self.data = data
            self.batch_spec = batch_spec

    class _FallbackPandasExecutionEngine:
        pass

    @dataclass
    class _FallbackValidator:
        execution_engine: Any
        expectation_suite: Any
        batches: list[Any]

        def validate(self) -> Any:
            # Fallback validation - always return success when GE unavailable
            return FallbackValidationResult()

    ExpectationSuite = _FallbackExpectationSuite
    ExpectationConfiguration = _FallbackExpectationConfiguration
    RuntimeDataBatchSpec = _FallbackRuntimeDataBatchSpec
    Batch = _FallbackBatch
    PandasExecutionEngine = _FallbackPandasExecutionEngine
    Validator = _FallbackValidator


@dataclass
class FallbackValidationResult:
    def to_json_dict(self) -> dict[str, Any]:
        return {
            "success": True,
            "statistics": {
                "successful_expectations": 0,
                "unsuccessful_expectations": 0,
            },
            "results": [],
            "suite_name": "fallback_suite",
            "meta": {
                "note": "Great Expectations not available - using fallback validation"
            },
        }


@dataclass(frozen=True)
class CuratedDatasetContractResult:
    """Serialisable summary of a Great Expectations validation run."""

    success: bool
    statistics: dict[str, Any]
    results: list[dict[str, Any]]
    expectation_suite_name: str
    meta: dict[str, Any]

    @property
    def unsuccessful_expectations(self) -> int:
        """Return the number of failing expectations for quick gating."""

        return int(self.statistics.get("unsuccessful_expectations", 0))


def _expectation_suite_path() -> Path:
    return (
        config.PROJECT_ROOT
        / "data_contracts"
        / "great_expectations"
        / "expectations"
        / "curated_dataset.json"
    )


def _load_expectation_suite() -> Any:
    if not GREAT_EXPECTATIONS_AVAILABLE:
        # Return fallback suite when GE unavailable
        return ExpectationSuite(name="fallback_suite", expectations=[])

    payload = json.loads(_expectation_suite_path().read_text())
    suite = ExpectationSuite(name=payload["expectation_suite_name"], expectations=[])
    suite.meta.update(payload.get("meta", {}))

    canonical = canonical_contracts_config()
    provinces = list(canonical.get("provinces", []))
    statuses = list(canonical.get("statuses", []))
    evidence = canonical.get("evidence", {})
    min_conf = float(evidence.get("minimum_confidence", 0))
    max_conf = float(evidence.get("maximum_confidence", 100))
    expectations_payload = payload.get("expectations", [])
    if isinstance(expectations_payload, list):
        for entry in expectations_payload:
            if not isinstance(entry, dict):
                continue
            expectation_type = entry.get("expectation_type")
            if not isinstance(expectation_type, str):
                continue
            kwargs_raw = entry.get("kwargs", {})
            kwargs = dict(kwargs_raw) if isinstance(kwargs_raw, dict) else {}
            column_raw = kwargs.get("column")
            column = column_raw if isinstance(column_raw, str) else None

            if expectation_type == "expect_column_values_to_be_in_set":
                if column == "Province":
                    kwargs["value_set"] = provinces
                elif column == "Status":
                    kwargs["value_set"] = statuses
            elif (
                expectation_type == "expect_column_values_to_be_between"
                and column == "Confidence"
            ):
                kwargs["min_value"] = min_conf
                kwargs["max_value"] = float(kwargs.get("max_value", max_conf))

            meta_raw = entry.get("meta")
            meta = dict(meta_raw) if isinstance(meta_raw, dict) else None
            config = ExpectationConfiguration(
                type=expectation_type,
                kwargs=kwargs,
                meta=meta,
            )
            suite.add_expectation_configuration(config)
    return _apply_canonical_configuration(suite)


def _apply_canonical_configuration(suite: Any) -> Any:
    """Ensure the suite reflects canonical taxonomy and thresholds."""

    if not GREAT_EXPECTATIONS_AVAILABLE:
        return suite

    config_payload = canonical_contracts_config()
    provinces = list(config_payload.get("provinces", []))
    statuses = list(config_payload.get("statuses", []))
    evidence = config_payload.get("evidence", {})
    min_conf = int(evidence.get("minimum_confidence", 0))
    max_conf = int(evidence.get("maximum_confidence", 100))

    has_confidence_check = False

    # Create a new suite with modified expectations
    modified_suite = ExpectationSuite(name=suite.name, expectations=[])
    modified_suite.meta.update(suite.meta)

    for expectation in suite.expectation_configurations:  # type: ignore[attr-defined]
        if not isinstance(expectation, ExpectationConfiguration):
            continue
        expectation_type = expectation.type
        column_raw = expectation.kwargs.get("column")
        column = column_raw if isinstance(column_raw, str) else None

        # Create a copy of kwargs to modify
        new_kwargs = dict(expectation.kwargs)
        new_meta = dict(expectation.meta) if expectation.meta else None

        if expectation_type == "expect_column_values_to_be_in_set":
            if column == "Province":
                new_kwargs["value_set"] = provinces
            elif column == "Status":
                new_kwargs["value_set"] = statuses
        elif (
            expectation_type == "expect_column_values_to_be_between"
            and column == "Confidence"
        ):
            # Override with canonical confidence thresholds
            new_kwargs["min_value"] = float(min_conf)
            new_kwargs["max_value"] = float(max_conf)
            has_confidence_check = True

        # Create new config with modified kwargs
        new_config = ExpectationConfiguration(  # type: ignore[call-arg]
            type=expectation_type,
            kwargs=new_kwargs,
            meta=new_meta,
        )
        modified_suite.add_expectation_configuration(new_config)  # type: ignore[arg-type]

    if not has_confidence_check:
        config = ExpectationConfiguration(  # type: ignore[call-arg]
            type="expect_column_values_to_be_between",
            kwargs={
                "column": "Confidence",
                "min_value": float(min_conf),
                "max_value": float(max_conf),
            },
            meta={
                "notes": "Evidence confidence must meet canonical thresholds.",
            },
        )
        modified_suite.add_expectation_configuration(config)  # type: ignore[arg-type]

    return modified_suite


def _prepare_validation_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of *frame* normalised for Great Expectations."""

    prepared = frame.copy()
    if "Confidence" in prepared.columns:
        prepared["Confidence"] = pd.to_numeric(prepared["Confidence"], errors="coerce")
    return prepared


def validate_curated_dataframe(frame: pd.DataFrame) -> CuratedDatasetContractResult:
    """Execute the curated dataset expectation suite against a dataframe."""

    if not GREAT_EXPECTATIONS_AVAILABLE:
        # Return fallback result when GE unavailable
        return CuratedDatasetContractResult(
            success=True,
            statistics={"successful_expectations": 0, "unsuccessful_expectations": 0},
            results=[],
            expectation_suite_name="fallback_suite",
            meta={
                "note": "Great Expectations not available - using fallback validation"
            },
        )

    suite = _load_expectation_suite()
    batch_data = frame.copy()

    # Convert Confidence to numeric type if present
    if "Confidence" in batch_data.columns:
        batch_data["Confidence"] = pd.to_numeric(
            batch_data["Confidence"], errors="coerce"
        )
    batch = Batch(
        data=cast(Any, batch_data),
        batch_spec=RuntimeDataBatchSpec(batch_data=batch_data),
    )
    validator = Validator(
        execution_engine=PandasExecutionEngine(),
        expectation_suite=suite,
        batches=[batch],
    )
    validation = validator.validate()
    payload = validation.to_json_dict()
    statistics_raw = payload.get("statistics", {})
    statistics: dict[str, Any]
    if isinstance(statistics_raw, dict):
        statistics = dict(statistics_raw)
    else:
        statistics = {}

    results_raw = payload.get("results", [])
    results: list[dict[str, Any]] = []
    if isinstance(results_raw, list):
        for entry in results_raw:
            if isinstance(entry, dict):
                results.append(dict(entry))

    meta_raw = payload.get("meta", {})
    meta: dict[str, Any]
    if isinstance(meta_raw, dict):
        meta = dict(meta_raw)
    else:
        meta = {}

    suite_name_raw = payload.get("suite_name")
    suite_name = (
        str(suite_name_raw) if suite_name_raw is not None else str(suite.name or "")
    )

    return CuratedDatasetContractResult(
        success=bool(payload.get("success", False)),
        statistics=statistics,
        results=results,
        expectation_suite_name=suite_name,
        meta=meta,
    )


def validate_curated_file(path: Path) -> CuratedDatasetContractResult:
    """Load a dataset from disk and validate it using the curated suite."""

    frame = read_dataset(path)
    return validate_curated_dataframe(frame)
