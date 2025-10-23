"""Shared CLI scaffolding for plan guards, telemetry, and pipeline wiring."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from watercrawl.application.pipeline import Pipeline
from watercrawl.core import config
from watercrawl.domain.contracts import CommitArtifactContract, PlanArtifactContract
from watercrawl.governance.safety import (
    SafetyDecision,
    SafetyPolicy,
    evaluate_plan_commit,
)
from watercrawl.infrastructure.planning import (
    PlanCommitContract,
    build_infrastructure_plan,
)


class PlanCommitError(RuntimeError):
    """Raised when a destructive command violates plan→commit policy."""


@dataclass(frozen=True)
class PlanValidationResult:
    """Validated artefacts captured during plan→commit enforcement."""

    plan_paths: list[Path]
    commit_paths: list[Path]
    commit_payloads: list[Mapping[str, Any]]


@dataclass(slots=True)
class PlanCommitGuard:
    """Validate plan artefacts before executing destructive operations."""

    contract: PlanCommitContract
    policy: SafetyPolicy | None = None
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("watercrawl.plan_commit")
    )

    def __post_init__(self) -> None:
        if self.policy is None:
            self.policy = SafetyPolicy(
                blocked_domains=set(self.contract.blocked_domains),
                blocked_keywords=set(self.contract.blocked_keywords),
                max_diff_size=self.contract.max_diff_size,
            )

    def require(
        self,
        command: str,
        plan_paths: Sequence[Path] | None,
        *,
        commit_paths: Sequence[Path] | None = None,
        force: bool = False,
    ) -> PlanValidationResult:
        """Ensure the provided plan and commit artefacts satisfy policy contracts."""

        if force and not self.contract.allow_force_commit:
            raise PlanCommitError("Force overrides are disabled by policy")

        resolved_plans = self._normalise_paths(plan_paths)
        if not resolved_plans and self.contract.require_plan and not force:
            raise PlanCommitError(
                f"Command '{command}' requires at least one *.plan artefact. "
                "Provide --plan <path> or use --force when policy allows it."
            )

        plan_payloads = self._load_plan_payloads(resolved_plans, force=force)

        resolved_commits = self._normalise_paths(commit_paths)
        if self.contract.require_commit and not resolved_commits and not force:
            raise PlanCommitError(
                f"Command '{command}' requires at least one *.commit artefact. "
                "Provide --commit <path> or use --force when policy allows it."
            )

        commit_payloads = self._load_commit_payloads(resolved_commits, force=force)

        if self.contract.require_if_match and not force:
            missing_if_match = [
                str(path)
                for path, payload in zip(
                    resolved_commits, commit_payloads, strict=False
                )
                if not self._extract_if_match(payload)
            ]
            if missing_if_match:
                raise PlanCommitError(
                    "Commit artefacts missing required If-Match header: "
                    + ", ".join(missing_if_match)
                )

        metrics = self._extract_commit_metrics(commit_payloads)
        aggregated_plan = self._aggregate_plan(plan_payloads, commit_payloads)

        active_policy = self.policy or SafetyPolicy(
            blocked_domains=set(self.contract.blocked_domains),
            blocked_keywords=set(self.contract.blocked_keywords),
            max_diff_size=self.contract.max_diff_size,
        )

        decision = evaluate_plan_commit(
            plan=aggregated_plan,
            metrics=metrics,
            policy=active_policy,
            rag_thresholds=self.contract.rag_thresholds,
        )
        allowed = decision.allowed or force

        self._log_audit(
            command=command,
            plan_paths=resolved_plans,
            commit_paths=resolved_commits,
            commit_payloads=commit_payloads,
            metrics=metrics,
            decision=decision,
            force=force,
        )

        if not allowed:
            violation_text = "; ".join(
                f"{violation.code}: {violation.message}"
                for violation in decision.violations
            )
            raise PlanCommitError(violation_text or "Plan→commit policy rejected")

        return PlanValidationResult(
            plan_paths=resolved_plans,
            commit_paths=resolved_commits,
            commit_payloads=commit_payloads,
        )

    def require_for_payload(
        self, command: str, payload: Mapping[str, object]
    ) -> PlanValidationResult:
        """Extract artefacts from an MCP payload and validate them."""

        force_override = bool(payload.get("force", False))
        raw_plans = payload.get("plan_artifacts") or payload.get("plan")
        raw_commits = payload.get("commit_artifacts") or payload.get("commit")

        plan_paths = self._coerce_artifact_paths(raw_plans, "plan_artifacts")
        commit_paths = self._coerce_artifact_paths(raw_commits, "commit_artifacts")

        return self.require(
            command,
            plan_paths,
            commit_paths=commit_paths,
            force=force_override,
        )

    @property
    def audit_topic(self) -> str:
        """Return the audit topic configured for plan→commit events."""

        return self.contract.audit_topic

    def _normalise_paths(
        self, artefact_paths: Sequence[Path] | None
    ) -> list[Path]:  # pragma: no cover - trivial helper
        if not artefact_paths:
            return []
        return [Path(path).expanduser().resolve() for path in artefact_paths]

    def _coerce_artifact_paths(
        self, raw_value: object, field_name: str
    ) -> list[Path] | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, (str, Path)):
            return [Path(raw_value)]
        if isinstance(raw_value, Iterable):
            paths: list[Path] = []
            for item in raw_value:
                if not isinstance(item, (str, Path)):
                    raise PlanCommitError(
                        f"{field_name} entries must be string or Path instances"
                    )
                paths.append(Path(item))
            return paths
        raise PlanCommitError(
            f"{field_name} must be a list of paths or a single path string"
        )

    def _load_plan_payloads(
        self, plan_paths: Sequence[Path], *, force: bool
    ) -> list[Mapping[str, Any]]:
        payloads: list[Mapping[str, Any]] = []
        for path in plan_paths:
            if path.suffix != ".plan":
                raise PlanCommitError(
                    f"Plan artefacts must end with '.plan': {path.as_posix()}"
                )
            if not path.exists():
                raise PlanCommitError(f"Plan artefact not found: {path.as_posix()}")
            if path.stat().st_size == 0 and not force:
                raise PlanCommitError(f"Plan artefact is empty: {path.as_posix()}")
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise PlanCommitError(
                    f"Plan artefact {path.as_posix()} is not valid JSON"
                ) from exc
            if not isinstance(data, Mapping):
                raise PlanCommitError(
                    f"Plan artefact {path.as_posix()} must contain a JSON object"
                )
            contract = PlanArtifactContract.model_validate(data)
            payloads.append(contract.model_dump())
        return payloads

    def _load_commit_payloads(
        self, commit_paths: Sequence[Path], *, force: bool
    ) -> list[Mapping[str, Any]]:
        payloads: list[Mapping[str, Any]] = []
        for path in commit_paths:
            if path.suffix != ".commit":
                raise PlanCommitError(
                    f"Commit artefacts must end with '.commit': {path.as_posix()}"
                )
            if not path.exists():
                raise PlanCommitError(f"Commit artefact not found: {path.as_posix()}")
            if path.stat().st_size == 0 and not force:
                raise PlanCommitError(
                    f"Commit artefact is empty: {path.as_posix()}. Provide diff approval metadata."
                )
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise PlanCommitError(
                    f"Commit artefact {path.as_posix()} is not valid JSON"
                ) from exc
            if not isinstance(data, Mapping):
                raise PlanCommitError(
                    f"Commit artefact {path.as_posix()} must contain a JSON object"
                )
            diff_format = data.get("diff_format")
            if diff_format and diff_format != self.contract.diff_format:
                raise PlanCommitError(
                    f"Commit artefact {path.as_posix()} reports diff_format "
                    f"{diff_format!r} but policy requires {self.contract.diff_format!r}"
                )
            contract = CommitArtifactContract.model_validate(data)
            payloads.append(contract.model_dump())
        return payloads

    def _aggregate_plan(
        self,
        plan_payloads: Sequence[Mapping[str, Any]],
        commit_payloads: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        aggregated: dict[str, Any] = {"changes": []}
        instructions: list[str] = []
        for payload in plan_payloads:
            changes = payload.get("changes")
            if isinstance(changes, Iterable):
                aggregated["changes"].extend(changes)
            instruction = payload.get("instructions") or payload.get("summary")
            if isinstance(instruction, str):
                instructions.append(instruction.strip())
        combined_instructions = " ".join(text for text in instructions if text)
        if combined_instructions:
            aggregated["instructions"] = combined_instructions

        diff_summaries: list[str] = []
        for payload in commit_payloads:
            summary = payload.get("diff_summary") or payload.get("diff")
            if isinstance(summary, str):
                diff_summaries.append(summary.strip())
        if diff_summaries:
            aggregated["diff_summary"] = "\n".join(diff_summaries)
        return aggregated

    def _extract_commit_metrics(
        self, commit_payloads: Sequence[Mapping[str, Any]]
    ) -> dict[str, float]:
        metrics: dict[str, float] = {}
        for payload in commit_payloads:
            rag_section = payload.get("rag") or payload.get("rag_metrics")
            if isinstance(rag_section, Mapping):
                for name, value in rag_section.items():
                    if isinstance(value, (int, float)):
                        metrics[f"rag_{name}"] = float(value)
                if "faithfulness" in rag_section:
                    metrics.setdefault("rag_score", float(rag_section["faithfulness"]))
            diff_summary = payload.get("diff_summary") or payload.get("diff")
            if isinstance(diff_summary, str):
                metrics["diff_size"] = float(len(diff_summary))
        return metrics

    @staticmethod
    def _extract_if_match(payload: Mapping[str, Any]) -> str | None:
        candidate = payload.get("if_match")
        if isinstance(candidate, str):
            return candidate.strip()
        headers = payload.get("headers")
        if isinstance(headers, Mapping):
            value = headers.get("If-Match")
            if isinstance(value, str):
                return value.strip()
        return None

    def _log_audit(
        self,
        *,
        command: str,
        plan_paths: Sequence[Path],
        commit_paths: Sequence[Path],
        commit_payloads: Sequence[Mapping[str, Any]],
        metrics: Mapping[str, float],
        decision: SafetyDecision,
        force: bool,
    ) -> None:
        audit_record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "topic": self.contract.audit_topic,
            "command": command,
            "plans": [path.as_posix() for path in plan_paths],
            "commits": [path.as_posix() for path in commit_paths],
            "diff_format": self.contract.diff_format,
            "force": force,
            "allowed": decision.allowed or force,
            "violations": [
                {"code": violation.code, "message": violation.message}
                for violation in decision.violations
            ],
            "if_match": [
                self._extract_if_match(payload) for payload in commit_payloads
            ],
        }
        if metrics:
            audit_record["metrics"] = dict(metrics)

        self.logger.info("plan_commit.audit %s", audit_record)

        try:
            audit_path = self.contract.audit_log_path
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(audit_record) + "\n")
        except OSError:
            self.logger.warning(
                "plan_commit.audit_write_failed",
                exc_info=True,
            )


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
