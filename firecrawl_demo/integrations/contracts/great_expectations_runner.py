"""Helpers for executing Great Expectations contracts on curated datasets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pandas as pd
from great_expectations.core.batch import Batch
from great_expectations.core.batch_spec import RuntimeDataBatchSpec
from great_expectations.core.expectation_suite import ExpectationSuite
from great_expectations.data_context.data_context.context_factory import project_manager
from great_expectations.execution_engine.pandas_execution_engine import (
    PandasExecutionEngine,
)
from great_expectations.expectations.expectation_configuration import (
    ExpectationConfiguration,
)
from great_expectations.validator.validator import Validator

from firecrawl_demo.core import config
from firecrawl_demo.core.excel import read_dataset

from .shared_config import canonical_contracts_config

project_manager.is_using_cloud = lambda: False  # type: ignore[assignment]


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


def _load_expectation_suite() -> ExpectationSuite:
    payload = json.loads(_expectation_suite_path().read_text())
    suite = ExpectationSuite(name=payload["expectation_suite_name"], expectations=[])
    suite.meta.update(payload.get("meta", {}))
    suite.expectations.extend(
        [
            ExpectationConfiguration(
                type=entry["expectation_type"],
                kwargs=entry.get("kwargs", {}),
                meta=entry.get("meta"),
            ).to_domain_obj()
            for entry in payload.get("expectations", [])
        ]
    )
    return _apply_canonical_configuration(suite)


def _apply_canonical_configuration(suite: ExpectationSuite) -> ExpectationSuite:
    """Ensure the suite reflects canonical taxonomy and thresholds."""

    config_payload = canonical_contracts_config()
    provinces = list(config_payload.get("provinces", []))
    statuses = list(config_payload.get("statuses", []))
    evidence = config_payload.get("evidence", {})
    min_conf = int(evidence.get("minimum_confidence", 0))
    max_conf = int(evidence.get("maximum_confidence", 100))

    has_confidence_check = False

    for expectation in suite.expectations:
        expectation_type = getattr(expectation, "expectation_type", "")
        column = expectation.kwargs.get("column") if hasattr(expectation, "kwargs") else None

        if expectation_type == "expect_column_values_to_be_in_set":
            if column == "Province":
                expectation.kwargs["value_set"] = provinces
            elif column == "Status":
                expectation.kwargs["value_set"] = statuses
        elif expectation_type == "expect_column_values_to_be_between" and column == "Confidence":
            expectation.kwargs["min_value"] = min_conf
            expectation.kwargs.setdefault("max_value", max_conf)
            has_confidence_check = True

    if not has_confidence_check:
        suite.expectations.append(
            ExpectationConfiguration(
                type="expect_column_values_to_be_between",
                kwargs={
                    "column": "Confidence",
                    "min_value": min_conf,
                    "max_value": max_conf,
                },
                meta={
                    "notes": "Evidence confidence must meet canonical thresholds.",
                },
            ).to_domain_obj()
        )

    return suite


def validate_curated_dataframe(frame: pd.DataFrame) -> CuratedDatasetContractResult:
    """Execute the curated dataset expectation suite against a dataframe."""

    suite = _load_expectation_suite()
    batch_data = frame.copy()
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
