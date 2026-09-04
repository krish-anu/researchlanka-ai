"""Structured Gemini response validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


AI_LABELS = ("AI", "NON_AI", "REVIEW")
AI_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": list(AI_LABELS)},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "ai_category": {"type": "string"},
        "reason": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 3,
        },
    },
    "required": ["label", "confidence", "ai_category", "reason", "evidence"],
}


@dataclass(frozen=True)
class AIClassification:
    label: str
    confidence: float
    ai_category: str
    reason: str
    evidence: tuple[str, ...]

    def as_output_fields(self) -> dict[str, str]:
        return {
            "ai_llm_label": self.label,
            "ai_llm_confidence": f"{self.confidence:.6f}",
            "ai_llm_category": self.ai_category,
            "ai_llm_reason": self.reason,
            "ai_llm_evidence": " | ".join(self.evidence),
        }


def validate_ai_response(payload: Mapping[str, Any]) -> AIClassification:
    """Validate Gemini JSON and normalize it for CSV output."""

    missing = [key for key in AI_RESPONSE_SCHEMA["required"] if key not in payload]
    if missing:
        raise ValueError("missing required response field(s): " + ", ".join(missing))

    label = str(payload["label"]).strip()
    if label not in AI_LABELS:
        raise ValueError(f"invalid label: {label!r}")

    try:
        confidence = float(payload["confidence"])
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")

    category = str(payload["ai_category"]).strip()
    if label == "NON_AI" and category != "Not Applicable":
        raise ValueError("NON_AI responses must use ai_category='Not Applicable'")
    if label == "REVIEW" and category != "Unclear":
        raise ValueError("REVIEW responses must use ai_category='Unclear'")
    if not category:
        raise ValueError("ai_category must not be empty")

    reason = " ".join(str(payload["reason"]).split())
    if not reason:
        raise ValueError("reason must not be empty")

    evidence_value = payload["evidence"]
    if not isinstance(evidence_value, list):
        raise ValueError("evidence must be a list")
    if len(evidence_value) > 3:
        raise ValueError("evidence must contain at most 3 items")
    evidence = tuple(" ".join(str(item).split()) for item in evidence_value if str(item).strip())

    return AIClassification(
        label=label,
        confidence=confidence,
        ai_category=category,
        reason=reason,
        evidence=evidence,
    )


def classification_from_fields(row: Mapping[str, Any]) -> AIClassification:
    evidence = str(row.get("ai_llm_evidence", ""))
    return AIClassification(
        label=str(row.get("ai_llm_label", "")),
        confidence=float(row.get("ai_llm_confidence", 0) or 0),
        ai_category=str(row.get("ai_llm_category", "")),
        reason=str(row.get("ai_llm_reason", "")),
        evidence=tuple(part.strip() for part in evidence.split("|") if part.strip()),
    )
