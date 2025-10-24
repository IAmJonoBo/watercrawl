from __future__ import annotations

from watercrawl.governance.rag_evaluation import (
    RagEvaluationConfig,
    evaluate_responses,
)


def test_evaluate_responses_returns_threshold_gate() -> None:
    config = RagEvaluationConfig(similarity_threshold=0.2)
    responses = [
        "The school is accredited by SACAA and operates in Gauteng.",
        "Contact email is ops@aero.example with +27110000000",
    ]
    references = [
        "SACAA accreditation and Gauteng operations confirmed",
        "Contact information includes ops@aero.example and +27110000000",
    ]

    report = evaluate_responses(
        responses=responses, references=references, config=config
    )

    assert report.average_score >= 0.0
    assert report.passed is True
    assert report.scores
    assert len(report.scores) == len(responses)
