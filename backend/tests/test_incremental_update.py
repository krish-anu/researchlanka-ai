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


class SecondaryProbabilityModel:
    classes_ = ["non-AI", "AI"]

    def predict(self, text):
        return ["NON_AI"] * len(text)

    def predict_proba(self, text):
        return [[0.65, 0.35] for _item in text]


def test_incremental_classification_uses_ai_probability_tiers(monkeypatch) -> None:
    monkeypatch.setattr(incremental_update.joblib, "load", lambda _path: ProbabilityModel())
    monkeypatch.setattr(incremental_update, "validate_model_path", lambda _path: None)

    rows = [{"title": f"paper {index}"} for index in range(5)]
    classified = apply_ai_classification(
        rows,
        model_path=Path("model.joblib"),
        text_columns=("title",),
        confidence_review_threshold=0.85,
        auto_ai_threshold=0.85,
        calibrator_path="disabled",
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
        auto_ai_threshold=0.85,
        calibrator_path="disabled",
    )

    assert classified[0]["ai_classification_label"] == "review"
    assert classified[0]["ai_classification_reason"].startswith(
        "borderline_false_positive_risk:"
    )


def test_incremental_clear_ai_evidence_overrides_borderline_terms(monkeypatch) -> None:
    monkeypatch.setattr(incremental_update.joblib, "load", lambda _path: ProbabilityModel())
    monkeypatch.setattr(incremental_update, "validate_model_path", lambda _path: None)

    classified = apply_ai_classification(
        [{"title": "Machine-learning based smart IoT system"}],
        model_path=Path("model.joblib"),
        text_columns=("title",),
        confidence_review_threshold=0.85,
        auto_ai_threshold=0.85,
        calibrator_path="disabled",
    )

    assert classified[0]["ai_classification_label"] == "AI"
    assert classified[0]["ai_classification_reason"] is None


def test_incremental_classification_thresholds_calibrated_probability(monkeypatch) -> None:
    monkeypatch.setattr(incremental_update.joblib, "load", lambda _path: ProbabilityModel())
    monkeypatch.setattr(incremental_update, "validate_model_path", lambda _path: None)
    monkeypatch.setattr(
        incremental_update,
        "configured_calibrator_path",
        lambda _value=None: Path("calibrator.joblib"),
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


def test_incremental_numeric_binary_model_treats_class_one_as_ai(monkeypatch) -> None:
    class NumericProbabilityModel:
        classes_ = [0, 1]

        def predict(self, text):
            return [0, 1][: len(text)]

        def predict_proba(self, text):
            scores = [0.10, 0.91]
            return [[1.0 - score, score] for score in scores[: len(text)]]

    monkeypatch.setattr(incremental_update.joblib, "load", lambda _path: NumericProbabilityModel())
    monkeypatch.setattr(incremental_update, "validate_model_path", lambda _path: None)

    classified = apply_ai_classification(
        [
            {"title": "Bridge maintenance"},
            {"title": "Deep learning for crop detection"},
        ],
        model_path=Path("model.joblib"),
        text_columns=("title",),
        confidence_review_threshold=0.85,
        auto_ai_threshold=0.85,
        calibrator_path="disabled",
    )

    assert [row["ai_classification_label"] for row in classified] == ["non-AI", "AI"]
    assert [row["ai_classification_confidence"] for row in classified] == [
        "0.100000",
        "0.910000",
    ]


def test_incremental_secondary_model_disagreement_forces_review(monkeypatch) -> None:
    def fake_load(path):
        if Path(path).name == "secondary.joblib":
            return SecondaryProbabilityModel()
        return ProbabilityModel()

    monkeypatch.setattr(incremental_update.joblib, "load", fake_load)
    monkeypatch.setattr(incremental_update, "validate_model_path", lambda _path: None)

    classified = apply_ai_classification(
        [{"title": "Deep learning for crop disease detection"}],
        model_path=Path("model.joblib"),
        secondary_model_path=Path("secondary.joblib"),
        text_columns=("title",),
        confidence_review_threshold=0.85,
        auto_ai_threshold=0.85,
        calibrator_path="disabled",
    )

    assert classified[0]["ai_classification_label"] == "review"
    assert classified[0]["ai_classification_reason"] == "model_disagreement:AI_vs_non-AI"
    assert classified[0]["ai_classification_secondary_label"] == "non-AI"
    assert classified[0]["ai_classification_secondary_confidence"] == "0.350000"
    assert classified[0]["ai_classification_disagreement_gap"] == "0.510000"
