from __future__ import annotations

from firecrawl_demo.governance.safety import (
    SafetyDecision,
    SafetyPolicy,
    evaluate_plan_commit,
)


def test_evaluate_plan_commit_blocks_blocklisted_domain() -> None:
    policy = SafetyPolicy(blocked_domains={"example.com"}, max_diff_size=1000)
    plan: dict[str, object] = {
        "changes": [
            {
                "type": "update",
                "field": "Website URL",
                "value": "http://example.com/bad",
            }
        ]
    }
    metrics: dict[str, float] = {"rag_score": 0.9}

    decision = evaluate_plan_commit(
        plan=plan, metrics=metrics, policy=policy, rag_threshold=0.8
    )

    assert isinstance(decision, SafetyDecision)
    assert decision.allowed is False
    assert any(violation.code == "blocked_domain" for violation in decision.violations)


def test_evaluate_plan_commit_enforces_diff_size() -> None:
    policy = SafetyPolicy(blocked_domains=set(), max_diff_size=10)
    plan: dict[str, object] = {"changes": ["x" * 20]}
    metrics: dict[str, float] = {"rag_score": 0.95}

    decision = evaluate_plan_commit(
        plan=plan, metrics=metrics, policy=policy, rag_threshold=0.9
    )

    assert decision.allowed is False
    assert any(violation.code == "diff_too_large" for violation in decision.violations)
