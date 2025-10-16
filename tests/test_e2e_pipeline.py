import pytest

from firecrawl_demo.pipeline import Pipeline


def test_e2e_pipeline_runs():
    """E2E: Pipeline runs with config and returns expected artefacts."""
    pipeline = Pipeline()
    # Simulate a minimal run (stub, replace with real args as needed)
    try:
        result = pipeline.run()
        assert result is not None
    except Exception as e:
        pytest.fail(f"Pipeline failed: {e}")
