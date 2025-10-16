"""Scaffolding for infrastructure planning across crawler, policy, and observability layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import cast

from .. import config


@dataclass(frozen=True)
class CrawlerPlan:
    """Normalised view of crawler infrastructure settings."""

    frontier_backend: str
    scheduler_mode: str
    politeness_delay_seconds: float
    max_depth: int
    max_pages: int
    trap_rules_path: Path | None
    user_agent: str
    robots_cache_hours: float


@dataclass(frozen=True)
class SLOPlan:
    """Service-level objective thresholds for enforcement."""

    availability_target: float
    latency_p95_ms: float
    error_budget_percent: float


@dataclass(frozen=True)
class ProbePlan:
    """HTTP probe wiring for Kubernetes-style health checks."""

    port: int
    liveness_path: str
    readiness_path: str
    startup_path: str


@dataclass(frozen=True)
class ObservabilityPlan:
    """Aggregated observability strategy for the stack."""

    probes: ProbePlan
    slos: SLOPlan
    alert_routes: tuple[str, ...]


@dataclass(frozen=True)
class PolicyPlan:
    """OPA policy bundle contract used by the MCP/CLI surfaces."""

    bundle_path: Path | None
    decision_path: str
    enforcement_mode: str
    cache_seconds: int

    @property
    def enforcing(self) -> bool:
        """Return ``True`` when the policy gate is set to enforce mode."""

        return self.enforcement_mode.lower() == "enforce"


@dataclass(frozen=True)
class PlanCommitContract:
    """Constraints for the plan→commit workflow used by automation."""

    require_plan: bool
    diff_format: str
    audit_topic: str
    allow_force_commit: bool


@dataclass(frozen=True)
class DeploymentAlignment:
    """Links infrastructure configuration to deployed automation assets."""

    probe_paths: tuple[str, ...]
    opa_bundle_path: Path | None
    opa_decision_path: str
    automation_topics: tuple[str, ...]
    plan_required: bool


@dataclass(frozen=True)
class InfrastructurePlan:
    """Complete view of the infrastructure scaffolding."""

    crawler: CrawlerPlan
    observability: ObservabilityPlan
    policy: PolicyPlan
    plan_commit: PlanCommitContract
    deployment: DeploymentAlignment


def build_infrastructure_plan() -> InfrastructurePlan:
    """Assemble an :class:`InfrastructurePlan` from configuration values."""

    crawler_settings = config.CRAWLER_INFRASTRUCTURE
    observability_settings = config.OBSERVABILITY
    policy_settings = config.POLICY_GUARDS
    plan_commit_settings = config.PLAN_COMMIT

    crawler_plan = CrawlerPlan(
        frontier_backend=crawler_settings.frontier_backend,
        scheduler_mode=crawler_settings.scheduler_mode,
        politeness_delay_seconds=crawler_settings.politeness_delay_seconds,
        max_depth=crawler_settings.max_depth,
        max_pages=crawler_settings.max_pages,
        trap_rules_path=crawler_settings.trap_rules_path,
        user_agent=crawler_settings.user_agent,
        robots_cache_hours=crawler_settings.robots_cache_hours,
    )

    probe_plan = ProbePlan(
        port=observability_settings.probes.port,
        liveness_path=observability_settings.probes.liveness_path,
        readiness_path=observability_settings.probes.readiness_path,
        startup_path=observability_settings.probes.startup_path,
    )

    slo_plan = SLOPlan(
        availability_target=observability_settings.slos.availability_target,
        latency_p95_ms=observability_settings.slos.latency_p95_ms,
        error_budget_percent=observability_settings.slos.error_budget_percent,
    )

    observability_plan = ObservabilityPlan(
        probes=probe_plan,
        slos=slo_plan,
        alert_routes=observability_settings.alert_routes,
    )

    policy_plan = PolicyPlan(
        bundle_path=policy_settings.bundle_path,
        decision_path=policy_settings.decision_path,
        enforcement_mode=policy_settings.enforcement_mode,
        cache_seconds=policy_settings.cache_seconds,
    )

    plan_contract = PlanCommitContract(
        require_plan=plan_commit_settings.require_plan,
        diff_format=plan_commit_settings.diff_format,
        audit_topic=plan_commit_settings.audit_topic,
        allow_force_commit=plan_commit_settings.allow_force_commit,
    )

    deployment_alignment = DeploymentAlignment(
        probe_paths=(
            observability_settings.probes.liveness_path,
            observability_settings.probes.readiness_path,
            observability_settings.probes.startup_path,
        ),
        opa_bundle_path=policy_settings.bundle_path,
        opa_decision_path=policy_settings.decision_path,
        automation_topics=(plan_commit_settings.audit_topic,),
        plan_required=plan_commit_settings.require_plan,
    )

    return InfrastructurePlan(
        crawler=crawler_plan,
        observability=observability_plan,
        policy=policy_plan,
        plan_commit=plan_contract,
        deployment=deployment_alignment,
    )


def plan_to_mapping(plan: InfrastructurePlan) -> dict[str, object]:
    """Convert an :class:`InfrastructurePlan` into a serialisable mapping."""

    snapshot = _normalise_snapshot(asdict(plan))
    if not isinstance(snapshot, dict):  # pragma: no cover - defensive
        raise TypeError("InfrastructurePlan snapshot must be a mapping")
    return cast(dict[str, object], snapshot)


def detect_plan_drift(
    plan: InfrastructurePlan,
    reference: Mapping[str, object] | InfrastructurePlan | None = None,
) -> list[str]:
    """Return human-readable differences between ``plan`` and the reference."""

    baseline = reference
    if baseline is None:
        baseline_mapping = BASELINE_PLAN_SNAPSHOT
    elif isinstance(baseline, InfrastructurePlan):
        baseline_mapping = plan_to_mapping(baseline)
    else:
        baseline_mapping = dict(baseline)

    snapshot = plan_to_mapping(plan)
    differences: list[str] = []
    _compare_snapshots("", snapshot, baseline_mapping, differences)
    return differences


def _normalise_snapshot(value: object) -> object:
    if isinstance(value, dict):
        return {key: _normalise_snapshot(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalise_snapshot(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalise_snapshot(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    return value


def _compare_snapshots(
    prefix: str, current: object, baseline: object, differences: list[str]
) -> None:
    if isinstance(current, dict) and isinstance(baseline, dict):
        keys = sorted(set(current) | set(baseline))
        for key in keys:
            next_prefix = f"{prefix}.{key}" if prefix else key
            _compare_snapshots(
                next_prefix, current.get(key), baseline.get(key), differences
            )
        return

    if current == baseline:
        return

    differences.append(f"{prefix}: expected {baseline!r} but found {current!r}")


BASELINE_PLAN_SNAPSHOT = plan_to_mapping(build_infrastructure_plan())
