import sys

from pathlib import Path

from src.pipeline import build_ai_publication_dataset, incremental_update
from src.pipeline.incremental_update import apply_ai_classification, filter_rows_for_database
from src.pipeline.refresh_policy import (
    DEFAULT_CONFIDENCE_REVIEW_THRESHOLD,
    DEFAULT_DB_LABELS,
)


def test_filter_rows_for_database_requires_allowed_label_and_valid_doi() -> None:
    rows = [
        {
            "ai_classification_label": "AI",
            "doi": "https://doi.org/10.1000/ABC",
            "ownership_decision": "INCLUDE",
            "ownership_confidence": "HIGH",
            "needs_manual_review": "false",
        },
        {
            "ai_classification_label": "review",
            "doi": "10.1000/review",
            "ownership_decision": "INCLUDE",
            "ownership_confidence": "MEDIUM",
            "needs_manual_review": "false",
        },
        {"ai_classification_label": "AI", "doi": "", "ownership_decision": "INCLUDE", "ownership_confidence": "HIGH"},
        {"ai_classification_label": "AI", "doi": "not-a-doi", "ownership_decision": "INCLUDE", "ownership_confidence": "HIGH"},
        {"ai_classification_label": "AI", "doi": "10.1000/excluded", "ownership_decision": "EXCLUDE", "ownership_confidence": "HIGH"},
        {"ai_classification_label": "NON_AI", "doi": "10.1000/non-ai", "ownership_decision": "INCLUDE", "ownership_confidence": "HIGH"},
    ]

    selected = filter_rows_for_database(rows, labels=("AI", "review"))

    assert [row["doi"] for row in selected] == ["10.1000/abc", "10.1000/review"]


def test_refresh_entry_points_share_policy_defaults(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["incremental_update"])
    incremental_args = incremental_update.parse_args()

    monkeypatch.setattr(sys, "argv", ["build_ai_publication_dataset"])
    historical_args = build_ai_publication_dataset.parse_args()

    assert incremental_args.db_labels == DEFAULT_DB_LABELS
    assert historical_args.db_labels == DEFAULT_DB_LABELS
    assert incremental_args.confidence_review_threshold == DEFAULT_CONFIDENCE_REVIEW_THRESHOLD
    assert historical_args.confidence_review_threshold == DEFAULT_CONFIDENCE_REVIEW_THRESHOLD


class ProbabilityModel:
    classes_ = ["non-AI", "AI"]

    def predict(self, text):
        return ["AI"] * len(text)

    def predict_proba(self, text):
        scores = [0.86, 0.85, 0.84, 0.40, 0.39]
        return [[1.0 - score, score] for score in scores[: len(text)]]


def test_incremental_classification_uses_ai_probability_tiers(monkeypatch) -> None:
    monkeypatch.setattr(incremental_update.joblib, "load", lambda _path: ProbabilityModel())
    monkeypatch.setattr(incremental_update, "validate_model_path", lambda _path: None)

    rows = [{"title": f"paper {index}"} for index in range(5)]
    classified = apply_ai_classification(
        rows,
        model_path=Path("model.joblib"),
        text_columns=("title",),
        confidence_review_threshold=0.85,
    )

    assert [row["ai_classification_label"] for row in classified] == [
        "AI",
        "AI",
        "review",
        "review",
        "non-AI",
    ]


def test_incremental_borderline_detector_sends_smart_system_to_review(monkeypatch) -> None:
    monkeypatch.setattr(incremental_update.joblib, "load", lambda _path: ProbabilityModel())
    monkeypatch.setattr(incremental_update, "validate_model_path", lambda _path: None)

    classified = apply_ai_classification(
        [{"title": "Smart IoT sensor platform for irrigation"}],
        model_path=Path("model.joblib"),
        text_columns=("title",),
        confidence_review_threshold=0.85,
    )

    assert classified[0]["ai_classification_label"] == "review"
    assert classified[0]["ai_classification_reason"].startswith(
        "borderline_false_positive_risk:"
    )


def test_incremental_classification_thresholds_calibrated_probability(monkeypatch) -> None:
    monkeypatch.setattr(incremental_update.joblib, "load", lambda _path: ProbabilityModel())
    monkeypatch.setattr(incremental_update, "validate_model_path", lambda _path: None)
    monkeypatch.setattr(
        incremental_update,
        "configured_calibrator_path",
        lambda: Path("calibrator.joblib"),
    )
    monkeypatch.setattr(
        incremental_update,
        "calibrate_scores",
        lambda scores, *, calibrator_path: [0.70 for _score in scores],
    )

    classified = apply_ai_classification(
        [{"title": "Machine learning model for crop disease detection"}],
        model_path=Path("model.joblib"),
        text_columns=("title",),
        confidence_review_threshold=0.85,
    )

    assert classified[0]["ai_classification_label"] == "review"
    assert classified[0]["ai_classification_confidence"] == "0.700000"
    assert classified[0]["ai_classification_raw_confidence"] == "0.860000"
    assert classified[0]["ai_classification_calibrator"] == "calibrator.joblib"
