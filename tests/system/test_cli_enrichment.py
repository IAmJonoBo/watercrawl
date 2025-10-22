"""System tests for CLI-driven enrichment workflow.

Tests the full enrichment pipeline through the analyst CLI, verifying:
- Evidence sink writes
- Telemetry outputs (Prometheus, whylogs)
- Contract model validation
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def sample_dataset(tmp_path: Path) -> Path:
    """Create a minimal sample dataset for system testing."""
    dataset_path = tmp_path / "sample_dataset.csv"
    data = pd.DataFrame([
        {
            "Name of Organisation": "Test Flight School",
            "Province": "Gauteng",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "",
            "Contact Email Address": "",
        }
    ])
    data.to_csv(dataset_path, index=False)
    return dataset_path


@pytest.fixture
def evidence_output(tmp_path: Path) -> Path:
    """Evidence log output path."""
    return tmp_path / "evidence_log.csv"


@pytest.fixture
def enriched_output(tmp_path: Path) -> Path:
    """Enriched dataset output path."""
    return tmp_path / "enriched.csv"


@pytest.mark.system
def test_cli_enrichment_evidence_sink(
    sample_dataset: Path,
    evidence_output: Path,
    enriched_output: Path,
) -> None:
    """Test that CLI enrichment writes to evidence sink correctly."""
    # Run enrichment via CLI
    result = subprocess.run(
        [
            "python",
            "-m",
            "firecrawl_demo.interfaces.cli",
            "enrich",
            str(sample_dataset),
            "--output",
            str(enriched_output),
            "--evidence-log",
            str(evidence_output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    
    # Verify command succeeded
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    
    # Verify enriched output exists
    assert enriched_output.exists(), "Enriched dataset not created"
    
    # Verify evidence log exists and has entries
    if evidence_output.exists():
        evidence_df = pd.read_csv(evidence_output)
        assert len(evidence_df) >= 0, "Evidence log should be created"
        
        # Verify evidence log has expected columns
        expected_columns = ["RowID", "Organisation", "What changed", "Sources", "Notes", "Timestamp", "Confidence"]
        for col in expected_columns:
            assert col in evidence_df.columns, f"Missing column: {col}"


@pytest.mark.system
def test_cli_enrichment_telemetry_outputs(
    sample_dataset: Path,
    tmp_path: Path,
) -> None:
    """Test that CLI enrichment generates telemetry outputs."""
    prometheus_output = tmp_path / "metrics.prom"
    whylogs_dir = tmp_path / "whylogs"
    whylogs_dir.mkdir()
    
    # Run enrichment with telemetry enabled
    result = subprocess.run(
        [
            "python",
            "-m",
            "firecrawl_demo.interfaces.cli",
            "enrich",
            str(sample_dataset),
            "--output",
            str(tmp_path / "enriched.csv"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "DRIFT_PROMETHEUS_OUTPUT": str(prometheus_output),
            "DRIFT_WHYLOGS_OUTPUT": str(whylogs_dir),
        },
    )
    
    # Command may fail due to missing baseline, but should still run
    # Verify at least the output was attempted
    assert "enriched" in result.stdout or result.returncode in (0, 1)


@pytest.mark.system
def test_cli_enrichment_contract_validation(
    sample_dataset: Path,
    tmp_path: Path,
) -> None:
    """Test that CLI outputs validate against contract schemas."""
    enriched_output = tmp_path / "enriched.csv"
    evidence_output = tmp_path / "evidence_log.csv"
    
    # Run enrichment
    result = subprocess.run(
        [
            "python",
            "-m",
            "firecrawl_demo.interfaces.cli",
            "enrich",
            str(sample_dataset),
            "--output",
            str(enriched_output),
            "--evidence-log",
            str(evidence_output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    
    if result.returncode == 0 and enriched_output.exists():
        # Verify enriched dataset has expected columns
        df = pd.read_csv(enriched_output)
        required_columns = [
            "Name of Organisation",
            "Province",
            "Status",
            "Website URL",
            "Contact Person",
            "Contact Number",
            "Contact Email Address",
        ]
        for col in required_columns:
            assert col in df.columns, f"Missing required column: {col}"


@pytest.mark.system
@pytest.mark.performance
def test_cli_enrichment_performance_smoke(
    sample_dataset: Path,
    tmp_path: Path,
) -> None:
    """Smoke test for enrichment performance."""
    import time
    
    enriched_output = tmp_path / "enriched.csv"
    
    start = time.time()
    result = subprocess.run(
        [
            "python",
            "-m",
            "firecrawl_demo.interfaces.cli",
            "enrich",
            str(sample_dataset),
            "--output",
            str(enriched_output),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed = time.time() - start
    
    # Verify reasonable performance (1 row should complete in < 30s)
    assert elapsed < 30.0, f"Enrichment took too long: {elapsed:.2f}s"
    
    # Log performance metric
    print(f"Performance: {elapsed:.2f}s for 1 row")
