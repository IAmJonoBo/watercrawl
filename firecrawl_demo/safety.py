from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlparse


@dataclass(frozen=True)
class SafetyViolation:
    code: str
    message: str


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    violations: list[SafetyViolation]


@dataclass(slots=True)
class SafetyPolicy:
    blocked_domains: set[str] = field(default_factory=set)
    blocked_keywords: set[str] = field(default_factory=set)
    max_diff_size: int = 5000


def _domain_from_value(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    return parsed.hostname


def evaluate_plan_commit(
    *,
    plan: dict[str, object],
    metrics: dict[str, float],
    policy: SafetyPolicy,
    rag_threshold: float,
) -> SafetyDecision:
    """Assess a plan→commit proposal for policy compliance."""

    violations: list[SafetyViolation] = []

    rag_score = metrics.get("rag_score") or metrics.get("rag", 0.0)
    if rag_score < rag_threshold:
        violations.append(
            SafetyViolation(
                code="rag_below_threshold",
                message=f"RAG score {rag_score:.2f} below threshold {rag_threshold:.2f}",
            )
        )

    changes = plan.get("changes")
    change_items: Iterable[object]
    if isinstance(changes, Iterable) and not isinstance(changes, (str, bytes)):
        change_items = changes
    else:
        change_items = []

    total_change_size = 0
    for change in change_items:
        total_change_size += len(str(change))
        if isinstance(change, dict):
            candidate_value = str(change.get("value") or "")
            domain = _domain_from_value(candidate_value)
            if domain and domain.lower() in {
                host.lower() for host in policy.blocked_domains
            }:
                violations.append(
                    SafetyViolation(
                        code="blocked_domain",
                        message=f"Change targets blocked domain '{domain}'",
                    )
                )
            lower_value = candidate_value.lower()
            for keyword in policy.blocked_keywords:
                if keyword.lower() in lower_value:
                    violations.append(
                        SafetyViolation(
                            code="blocked_keyword",
                            message=f"Change contains blocked keyword '{keyword}'",
                        )
                    )
    if total_change_size > policy.max_diff_size:
        violations.append(
            SafetyViolation(
                code="diff_too_large",
                message=(
                    f"Proposed diff size {total_change_size} bytes exceeds limit {policy.max_diff_size}"
                ),
            )
        )

    allowed = not violations
    return SafetyDecision(allowed=allowed, violations=violations)


__all__ = [
    "SafetyDecision",
    "SafetyPolicy",
    "SafetyViolation",
    "evaluate_plan_commit",
]
