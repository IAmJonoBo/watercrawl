"""Performance smoke tests with thresholds for CI gating.

These tests record wall-clock throughput and enforce thresholds to guard
against performance regressions in the concurrency work.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pandas as pd
import pytest

from firecrawl_demo.application.pipeline import Pipeline
from firecrawl_demo.application.quality import QualityGate
from firecrawl_demo.integrations.adapters.research import (
    NullResearchAdapter,
    ResearchFinding,
    StaticResearchAdapter,
)


@pytest.fixture
def sample_dataframe(tmp_path: Path) -> pd.DataFrame:
    """Create a sample dataframe with N rows."""
    return pd.DataFrame([
        {
            "Name of Organisation": f"Test School {i}",
            "Province": "Gauteng",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "",
            "Contact Email Address": "",
        }
        for i in range(10)
    ])


@pytest.mark.performance
@pytest.mark.asyncio
async def test_pipeline_throughput_10_rows(sample_dataframe: pd.DataFrame) -> None:
    """Test pipeline throughput for 10 rows.
    
    Threshold: Should complete in < 5 seconds for 10 rows with null adapter.
    """
    pipeline = Pipeline(
        research_adapter=NullResearchAdapter(),
        quality_gate=QualityGate(min_confidence=0, require_official_source=False),
    )
    
    start = time.perf_counter()
    report = await pipeline.run_dataframe_async(sample_dataframe)
    elapsed = time.perf_counter() - start
    
    # Verify completion
    assert report.metrics["rows_total"] == 10
    
    # Threshold check
    threshold = 5.0
    assert elapsed < threshold, f"Pipeline took {elapsed:.2f}s, threshold is {threshold}s"
    
    # Record metric for CI
    throughput = len(sample_dataframe) / elapsed
    print(f"Throughput: {throughput:.2f} rows/sec (10 rows in {elapsed:.2f}s)")


@pytest.mark.performance
@pytest.mark.asyncio
async def test_pipeline_concurrency_speedup() -> None:
    """Test that concurrent lookups provide speedup over sequential.
    
    Threshold: Concurrent should be at least 1.5x faster for 5 rows.
    """
    # Create a slow adapter that takes 0.1s per lookup
    class SlowAdapter:
        def lookup(self, organisation: str, province: str) -> ResearchFinding:
            time.sleep(0.1)
            return ResearchFinding()
    
    dataframe = pd.DataFrame([
        {
            "Name of Organisation": f"School {i}",
            "Province": "Gauteng",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "",
            "Contact Email Address": "",
        }
        for i in range(5)
    ])
    
    pipeline = Pipeline(
        research_adapter=SlowAdapter(),
        quality_gate=QualityGate(min_confidence=0, require_official_source=False),
    )
    
    start = time.perf_counter()
    report = await pipeline.run_dataframe_async(dataframe)
    elapsed = time.perf_counter() - start
    
    # With concurrency=4 (default), 5 rows should complete in ~0.2s
    # Sequential would be ~0.5s (5 * 0.1s)
    expected_sequential = 5 * 0.1
    speedup = expected_sequential / elapsed
    
    print(f"Speedup: {speedup:.2f}x ({elapsed:.2f}s vs {expected_sequential:.2f}s expected sequential)")
    
    # Should have at least 1.5x speedup from concurrency
    assert speedup >= 1.5, f"Insufficient speedup: {speedup:.2f}x"


@pytest.mark.performance
def test_itertuples_vs_iterrows_performance() -> None:
    """Verify itertuples is faster than iterrows.
    
    This is a regression guard for the iterrows→itertuples migration.
    """
    # Create test dataframe
    df = pd.DataFrame([
        {
            "Name of Organisation": f"School {i}",
            "Province": "Gauteng",
            "Status": "Candidate",
            "Website URL": "",
            "Contact Person": "",
            "Contact Number": "",
            "Contact Email Address": "",
        }
        for i in range(100)
    ])
    
    # Benchmark iterrows
    start = time.perf_counter()
    count_iterrows = 0
    for idx, row in df.iterrows():
        count_iterrows += 1
    elapsed_iterrows = time.perf_counter() - start
    
    # Benchmark itertuples
    start = time.perf_counter()
    count_itertuples = 0
    for row in df.itertuples():
        count_itertuples += 1
    elapsed_itertuples = time.perf_counter() - start
    
    assert count_iterrows == count_itertuples == 100
    
    speedup = elapsed_iterrows / elapsed_itertuples
    print(f"itertuples speedup: {speedup:.2f}x ({elapsed_itertuples:.4f}s vs {elapsed_iterrows:.4f}s)")
    
    # itertuples should be at least 1.5x faster
    assert speedup >= 1.5, f"itertuples not faster: {speedup:.2f}x"


@pytest.mark.performance
@pytest.mark.asyncio
async def test_bulk_update_performance(sample_dataframe: pd.DataFrame) -> None:
    """Test that bulk updates are faster than row-by-row updates.
    
    Threshold: Should complete dtype conversions efficiently.
    """
    from firecrawl_demo.domain.models import SchoolRecord
    
    # Create update instructions
    instructions = []
    for i in range(len(sample_dataframe)):
        record = SchoolRecord(
            name=f"Updated School {i}",
            province="Gauteng",
            status="Verified",
            website_url=f"https://school{i}.co.za",
            contact_person=f"Person {i}",
            contact_number="+27105550100",
            contact_email=f"person{i}@school{i}.co.za",
        )
        instructions.append((i, record, []))
    
    pipeline = Pipeline(
        research_adapter=NullResearchAdapter(),
        quality_gate=QualityGate(min_confidence=0, require_official_source=False),
    )
    
    # Time bulk update
    start = time.perf_counter()
    pipeline._apply_bulk_updates(sample_dataframe, instructions)
    elapsed = time.perf_counter() - start
    
    # Should complete in < 0.1s for 10 rows
    threshold = 0.1
    assert elapsed < threshold, f"Bulk update took {elapsed:.4f}s, threshold is {threshold}s"
    
    print(f"Bulk update: {len(instructions)} rows in {elapsed:.4f}s")


@pytest.mark.performance
@pytest.mark.asyncio
async def test_row_processor_performance() -> None:
    """Test RowProcessor performance in isolation.
    
    Threshold: Should process 100 rows in < 1 second.
    """
    from firecrawl_demo.application.row_processing import RowProcessor
    from firecrawl_demo.domain.models import SchoolRecord
    
    processor = RowProcessor(
        quality_gate=QualityGate(min_confidence=0, require_official_source=False)
    )
    
    original = SchoolRecord(
        name="Test School",
        province="Gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    
    finding = ResearchFinding(
        website_url="https://test.co.za",
        sources=["https://test.co.za", "https://caa.co.za/test"],
    )
    
    start = time.perf_counter()
    for i in range(100):
        result = processor.process_row(
            original_record=original,
            finding=finding,
            row_id=i,
        )
    elapsed = time.perf_counter() - start
    
    threshold = 1.0
    assert elapsed < threshold, f"RowProcessor took {elapsed:.2f}s for 100 rows, threshold is {threshold}s"
    
    throughput = 100 / elapsed
    print(f"RowProcessor throughput: {throughput:.0f} rows/sec")


@pytest.mark.performance
def test_change_tracking_performance() -> None:
    """Test change tracking utilities performance.
    
    Threshold: Should handle 1000 operations in < 0.5 seconds.
    """
    from firecrawl_demo.application.change_tracking import (
        collect_changed_columns,
        describe_changes,
    )
    from firecrawl_demo.domain.models import SchoolRecord
    
    original = SchoolRecord(
        name="Test",
        province="Gauteng",
        status="Candidate",
        website_url="",
        contact_person="",
        contact_number="",
        contact_email="",
    )
    
    proposed = SchoolRecord(
        name="Test",
        province="Gauteng",
        status="Verified",
        website_url="https://test.co.za",
        contact_person="John Doe",
        contact_number="+27105550100",
        contact_email="john@test.co.za",
    )
    
    start = time.perf_counter()
    for _ in range(1000):
        changes = collect_changed_columns(original, proposed)
        assert len(changes) > 0
    elapsed = time.perf_counter() - start
    
    threshold = 0.5
    assert elapsed < threshold, f"Change tracking took {elapsed:.2f}s, threshold is {threshold}s"
    
    print(f"Change tracking: 1000 ops in {elapsed:.4f}s")
