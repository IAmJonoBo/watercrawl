"""Backwards compatible shim for the analyst CLI entry point."""

try:
    import pandas as pd  # noqa: F401

    from firecrawl_demo.interfaces import analyst_cli as _analyst_cli

    cli = _analyst_cli.cli
    RichPipelineProgress = _analyst_cli.RichPipelineProgress
    LineageManager = _analyst_cli.LineageManager
    build_lakehouse_writer = _analyst_cli.build_lakehouse_writer

    def _resolve_progress_flag(output_format: str, requested: bool | None) -> bool:
        """Compatibility wrapper for the analyst progress toggle helper."""
        return _analyst_cli._resolve_progress_flag(output_format, requested)

    Progress = _analyst_cli.Progress
    asyncio = _analyst_cli.asyncio
    CopilotMCPServer = _analyst_cli.CopilotMCPServer
    Pipeline = _analyst_cli.Pipeline
    build_evidence_sink = _analyst_cli.build_evidence_sink
    read_dataset = _analyst_cli.read_dataset
    override_cli_dependencies = _analyst_cli.override_cli_dependencies

except ImportError:
    # Provide dummy objects when pandas is not available
    cli = None  # type: ignore
    RichPipelineProgress = None  # type: ignore
    LineageManager = None  # type: ignore
    build_lakehouse_writer = None  # type: ignore

    def _resolve_progress_flag(output_format: str, requested: bool | None) -> bool:
        """Compatibility wrapper for the analyst progress toggle helper."""
        raise NotImplementedError("CLI functionality requires pandas (Python < 3.14)")

    Progress = None  # type: ignore
    asyncio = None  # type: ignore
    CopilotMCPServer = None  # type: ignore
    Pipeline = None  # type: ignore
    build_evidence_sink = None  # type: ignore
    read_dataset = None  # type: ignore
    override_cli_dependencies = None  # type: ignore

__all__ = [
    "cli",
    "RichPipelineProgress",
    "LineageManager",
    "build_lakehouse_writer",
    "_resolve_progress_flag",
    "Progress",
    "asyncio",
    "CopilotMCPServer",
    "Pipeline",
    "build_evidence_sink",
    "read_dataset",
    "override_cli_dependencies",
]


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    if cli is not None:
        cli()
    else:
        print("CLI not available: requires pandas (Python < 3.14)")
