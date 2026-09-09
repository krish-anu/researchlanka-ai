"""Evaluate LLM AI-relevance labels against human verification labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


AI_LABEL = "AI"
NON_AI_LABEL = "NON_AI"
REVIEW_LABEL = "REVIEW"


@dataclass(frozen=True)
class BinaryMetrics:
    total_rows: int
    verified_rows: int
    blank_human_label_rows: int
    model_review_rows: int
    model_review_rows_with_human_label: int
    evaluated_rows: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    accuracy: float
    precision: float
    recall: float
    f1_score: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "total_rows": self.total_rows,
            "verified_rows": self.verified_rows,
            "blank_human_label_rows": self.blank_human_label_rows,
            "model_review_rows": self.model_review_rows,
            "model_review_rows_with_human_label": self.model_review_rows_with_human_label,
            "evaluated_rows": self.evaluated_rows,
            "true_positive": self.true_positive,
            "true_negative": self.true_negative,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
        }


def normalize_human_label(value: object) -> bool | None:
    """Map human labels to True for AI, False for non-AI, and None for blank."""

    if pd.isna(value):
        return None

    text = str(value).strip().casefold()
    if not text:
        return None
    if text in {"true", "1", "yes", "y", "ai"}:
        return True
    if text in {"false", "0", "no", "n", "non_ai", "non-ai", "non ai"}:
        return False

    raise ValueError(f"Unsupported human_label value: {value!r}")


def normalize_model_label(value: object) -> bool | None:
    """Map model labels to True for AI, False for non-AI, and None for REVIEW."""

    text = "" if pd.isna(value) else str(value).strip().upper()
    if text == AI_LABEL:
        return True
    if text == NON_AI_LABEL:
        return False
    if text == REVIEW_LABEL or not text:
        return None

    raise ValueError(f"Unsupported ai_llm_label value: {value!r}")


def calculate_human_verification_metrics(frame: pd.DataFrame) -> BinaryMetrics:
    """Calculate binary AI-vs-non-AI metrics from a human verification frame."""

    required = {"ai_llm_label", "human_label"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    human_ai = frame["human_label"].map(normalize_human_label)
    model_ai = frame["ai_llm_label"].map(normalize_model_label)
    model_label = frame["ai_llm_label"].fillna("").astype(str).str.strip().str.upper()

    evaluated_mask = human_ai.notna() & model_ai.notna()
    y_true = human_ai[evaluated_mask]
    y_pred = model_ai[evaluated_mask]

    true_positive = int(((y_pred == True) & (y_true == True)).sum())
    true_negative = int(((y_pred == False) & (y_true == False)).sum())
    false_positive = int(((y_pred == True) & (y_true == False)).sum())
    false_negative = int(((y_pred == False) & (y_true == True)).sum())
    evaluated_rows = int(evaluated_mask.sum())

    accuracy = _safe_divide(true_positive + true_negative, evaluated_rows)
    precision = _safe_divide(true_positive, true_positive + false_positive)
    recall = _safe_divide(true_positive, true_positive + false_negative)
    f1_score = _safe_divide(2 * precision * recall, precision + recall)

    return BinaryMetrics(
        total_rows=len(frame),
        verified_rows=int(human_ai.notna().sum()),
        blank_human_label_rows=int(human_ai.isna().sum()),
        model_review_rows=int(model_label.eq(REVIEW_LABEL).sum()),
        model_review_rows_with_human_label=int((human_ai.notna() & model_label.eq(REVIEW_LABEL)).sum()),
        evaluated_rows=evaluated_rows,
        true_positive=true_positive,
        true_negative=true_negative,
        false_positive=false_positive,
        false_negative=false_negative,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
    )


def load_and_calculate_human_verification_metrics(path: str | Path) -> BinaryMetrics:
    return calculate_human_verification_metrics(pd.read_csv(path))


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0

