"""Tests for AI relevance classification and filtering."""

from pathlib import Path

import joblib
import pandas as pd

from src.pipeline.classify_ai_relevance_dataset import (
    classify_ai_relevance_dataset,
    filter_ai_review_dataset,
    label_from_ai_score,
)


class FixedProbabilityModel:
    classes_ = ["AI", "NON_AI"]

    def predict_proba(self, text):
        scores = [0.90, 0.85, 0.84, 0.40, 0.39]
        return [[score, 1.0 - score] for score in scores[: len(text)]]


def test_label_from_ai_score_uses_requested_boundaries() -> None:
    assert label_from_ai_score(0.85) == "AI"
    assert label_from_ai_score(0.849999) == "review"
    assert label_from_ai_score(0.40) == "review"
    assert label_from_ai_score(0.399999) == "non-AI"


def test_classification_writes_all_predictions_and_filters_ai_review(tmp_path: Path) -> None:
    input_csv = tmp_path / "analysis_ready.csv"
    classified_csv = tmp_path / "classified.csv"
    filtered_csv = tmp_path / "ai_review.csv"
    model_path = tmp_path / "model.joblib"
    pd.DataFrame(
        {
            "source_record_id": ["one", "two", "three", "four", "five"],
            "doi": ["10.1000/one", pd.NA, "10.1000/three", pd.NA, "10.1000/five"],
            "title": ["AI research"] * 5,
        }
    ).to_csv(input_csv, index=False)
    joblib.dump(FixedProbabilityModel(), model_path)

    result = classify_ai_relevance_dataset(
        input_csv,
        classified_csv,
        model_path=model_path,
        text_columns=("title",),
    )
    filter_result = filter_ai_review_dataset(classified_csv, filtered_csv)

    classified = pd.read_csv(classified_csv)
    filtered = pd.read_csv(filtered_csv)
    assert classified["ai_classification_label"].tolist() == [
        "AI",
        "AI",
        "review",
        "review",
        "non-AI",
    ]
    assert filtered["source_record_id"].tolist() == ["one", "two", "three", "four"]
    assert pd.isna(filtered.loc[1, "doi"])
    assert result.input_rows == 5
    assert result.ai_rows == 2
    assert result.review_rows == 2
    assert result.non_ai_rows == 1
    assert filter_result.filtered_rows == 4


def test_borderline_smart_system_without_clear_ai_goes_to_review(tmp_path: Path) -> None:
    input_csv = tmp_path / "analysis_ready.csv"
    classified_csv = tmp_path / "classified.csv"
    model_path = tmp_path / "model.joblib"
    pd.DataFrame(
        {
            "source_record_id": ["smart", "ml"],
            "doi": ["10.1000/smart", "10.1000/ml"],
            "title": [
                "Smart irrigation system using wireless sensors",
                "Machine learning model for smart irrigation prediction",
            ],
            "abstract": [""] * 2,
        }
    ).to_csv(input_csv, index=False)

    joblib.dump(FixedProbabilityModel(), model_path)

    classify_ai_relevance_dataset(
        input_csv,
        classified_csv,
        model_path=model_path,
        text_columns=("title", "abstract"),
    )

    classified = pd.read_csv(classified_csv)
    assert classified["ai_classification_label"].tolist() == ["review", "AI"]
    assert classified.loc[0, "ai_classification_reason"].startswith(
        "borderline_false_positive_risk:"
    )
