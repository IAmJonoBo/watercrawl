"""Shared CLI scaffolding for plan guards, telemetry, and pipeline wiring."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from firecrawl_demo.application.pipeline import Pipeline
from firecrawl_demo.core import config
from firecrawl_demo.infrastructure.planning import (
    PlanCommitContract,
    build_infrastructure_plan,
)


class PlanCommitError(RuntimeError):
    """Raised when a destructive command violates plan→commit policy."""


@dataclass(slots=True)
class PlanCommitGuard:
    """Validate plan artefacts before executing destructive operations."""

    contract: PlanCommitContract
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("firecrawl_demo.plan_commit")
    )

    def require(
        self,
        command: str,
        plan_paths: Sequence[Path] | None,
        *,
        force: bool = False,
    ) -> list[Path]:
        """Ensure the provided plan artefacts satisfy the policy contract."""

        if force and not self.contract.allow_force_commit:
            raise PlanCommitError("Force overrides are disabled by policy")

        resolved = self._normalise_paths(plan_paths)
        if not resolved:
            if self.contract.require_plan and not force:
                raise PlanCommitError(
                    (
                        f"Command '{command}' requires at least one *.plan artefact. "
                        "Provide --plan <path> or use --force when policy allows it."
                    )
                )
            self._log_audit(command, resolved, force)
            return []

        invalid_suffix = [path for path in resolved if path.suffix != ".plan"]
        if invalid_suffix:
            joined = ", ".join(str(path) for path in invalid_suffix)
            raise PlanCommitError(f"Plan artefacts must end with '.plan': {joined}")

        missing = [path for path in resolved if not path.exists()]
        if missing:
            joined = ", ".join(str(path) for path in missing)
            raise PlanCommitError(f"Plan artefact not found: {joined}")

        empty = [path for path in resolved if path.stat().st_size == 0]
        if empty and not force:
            joined = ", ".join(str(path) for path in empty)
            raise PlanCommitError(f"Plan artefact is empty: {joined}")

        self._log_audit(command, resolved, force)
        return resolved

    def require_for_payload(
        self, command: str, payload: Mapping[str, object]
    ) -> list[Path]:
        """Extract plan artefacts from an MCP payload and validate them."""

        force_override = bool(payload.get("force", False))
        raw_plans = payload.get("plan_artifacts")
        if raw_plans is None and "plan" in payload:
            raw_plans = payload["plan"]

        plan_paths: list[Path] | None
        if raw_plans is None:
            plan_paths = None
        elif isinstance(raw_plans, (str, Path)):
            plan_paths = [Path(raw_plans)]
        elif isinstance(raw_plans, Iterable):
            plan_paths = []
            for item in raw_plans:
                if not isinstance(item, (str, Path)):
                    raise PlanCommitError(
                        "plan_artifacts entries must be string or Path instances"
                    )
                plan_paths.append(Path(item))
        else:
            raise PlanCommitError(
                "plan_artifacts must be a list of string paths or a single path"
            )

        return self.require(command, plan_paths, force=force_override)

    @property
    def audit_topic(self) -> str:
        """Return the audit topic configured for plan→commit events."""

        return self.contract.audit_topic

    def _normalise_paths(
        self, plan_paths: Sequence[Path] | None
    ) -> list[Path]:  # pragma: no cover - trivial helper
        if not plan_paths:
            return []
        return [Path(path).expanduser().resolve() for path in plan_paths]

    def _log_audit(self, command: str, plan_paths: Sequence[Path], force: bool) -> None:
        payload = {
            "topic": self.contract.audit_topic,
            "command": command,
            "plans": [path.as_posix() for path in plan_paths],
            "diff_format": self.contract.diff_format,
            "force": force,
        }
        self.logger.info("plan_commit.audit %s", payload)


@dataclass(frozen=True)
class CliTelemetry:
    """Telemetry metadata shared across CLI surfaces."""

    namespace: str
    job_name: str
    dataset_name: str


@dataclass(frozen=True)
class CliEnvironment:
    """Environment hooks shared by analyst, developer, and MCP surfaces."""

    pipeline_factory: type[Pipeline]
    plan_guard: PlanCommitGuard
    telemetry: CliTelemetry


def load_cli_environment() -> CliEnvironment:
    """Construct the shared CLI environment bindings."""

    infrastructure_plan = build_infrastructure_plan()
    guard = PlanCommitGuard(infrastructure_plan.plan_commit)
    telemetry = CliTelemetry(
        namespace=config.LINEAGE.namespace,
        job_name=config.LINEAGE.job_name,
        dataset_name=config.LINEAGE.dataset_name,
    )
    return CliEnvironment(
        pipeline_factory=Pipeline, plan_guard=guard, telemetry=telemetry
    )


__all__ = [
    "CliEnvironment",
    "CliTelemetry",
    "PlanCommitError",
    "PlanCommitGuard",
    "load_cli_environment",
]
