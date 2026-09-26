"""Shared production refresh policy for publication ingestion entry points."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

    
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AI_RELEVANCE_MODEL_PATH = (
    PROJECT_ROOT / "data" / "models" / "ai_relevance" / "ai_relevance_linear_svm.joblib"
)
DEFAULT_TEXT_COLUMNS = ("title", "abstract", "keywords", "topics", "concepts")
DEFAULT_CONFIDENCE_REVIEW_THRESHOLD = 0.8
DEFAULT_DB_LABELS = ("AI", "review")


@dataclass(frozen=True)
class PublicationRefreshPolicy:
    """One policy shared by full, incremental, Kaggle, and admin refreshes."""

    model_path: Path | None
    text_columns: tuple[str, ...] = DEFAULT_TEXT_COLUMNS
    confidence_review_threshold: float = DEFAULT_CONFIDENCE_REVIEW_THRESHOLD
    db_labels: tuple[str, ...] = DEFAULT_DB_LABELS


def configured_model_path(value: str | Path | None = None) -> Path | None:
    raw_value = value or os.getenv("RESEARCHLANKA_AI_RELEVANCE_MODEL_PATH")
    raw_value = raw_value or os.getenv("INCREMENTAL_MODEL") or DEFAULT_AI_RELEVANCE_MODEL_PATH
    if str(raw_value).strip().casefold() in {"none", "disabled", "off"}:
        return None
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def configured_confidence_review_threshold(value: float | str | None = None) -> float:
    raw_value = value
    if raw_value is None:
        raw_value = os.getenv("RESEARCHLANKA_CONFIDENCE_REVIEW_THRESHOLD")
    if raw_value in (None, ""):
        return DEFAULT_CONFIDENCE_REVIEW_THRESHOLD
    threshold = float(raw_value)
    if threshold < 0 or threshold > 1:
        raise ValueError("confidence review threshold must be between 0 and 1.")
    return threshold


def default_refresh_policy(
    *,
    model_path: str | Path | None = None,
    confidence_review_threshold: float | str | None = None,
    text_columns: tuple[str, ...] = DEFAULT_TEXT_COLUMNS,
    db_labels: tuple[str, ...] = DEFAULT_DB_LABELS,
) -> PublicationRefreshPolicy:
    return PublicationRefreshPolicy(
        model_path=configured_model_path(model_path),
        text_columns=text_columns,
        confidence_review_threshold=configured_confidence_review_threshold(
            confidence_review_threshold
        ),
        db_labels=db_labels,
    )
