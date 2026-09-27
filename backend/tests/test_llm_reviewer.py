"""Tests for LLM-as-reviewer second-opinion flow."""

from __future__ import annotations

import pandas as pd

from src.ai_relevance.gemini_client import GeminiClassificationResult, GeminiUsage
from src.ai_relevance.llm_reviewer import (
    LLMReviewerConfig,
    add_llm_reviewer_candidate_columns,
    apply_llm_second_opinions,
    select_llm_review_indices,
)
from src.ai_relevance.schema import AIClassification


class FakeReviewer:
    def classify(self, publication):
        return GeminiClassificationResult(
            classification=AIClassification(
                label="AI",
                confidence=0.91,
                ai_category="Computer Vision",
                reason=f"{publication.publication_id} explicitly mentions CNN.",
                evidence=("abstract explicitly says CNN",),
            ),
            usage=GeminiUsage(input_tokens=10, output_tokens=8, total_tokens=18),
            raw_response="{}",
        )


def test_llm_candidates_are_limited_to_difficult_review_rows() -> None:
    frame = pd.DataFrame(
        [
            {
                "source_record_id": "auto-ai",
                "ai_classification_label": "AI",
                "ai_classification_confidence": "0.93",
                "ai_classification_reason": "ai_score_gte_0.85",
            },
            {
                "source_record_id": "uncertain",
                "ai_classification_label": "review",
                "ai_classification_confidence": "0.62",
                "ai_classification_reason": "ai_score_gte_0.40_and_lt_0.85",
            },
            {
                "source_record_id": "borderline",
                "ai_classification_label": "review",
                "ai_classification_confidence": "0.88",
                "ai_classification_reason": (
                    "borderline_false_positive_risk:iot:weak_ai_evidence"
                ),
            },
            {
                "source_record_id": "auto-non",
                "ai_classification_label": "non-AI",
                "ai_classification_confidence": "0.15",
                "ai_classification_reason": "ai_score_lt_0.40",
            },
        ]
    )

    config = LLMReviewerConfig(max_fraction=0.50)
    marked = add_llm_reviewer_candidate_columns(frame, config)

    assert set(select_llm_review_indices(frame, config)) == {1, 2}
    assert marked["ai_llm_reviewer_status"].tolist() == [
        "not_candidate",
        "pending",
        "pending",
        "not_candidate",
    ]
    assert marked.loc[2, "ai_llm_reviewer_decision_effect"] == (
        "human_review_context_only"
    )


def test_llm_second_opinion_does_not_override_ml_review_decision() -> None:
    frame = pd.DataFrame(
        [
            {
                "source_record_id": "paper-a",
                "title": "Forecasting with convolutional neural networks",
                "abstract": "The abstract explicitly says CNN.",
                "ai_classification_label": "review",
                "ai_classification_confidence": "0.58",
                "ai_classification_reason": "ai_score_gte_0.40_and_lt_0.85",
            }
        ]
    )

    reviewed = apply_llm_second_opinions(
        frame,
        client=FakeReviewer(),
        config=LLMReviewerConfig(
            max_fraction=1.0,
            model="gemini-test",
            prompt_version="v-test",
        ),
    )

    assert reviewed.loc[0, "ai_classification_label"] == "review"
    assert reviewed.loc[0, "ai_llm_reviewer_status"] == "success"
    assert reviewed.loc[0, "ai_llm_reviewer_label"] == "AI"
    assert reviewed.loc[0, "ai_llm_reviewer_model"] == "gemini-test"
    assert "human remains final" in reviewed.loc[0, "human_review_reason"]
