"""Borderline AI false-positive detector used after probability scoring."""

from __future__ import annotations

import re
from typing import Any, Mapping


TEXT_FIELDS = (
    "title",
    "abstract",
    "keywords",
    "topics",
    "concepts",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
)

CLEAR_AI_PATTERNS = (
    r"\bartificial intelligence\b",
    r"\bmachine learning\b",
    r"\bdeep learning\b",
    r"\bneural network",
    r"\bconvolutional neural",
    r"\brecurrent neural",
    r"\btransformer\b",
    r"\blarge language model",
    r"\bllm\b",
    r"\bnatural language processing\b",
    r"\bcomputer vision\b",
    r"\breinforcement learning\b",
    r"\bsupport vector machine\b",
    r"\brandom forest\b",
    r"\bxgboost\b",
    r"\bgradient boosting\b",
    r"\bclassification model\b",
    r"\bclassifier\b",
    r"\bclustering\b",
)

BORDERLINE_PATTERNS: dict[str, tuple[str, ...]] = {
    "iot_or_smart_system_without_clear_ai": (
        r"\biot\b",
        r"internet of things",
        r"\bsmart\b",
        r"embedded",
        r"sensor",
        r"wireless",
        r"automation",
        r"automated",
    ),
    "statistical_prediction_or_forecasting": (
        r"forecast",
        r"predict",
        r"prediction",
        r"regression",
        r"time series",
        r"statistical",
        r"econometric",
    ),
    "signal_or_image_processing_without_clear_ai": (
        r"signal processing",
        r"image processing",
        r"filtering",
        r"segmentation",
        r"feature extraction",
        r"wavelet",
        r"fourier",
    ),
    "education_or_assessment_automation": (
        r"education",
        r"student",
        r"learning environment",
        r"assessment",
        r"answers",
        r"exam",
    ),
    "generic_intelligent_or_algorithmic_wording": (
        r"intelligent",
        r"algorithm",
        r"computational",
        r"decision support",
        r"expert system",
        r"knowledge based",
    ),
}


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def combined_text(row: Mapping[str, Any]) -> str:
    return " ".join(clean(row.get(field)) for field in TEXT_FIELDS).strip()


def has_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(re.search(pattern, lowered) for pattern in patterns)


def borderline_false_positive_category(row: Mapping[str, Any]) -> str | None:
    text = combined_text(row)
    if not text or has_pattern(text, CLEAR_AI_PATTERNS):
        return None
    for category, patterns in BORDERLINE_PATTERNS.items():
        if has_pattern(text, patterns):
            return category
    return None
