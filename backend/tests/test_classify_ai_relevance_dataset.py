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


class FixedSecondaryModel:
    classes_ = ["AI", "NON_AI"]

    def __init__(self, scores):
        self.scores = scores

    def predict_proba(self, text):
        return [[score, 1.0 - score] for score in self.scores[: len(text)]]

    def predict(self, text):
        return ["AI" if score >= 0.85 else "NON_AI" for score in self.scores[: len(text)]]


class NumericProbabilityModel:
    classes_ = [0, 1]

    def predict(self, text):
        return [0, 1][: len(text)]

    def predict_proba(self, text):
        scores = [0.10, 0.91]
        return [[1.0 - score, score] for score in scores[: len(text)]]


def test_label_from_ai_score_uses_requested_boundaries() -> None:
    assert label_from_ai_score(0.85, ai_threshold=0.85) == "AI"
    assert label_from_ai_score(0.849999, ai_threshold=0.85) == "review"
    assert label_from_ai_score(0.40, ai_threshold=0.85) == "review"
    assert label_from_ai_score(0.399999, ai_threshold=0.85) == "non-AI"


def test_numeric_binary_model_treats_class_one_as_ai(tmp_path: Path) -> None:
    input_csv = tmp_path / "analysis_ready.csv"
    classified_csv = tmp_path / "classified.csv"
    model_path = tmp_path / "model.joblib"
    pd.DataFrame(
        {
            "source_record_id": ["one", "two"],
            "title": ["Bridge maintenance", "Deep learning for crop detection"],
        }
    ).to_csv(input_csv, index=False)
    joblib.dump(NumericProbabilityModel(), model_path)

    classify_ai_relevance_dataset(
        input_csv,
        classified_csv,
        model_path=model_path,
        text_columns=("title",),
        ai_threshold=0.85,
        calibrator_path="disabled",
    )

    classified = pd.read_csv(classified_csv)
    assert classified["ai_classification_label"].tolist() == ["non-AI", "AI"]
    assert classified["ai_classification_confidence"].tolist() == [0.1, 0.91]


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
        ai_threshold=0.85,
        calibrator_path="disabled",
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
    assert classified["ai_llm_reviewer_status"].tolist() == [
        "not_candidate",
        "not_candidate",
        "pending",
        "not_candidate",
        "not_candidate",
    ]
    assert classified.loc[0, "ai_explanation_confidence"] == "High"
    assert pd.isna(classified.loc[0, "ai_explanation_evidence"])
    assert classified.loc[2, "ai_explanation_confidence"] == "Needs review"
    assert classified.loc[2, "ai_explanation_reason"].startswith(
        "The calibrated model score"
    )
    assert classified.loc[2, "ai_llm_reviewer_decision_effect"] == (
        "human_review_context_only"
    )
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
        ai_threshold=0.85,
        calibrator_path="disabled",
    )

    classified = pd.read_csv(classified_csv)
    assert classified["ai_classification_label"].tolist() == ["review", "AI"]
    assert classified.loc[0, "ai_classification_reason"].startswith(
        "hard_negative_constraint:"
    )
    assert "smart-system terminology" in classified.loc[
        0,
        "ai_explanation_borderline_terms",
    ]
    assert "no explicit AI/ML methodology" in classified.loc[
        0,
        "ai_explanation_reason",
    ]


def test_borderline_smart_iot_with_clear_ai_evidence_stays_ai(tmp_path: Path) -> None:
    input_csv = tmp_path / "analysis_ready.csv"
    classified_csv = tmp_path / "classified.csv"
    model_path = tmp_path / "model.joblib"
    pd.DataFrame(
        {
            "source_record_id": ["ml-smart"],
            "doi": ["10.1000/ml-smart"],
            "title": ["Machine-learning based smart IoT system"],
            "abstract": ["A machine learning classifier controls sensor alerts."],
        }
    ).to_csv(input_csv, index=False)
    joblib.dump(FixedProbabilityModel(), model_path)

    classify_ai_relevance_dataset(
        input_csv,
        classified_csv,
        model_path=model_path,
        text_columns=("title", "abstract"),
        ai_threshold=0.85,
        calibrator_path="disabled",
    )

    classified = pd.read_csv(classified_csv)
    assert classified["ai_classification_label"].tolist() == ["AI"]
    assert classified.loc[0, "ai_classification_reason"] == "ai_score_gte_0.85"
    assert "machine learning" in classified.loc[0, "ai_explanation_evidence"]


