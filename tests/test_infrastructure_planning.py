"""Tests for the infrastructure planning scaffolding."""

from __future__ import annotations

from dataclasses import dataclass

from firecrawl_demo.core import config
from firecrawl_demo.infrastructure import planning


@dataclass
class DummyProvider:
    values: dict[str, str | None]

    def get(self, name: str) -> str | None:  # pragma: no cover - simple helper
        return self.values.get(name)


def test_build_infrastructure_plan_uses_defaults() -> None:
    plan = planning.build_infrastructure_plan()

    assert plan.crawler.frontier_backend == "scrapy"
    assert plan.crawler.scheduler_mode == "priority"
    assert plan.observability.slos.availability_target == 99.5
    assert plan.policy.enforcement_mode == "enforce"
    assert plan.policy.enforcing is True
    assert plan.plan_commit.require_plan is True
    assert plan.plan_commit.require_commit is True
    assert plan.plan_commit.require_if_match is True
    assert plan.plan_commit.audit_log_path.name == "plan_commit_audit.jsonl"
    assert plan.plan_commit.max_diff_size == 5000
    assert plan.plan_commit.rag_thresholds["faithfulness"] == 0.75
    assert plan.deployment.commit_required is True
    assert plan.deployment.audit_log_path.name == "plan_commit_audit.jsonl"


def test_build_infrastructure_plan_respects_configuration() -> None:
    provider = DummyProvider(
        {
            "CRAWLER_FRONTIER_BACKEND": "stormcrawler",
            "CRAWLER_SCHEDULER_MODE": "bandit",
            "CRAWLER_POLITENESS_DELAY_SECONDS": "2.5",
            "CRAWLER_MAX_DEPTH": "12",
            "CRAWLER_MAX_PAGES": "9000",
            "CRAWLER_USER_AGENT": "ACESBot/2.0",
            "CRAWLER_ROBOTS_CACHE_HOURS": "12",
            "OBSERVABILITY_PORT": "9090",
            "OBSERVABILITY_LIVENESS_PATH": "/health/live",
            "OBSERVABILITY_READINESS_PATH": "/health/ready",
            "OBSERVABILITY_STARTUP_PATH": "/health/start",
            "OBSERVABILITY_ALERT_ROUTES": "slack,pagerduty",
            "SLO_AVAILABILITY_TARGET": "99.9",
            "SLO_LATENCY_P95_MS": "250",
            "SLO_ERROR_BUDGET_PERCENT": "1.2",
            "OPA_BUNDLE_PATH": "policies/bundle.tar.gz",
            "OPA_DECISION_PATH": "copilot/allow",
            "OPA_ENFORCEMENT_MODE": "dry-run",
            "OPA_CACHE_SECONDS": "120",
            "PLAN_COMMIT_REQUIRED": "0",
            "PLAN_COMMIT_DIFF_FORMAT": "json",
            "PLAN_COMMIT_AUDIT_TOPIC": "audit.plan-commit.test",
            "PLAN_COMMIT_ALLOW_FORCE": "1",
            "PLAN_COMMIT_REQUIRE_COMMIT": "0",
            "PLAN_COMMIT_REQUIRE_IF_MATCH": "0",
            "PLAN_COMMIT_AUDIT_LOG_PATH": "logs/custom_audit.jsonl",
            "PLAN_COMMIT_MAX_DIFF_SIZE": "2048",
            "PLAN_COMMIT_BLOCKED_DOMAINS": "blocked.example.com",
            "PLAN_COMMIT_BLOCKED_KEYWORDS": "rm -rf,net use",
            "PLAN_COMMIT_RAG_FAITHFULNESS": "0.85",
            "PLAN_COMMIT_RAG_CONTEXT_PRECISION": "0.8",
            "PLAN_COMMIT_RAG_ANSWER_RELEVANCY": "0.75",
        }
    )

    config.configure(provider)
    try:
        plan = planning.build_infrastructure_plan()
    finally:
        config.configure()

    assert plan.crawler.frontier_backend == "stormcrawler"
    assert plan.crawler.scheduler_mode == "bandit"
    assert plan.crawler.politeness_delay_seconds == 2.5
    assert plan.crawler.max_depth == 12
    assert plan.crawler.max_pages == 9000
    assert plan.crawler.user_agent == "ACESBot/2.0"
    assert plan.crawler.robots_cache_hours == 12.0
    assert plan.observability.probes.port == 9090
    assert plan.observability.probes.liveness_path == "/health/live"
    assert plan.observability.probes.readiness_path == "/health/ready"
    assert plan.observability.probes.startup_path == "/health/start"
    assert plan.observability.alert_routes == ("slack", "pagerduty")
    assert plan.observability.slos.availability_target == 99.9
    assert plan.observability.slos.latency_p95_ms == 250.0
    assert plan.observability.slos.error_budget_percent == 1.2
    assert plan.policy.bundle_path is not None
    assert str(plan.policy.bundle_path).endswith("policies/bundle.tar.gz")
    assert plan.policy.decision_path == "copilot/allow"
    assert plan.policy.enforcement_mode == "dry-run"
    assert plan.policy.cache_seconds == 120
    assert plan.policy.enforcing is False
    assert plan.plan_commit.require_plan is False
    assert plan.plan_commit.diff_format == "json"
    assert plan.plan_commit.audit_topic == "audit.plan-commit.test"
    assert plan.plan_commit.allow_force_commit is True
    assert plan.plan_commit.require_commit is False
    assert plan.plan_commit.require_if_match is False
    assert str(plan.plan_commit.audit_log_path).endswith("logs/custom_audit.jsonl")
    assert plan.plan_commit.max_diff_size == 2048
    assert plan.plan_commit.blocked_domains == ("blocked.example.com",)
    assert plan.plan_commit.blocked_keywords == ("rm -rf", "net use")
    assert plan.plan_commit.rag_thresholds["faithfulness"] == 0.85
    assert plan.plan_commit.rag_thresholds["context_precision"] == 0.8
    assert plan.plan_commit.rag_thresholds["answer_relevancy"] == 0.75
    assert plan.deployment.commit_required is False
    assert str(plan.deployment.audit_log_path).endswith("logs/custom_audit.jsonl")


def test_infrastructure_plan_matches_baseline_snapshot() -> None:
    snapshot = planning.plan_to_mapping(planning.build_infrastructure_plan())
    assert snapshot == planning.BASELINE_PLAN_SNAPSHOT


def test_infrastructure_plan_drift_detection_flags_changes(monkeypatch) -> None:
    provider = DummyProvider(
        {
            "OBSERVABILITY_READINESS_PATH": "/health/readyz-v2",
            "OPA_DECISION_PATH": "opa/deny",
            "PLAN_COMMIT_AUDIT_TOPIC": "audit.plan-commit.override",
        }
    )
    config.configure(provider)
    try:
        drift_plan = planning.build_infrastructure_plan()
    finally:
        config.configure()

    drift = planning.detect_plan_drift(drift_plan)

    assert any("ready" in entry for entry in drift)
    assert any("opa/deny" in entry for entry in drift)
    assert any("audit.plan-commit.override" in entry for entry in drift)
