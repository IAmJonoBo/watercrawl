"""
CLI telemetry and DevEx metrics collection.

This module tracks CLI run timings, adapter metrics, and developer
experience indicators to improve tooling and identify friction points.

WC-18 acceptance criteria:
- CLI emits run timings
- Telemetry captured and aggregated
- SPACE survey template published
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CommandTiming:
    """Timing information for a CLI command."""
    
    command: str
    start_time: str
    end_time: str
    duration_seconds: float
    success: bool
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DevExMetrics:
    """Developer experience metrics (SPACE framework)."""
    
    # Satisfaction & Well-being
    command_success_rate: float = 0.0
    avg_error_recovery_time_s: float = 0.0
    
    # Performance
    avg_command_duration_s: float = 0.0
    p95_command_duration_s: float = 0.0
    
    # Activity
    total_commands_run: int = 0
    unique_commands: int = 0
    
    # Communication & Collaboration
    # (Would be measured via surveys, not automated)
    
    # Efficiency & Flow
    commands_under_target_latency: int = 0
    target_latency_s: float = 5.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


class TelemetryCollector:
    """
    Collects and aggregates CLI telemetry data.
    
    Example:
        >>> collector = TelemetryCollector()
        >>> with collector.time_command("validate") as timing:
        ...     # Perform validation
        ...     timing["dataset_size"] = 100
        >>> 
        >>> collector.save()
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("artifacts/telemetry")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.timings: List[CommandTiming] = []
        self._load_existing()
    
    def _load_existing(self) -> None:
        """Load existing telemetry data."""
        telemetry_file = self.output_dir / "command_timings.jsonl"
        
        if not telemetry_file.exists():
            return
        
        try:
            with open(telemetry_file, 'r') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        timing = CommandTiming(**data)
                        self.timings.append(timing)
        except Exception as e:
            logger.warning(f"Failed to load existing telemetry: {e}")
    
    @contextmanager
    def time_command(self, command: str) -> Generator[Dict[str, Any], None, None]:
        """
        Time a CLI command and record telemetry.
        
        Args:
            command: Name of the command
            
        Yields:
            Metadata dictionary for adding context
        """
        start_time = time.time()
        start_timestamp = datetime.now().isoformat()
        success = True
        error_message = None
        metadata: Dict[str, Any] = {}
        
        try:
            yield metadata
        except Exception as e:
            success = False
            error_message = str(e)
            raise
        finally:
            end_time = time.time()
            end_timestamp = datetime.now().isoformat()
            duration = end_time - start_time
            
            timing = CommandTiming(
                command=command,
                start_time=start_timestamp,
                end_time=end_timestamp,
                duration_seconds=duration,
                success=success,
                error_message=error_message,
                metadata=metadata
            )
            
            self.timings.append(timing)
            
            # Log timing
            status = "✓" if success else "✗"
            logger.info(f"{status} {command} completed in {duration:.2f}s")
    
    def save(self) -> None:
        """Save telemetry data to disk."""
        telemetry_file = self.output_dir / "command_timings.jsonl"
        
        try:
            # Append new timings
            with open(telemetry_file, 'a') as f:
                # Find timings not yet written
                existing_count = sum(1 for _ in open(telemetry_file)) if telemetry_file.exists() else 0
                new_timings = self.timings[existing_count:]
                
                for timing in new_timings:
                    json.dump(asdict(timing), f)
                    f.write('\n')
            
            logger.debug(f"Saved {len(new_timings)} new timing entries")
            
        except Exception as e:
            logger.error(f"Failed to save telemetry: {e}")
    
    def get_metrics(self) -> DevExMetrics:
        """
        Calculate DevEx metrics from collected telemetry.
        
        Returns:
            DevExMetrics with aggregated statistics
        """
        if not self.timings:
            return DevExMetrics()
        
        # Calculate success rate
        successful = sum(1 for t in self.timings if t.success)
        total = len(self.timings)
        success_rate = successful / total if total > 0 else 0.0
        
        # Calculate durations
        durations = [t.duration_seconds for t in self.timings]
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        
        # Calculate p95
        sorted_durations = sorted(durations)
        p95_index = int(len(sorted_durations) * 0.95)
        p95_duration = sorted_durations[p95_index] if sorted_durations else 0.0
        
        # Count unique commands
        unique_commands = len(set(t.command for t in self.timings))
        
        # Count commands under target latency
        target_latency = 5.0
        under_target = sum(1 for d in durations if d <= target_latency)
        
        return DevExMetrics(
            command_success_rate=success_rate,
            avg_command_duration_s=avg_duration,
            p95_command_duration_s=p95_duration,
            total_commands_run=total,
            unique_commands=unique_commands,
            commands_under_target_latency=under_target,
            target_latency_s=target_latency,
        )
    
    def export_summary(self) -> str:
        """
        Export a human-readable summary of metrics.
        
        Returns:
            Formatted summary text
        """
        metrics = self.get_metrics()
        
        lines = [
            "=== DevEx Telemetry Summary ===",
            "",
            f"Total commands run: {metrics.total_commands_run}",
            f"Unique commands: {metrics.unique_commands}",
            f"Success rate: {metrics.command_success_rate:.1%}",
            "",
            f"Average duration: {metrics.avg_command_duration_s:.2f}s",
            f"P95 duration: {metrics.p95_command_duration_s:.2f}s",
            f"Commands under {metrics.target_latency_s}s target: {metrics.commands_under_target_latency}",
            "",
            "Recent commands:",
        ]
        
        # Show last 5 commands
        for timing in self.timings[-5:]:
            status = "✓" if timing.success else "✗"
            lines.append(
                f"  {status} {timing.command} ({timing.duration_seconds:.2f}s)"
            )
        
        return "\n".join(lines)
    
    def export_prometheus(self) -> str:
        """
        Export metrics in Prometheus text format.
        
        Returns:
            Prometheus-formatted metrics
        """
        metrics = self.get_metrics()
        
        lines = [
            "# HELP watercrawl_cli_commands_total Total CLI commands run",
            "# TYPE watercrawl_cli_commands_total counter",
            f"watercrawl_cli_commands_total {metrics.total_commands_run}",
            "",
            "# HELP watercrawl_cli_success_rate CLI command success rate",
            "# TYPE watercrawl_cli_success_rate gauge",
            f"watercrawl_cli_success_rate {metrics.command_success_rate:.4f}",
            "",
            "# HELP watercrawl_cli_avg_duration_seconds Average CLI duration",
            "# TYPE watercrawl_cli_avg_duration_seconds gauge",
            f"watercrawl_cli_avg_duration_seconds {metrics.avg_command_duration_s:.4f}",
            "",
            "# HELP watercrawl_cli_p95_duration_seconds P95 CLI duration",
            "# TYPE watercrawl_cli_p95_duration_seconds gauge",
            f"watercrawl_cli_p95_duration_seconds {metrics.p95_command_duration_s:.4f}",
        ]
        
        return "\n".join(lines)


