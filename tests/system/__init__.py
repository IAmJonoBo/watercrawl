"""System integration tests for the Watercrawl enrichment pipeline.

These tests drive the analyst CLI against sample datasets and verify:
- Evidence sink writes
- Telemetry outputs (Prometheus, whylogs)
- Contract model validation
"""
