from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RagEvaluationConfig:
    similarity_threshold: float = 0.75


@dataclass(frozen=True)
class RagEvaluationReport:
    scores: list[float]
    average_score: float
    passed: bool


def _tokenise(text: str) -> set[str]:
    return {token.strip(".,;:!?").lower() for token in text.split() if token}


def _similarity(candidate: str, reference: str) -> float:
    candidate_tokens = _tokenise(candidate)
    reference_tokens = _tokenise(reference)
    if not candidate_tokens or not reference_tokens:
        return 0.0
    intersection = candidate_tokens & reference_tokens
    union = candidate_tokens | reference_tokens
    return len(intersection) / len(union)


def evaluate_responses(
    *, responses: Iterable[str], references: Iterable[str], config: RagEvaluationConfig
) -> RagEvaluationReport:
    """Compute lexical overlap scores for responses against references."""

    scores: list[float] = []
    for response, reference in zip(responses, references, strict=False):
        scores.append(_similarity(response, reference))
    if not scores:
        return RagEvaluationReport(scores=[], average_score=0.0, passed=False)
    average = sum(scores) / len(scores)
    passed = average >= config.similarity_threshold and all(
        score >= config.similarity_threshold for score in scores
    )
    return RagEvaluationReport(scores=scores, average_score=average, passed=passed)


__all__ = [
    "RagEvaluationConfig",
    "RagEvaluationReport",
    "evaluate_responses",
]
