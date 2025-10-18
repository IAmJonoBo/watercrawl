"""Backwards compatible shim for the analyst CLI entry point."""

from firecrawl_demo.interfaces import analyst_cli as _analyst_cli

cli = _analyst_cli.cli
RichPipelineProgress = _analyst_cli.RichPipelineProgress
LineageManager = _analyst_cli.LineageManager
build_lakehouse_writer = _analyst_cli.build_lakehouse_writer
# _resolve_progress_flag = _analyst_cli._resolve_progress_flag  # Removed direct access to protected member
Progress = _analyst_cli.Progress
asyncio = _analyst_cli.asyncio
CopilotMCPServer = _analyst_cli.CopilotMCPServer
Pipeline = _analyst_cli.Pipeline
build_evidence_sink = _analyst_cli.build_evidence_sink
read_dataset = _analyst_cli.read_dataset
override_cli_dependencies = _analyst_cli.override_cli_dependencies

__all__ = [
    "cli",
    "RichPipelineProgress",
    "LineageManager",
    "build_lakehouse_writer",
    # "_resolve_progress_flag",  # Removed from __all__ due to protected member access
    "Progress",
    "asyncio",
    "CopilotMCPServer",
    "Pipeline",
    "build_evidence_sink",
    "read_dataset",
    "override_cli_dependencies",
]


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    cli()
