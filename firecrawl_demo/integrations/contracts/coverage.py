"""Contract coverage tracking for curated datasets.

This module tracks which tables have contracts defined and reports coverage
metrics to ensure ≥95% of curated tables are covered by quality checks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from firecrawl_demo.core import config


@dataclass
class ContractCoverage:
    """Coverage metrics for contract enforcement.

    Attributes:
        total_tables: Total number of curated tables tracked.
        covered_tables: Number of tables with contracts defined.
        coverage_percent: Percentage of tables covered by contracts.
        uncovered_tables: List of table names without contracts.
        coverage_by_tool: Dictionary mapping tool names to coverage counts.
    """

    total_tables: int
    covered_tables: int
    coverage_percent: float
    uncovered_tables: list[str]
    coverage_by_tool: dict[str, int]

    @property
    def meets_threshold(self) -> bool:
        """Check if coverage meets the 95% threshold."""
        return self.coverage_percent >= 95.0


def _discover_curated_tables() -> list[str]:
    """Discover all curated tables that should have contracts.

    Returns:
        List of table names (e.g., dataset names from data/processed/).

    For Phase 1, we track the sample dataset as the primary curated table.
    Future iterations will scan the data/processed/ directory for additional
    curated exports.
    """
    # For now, we have one primary curated dataset: sample.csv
    curated_tables = ["sample"]

    # Future: scan data/processed/ for additional tables
    processed_dir = config.DATA_DIR / "processed"
    if processed_dir.exists():
        for csv_file in processed_dir.glob("*.csv"):
            table_name = csv_file.stem
            if table_name not in curated_tables:
                curated_tables.append(table_name)

    return curated_tables


def _check_great_expectations_coverage(table_name: str) -> bool:
    """Check if Great Expectations suite exists for the table.

    Args:
        table_name: Name of the table to check.

    Returns:
        True if an expectation suite exists for this table.
    """
    ge_root = config.PROJECT_ROOT / "data_contracts" / "great_expectations"
    expectations_dir = ge_root / "expectations"

    # Check for table-specific or generic curated_dataset expectation suite
    table_suite = expectations_dir / f"{table_name}.json"
    generic_suite = expectations_dir / "curated_dataset.json"

    return table_suite.exists() or generic_suite.exists()


def _check_dbt_coverage(table_name: str) -> bool:
    """Check if dbt models/tests exist for the table.

    Args:
        table_name: Name of the table to check.

    Returns:
        True if dbt models exist for this table.
    """
    dbt_root = config.PROJECT_ROOT / "data_contracts" / "analytics"
    models_dir = dbt_root / "models" / "staging"

    # Check for table-specific or generic staging model
    table_model = models_dir / f"stg_{table_name}.sql"
    generic_model = models_dir / "stg_curated_dataset.sql"

    return table_model.exists() or generic_model.exists()


def _check_deequ_coverage(table_name: str) -> bool:
    """Check if Deequ checks exist for the table.

    Args:
        table_name: Name of the table to check.

    Returns:
        True if Deequ checks exist for this table.
    """
    deequ_root = config.PROJECT_ROOT / "data_contracts" / "deequ"

    # Check for Deequ configuration files
    # For now, return False as Deequ is not yet fully implemented
    table_config = deequ_root / f"{table_name}.json"
    return table_config.exists()


def calculate_contract_coverage() -> ContractCoverage:
    """Calculate contract coverage across all curated tables.

    Returns:
        ContractCoverage with metrics and uncovered table list.
    """
    curated_tables = _discover_curated_tables()
    total_tables = len(curated_tables)

    covered_tables: set[str] = set()
    uncovered_tables: list[str] = []
    coverage_by_tool: dict[str, int] = {
        "great_expectations": 0,
        "dbt": 0,
        "deequ": 0,
    }

    for table in curated_tables:
        has_ge = _check_great_expectations_coverage(table)
        has_dbt = _check_dbt_coverage(table)
        has_deequ = _check_deequ_coverage(table)

        if has_ge:
            coverage_by_tool["great_expectations"] += 1
        if has_dbt:
            coverage_by_tool["dbt"] += 1
        if has_deequ:
            coverage_by_tool["deequ"] += 1

        # A table is considered covered if it has at least one contract tool
        if has_ge or has_dbt or has_deequ:
            covered_tables.add(table)
        else:
            uncovered_tables.append(table)

    coverage_percent = (
        (len(covered_tables) / total_tables * 100.0) if total_tables > 0 else 0.0
    )

    return ContractCoverage(
        total_tables=total_tables,
        covered_tables=len(covered_tables),
        coverage_percent=coverage_percent,
        uncovered_tables=uncovered_tables,
        coverage_by_tool=coverage_by_tool,
    )


def report_coverage(output_path: Path | None = None) -> dict[str, Any]:
    """Generate a contract coverage report.

    Args:
        output_path: Optional path to write JSON report to disk.

    Returns:
        Dictionary containing coverage metrics and details.
    """
    coverage = calculate_contract_coverage()

    report = {
        "total_tables": coverage.total_tables,
        "covered_tables": coverage.covered_tables,
        "coverage_percent": round(coverage.coverage_percent, 2),
        "meets_threshold": coverage.meets_threshold,
        "threshold": 95.0,
        "uncovered_tables": coverage.uncovered_tables,
        "coverage_by_tool": coverage.coverage_by_tool,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True))

    return report
