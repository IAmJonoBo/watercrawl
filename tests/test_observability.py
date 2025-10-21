"""Tests for OpenTelemetry observability integration."""

from __future__ import annotations

import time

import pytest

from firecrawl_demo.integrations.observability import (
    ObservabilityConfig,
    ObservabilityManager,
    SLOMetrics,
    create_default_manager,
)


class TestSLOMetrics:
    """Test SLO metrics tracking."""

    def test_tracks_successful_requests(self) -> None:
        metrics = SLOMetrics()

        metrics.add_request(success=True, latency_ms=100, target_latency_ms=1000)

        assert metrics.total_requests == 1
        assert metrics.successful_requests == 1
        assert metrics.failed_requests == 0

    def test_tracks_failed_requests(self) -> None:
        metrics = SLOMetrics()

        metrics.add_request(success=False, latency_ms=100, target_latency_ms=1000)

        assert metrics.total_requests == 1
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 1

    def test_calculates_availability(self) -> None:
        metrics = SLOMetrics()

        metrics.add_request(success=True, latency_ms=100, target_latency_ms=1000)
        metrics.add_request(success=True, latency_ms=200, target_latency_ms=1000)
        metrics.add_request(success=False, latency_ms=300, target_latency_ms=1000)

        assert metrics.availability() == 2.0 / 3.0

    def test_calculates_latency_sli(self) -> None:
        metrics = SLOMetrics()

        # Two within SLO, one exceeds
        metrics.add_request(success=True, latency_ms=500, target_latency_ms=1000)
        metrics.add_request(success=True, latency_ms=800, target_latency_ms=1000)
        metrics.add_request(success=True, latency_ms=1500, target_latency_ms=1000)

        assert metrics.latency_sli() == 2.0 / 3.0

    def test_calculates_error_rate(self) -> None:
        metrics = SLOMetrics()

        for _ in range(97):
            metrics.add_request(success=True, latency_ms=100, target_latency_ms=1000)
        for _ in range(3):
            metrics.add_request(success=False, latency_ms=100, target_latency_ms=1000)

        assert metrics.error_rate() == pytest.approx(0.03, abs=0.001)

    def test_calculates_avg_latency(self) -> None:
        metrics = SLOMetrics()

        metrics.add_request(success=True, latency_ms=100, target_latency_ms=1000)
        metrics.add_request(success=True, latency_ms=200, target_latency_ms=1000)
        metrics.add_request(success=True, latency_ms=300, target_latency_ms=1000)

        assert metrics.avg_latency_ms() == 200.0

    def test_calculates_error_budget(self) -> None:
        metrics = SLOMetrics()

        # 1% error rate with 2% target = 50% budget remaining
        for _ in range(99):
            metrics.add_request(success=True, latency_ms=100, target_latency_ms=1000)
        metrics.add_request(success=False, latency_ms=100, target_latency_ms=1000)

        budget = metrics.error_budget_remaining(target_error_rate=0.02)
        assert budget == pytest.approx(0.5, abs=0.01)

    def test_zero_budget_when_exceeded(self) -> None:
        metrics = SLOMetrics()

        # 5% error rate with 2% target = 0% budget
        for _ in range(95):
            metrics.add_request(success=True, latency_ms=100, target_latency_ms=1000)
        for _ in range(5):
            metrics.add_request(success=False, latency_ms=100, target_latency_ms=1000)

        budget = metrics.error_budget_remaining(target_error_rate=0.02)
        assert budget == 0.0

    def test_handles_zero_requests(self) -> None:
        metrics = SLOMetrics()

        assert metrics.availability() == 1.0
        assert metrics.latency_sli() == 1.0
        assert metrics.error_rate() == 0.0
        assert metrics.avg_latency_ms() == 0.0


