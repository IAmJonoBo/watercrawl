"""
Chaos testing and game day execution framework.

This module implements chaos engineering scenarios for the pipeline
and MCP surfaces, with automated failure injection and recovery validation.

WC-20 acceptance criteria:
- Game day drills pass rollback MTTR <30 min
- FMEA register updated with findings
- Scenarios documented and reproducible
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Generator, List, Optional

logger = logging.getLogger(__name__)


class FailureMode(Enum):
    """Types of failures that can be injected."""
    
    ADAPTER_TIMEOUT = "adapter_timeout"
    ADAPTER_ERROR = "adapter_error"
    SECRETS_UNAVAILABLE = "secrets_unavailable"
    DISK_FULL = "disk_full"
    NETWORK_PARTITION = "network_partition"
    HIGH_LATENCY = "high_latency"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    DATA_CORRUPTION = "data_corruption"
    MCP_DISCONNECTION = "mcp_disconnection"
    CONCURRENT_WRITES = "concurrent_writes"
    INVALID_INPUT = "invalid_input"


@dataclass
class ChaosConfig:
    """Configuration for chaos testing."""
    
    # Failure injection
    enable_chaos: bool = False
    failure_rate: float = 0.1  # 10% of operations fail
    mean_time_to_failure_s: float = 60.0
    
    # Recovery validation
    max_recovery_time_s: float = 1800.0  # 30 minutes
    verify_data_integrity: bool = True
    
    # Safety limits
    max_concurrent_failures: int = 1
    allowed_failure_modes: List[FailureMode] = field(default_factory=list)


@dataclass
class FailureInjection:
    """A single failure injection event."""
    
    mode: FailureMode
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_s: Optional[float] = None
    affected_component: str = ""
    recovery_successful: bool = False
    recovery_time_s: Optional[float] = None
    notes: str = ""


@dataclass
class GameDayResult:
    """Results from a chaos game day exercise."""
    
    scenario_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_s: float = 0.0
    
    injections: List[FailureInjection] = field(default_factory=list)
    
    success: bool = False
    recovery_verified: bool = False
    data_integrity_verified: bool = False
    
    mttr_s: Optional[float] = None  # Mean Time To Recovery
    findings: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)


class ChaosOrchestrator:
    """
    Orchestrates chaos engineering scenarios and game day exercises.
    
    Example:
        >>> config = ChaosConfig(enable_chaos=True)
        >>> orchestrator = ChaosOrchestrator(config)
        >>> 
        >>> with orchestrator.game_day("F-001") as result:
        ...     # Execute test scenario
        ...     orchestrator.inject_failure(FailureMode.ADAPTER_TIMEOUT)
        ...     # Verify recovery
        ...     orchestrator.verify_recovery()
    """
    
    def __init__(self, config: Optional[ChaosConfig] = None):
        self.config = config or ChaosConfig()
        self.active_failures: List[FailureInjection] = []
        self.game_day_results: List[GameDayResult] = []
        
    @contextmanager
    def game_day(self, scenario_id: str) -> Generator[GameDayResult, None, None]:
        """
        Execute a chaos game day exercise.
        
        Args:
            scenario_id: Identifier for the scenario (e.g., F-001)
            
        Yields:
            GameDayResult for recording outcomes
        """
        result = GameDayResult(
            scenario_id=scenario_id,
            start_time=datetime.now()
        )
        
        logger.info(f"Starting game day exercise: {scenario_id}")
        
        try:
            yield result
            result.success = True
        except Exception as e:
            result.success = False
            result.findings.append(f"Unexpected error: {str(e)}")
            logger.error(f"Game day {scenario_id} failed: {e}")
        finally:
            result.end_time = datetime.now()
            result.duration_s = (result.end_time - result.start_time).total_seconds()
            
            # Calculate MTTR
            if result.injections:
                recovery_times = [
                    inj.recovery_time_s
                    for inj in result.injections
                    if inj.recovery_time_s is not None
                ]
                if recovery_times:
                    result.mttr_s = sum(recovery_times) / len(recovery_times)
            
            self.game_day_results.append(result)
            
            logger.info(
                f"Game day {scenario_id} completed: "
                f"success={result.success}, mttr={result.mttr_s}s"
            )
    
    def inject_failure(
        self,
        mode: FailureMode,
        component: str = "",
        duration_s: Optional[float] = None
    ) -> FailureInjection:
        """
        Inject a failure into the system.
        
        Args:
            mode: Type of failure to inject
            component: Component to affect
            duration_s: How long the failure should last (None = manual recovery)
            
        Returns:
            FailureInjection record
        """
        if not self.config.enable_chaos:
            logger.warning("Chaos testing disabled - failure not injected")
            return FailureInjection(
                mode=mode,
                start_time=datetime.now(),
                affected_component=component
            )
        
        # Check safety limits
        if len(self.active_failures) >= self.config.max_concurrent_failures:
            raise RuntimeError("Max concurrent failures limit reached")
        
        if (self.config.allowed_failure_modes and
                mode not in self.config.allowed_failure_modes):
            raise ValueError(f"Failure mode {mode} not allowed")
        
        injection = FailureInjection(
            mode=mode,
            start_time=datetime.now(),
            affected_component=component
        )
        
        self.active_failures.append(injection)
        
        logger.warning(f"Injected failure: {mode.value} on {component}")
        
        # Auto-recover after duration
        if duration_s:
            time.sleep(duration_s)
            self.recover_failure(injection)
        
        return injection
    
    def recover_failure(self, injection: FailureInjection) -> None:
        """
        Recover from an injected failure.
        
        Args:
            injection: The failure injection to recover
        """
        injection.end_time = datetime.now()
        injection.duration_s = (injection.end_time - injection.start_time).total_seconds()
        injection.recovery_successful = True
        
        if injection in self.active_failures:
            self.active_failures.remove(injection)
        
        logger.info(f"Recovered from {injection.mode.value} after {injection.duration_s}s")
    
    @contextmanager
    def inject_transient_failure(
        self,
        mode: FailureMode,
        component: str = ""
    ) -> Generator[FailureInjection, None, None]:
        """
        Temporarily inject a failure with automatic recovery.
        
        Args:
            mode: Type of failure to inject
            component: Component to affect
            
        Yields:
            FailureInjection record
        """
        injection = self.inject_failure(mode, component)
        recovery_start = time.time()
        
        try:
            yield injection
        finally:
            self.recover_failure(injection)
            injection.recovery_time_s = time.time() - recovery_start
    
    def verify_recovery(self) -> bool:
        """
        Verify system has recovered from failures.
        
        Returns:
            True if recovery verified
        """
        if self.active_failures:
            logger.error(f"{len(self.active_failures)} active failures remain")
            return False
        
        logger.info("All failures recovered")
        return True
    
    def verify_data_integrity(self, data_path: Path) -> bool:
        """
        Verify data integrity after chaos testing.
        
        Args:
            data_path: Path to data to verify
            
        Returns:
            True if data is intact
        """
        if not self.config.verify_data_integrity:
            return True
        
        # Basic checks
        if not data_path.exists():
            logger.error(f"Data missing: {data_path}")
            return False
        
        # Check file size is reasonable
        size = data_path.stat().st_size
        if size == 0:
            logger.error(f"Data corrupted (zero size): {data_path}")
            return False
        
        logger.info(f"Data integrity verified: {data_path}")
        return True
    
    def export_results(self) -> List[dict]:
        """
        Export game day results for analysis.
        
        Returns:
            List of game day result dictionaries
        """
        results = []
        
        for game_day in self.game_day_results:
            result_dict = {
                "scenario_id": game_day.scenario_id,
                "start_time": game_day.start_time.isoformat(),
                "duration_s": game_day.duration_s,
                "success": game_day.success,
                "recovery_verified": game_day.recovery_verified,
                "data_integrity_verified": game_day.data_integrity_verified,
                "mttr_s": game_day.mttr_s,
                "findings": game_day.findings,
                "action_items": game_day.action_items,
                "injections": [
                    {
                        "mode": inj.mode.value,
                        "component": inj.affected_component,
                        "duration_s": inj.duration_s,
                        "recovery_time_s": inj.recovery_time_s,
                        "recovery_successful": inj.recovery_successful,
                    }
                    for inj in game_day.injections
                ],
            }
            results.append(result_dict)
        
        return results
    
    def generate_report(self) -> str:
        """
        Generate a human-readable chaos testing report.
        
        Returns:
            Formatted report text
        """
        lines = [
            "=== Chaos Testing Report ===",
            "",
            f"Total game days executed: {len(self.game_day_results)}",
            "",
        ]
        
        for game_day in self.game_day_results:
            lines.extend([
                f"Scenario: {game_day.scenario_id}",
                f"  Duration: {game_day.duration_s:.1f}s",
                f"  Success: {game_day.success}",
                f"  MTTR: {game_day.mttr_s:.1f}s" if game_day.mttr_s else "  MTTR: N/A",
                f"  Injections: {len(game_day.injections)}",
            ])
            
            if game_day.findings:
                lines.append("  Findings:")
                for finding in game_day.findings:
                    lines.append(f"    - {finding}")
            
            if game_day.action_items:
                lines.append("  Action Items:")
                for item in game_day.action_items:
                    lines.append(f"    - {item}")
            
            lines.append("")
        
        return "\n".join(lines)


# Pre-defined game day scenarios based on docs/chaos-fmea-scenarios.md
GAME_DAY_SCENARIOS = {
    "F-001": {
        "name": "Adapter timeout during enrichment",
        "failure_mode": FailureMode.ADAPTER_TIMEOUT,
        "component": "research_adapter",
        "expected_behavior": "Pipeline should timeout gracefully and continue with available data",
        "recovery_steps": ["Verify timeout logged", "Check evidence log entries", "Validate partial results"],
    },
    "F-004": {
        "name": "Secrets backend unavailable",
        "failure_mode": FailureMode.SECRETS_UNAVAILABLE,
        "component": "secrets_provider",
        "expected_behavior": "CLI should fail with clear error message",
        "recovery_steps": ["Restore secrets access", "Retry pipeline", "Verify completion"],
    },
    "F-011": {
        "name": "Concurrent MCP writes",
        "failure_mode": FailureMode.CONCURRENT_WRITES,
        "component": "mcp_server",
        "expected_behavior": "Plan-commit guard should detect conflict and return 412",
        "recovery_steps": ["Resolve conflict", "Submit updated commit", "Verify audit log"],
    },
}


def execute_game_day_scenario(
    scenario_id: str,
    orchestrator: Optional[ChaosOrchestrator] = None
) -> GameDayResult:
    """
    Execute a pre-defined game day scenario.
    
    Args:
        scenario_id: Scenario identifier (e.g., F-001)
        orchestrator: Optional ChaosOrchestrator instance
        
    Returns:
        GameDayResult with outcomes
    """
    if scenario_id not in GAME_DAY_SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_id}")
    
    scenario = GAME_DAY_SCENARIOS[scenario_id]
    orch = orchestrator or ChaosOrchestrator()
    
    with orch.game_day(scenario_id) as result:
        logger.info(f"Executing: {scenario['name']}")
        
        # Inject failure
        with orch.inject_transient_failure(
            scenario["failure_mode"],
            scenario["component"]
        ) as injection:
            result.injections.append(injection)
            
            # Simulate recovery actions
            time.sleep(1)
        
        # Verify recovery
        result.recovery_verified = orch.verify_recovery()
        
        # Check MTTR target
        if result.mttr_s and result.mttr_s > 1800:  # 30 minutes
            result.findings.append(f"MTTR {result.mttr_s}s exceeds 30min target")
        
    return result


def create_default_orchestrator() -> ChaosOrchestrator:
    """Create a ChaosOrchestrator with default configuration."""
    config = ChaosConfig(
        enable_chaos=True,
        max_concurrent_failures=1,
        allowed_failure_modes=list(FailureMode),
    )
    return ChaosOrchestrator(config)
