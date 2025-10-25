"""Tests for CLI telemetry and DevEx metrics."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from watercrawl.interfaces.telemetry import (
    TelemetryCollector,
    get_space_survey_template,
)


class TestTelemetryCollector:
    """Test telemetry collection."""

    def test_times_successful_command(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        with collector.time_command("test_cmd") as metadata:
            time.sleep(0.01)
            metadata["test_key"] = "test_value"

        assert len(collector.timings) == 1
        timing = collector.timings[0]

        assert timing.command == "test_cmd"
        assert timing.success is True
        assert timing.duration_seconds >= 0.01
        assert timing.metadata["test_key"] == "test_value"

    def test_records_failed_command(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        with pytest.raises(ValueError):
            with collector.time_command("failing_cmd"):
                raise ValueError("Test error")

        assert len(collector.timings) == 1
        timing = collector.timings[0]

        assert timing.command == "failing_cmd"
        assert timing.success is False
        assert timing.error_message == "Test error"

    def test_saves_telemetry(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        with collector.time_command("cmd1"):
            pass

        with collector.time_command("cmd2"):
            pass

        collector.save()

        # Verify file was created
        telemetry_file = tmp_path / "command_timings.jsonl"
        assert telemetry_file.exists()

        # Verify content
        lines = telemetry_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_loads_existing_telemetry(self, tmp_path: Path) -> None:
        # Create initial telemetry
        collector1 = TelemetryCollector(output_dir=tmp_path)
        with collector1.time_command("cmd1"):
            pass
        collector1.save()

        # Load in new collector
        collector2 = TelemetryCollector(output_dir=tmp_path)
        assert len(collector2.timings) == 1
        assert collector2.timings[0].command == "cmd1"


class TestDevExMetrics:
    """Test DevEx metrics calculation."""

    def test_calculates_success_rate(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        # 3 successful, 1 failed
        for _ in range(3):
            with collector.time_command("success"):
                pass

        with pytest.raises(ValueError):
            with collector.time_command("failure"):
                raise ValueError("Test")

        metrics = collector.get_metrics()
        assert metrics.command_success_rate == 0.75

    def test_calculates_avg_duration(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        with collector.time_command("cmd1"):
            time.sleep(0.1)

        with collector.time_command("cmd2"):
            time.sleep(0.2)

        metrics = collector.get_metrics()
        assert 0.1 < metrics.avg_command_duration_s < 0.3

    def test_calculates_p95_duration(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        # Create 20 commands with varying durations
        for i in range(20):
            with collector.time_command(f"cmd{i}"):
                time.sleep(0.001 * i)  # 0ms to 19ms

        metrics = collector.get_metrics()
        # P95 should be around 18ms
        assert metrics.p95_command_duration_s > metrics.avg_command_duration_s

    def test_counts_unique_commands(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        with collector.time_command("validate"):
            pass

        with collector.time_command("enrich"):
            pass

        with collector.time_command("validate"):
            pass

        metrics = collector.get_metrics()
        assert metrics.total_commands_run == 3
        assert metrics.unique_commands == 2

    def test_tracks_target_latency(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        # 2 under target (5s), 1 over
        with collector.time_command("fast1"):
            time.sleep(0.01)

        with collector.time_command("fast2"):
            time.sleep(0.01)

        with collector.time_command("slow"):
            time.sleep(6.0)

        metrics = collector.get_metrics()
        assert metrics.commands_under_target_latency == 2

    def test_handles_empty_timings(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        metrics = collector.get_metrics()

        assert metrics.total_commands_run == 0
        assert metrics.command_success_rate == 0.0
        assert metrics.avg_command_duration_s == 0.0


class TestExports:
    """Test metric export formats."""

    def test_exports_summary(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        with collector.time_command("test"):
            pass

        summary = collector.export_summary()

        assert "DevEx Telemetry Summary" in summary
        assert "Total commands run: 1" in summary
        assert "test" in summary

    def test_exports_prometheus_format(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        with collector.time_command("test"):
            pass

        output = collector.export_prometheus()

        assert "watercrawl_cli_commands_total 1" in output
        assert "watercrawl_cli_success_rate" in output
        assert "watercrawl_cli_avg_duration_seconds" in output


class TestSPACSurvey:
    """Test SPACE survey template."""

    def test_gets_survey_template(self) -> None:
        template = get_space_survey_template()

        assert "SPACE Framework" in template
        assert "Satisfaction" in template
        assert "Performance" in template
        assert "Activity" in template
        assert "Communication" in template
        assert "Efficiency" in template

        # Should have questions
        assert "[1-5]" in template


class TestIntegration:
    """Integration tests for telemetry."""

    def test_end_to_end_workflow(self, tmp_path: Path) -> None:
        collector = TelemetryCollector(output_dir=tmp_path)

        # Simulate pipeline commands
        commands = ["validate", "enrich", "contracts"]

        for cmd in commands:
            with collector.time_command(cmd) as metadata:
                time.sleep(0.01)
                metadata["dataset"] = "sample.csv"

        # Save telemetry
        collector.save()

        # Get metrics
        metrics = collector.get_metrics()

        assert metrics.total_commands_run == 3
        assert metrics.command_success_rate == 1.0
        assert metrics.unique_commands == 3

        # Export summary
        summary = collector.export_summary()
        assert "validate" in summary
        assert "enrich" in summary
        assert "contracts" in summary

    def test_persistent_telemetry(self, tmp_path: Path) -> None:
        # First session
        collector1 = TelemetryCollector(output_dir=tmp_path)
        with collector1.time_command("cmd1"):
            pass
        collector1.save()

        # Second session
        collector2 = TelemetryCollector(output_dir=tmp_path)
        with collector2.time_command("cmd2"):
            pass
        collector2.save()

        # Third session - should see all timings
        collector3 = TelemetryCollector(output_dir=tmp_path)
        assert len(collector3.timings) == 2

        metrics = collector3.get_metrics()
        assert metrics.total_commands_run == 2
