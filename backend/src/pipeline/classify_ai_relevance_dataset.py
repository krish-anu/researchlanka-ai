"""Classify the analysis-ready corpus and retain AI/review publications."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd

from src.ai_relevance.borderline import borderline_false_positive_assessment
from src.ai_relevance.calibration import calibrate_scores, configured_calibrator_path
from src.ai_relevance.disagreement import disagreement_result, model_votes
from src.ai_relevance.explainability import add_explanation_columns
from src.ai_relevance.llm_reviewer import (
    LLM_REVIEWER_COLUMNS,
    LLMReviewerConfig,
    add_llm_reviewer_candidate_columns,
)
from src.modeling.training import combined_text
from src.pipeline.refresh_policy import (
    DEFAULT_AUTO_AI_THRESHOLD,
    DEFAULT_AUTO_NON_AI_THRESHOLD,
    DEFAULT_AI_RELEVANCE_MODEL_PATH,
    DEFAULT_TEXT_COLUMNS,
    configured_auto_ai_threshold,
    configured_auto_non_ai_threshold,
    configured_secondary_model_path,
    configured_model_path,
    configured_text_columns,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = DEFAULT_AI_RELEVANCE_MODEL_PATH
DEFAULT_AI_THRESHOLD = DEFAULT_AUTO_AI_THRESHOLD
DEFAULT_REVIEW_THRESHOLD = DEFAULT_AUTO_NON_AI_THRESHOLD
AI_CLASSIFICATION_COLUMNS = (
    "ai_classification_label",
    "ai_classification_confidence",
    "ai_classification_model",
    "ai_classification_reason",
    "ai_classification_primary_confidence",
    "ai_classification_secondary_model",
    "ai_classification_secondary_label",
    "ai_classification_secondary_confidence",
    "ai_classification_disagreement_gap",
    *LLM_REVIEWER_COLUMNS,
)


@dataclass(frozen=True)
class AIClassificationResult:
    input_rows: int
    ai_rows: int
    review_rows: int
    non_ai_rows: int


@dataclass(frozen=True)
class AIFilterResult:
    input_rows: int
    ai_rows: int
    review_rows: int
    filtered_rows: int


def configured_ai_model_path(value: str | Path | None = None) -> Path:
    path = configured_model_path(value)
    if path is None:
        raise ValueError("AI relevance model is disabled for dataset classification.")
    return path


def validate_thresholds(*, ai_threshold: float, review_threshold: float) -> None:
    if not 0.0 <= review_threshold < ai_threshold <= 1.0:
        raise ValueError(
            "AI relevance thresholds must satisfy "
            "0 <= review_threshold < ai_threshold <= 1."
        )


def _normalized_class(value: Any) -> str:
    return str(value).strip().casefold().replace("_", "-").replace(" ", "-")


def _ai_class_index(model: Any) -> int:
    classes = list(getattr(model, "classes_", ()))
    for index, label in enumerate(classes):
        if _normalized_class(label) in {"ai", "artificial-intelligence"}:
            return index
    raise ValueError("AI relevance model does not expose an AI class in classes_.")


def ai_probability_scores(model: Any, text: pd.Series) -> list[float]:
    """Return P(AI) for each row using probabilities or a binary decision margin."""
    if text.empty:
        return []

    ai_index = _ai_class_index(model)
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(text)
        return [float(row[ai_index]) for row in probabilities]

    if hasattr(model, "decision_function"):
        classes = list(model.classes_)
        if len(classes) != 2:
            raise ValueError("Decision-margin AI scoring requires a binary model.")
        margins = model.decision_function(text)
        scores_for_second_class = [
            1.0 / (1.0 + math.exp(-float(margin))) for margin in margins
        ]
        if ai_index == 1:
            return scores_for_second_class
        return [1.0 - score for score in scores_for_second_class]

    raise ValueError(
        "AI relevance model must provide predict_proba or decision_function "
        "to apply confidence thresholds."
    )


def label_from_ai_score(
    score: float,
    *,
    ai_threshold: float = DEFAULT_AI_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> str:
    validate_thresholds(
        ai_threshold=ai_threshold,
        review_threshold=review_threshold,
    )
    if score >= ai_threshold:
        return "AI"
    if score >= review_threshold:
        return "review"
    return "non-AI"


def classify_ai_relevance_dataframe(
    frame: pd.DataFrame,
    *,
    model: Any,
    model_name: str,
    text_columns: Iterable[str] = DEFAULT_TEXT_COLUMNS,
    ai_threshold: float = DEFAULT_AI_THRESHOLD,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
    calibrator_path: Path | None = None,
    secondary_model: Any | None = None,
    secondary_model_name: str | None = None,
    disagreement_gap_threshold: float = 0.35,
    llm_review_max_fraction: float = 0.20,
    llm_review_max_records: int | None = None,
) -> pd.DataFrame:
    validate_thresholds(
        ai_threshold=ai_threshold,
        review_threshold=review_threshold,
    )
    cleaned = frame.copy()
    selected_text_columns = tuple(
        column for column in text_columns if column in cleaned.columns
    )
    if not selected_text_columns:
        raise ValueError("Analysis-ready dataset has no configured model text columns.")

    text = combined_text(cleaned.fillna(""), selected_text_columns)
    raw_scores = ai_probability_scores(model, text)
    selected_calibrator_path = configured_calibrator_path(calibrator_path)
    scores = calibrate_scores(raw_scores, calibrator_path=selected_calibrator_path)
    secondary_votes = (
        model_votes(
            secondary_model,
            text,
            ai_threshold=ai_threshold,
            non_ai_threshold=review_threshold,
        )
        if secondary_model is not None
        else [None for _score in scores]
    )
    labels = [
        label_from_ai_score(
            score,
            ai_threshold=ai_threshold,
            review_threshold=review_threshold,
        )
        for score in scores
    ]
    reasons = [
        {
            "AI": f"ai_score_gte_{ai_threshold:.2f}",
            "review": (
                f"ai_score_gte_{review_threshold:.2f}_and_lt_{ai_threshold:.2f}"
            ),
            "non-AI": f"ai_score_lt_{review_threshold:.2f}",
        }[label]
        for label in labels
    ]
    for index, record in enumerate(cleaned.to_dict("records")):
        disagreement = disagreement_result(
            primary_label=labels[index],
            primary_probability=scores[index],
            secondary_vote=secondary_votes[index],
            probability_gap_threshold=disagreement_gap_threshold,
        )
        if disagreement.requires_review:
            labels[index] = "review"
            reasons[index] = disagreement.reason or "model_disagreement"
            continue
        assessment = borderline_false_positive_assessment(record)
        if labels[index] == "AI" and assessment.requires_review:
            labels[index] = "review"
            reasons[index] = (
                "borderline_false_positive_risk:"
                f"{assessment.risk_category}:weak_ai_evidence"
            )
    cleaned["ai_classification_label"] = labels
    cleaned["ai_classification_confidence"] = [f"{score:.6f}" for score in scores]
    cleaned["ai_classification_primary_confidence"] = [
        f"{score:.6f}" for score in scores
    ]
    cleaned["ai_classification_model"] = model_name
    cleaned["ai_classification_reason"] = reasons
    if secondary_model is not None:
        cleaned["ai_classification_secondary_model"] = secondary_model_name or ""
        cleaned["ai_classification_secondary_label"] = [
            vote.label if vote is not None else "" for vote in secondary_votes
        ]
        cleaned["ai_classification_secondary_confidence"] = [
            ""
            if vote is None or vote.ai_probability is None
            else f"{vote.ai_probability:.6f}"
            for vote in secondary_votes
        ]
        cleaned["ai_classification_disagreement_gap"] = [
            ""
            if vote is None or vote.ai_probability is None
            else f"{abs(scores[index] - vote.ai_probability):.6f}"
            for index, vote in enumerate(secondary_votes)
        ]
    if selected_calibrator_path is not None:
        cleaned["ai_classification_raw_confidence"] = [
            f"{score:.6f}" for score in raw_scores
        ]
        cleaned["ai_classification_calibrator"] = str(selected_calibrator_path)
    explained = add_explanation_columns(cleaned)
    return add_llm_reviewer_candidate_columns(
        explained,
        LLMReviewerConfig(
            max_fraction=llm_review_max_fraction,
            max_records=llm_review_max_records,
            auto_ai_threshold=ai_threshold,
            auto_non_ai_threshold=review_threshold,
        ),
    )


def classify_ai_relevance_dataset(
    input_csv: Path,
    classified_output_csv: Path,
    *,
    model_path: Path | None = None,
    text_columns: Iterable[str] | None = None,
    ai_threshold: float | None = None,
    review_threshold: float | None = None,
    calibrator_path: Path | None = None,
    secondary_model_path: Path | None = None,
    disagreement_gap_threshold: float = 0.35,
    llm_review_max_fraction: float = 0.20,
    llm_review_max_records: int | None = None,
) -> AIClassificationResult:
    selected_model_path = configured_ai_model_path(model_path)
    if not selected_model_path.is_file():
        raise FileNotFoundError(
            f"AI relevance model was not found: {selected_model_path}. "
            "Set RESEARCHLANKA_AI_RELEVANCE_MODEL_PATH to the trained model."
        )

    frame = pd.read_csv(input_csv, dtype="object", low_memory=False)
    model = joblib.load(selected_model_path)
    selected_secondary_model_path = configured_secondary_model_path(secondary_model_path)
    secondary_model = None
    if selected_secondary_model_path is not None:
        if not selected_secondary_model_path.is_file():
            raise FileNotFoundError(
                f"Secondary AI relevance model was not found: {selected_secondary_model_path}."
            )
        secondary_model = joblib.load(selected_secondary_model_path)
    selected_ai_threshold = configured_auto_ai_threshold(ai_threshold)
    selected_review_threshold = configured_auto_non_ai_threshold(review_threshold)
    classified = classify_ai_relevance_dataframe(
        frame,
        model=model,
        model_name=str(selected_model_path),
        text_columns=configured_text_columns(tuple(text_columns) if text_columns else None),
        ai_threshold=selected_ai_threshold,
        review_threshold=selected_review_threshold,
        calibrator_path=calibrator_path,
        secondary_model=secondary_model,
        secondary_model_name=(
            str(selected_secondary_model_path)
            if selected_secondary_model_path is not None
            else None
        ),
        disagreement_gap_threshold=disagreement_gap_threshold,
        llm_review_max_fraction=llm_review_max_fraction,
        llm_review_max_records=llm_review_max_records,
    )
    if len(classified) != len(frame):
        raise RuntimeError("Every analysis-ready row must receive an AI classification.")

    classified_output_csv.parent.mkdir(parents=True, exist_ok=True)
    classified.to_csv(classified_output_csv, index=False)

    counts = classified["ai_classification_label"].value_counts()
    return AIClassificationResult(
        input_rows=len(classified),
        ai_rows=int(counts.get("AI", 0)),
        review_rows=int(counts.get("review", 0)),
        non_ai_rows=int(counts.get("non-AI", 0)),
    )


def filter_ai_review_dataset(
    classified_input_csv: Path,
    filtered_output_csv: Path,
) -> AIFilterResult:
    classified = pd.read_csv(classified_input_csv, dtype="object", low_memory=False)
    if "ai_classification_label" not in classified.columns:
        raise ValueError("Classified dataset is missing ai_classification_label.")

    filtered = classified[
        classified["ai_classification_label"].isin(("AI", "review"))
    ].copy()
    filtered_output_csv.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(filtered_output_csv, index=False)
    counts = filtered["ai_classification_label"].value_counts()
    return AIFilterResult(
        input_rows=len(classified),
        ai_rows=int(counts.get("AI", 0)),
        review_rows=int(counts.get("review", 0)),
        filtered_rows=len(filtered),
    )
