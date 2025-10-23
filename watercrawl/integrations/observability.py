"""
OpenTelemetry observability integration.

This module instruments the CLI pipeline with:
- Distributed tracing (OTLP)
- Metrics export (Prometheus)
- Error budget tracking
- SLO/SLI monitoring

WC-17 acceptance criteria:
- Traces visible in OTLP backend
- Metrics dashboard available
- SLOs defined with alerts
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Generator, Optional

logger = logging.getLogger(__name__)

# Check if OpenTelemetry is available (optional dependency)
try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    logger.debug("OpenTelemetry not available - observability features disabled")


@dataclass
class ObservabilityConfig:
    """Configuration for observability integration."""

    # Service identification
    service_name: str = "watercrawl"
    service_version: str = "1.0.0"
    deployment_environment: str = "development"

    # Tracing
    enable_tracing: bool = True
    otlp_endpoint: str = "http://localhost:4317"

    # Metrics
    enable_metrics: bool = True
    prometheus_port: int = 9090

    # SLOs
    enable_slos: bool = True
    target_latency_ms: float = 5000.0  # 5s target
    target_availability: float = 0.99  # 99% uptime
    target_error_rate: float = 0.01  # 1% error budget


@dataclass
class SLOMetrics:
    """Service Level Objective metrics."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    requests_within_slo: int = 0

    def add_request(
        self, success: bool, latency_ms: float, target_latency_ms: float
    ) -> None:
        """Record a request for SLO tracking."""
        self.total_requests += 1
        self.total_latency_ms += latency_ms

        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        if latency_ms <= target_latency_ms:
            self.requests_within_slo += 1

    def availability(self) -> float:
        """Calculate availability SLI."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    def latency_sli(self) -> float:
        """Calculate latency SLI (% within target)."""
        if self.total_requests == 0:
            return 1.0
        return self.requests_within_slo / self.total_requests

    def error_rate(self) -> float:
        """Calculate error rate."""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests

    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests

    def error_budget_remaining(self, target_error_rate: float) -> float:
        """Calculate remaining error budget."""
        current_error_rate = self.error_rate()
        if current_error_rate >= target_error_rate:
            return 0.0
        return 1.0 - (current_error_rate / target_error_rate)


class ObservabilityManager:
    """
    Manages OpenTelemetry instrumentation and SLO tracking.

    Example:
        >>> config = ObservabilityConfig()
        >>> manager = ObservabilityManager(config)
        >>> manager.initialize()
        >>>
        >>> with manager.trace_operation("enrich_dataset") as span:
        ...     # Perform operation
        ...     span.set_attribute("dataset_size", 100)
        >>>
        >>> manager.shutdown()
    """

    def __init__(self, config: Optional[ObservabilityConfig] = None):
        self.config = config or ObservabilityConfig()
        self.initialized = False
        self.tracer = None
        self.meter = None
        self.slo_metrics = SLOMetrics()

        # Metrics instruments
        self._request_counter = None
        self._latency_histogram = None
        self._error_counter = None
        self._slo_gauge = None

    def initialize(self) -> None:
        """Initialize OpenTelemetry providers and exporters."""
        if not OTEL_AVAILABLE:
            logger.warning("OpenTelemetry not available - using no-op instrumentation")
            self.initialized = True
            return

        try:
            # Set up resource
            resource = Resource.create(
                {
                    "service.name": self.config.service_name,
                    "service.version": self.config.service_version,
                    "deployment.environment": self.config.deployment_environment,
                }
            )

            # Initialize tracing
            if self.config.enable_tracing:
                self._init_tracing(resource)

            # Initialize metrics
            if self.config.enable_metrics:
                self._init_metrics(resource)

            self.initialized = True
            logger.info("OpenTelemetry initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry: {e}")
            self.initialized = False

    def _init_tracing(self, resource: Resource) -> None:
        """Initialize tracing with OTLP exporter."""
        trace_provider = TracerProvider(resource=resource)

        # Configure OTLP exporter
        otlp_exporter = OTLPSpanExporter(endpoint=self.config.otlp_endpoint)
        span_processor = BatchSpanProcessor(otlp_exporter)
        trace_provider.add_span_processor(span_processor)

        # Set global tracer provider
        trace.set_tracer_provider(trace_provider)
        self.tracer = trace.get_tracer(__name__)

        logger.info(
            f"Tracing initialized with OTLP endpoint: {self.config.otlp_endpoint}"
        )

    def _init_metrics(self, resource: Resource) -> None:
        """Initialize metrics with Prometheus exporter."""
        # Set Prometheus port via environment variable
        os.environ["OTEL_PYTHON_METRICS_EXPORTER_PROMETHEUS_PORT"] = str(
            self.config.prometheus_port
        )

        # Create Prometheus reader
        prometheus_reader = PrometheusMetricReader()

        # Set up meter provider
        meter_provider = MeterProvider(
            resource=resource, metric_readers=[prometheus_reader]
        )
        metrics.set_meter_provider(meter_provider)

        # Get meter from the provider (preferred) and fall back to the global API if needed
        self.meter = meter_provider.get_meter(__name__, self.config.service_version)
        if self.meter is None:
            # Fallback to the global metrics API (may still be None in some runtimes)
            self.meter = metrics.get_meter(__name__, self.config.service_version)

        if self.meter is None:
            logger.warning(
                "Failed to obtain a Meter instance - metrics instruments will be no-op"
            )
            return

        # Create metric instruments
        self._request_counter = self.meter.create_counter(
            "watercrawl_requests_total",
            description="Total number of requests",
            unit="1",
        )

        self._latency_histogram = self.meter.create_histogram(
            "watercrawl_request_duration_ms",
            description="Request latency in milliseconds",
            unit="ms",
        )

        self._error_counter = self.meter.create_counter(
            "watercrawl_errors_total", description="Total number of errors", unit="1"
        )

        self._slo_gauge = self.meter.create_observable_gauge(
            "watercrawl_slo_status",
            description="SLO compliance status",
            callbacks=[self._observe_slo],
        )

        logger.info(
            f"Metrics initialized with Prometheus on port {self.config.prometheus_port}"
        )

    def _observe_slo(self, options) -> Generator[Any, None, None]:
        """Callback to observe SLO metrics."""
        yield metrics.Observation(
            self.slo_metrics.availability(), {"sli": "availability"}
        )
        yield metrics.Observation(self.slo_metrics.latency_sli(), {"sli": "latency"})
        yield metrics.Observation(
            self.slo_metrics.error_budget_remaining(self.config.target_error_rate),
            {"sli": "error_budget"},
        )

    @contextmanager
    def trace_operation(
        self, operation_name: str, attributes: Optional[Dict[str, Any]] = None
    ) -> Generator[Any, None, None]:
        """
        Trace an operation with automatic timing and error handling.

        Args:
            operation_name: Name of the operation
            attributes: Optional attributes to attach to span

        Yields:
            Span object (or None if tracing disabled)
        """
        start_time = time.time()
        success = True
        error_message = None

        # Create span if tracing is available
        if self.tracer and self.config.enable_tracing:
            with self.tracer.start_as_current_span(operation_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, str(value))

                try:
                    yield span
                except Exception as e:
                    success = False
                    error_message = str(e)
                    span.set_attribute("error", True)
                    span.set_attribute("error.message", error_message)
                    raise
                finally:
                    # Record metrics
                    latency_ms = (time.time() - start_time) * 1000
                    span.set_attribute("latency_ms", latency_ms)
                    self._record_request(
                        operation_name, success, latency_ms, error_message
                    )
        else:
            # No tracing - just time the operation
            try:
                yield None
            except Exception as e:
                success = False
                error_message = str(e)
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000
                self._record_request(operation_name, success, latency_ms, error_message)

    def _record_request(
        self,
        operation: str,
        success: bool,
        latency_ms: float,
        error_message: Optional[str] = None,
    ) -> None:
        """Record request metrics."""
        # Record to SLO tracker
        if self.config.enable_slos:
            self.slo_metrics.add_request(
                success, latency_ms, self.config.target_latency_ms
            )

        # Record to metrics instruments
        if self._request_counter:
            self._request_counter.add(
                1, {"operation": operation, "success": str(success)}
            )

        if self._latency_histogram:
            self._latency_histogram.record(latency_ms, {"operation": operation})

        if not success and self._error_counter:
            self._error_counter.add(1, {"operation": operation})

    def get_slo_status(self) -> dict:
        """
        Get current SLO status and metrics.

        Returns:
            Dictionary with SLO metrics and compliance
        """
        metrics_dict = {
            "total_requests": self.slo_metrics.total_requests,
            "successful_requests": self.slo_metrics.successful_requests,
            "failed_requests": self.slo_metrics.failed_requests,
            "availability": self.slo_metrics.availability(),
            "latency_sli": self.slo_metrics.latency_sli(),
            "error_rate": self.slo_metrics.error_rate(),
            "avg_latency_ms": self.slo_metrics.avg_latency_ms(),
            "error_budget_remaining": self.slo_metrics.error_budget_remaining(
                self.config.target_error_rate
            ),
        }

        # Check SLO compliance
        compliance = {
            "availability_ok": metrics_dict["availability"]
            >= self.config.target_availability,
            "latency_ok": metrics_dict["latency_sli"]
            >= self.config.target_availability,
            "error_rate_ok": metrics_dict["error_rate"]
            <= self.config.target_error_rate,
        }

        return {
            "metrics": metrics_dict,
            "compliance": compliance,
            "targets": {
                "availability": self.config.target_availability,
                "latency_ms": self.config.target_latency_ms,
                "error_rate": self.config.target_error_rate,
            },
        }

    def export_prometheus_metrics(self) -> str:
        """
        Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics
        """
        slo_status = self.get_slo_status()
        metrics = slo_status["metrics"]

        lines = [
            "# HELP watercrawl_requests_total Total number of requests",
            "# TYPE watercrawl_requests_total counter",
            f"watercrawl_requests_total {metrics['total_requests']}",
            "",
            "# HELP watercrawl_availability Current availability SLI",
            "# TYPE watercrawl_availability gauge",
            f"watercrawl_availability {metrics['availability']:.4f}",
            "",
            "# HELP watercrawl_latency_sli Latency SLI (% within target)",
            "# TYPE watercrawl_latency_sli gauge",
            f"watercrawl_latency_sli {metrics['latency_sli']:.4f}",
            "",
            "# HELP watercrawl_error_budget_remaining Remaining error budget",
            "# TYPE watercrawl_error_budget_remaining gauge",
            f"watercrawl_error_budget_remaining {metrics['error_budget_remaining']:.4f}",
            "",
            "# HELP watercrawl_avg_latency_ms Average latency in milliseconds",
            "# TYPE watercrawl_avg_latency_ms gauge",
            f"watercrawl_avg_latency_ms {metrics['avg_latency_ms']:.2f}",
        ]

        return "\n".join(lines)

    def shutdown(self) -> None:
        """Shutdown observability providers and flush data."""
        if not self.initialized:
            return

        try:
            # Flush traces
            if self.tracer and OTEL_AVAILABLE:
                trace.get_tracer_provider().shutdown()

            # Shutdown metrics
            if self.meter and OTEL_AVAILABLE:
                metrics.get_meter_provider().shutdown()

            logger.info("OpenTelemetry shutdown successfully")

        except Exception as e:
            logger.error(f"Error during OpenTelemetry shutdown: {e}")


def create_default_manager() -> ObservabilityManager:
    """Create an ObservabilityManager with default configuration."""
    return ObservabilityManager(ObservabilityConfig())
