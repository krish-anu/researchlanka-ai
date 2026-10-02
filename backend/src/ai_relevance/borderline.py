"""Borderline AI false-positive detector used after probability scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass
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

CORE_EVIDENCE_FIELDS = (
    "title",
    "abstract",
    "keywords",
)

CLEAR_AI_PATTERNS = (
    r"\bartificial[- ]intelligence\b",
    r"\bmachine[- ]learning\b",
    r"\bdeep[- ]learning\b",
    r"\bneural network",
    r"\bconvolutional neural",
    r"\bcnn\b",
    r"\brecurrent neural",
    r"\btransformer\b",
    r"\btransfer learning\b",
    r"\blarge language model",
    r"\bllm\b",
    r"\bnatural language processing\b",
    r"\bcomputer vision\b",
    r"\bimage classification\b",
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
    "manual_pattern_cases": (
        r"manual",
        r"hand[- ]crafted",
        r"hand crafted",
        r"rule[- ]based",
        r"pattern",
        r"template",
        r"heuristic",
    ),
    "decision_optimization_without_clear_ai": (
        r"fuzzy topsis",
        r"intuitionistic fuzzy",
        r"\btopsis\b",
        r"\bahp\b",
        r"\bmcdm\b",
        r"multi-criteria decision",
        r"multi criteria decision",
        r"mathematical optimi[sz]ation",
    ),
}


@dataclass(frozen=True)
class BorderlineAssessment:
    """Explain whether a high AI score should be routed to review."""

    has_strong_ai_evidence: bool
    risk_category: str | None
    evidence_patterns: tuple[str, ...] = ()
    risk_patterns: tuple[str, ...] = ()

    @property
    def requires_review(self) -> bool:
        return self.risk_category is not None and not self.has_strong_ai_evidence


@dataclass(frozen=True)
class HardNegativeConstraintResult:
    """Result of applying false-positive hard-negative constraints."""

    label: str
    reason: str | None
    applied: bool
    category: str | None = None
    evidence: str = ""


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def combined_text(row: Mapping[str, Any]) -> str:
    return " ".join(clean(row.get(field)) for field in TEXT_FIELDS).strip()


def core_evidence_text(row: Mapping[str, Any]) -> str:
    return " ".join(clean(row.get(field)) for field in CORE_EVIDENCE_FIELDS).strip()


def has_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(re.search(pattern, lowered) for pattern in patterns)


def matched_patterns(text: str, patterns: tuple[str, ...]) -> tuple[str, ...]:
    lowered = text.casefold()
    return tuple(pattern for pattern in patterns if re.search(pattern, lowered))


def borderline_false_positive_assessment(row: Mapping[str, Any]) -> BorderlineAssessment:
    text = combined_text(row)
    if not text:
        return BorderlineAssessment(has_strong_ai_evidence=False, risk_category=None)

    # Broad metadata fields such as topics/concepts can contain generic
    # "Artificial intelligence" tags for otherwise non-AI work. For risky
    # borderline categories, require clear AI evidence in core publication text.
    evidence = matched_patterns(core_evidence_text(row), CLEAR_AI_PATTERNS)
    for category, patterns in BORDERLINE_PATTERNS.items():
        risk = matched_patterns(text, patterns)
        if risk:
            return BorderlineAssessment(
                has_strong_ai_evidence=bool(evidence),
                risk_category=category,
                evidence_patterns=evidence,
                risk_patterns=risk,
            )
    return BorderlineAssessment(
        has_strong_ai_evidence=bool(evidence),
        risk_category=None,
        evidence_patterns=evidence,
    )


def borderline_false_positive_category(row: Mapping[str, Any]) -> str | None:
    assessment = borderline_false_positive_assessment(row)
    return assessment.risk_category if assessment.requires_review else None


def normalize_ai_label(value: Any) -> str:
    label = clean(value).casefold().replace("_", "-").replace(" ", "-")
    if label in {"ai", "artificial-intelligence", "artificial intelligence"}:
        return "AI"
    if label in {"non-ai", "nonai", "not-ai", "not ai"}:
        return "NON_AI"
    if label in {"review", "manual-review", "manual review", "uncertain"}:
        return "REVIEW"
    return clean(value)


def hard_negative_constraint_result(
    *,
    label: Any,
    row: Mapping[str, Any],
    review_label: str = "review",
    reason: str | None = None,
) -> HardNegativeConstraintResult:
    """Route known weak-evidence false-positive patterns away from AUTO_AI."""

    normalized = normalize_ai_label(label)
    assessment = borderline_false_positive_assessment(row)
    if normalized == "AI" and assessment.requires_review:
        category = assessment.risk_category or "known_false_positive_pattern"
        evidence = "; ".join(assessment.risk_patterns)
        return HardNegativeConstraintResult(
            label=review_label,
            reason=f"hard_negative_constraint:{category}:weak_ai_evidence",
            applied=True,
            category=category,
            evidence=evidence,
        )
    return HardNegativeConstraintResult(
        label=str(label),
        reason=reason,
        applied=False,
        category=assessment.risk_category if assessment.requires_review else None,
        evidence="; ".join(assessment.risk_patterns),
    )
