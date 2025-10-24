"""Tests for the column inference engine."""

from __future__ import annotations

import pytest

pytest.importorskip("yaml")

from watercrawl.core.column_inference import (
    ColumnInferenceEngine,
    ColumnInferenceResult,
    ColumnMatch,
)
from watercrawl.core.profiles import ColumnDescriptor

pd = pytest.importorskip("pandas")


def test_inference_scores_synonyms_and_ontologies() -> None:
    descriptors = (
        ColumnDescriptor(
            name="Name of Organisation",
            synonyms=("Organisation Name", "School Name"),
        ),
        ColumnDescriptor(
            name="Province",
            allowed_values=(
                "Eastern Cape",
                "Gauteng",
                "Western Cape",
            ),
            detection_hooks=("allowed_values",),
        ),
        ColumnDescriptor(
            name="Website URL",
            synonyms=("Website", "URL"),
            detection_hooks=("url_pattern",),
        ),
    )
    frame = pd.DataFrame(
        {
            "Org Name": ["Skywings Academy"],
            "Region": ["Gauteng"],
            "Website": ["https://skywings.example"],
        }
    )
    engine = ColumnInferenceEngine(descriptors)
    result = engine.infer(frame)

    assert result.rename_map["Org Name"] == "Name of Organisation"
    assert result.rename_map["Region"] == "Province"
    assert result.rename_map["Website"] == "Website URL"

    province_match = next(
        match for match in result.matches if match.canonical == "Province"
    )
    assert province_match.score > 0.8
    assert any("ontology" in reason.lower() for reason in province_match.reasons)


def test_merge_prefers_highest_score() -> None:
    match_low = ColumnMatch(
        source="Region",
        canonical="Province",
        score=0.6,
        matched_label="Province",
        reasons=("Fuzzy match",),
        sample_size=3,
    )
    match_high = ColumnMatch(
        source="Region",
        canonical="Province",
        score=0.92,
        matched_label="Province",
        reasons=("Synonym match",),
        sample_size=3,
    )
    result_low = ColumnInferenceResult(
        matches=(match_low,),
        unmatched_sources=("Region",),
        missing_targets=("Province",),
        rename_map={"Region": "Province"},
    )
    result_high = ColumnInferenceResult(
        matches=(match_high,),
        unmatched_sources=(),
        missing_targets=(),
        rename_map={"Region": "Province"},
    )

    merged = ColumnInferenceResult.merge([result_low, result_high])

    assert merged.rename_map["Region"] == "Province"
    assert merged.matches[0].score == match_high.score
    assert merged.unmatched_sources == ()
    assert merged.missing_targets == ()