def test_broad_metadata_ai_tag_does_not_override_borderline_review(tmp_path: Path) -> None:
    input_csv = tmp_path / "analysis_ready.csv"
    classified_csv = tmp_path / "classified.csv"
    model_path = tmp_path / "model.joblib"
    pd.DataFrame(
        {
            "source_record_id": ["metadata-only-ai"],
            "doi": ["10.1000/metadata-only-ai"],
            "title": ["Smart water meter with wireless sensor automation"],
            "abstract": ["A conventional embedded monitoring system."],
            "keywords": ["IoT; sensor; automation"],
            "concepts": ["Artificial intelligence"],
            "topics": ["Computer science"],
        }
    ).to_csv(input_csv, index=False)
    joblib.dump(FixedProbabilityModel(), model_path)

    classify_ai_relevance_dataset(
        input_csv,
        classified_csv,
        model_path=model_path,
        text_columns=("title", "abstract", "keywords"),
        ai_threshold=0.85,
        calibrator_path="disabled",
    )

    classified = pd.read_csv(classified_csv)
    assert classified["ai_classification_label"].tolist() == ["review"]
    assert classified.loc[0, "ai_classification_reason"].startswith(
        "hard_negative_constraint:"
    )
    assert "no explicit AI/ML methodology" in classified.loc[
        0,
        "ai_explanation_reason",
    ]


def test_fuzzy_topsis_hard_negative_pattern_goes_to_review(tmp_path: Path) -> None:
    input_csv = tmp_path / "analysis_ready.csv"
    classified_csv = tmp_path / "classified.csv"
    model_path = tmp_path / "model.joblib"
    pd.DataFrame(
        {
            "source_record_id": ["topsis"],
            "doi": ["10.1000/topsis"],
            "title": ["Supplier selection using intuitionistic fuzzy TOPSIS"],
            "abstract": ["A multi-criteria decision making approach is evaluated."],
            "keywords": ["MCDM; TOPSIS"],
        }
    ).to_csv(input_csv, index=False)
    joblib.dump(FixedProbabilityModel(), model_path)

    classify_ai_relevance_dataset(
        input_csv,
        classified_csv,
        model_path=model_path,
        text_columns=("title", "abstract", "keywords"),
        ai_threshold=0.85,
        calibrator_path="disabled",
    )

    classified = pd.read_csv(classified_csv)
    assert classified["ai_classification_label"].tolist() == ["review"]
    assert classified.loc[0, "ai_classification_reason"].startswith(
        "hard_negative_constraint:decision_optimization_without_clear_ai"
    )


def test_secondary_model_disagreement_forces_review(tmp_path: Path) -> None:
    input_csv = tmp_path / "analysis_ready.csv"
    classified_csv = tmp_path / "classified.csv"
    model_path = tmp_path / "model.joblib"
    secondary_path = tmp_path / "secondary.joblib"
    pd.DataFrame(
        {
            "source_record_id": ["disagree"],
            "doi": ["10.1000/disagree"],
            "title": ["AI research"],
        }
    ).to_csv(input_csv, index=False)
    joblib.dump(FixedProbabilityModel(), model_path)
    joblib.dump(FixedSecondaryModel([0.35]), secondary_path)

    classify_ai_relevance_dataset(
        input_csv,
        classified_csv,
        model_path=model_path,
        secondary_model_path=secondary_path,
        text_columns=("title",),
        ai_threshold=0.85,
        calibrator_path="disabled",
    )

    classified = pd.read_csv(classified_csv)
    assert classified["ai_classification_label"].tolist() == ["review"]
    assert classified.loc[0, "ai_classification_reason"] == "model_disagreement:AI_vs_non-AI"
    assert classified.loc[0, "ai_classification_secondary_label"] == "non-AI"
    assert classified.loc[0, "ai_classification_secondary_confidence"] == 0.35


def test_secondary_model_agreement_keeps_auto_ai(tmp_path: Path) -> None:
    input_csv = tmp_path / "analysis_ready.csv"
    classified_csv = tmp_path / "classified.csv"
    model_path = tmp_path / "model.joblib"
    secondary_path = tmp_path / "secondary.joblib"
    pd.DataFrame({"source_record_id": ["agree"], "title": ["AI research"]}).to_csv(
        input_csv,
        index=False,
    )
    joblib.dump(FixedProbabilityModel(), model_path)
    joblib.dump(FixedSecondaryModel([0.89]), secondary_path)

    classify_ai_relevance_dataset(
        input_csv,
        classified_csv,
        model_path=model_path,
        secondary_model_path=secondary_path,
        text_columns=("title",),
        ai_threshold=0.85,
        calibrator_path="disabled",
    )

    classified = pd.read_csv(classified_csv)
    assert classified["ai_classification_label"].tolist() == ["AI"]
    assert classified.loc[0, "ai_classification_secondary_label"] == "AI"