def create_default_collector() -> TelemetryCollector:
    """Create a TelemetryCollector with default configuration."""
    return TelemetryCollector()


# SPACE Survey Template
SPACE_SURVEY_TEMPLATE = """
# Developer Experience Survey (SPACE Framework)

This survey helps measure developer experience across five dimensions:
Satisfaction, Performance, Activity, Communication & Collaboration, Efficiency & Flow.

## Instructions
Rate each statement on a scale of 1-5 (1=Strongly Disagree, 5=Strongly Agree)

---

## Satisfaction & Well-being

1. I feel productive when using the Watercrawl tooling [1-5]
2. The CLI commands are intuitive and easy to remember [1-5]
3. Error messages are helpful and actionable [1-5]
4. Documentation is clear and up-to-date [1-5]
5. I enjoy working with the codebase [1-5]

## Performance

6. The test suite runs quickly enough for my workflow [1-5]
7. Linting and type-checking provide fast feedback [1-5]
8. I can iterate on changes without long wait times [1-5]
9. The CI pipeline provides timely feedback [1-5]

## Activity

10. I complete my planned tasks during development sessions [1-5]
11. The tooling helps me maintain focus [1-5]
12. I rarely encounter unexpected blockers [1-5]

## Communication & Collaboration

13. The codebase structure is easy to understand [1-5]
14. Code reviews are efficient and constructive [1-5]
15. I can easily find help when I'm stuck [1-5]
16. Documentation helps me onboard new team members [1-5]

## Efficiency & Flow

17. I can enter "flow state" while developing [1-5]
18. Context switching between tasks is smooth [1-5]
19. I rarely have to work around tool limitations [1-5]
20. The development environment is reliable [1-5]

---

## Open-Ended Feedback

21. What is the most frustrating aspect of the development workflow?

22. What improvement would have the biggest positive impact?

23. What tooling or documentation do you wish existed?

---

Thank you for your feedback! Results will be used to prioritize DX improvements.
"""


def get_space_survey_template() -> str:
    """Get the SPACE framework survey template."""
    return SPACE_SURVEY_TEMPLATE
