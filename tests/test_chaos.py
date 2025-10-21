"""Tests for chaos testing and game day execution."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from firecrawl_demo.testing.chaos import (
    ChaosConfig,
    ChaosOrchestrator,
    FailureMode,
    GAME_DAY_SCENARIOS,
    create_default_orchestrator,
    execute_game_day_scenario,
)


class TestFailureInjection:
    """Test failure injection functionality."""
    
    def test_injects_failure_when_enabled(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        injection = orchestrator.inject_failure(
            FailureMode.ADAPTER_TIMEOUT,
            component="test_component"
        )
        
        assert injection.mode == FailureMode.ADAPTER_TIMEOUT
        assert injection.affected_component == "test_component"
        assert len(orchestrator.active_failures) == 1
    
    def test_respects_chaos_disabled(self) -> None:
        config = ChaosConfig(enable_chaos=False)
        orchestrator = ChaosOrchestrator(config)
        
        injection = orchestrator.inject_failure(FailureMode.ADAPTER_TIMEOUT)
        
        # Should create record but not actually inject
        assert len(orchestrator.active_failures) == 0
    
    def test_enforces_concurrent_limit(self) -> None:
        config = ChaosConfig(
            enable_chaos=True,
            max_concurrent_failures=1,
            allowed_failure_modes=list(FailureMode)
        )
        orchestrator = ChaosOrchestrator(config)
        
        orchestrator.inject_failure(FailureMode.ADAPTER_TIMEOUT)
        
        with pytest.raises(RuntimeError, match="Max concurrent failures"):
            orchestrator.inject_failure(FailureMode.ADAPTER_ERROR)
    
    def test_enforces_allowed_modes(self) -> None:
        config = ChaosConfig(
            enable_chaos=True,
            allowed_failure_modes=[FailureMode.ADAPTER_TIMEOUT]
        )
        orchestrator = ChaosOrchestrator(config)
        
        with pytest.raises(ValueError, match="not allowed"):
            orchestrator.inject_failure(FailureMode.DISK_FULL)


class TestRecovery:
    """Test recovery functionality."""
    
    def test_recovers_from_failure(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        injection = orchestrator.inject_failure(FailureMode.ADAPTER_TIMEOUT)
        assert len(orchestrator.active_failures) == 1
        
        orchestrator.recover_failure(injection)
        assert len(orchestrator.active_failures) == 0
        assert injection.recovery_successful is True
        assert injection.duration_s is not None
    
    def test_transient_failure_auto_recovers(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        with orchestrator.inject_transient_failure(FailureMode.ADAPTER_TIMEOUT) as injection:
            assert len(orchestrator.active_failures) == 1
        
        # Should auto-recover
        assert len(orchestrator.active_failures) == 0
        assert injection.recovery_time_s is not None
    
    def test_verifies_recovery(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        injection = orchestrator.inject_failure(FailureMode.ADAPTER_TIMEOUT)
        assert orchestrator.verify_recovery() is False
        
        orchestrator.recover_failure(injection)
        assert orchestrator.verify_recovery() is True


class TestDataIntegrity:
    """Test data integrity verification."""
    
    def test_verifies_existing_file(self, tmp_path: Path) -> None:
        config = ChaosConfig(verify_data_integrity=True)
        orchestrator = ChaosOrchestrator(config)
        
        test_file = tmp_path / "data.csv"
        test_file.write_text("test data")
        
        assert orchestrator.verify_data_integrity(test_file) is True
    
    def test_detects_missing_file(self, tmp_path: Path) -> None:
        config = ChaosConfig(verify_data_integrity=True)
        orchestrator = ChaosOrchestrator(config)
        
        test_file = tmp_path / "missing.csv"
        
        assert orchestrator.verify_data_integrity(test_file) is False
    
    def test_detects_corrupted_file(self, tmp_path: Path) -> None:
        config = ChaosConfig(verify_data_integrity=True)
        orchestrator = ChaosOrchestrator(config)
        
        test_file = tmp_path / "corrupted.csv"
        test_file.write_text("")  # Empty file
        
        assert orchestrator.verify_data_integrity(test_file) is False
    
    def test_skips_when_disabled(self, tmp_path: Path) -> None:
        config = ChaosConfig(verify_data_integrity=False)
        orchestrator = ChaosOrchestrator(config)
        
        test_file = tmp_path / "missing.csv"
        
        # Should return True even for missing file
        assert orchestrator.verify_data_integrity(test_file) is True


class TestGameDay:
    """Test game day execution."""
    
    def test_executes_game_day(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        with orchestrator.game_day("TEST-001") as result:
            # Inject and recover from failure
            with orchestrator.inject_transient_failure(FailureMode.ADAPTER_TIMEOUT) as injection:
                result.injections.append(injection)
                time.sleep(0.01)
            
            result.recovery_verified = orchestrator.verify_recovery()
        
        assert len(orchestrator.game_day_results) == 1
        game_day = orchestrator.game_day_results[0]
        
        assert game_day.scenario_id == "TEST-001"
        assert game_day.success is True
        assert game_day.recovery_verified is True
        assert game_day.mttr_s is not None
        assert game_day.mttr_s < 1.0  # Should recover quickly
    
    def test_handles_game_day_failure(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        with orchestrator.game_day("FAIL-001") as result:
            raise ValueError("Simulated game day failure")
        
        game_day = orchestrator.game_day_results[0]
        assert game_day.success is False
        assert "Unexpected error" in game_day.findings[0]
    
    def test_calculates_mttr(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        with orchestrator.game_day("MTTR-001") as result:
            # Inject multiple failures with different recovery times
            with orchestrator.inject_transient_failure(FailureMode.ADAPTER_TIMEOUT) as inj1:
                result.injections.append(inj1)
                time.sleep(0.1)
            
            with orchestrator.inject_transient_failure(FailureMode.HIGH_LATENCY) as inj2:
                result.injections.append(inj2)
                time.sleep(0.2)
        
        game_day = orchestrator.game_day_results[0]
        assert game_day.mttr_s is not None
        # MTTR should be average of recovery times
        assert 0.1 < game_day.mttr_s < 0.3


class TestReporting:
    """Test reporting functionality."""
    
    def test_exports_results(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        with orchestrator.game_day("EXP-001") as result:
            with orchestrator.inject_transient_failure(FailureMode.ADAPTER_TIMEOUT) as injection:
                result.injections.append(injection)
        
        results = orchestrator.export_results()
        
        assert len(results) == 1
        result = results[0]
        
        assert result["scenario_id"] == "EXP-001"
        assert result["success"] is True
        assert "injections" in result
        assert len(result["injections"]) == 1
    
    def test_generates_report(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        with orchestrator.game_day("REP-001") as result:
            with orchestrator.inject_transient_failure(FailureMode.ADAPTER_TIMEOUT) as injection:
                result.injections.append(injection)
            result.findings.append("Test finding")
            result.action_items.append("Test action")
        
        report = orchestrator.generate_report()
        
        assert "Chaos Testing Report" in report
        assert "REP-001" in report
        assert "Test finding" in report
        assert "Test action" in report


class TestPredefinedScenarios:
    """Test pre-defined game day scenarios."""
    
    def test_scenario_f001_adapter_timeout(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        result = execute_game_day_scenario("F-001", orchestrator)
        
        assert result.scenario_id == "F-001"
        assert result.success is True
        assert result.recovery_verified is True
        assert len(result.injections) == 1
        assert result.injections[0].mode == FailureMode.ADAPTER_TIMEOUT
    
    def test_scenario_f004_secrets_unavailable(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        result = execute_game_day_scenario("F-004", orchestrator)
        
        assert result.scenario_id == "F-004"
        assert result.success is True
        assert result.injections[0].mode == FailureMode.SECRETS_UNAVAILABLE
    
    def test_scenario_f011_concurrent_writes(self) -> None:
        config = ChaosConfig(enable_chaos=True, allowed_failure_modes=list(FailureMode))
        orchestrator = ChaosOrchestrator(config)
        
        result = execute_game_day_scenario("F-011", orchestrator)
        
        assert result.scenario_id == "F-011"
        assert result.success is True
        assert result.injections[0].mode == FailureMode.CONCURRENT_WRITES
    
    def test_unknown_scenario_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown scenario"):
            execute_game_day_scenario("INVALID")
    
    def test_all_scenarios_defined(self) -> None:
        # Verify all documented scenarios exist
        required_scenarios = ["F-001", "F-004", "F-011"]
        
        for scenario_id in required_scenarios:
            assert scenario_id in GAME_DAY_SCENARIOS


class TestConfiguration:
    """Test configuration options."""
    
    def test_default_config(self) -> None:
        config = ChaosConfig()
        
        assert config.enable_chaos is False
        assert config.max_recovery_time_s == 1800.0
        assert config.verify_data_integrity is True
    
    def test_custom_config(self) -> None:
        config = ChaosConfig(
            enable_chaos=True,
            failure_rate=0.2,
            max_recovery_time_s=900.0,
        )
        
        assert config.enable_chaos is True
        assert config.failure_rate == 0.2
        assert config.max_recovery_time_s == 900.0
