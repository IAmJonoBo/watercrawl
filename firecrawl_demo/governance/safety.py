from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
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
    prompt_injection_tokens: set[str] = field(
        default_factory=lambda: {
            "ignore previous instructions",
            "override safety",
            "system:",
            "assistant:",
            "user:",
            "<script",
            "{{",
        }
    )
    blocked_commands: set[str] = field(
        default_factory=lambda: {"rm -rf", "curl", "wget", "powershell"}
    )


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
    rag_thresholds: Mapping[str, float] | float,
) -> SafetyDecision:
    """Assess a plan→commit proposal for policy compliance."""

    violations: list[SafetyViolation] = []

    if isinstance(rag_thresholds, Mapping):
        thresholds = dict(rag_thresholds)
        base_rag_threshold = thresholds.get(
            "faithfulness", thresholds.get("score", 0.0)
        )
    else:
        base_rag_threshold = float(rag_thresholds)
        thresholds = {"faithfulness": base_rag_threshold}

    rag_score = (
        metrics.get("rag_score")
        or metrics.get("rag_faithfulness")
        or metrics.get("rag", 0.0)
    )
    if rag_score < base_rag_threshold:
        violations.append(
            SafetyViolation(
                code="rag_below_threshold",
                message=(
                    f"RAG score {rag_score:.2f} below threshold "
                    f"{base_rag_threshold:.2f}"
                ),
            )
        )

    for metric_name, threshold in thresholds.items():
        metric_key = f"rag_{metric_name}"
        metric_value = metrics.get(metric_key)
        if metric_value is None:
            continue
        if metric_value < threshold:
            violations.append(
                SafetyViolation(
                    code=f"rag_{metric_name}_below_threshold",
                    message=(
                        f"RAG metric '{metric_name}' {metric_value:.2f} below "
                        f"threshold {threshold:.2f}"
                    ),
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
            for keyword in policy.blocked_keywords | policy.blocked_commands:
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

    text_segments: list[str] = []
    if isinstance(changes, Iterable):
        for change in change_items:
            if isinstance(change, Mapping):
                value = change.get("value")
                if isinstance(value, str):
                    text_segments.append(value.lower())
    instructions = plan.get("instructions")
    if isinstance(instructions, str):
        text_segments.append(instructions.lower())
    diff_summary = plan.get("diff_summary")
    if isinstance(diff_summary, str):
        text_segments.append(diff_summary.lower())

    for segment in text_segments:
        for token in policy.prompt_injection_tokens:
            if token.lower() in segment:
                violations.append(
                    SafetyViolation(
                        code="prompt_injection_pattern",
                        message=f"Detected prompt-injection token '{token}'",
                    )
                )
                break
        for command in policy.blocked_commands:
            if command.lower() in segment:
                violations.append(
                    SafetyViolation(
                        code="blocked_command",
                        message=f"Detected blocked command '{command}' in diff summary",
                    )
                )
                break

    allowed = not violations
    return SafetyDecision(allowed=allowed, violations=violations)


__all__ = [
    "SafetyDecision",
    "SafetyPolicy",
    "SafetyViolation",
    "evaluate_plan_commit",
]
