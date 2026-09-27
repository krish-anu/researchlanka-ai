"""Human-readable explanations for AI relevance classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from src.ai_relevance.borderline import (
    BORDERLINE_PATTERNS,
    CLEAR_AI_PATTERNS,
    borderline_false_positive_assessment,
    matched_patterns,
)
from src.ai_relevance.fields import combined_evidence_text


EXPLANATION_VERSION = "ai-relevance-explainability-v1"
PUBLIC_EVIDENCE_LIMIT = 5

AI_PATTERN_LABELS = {
    r"\bartificial[- ]intelligence\b": "artificial intelligence",
    r"\bmachine[- ]learning\b": "machine learning",
    r"\bdeep[- ]learning\b": "deep learning",
    r"\bneural network": "neural network",
    r"\bconvolutional neural": "convolutional neural network",
    r"\bcnn\b": "convolutional neural network",
    r"\brecurrent neural": "recurrent neural network",
    r"\btransformer\b": "transformer model",
    r"\btransfer learning\b": "transfer learning",
    r"\blarge language model": "large language model",
    r"\bllm\b": "large language model",
    r"\bnatural language processing\b": "natural language processing",
    r"\bcomputer vision\b": "computer vision",
    r"\bimage classification\b": "image classification",
    r"\breinforcement learning\b": "reinforcement learning",
    r"\bsupport vector machine\b": "support vector machine",
    r"\brandom forest\b": "random forest",
    r"\bxgboost\b": "XGBoost",
    r"\bgradient boosting\b": "gradient boosting",
    r"\bclassification model\b": "classification model",
    r"\bclassifier\b": "classifier",
    r"\bclustering\b": "clustering",
}

BORDERLINE_PATTERN_LABELS = {
    r"\biot\b": "IoT",
    r"internet of things": "internet of things",
    r"\bsmart\b": "smart-system terminology",
    r"embedded": "embedded system",
    r"sensor": "sensor system",
    r"wireless": "wireless system",
    r"automation": "automation",
    r"automated": "automated system",
    r"forecast": "forecasting",
    r"predict": "prediction",
    r"prediction": "prediction",
    r"regression": "regression",
    r"time series": "time series",
    r"statistical": "statistical analysis",
    r"econometric": "econometric method",
    r"signal processing": "signal processing",
    r"image processing": "image processing",
    r"filtering": "filtering",
    r"segmentation": "segmentation",
    r"feature extraction": "feature extraction",
    r"wavelet": "wavelet method",
    r"fourier": "Fourier method",
    r"education": "education context",
    r"student": "student assessment context",
    r"learning environment": "learning environment",
    r"assessment": "assessment terminology",
    r"answers": "answer-evaluation terminology",
    r"exam": "exam context",
    r"intelligent": "intelligent-system wording",
    r"algorithm": "algorithmic wording",
    r"computational": "computational method",
    r"decision support": "decision-support terminology",
    r"expert system": "expert-system terminology",
    r"knowledge based": "knowledge-based terminology",
}


@dataclass(frozen=True)
class AIClassificationExplanation:
    classification: str
    confidence: str
    verification: str
    evidence_detected: tuple[str, ...]
    borderline_terms: tuple[str, ...]
    reason: str
    explanation_version: str = EXPLANATION_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "confidence": self.confidence,
            "verification": self.verification,
            "evidence_detected": list(self.evidence_detected),
            "borderline_terms": list(self.borderline_terms),
            "reason": self.reason,
            "explanation_version": self.explanation_version,
        }

    def as_output_fields(self) -> dict[str, str]:
        return {
            "ai_explanation_evidence": "; ".join(self.evidence_detected),
            "ai_explanation_borderline_terms": "; ".join(self.borderline_terms),
            "ai_explanation_reason": self.reason,
            "ai_explanation_confidence": self.confidence,
            "ai_explanation_verification": self.verification,
            "ai_explanation_version": self.explanation_version,
        }


def build_ai_explanation(row: Mapping[str, Any]) -> AIClassificationExplanation:
    label = normalized_label(
        row.get("ai_classification_label")
        or row.get("classifier_decision")
        or row.get("final_ai_decision")
    )
    score = numeric(
        row.get("ai_classification_confidence")
        or row.get("classifier_probability")
    )
    reason = str(row.get("ai_classification_reason") or "")
    assessment = borderline_false_positive_assessment(row)
    text = combined_evidence_text(row)
    evidence = readable_matches(matched_patterns(text, CLEAR_AI_PATTERNS), AI_PATTERN_LABELS)
    if not evidence:
        evidence = parsed_terms(row.get("ai_llm_reviewer_evidence"))
    borderline_terms = readable_matches(
        tuple(pattern for patterns in BORDERLINE_PATTERNS.values() for pattern in patterns),
        BORDERLINE_PATTERN_LABELS,
        text=text,
    )
    classification = display_classification(label)
    confidence = confidence_band(score, label=label)
    verification = verification_status(row)
    explanation_reason = public_reason(
        label=label,
        reason=reason,
        has_evidence=bool(evidence),
        assessment_requires_review=assessment.requires_review,
        borderline_terms=borderline_terms,
    )
    return AIClassificationExplanation(
        classification=classification,
        confidence=confidence,
        verification=verification,
        evidence_detected=evidence[:PUBLIC_EVIDENCE_LIMIT],
        borderline_terms=borderline_terms[:PUBLIC_EVIDENCE_LIMIT],
        reason=explanation_reason,
    )


def add_explanation_columns(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    rows = [build_ai_explanation(record).as_output_fields() for record in output.to_dict("records")]
    if not rows:
        return output
    explanation_frame = pd.DataFrame(rows, index=output.index)
    for column in explanation_frame.columns:
        output[column] = explanation_frame[column]
    return output


def explanation_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if has_flat_explanation(row):
        return {
            "classification": display_classification(
                normalized_label(
                    row.get("ai_classification_label")
                    or row.get("classifier_decision")
                    or row.get("final_ai_decision")
                )
            ),
            "confidence": text_or_default(row.get("ai_explanation_confidence"), "Unknown"),
            "verification": text_or_default(row.get("ai_explanation_verification"), "Not verified"),
            "evidence_detected": split_terms(row.get("ai_explanation_evidence")),
            "borderline_terms": split_terms(row.get("ai_explanation_borderline_terms")),
            "reason": text_or_default(row.get("ai_explanation_reason"), ""),
            "explanation_version": text_or_default(
                row.get("ai_explanation_version"),
                EXPLANATION_VERSION,
            ),
        }
    return build_ai_explanation(row).as_dict()


def normalized_label(value: Any) -> str:
    if is_missing(value):
        return ""
    return str(value).strip().casefold().replace("_", "-")


def display_classification(label: str) -> str:
    if label == "ai":
        return "AI"
    if label in {"non-ai", "non ai"}:
        return "NON_AI"
    if label == "review":
        return "Manual review required"
    return "Unknown"


def numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def confidence_band(score: float | None, *, label: str) -> str:
    if score is None:
        return "Unknown"
    if label == "review" or 0.40 <= score < 0.85:
        return "Needs review"
    if score >= 0.85 or score <= 0.15:
        return "High"
    if score >= 0.70 or score <= 0.30:
        return "Medium"
    return "Low"


def verification_status(row: Mapping[str, Any]) -> str:
    status = normalized_label(row.get("review_status"))
    if status in {"human-accepted", "human-rejected"}:
        return "Human verified"
    if status in {"auto-accepted", "auto-rejected"}:
        return "Automatically classified"
    if status in {"needs-manual-review", "pending", "review"}:
        return "Pending human review"
    if row.get("ai_llm_reviewer_status") == "success":
        return "LLM second opinion available; pending human review"
    return "Not verified"


def public_reason(
    *,
    label: str,
    reason: str,
    has_evidence: bool,
    assessment_requires_review: bool,
    borderline_terms: tuple[str, ...],
) -> str:
    if label == "ai" and has_evidence:
        return "Explicit AI/ML methodology or AI-focused terminology was detected in the publication metadata."
    if label in {"non-ai", "non ai"}:
        return "No explicit AI/ML methodology was detected in the publication metadata."
    if assessment_requires_review and borderline_terms:
        terms = ", ".join(borderline_terms[:3])
        return (
            f"{terms} terminology found, but no explicit AI/ML methodology was detected."
        )
    if label == "review":
        return "The calibrated model score or model checks were inconclusive, so this record requires manual review."
    return reason or "AI relevance explanation is unavailable for this record."


def readable_matches(
    patterns: tuple[str, ...],
    labels: Mapping[str, str],
    *,
    text: str | None = None,
) -> tuple[str, ...]:
    matched = patterns if text is None else matched_patterns(text, patterns)
    output = []
    seen = set()
    for pattern in matched:
        label = labels.get(pattern, pattern)
        key = label.casefold()
        if key not in seen:
            output.append(label)
            seen.add(key)
    return tuple(output)


def parsed_terms(value: Any) -> tuple[str, ...]:
    return tuple(split_terms(value))


def split_terms(value: Any) -> list[str]:
    if is_missing(value):
        return []
    if isinstance(value, (list, tuple)):
        return [str(part).strip() for part in value if str(part).strip()]
    return [part.strip() for part in str(value).replace("|", ";").split(";") if part.strip()]


def text_or_default(value: Any, default: str) -> str:
    if is_missing(value):
        return default
    text = str(value).strip()
    return text if text else default


def has_flat_explanation(row: Mapping[str, Any]) -> bool:
    return any(
        not is_missing(row.get(column)) and str(row.get(column)).strip()
        for column in (
            "ai_explanation_evidence",
            "ai_explanation_reason",
            "ai_explanation_confidence",
            "ai_explanation_verification",
        )
    )


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict)):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