class TestObservabilityManager:
    """Test observability manager."""

    def test_initializes_successfully(self) -> None:
        config = ObservabilityConfig(
            enable_tracing=False,  # Disable to avoid OTLP connection
            enable_metrics=False,
        )
        manager = ObservabilityManager(config)

        manager.initialize()
        assert manager.initialized is True

        manager.shutdown()

    def test_traces_operation(self) -> None:
        config = ObservabilityConfig(
            enable_tracing=False,
            enable_metrics=False,
        )
        manager = ObservabilityManager(config)
        manager.initialize()

        with manager.trace_operation("test_op") as span:
            time.sleep(0.01)

        # Should record the operation
        assert manager.slo_metrics.total_requests == 1
        assert manager.slo_metrics.successful_requests == 1

        manager.shutdown()

    def test_traces_failed_operation(self) -> None:
        config = ObservabilityConfig(
            enable_tracing=False,
            enable_metrics=False,
        )
        manager = ObservabilityManager(config)
        manager.initialize()

        with pytest.raises(ValueError):
            with manager.trace_operation("failing_op"):
                raise ValueError("Test error")

        # Should record the failure
        assert manager.slo_metrics.total_requests == 1
        assert manager.slo_metrics.failed_requests == 1

        manager.shutdown()

    def test_records_attributes(self) -> None:
        config = ObservabilityConfig(
            enable_tracing=False,
            enable_metrics=False,
        )
        manager = ObservabilityManager(config)
        manager.initialize()

        attrs = {"dataset": "sample.csv", "size": 100}
        with manager.trace_operation("enrich", attributes=attrs) as span:
            pass

        assert manager.slo_metrics.total_requests == 1

        manager.shutdown()

    def test_gets_slo_status(self) -> None:
        config = ObservabilityConfig(
            enable_tracing=False,
            enable_metrics=False,
            enable_slos=True,
        )
        manager = ObservabilityManager(config)
        manager.initialize()

        # Simulate some requests
        manager.slo_metrics.add_request(True, 100, 1000)
        manager.slo_metrics.add_request(True, 200, 1000)
        manager.slo_metrics.add_request(False, 300, 1000)

        status = manager.get_slo_status()

        assert "metrics" in status
        assert "compliance" in status
        assert "targets" in status

        assert status["metrics"]["total_requests"] == 3
        assert status["metrics"]["availability"] == pytest.approx(2.0 / 3.0)

        manager.shutdown()

    def test_exports_prometheus_metrics(self) -> None:
        config = ObservabilityConfig(
            enable_tracing=False,
            enable_metrics=False,
        )
        manager = ObservabilityManager(config)
        manager.initialize()

        # Add some metrics
        manager.slo_metrics.add_request(True, 100, 1000)
        manager.slo_metrics.add_request(True, 200, 1000)

        output = manager.export_prometheus_metrics()

        assert "watercrawl_requests_total 2" in output
        assert "watercrawl_availability" in output
        assert "watercrawl_latency_sli" in output

        manager.shutdown()


class TestConfiguration:
    """Test configuration options."""

    def test_default_config(self) -> None:
        config = ObservabilityConfig()

        assert config.service_name == "watercrawl"
        assert config.enable_tracing is True
        assert config.enable_metrics is True
        assert config.target_availability == 0.99

    def test_custom_config(self) -> None:
        config = ObservabilityConfig(
            service_name="custom-service",
            target_latency_ms=3000.0,
            target_availability=0.999,
        )

        assert config.service_name == "custom-service"
        assert config.target_latency_ms == 3000.0
        assert config.target_availability == 0.999


class TestIntegration:
    """Integration tests for observability."""

    def test_end_to_end_operation_tracking(self) -> None:
        manager = create_default_manager()
        manager.config.enable_tracing = False
        manager.config.enable_metrics = False
        manager.initialize()

        # Simulate pipeline run
        with manager.trace_operation("validate") as span:
            time.sleep(0.01)

        with manager.trace_operation("enrich") as span:
            time.sleep(0.02)

        with manager.trace_operation("contracts") as span:
            time.sleep(0.01)

        # Check metrics
        status = manager.get_slo_status()
        assert status["metrics"]["total_requests"] == 3
        assert status["metrics"]["successful_requests"] == 3
        assert status["metrics"]["availability"] == 1.0

        manager.shutdown()

    def test_slo_compliance_tracking(self) -> None:
        config = ObservabilityConfig(
            enable_tracing=False,
            enable_metrics=False,
            target_availability=0.95,
            target_latency_ms=100.0,
            target_error_rate=0.05,
        )
        manager = ObservabilityManager(config)
        manager.initialize()

        # Simulate 96% availability (meets 95% target)
        for _ in range(96):
            manager.slo_metrics.add_request(True, 50, 100)
        for _ in range(4):
            manager.slo_metrics.add_request(False, 50, 100)

        status = manager.get_slo_status()

        assert status["compliance"]["availability_ok"] is True
        assert status["compliance"]["latency_ok"] is True
        assert status["compliance"]["error_rate_ok"] is True

        manager.shutdown()
