"""LLM second-opinion reviewer for difficult AI relevance cases.

This module deliberately treats an LLM as review support, not as the primary
classifier. It can annotate difficult ML rows with an LLM recommendation and
evidence, but it never overwrites the ML decision column.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import pandas as pd

from src.ai_relevance.config import GeminiConfig
from src.ai_relevance.fields import publication_metadata
from src.ai_relevance.gemini_client import (
    GeminiAIClient,
    GeminiClassificationResult,
    OllamaAIClient,
    OpenRouterAIClient,
)


LLM_REVIEWER_COLUMNS = (
    "ai_llm_reviewer_candidate",
    "ai_llm_reviewer_priority",
    "ai_llm_reviewer_status",
    "ai_llm_reviewer_label",
    "ai_llm_reviewer_confidence",
    "ai_llm_reviewer_category",
    "ai_llm_reviewer_reason",
    "ai_llm_reviewer_evidence",
    "ai_llm_reviewer_model",
    "ai_llm_reviewer_prompt_version",
    "ai_llm_reviewer_processed_at",
    "ai_llm_reviewer_error",
    "ai_llm_reviewer_decision_effect",
    "human_review_reason",
)
HUMAN_CONTEXT_ONLY = "human_review_context_only"


class LLMReviewerClient(Protocol):
    def classify(self, publication: Any) -> GeminiClassificationResult:
        """Return a structured second opinion for one publication."""


@dataclass(frozen=True)
class LLMReviewerConfig:
    max_fraction: float = 0.20
    max_records: int | None = None
    min_priority: float = 0.0
    auto_ai_threshold: float = 0.85
    auto_non_ai_threshold: float = 0.40
    model: str = ""
    prompt_version: str = ""


def normalize_review_label(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().casefold()


def numeric(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def uncertainty_priority(
    score: float,
    *,
    auto_ai_threshold: float,
    auto_non_ai_threshold: float,
) -> float:
    """Return high priority near the middle of the REVIEW band."""

    if auto_ai_threshold <= auto_non_ai_threshold:
        return 0.0
    midpoint = (auto_ai_threshold + auto_non_ai_threshold) / 2.0
    half_width = (auto_ai_threshold - auto_non_ai_threshold) / 2.0
    distance = abs(score - midpoint)
    return max(0.0, 1.0 - (distance / half_width))


def llm_review_priority(row: pd.Series, config: LLMReviewerConfig) -> float:
    """Score how useful an LLM second opinion is likely to be."""

    if normalize_review_label(row.get("ai_classification_label")) != "review":
        return 0.0

    reason = str(row.get("ai_classification_reason") or "")
    score = numeric(row.get("ai_classification_confidence"))
    priority = uncertainty_priority(
        score,
        auto_ai_threshold=config.auto_ai_threshold,
        auto_non_ai_threshold=config.auto_non_ai_threshold,
    )
    if reason.startswith("model_disagreement"):
        priority += 1.0
    if reason.startswith("borderline_false_positive_risk"):
        priority += 0.9
    if "ai_score_gte" in reason:
        priority += 0.5
    return round(priority, 6)


def select_llm_review_indices(
    frame: pd.DataFrame,
    config: LLMReviewerConfig = LLMReviewerConfig(),
) -> list[int]:
    """Select only difficult REVIEW rows for LLM second opinion."""

    if not 0.0 < config.max_fraction <= 1.0:
        raise ValueError("LLM reviewer max_fraction must be between 0 and 1.")

    priorities = frame.apply(lambda row: llm_review_priority(row, config), axis=1)
    candidates = [
        (index, priority)
        for index, priority in priorities.items()
        if priority >= config.min_priority and priority > 0
    ]
    if not candidates:
        return []

    budget = max(1, math.ceil(len(frame) * config.max_fraction))
    if config.max_records is not None:
        budget = min(budget, max(0, config.max_records))
    candidates.sort(key=lambda item: (-item[1], item[0]))
    return [index for index, _priority in candidates[:budget]]


def add_llm_reviewer_candidate_columns(
    frame: pd.DataFrame,
    config: LLMReviewerConfig = LLMReviewerConfig(),
) -> pd.DataFrame:
    """Annotate difficult rows for optional LLM review without calling an LLM."""

    output = frame.copy()
    for column in LLM_REVIEWER_COLUMNS:
        if column not in output.columns:
            output[column] = ""

    priorities = output.apply(lambda row: llm_review_priority(row, config), axis=1)
    selected = set(select_llm_review_indices(output, config))
    output["ai_llm_reviewer_candidate"] = [
        "true" if index in selected else "false" for index in output.index
    ]
    output["ai_llm_reviewer_priority"] = [
        f"{float(priorities.loc[index]):.6f}" if index in selected else ""
        for index in output.index
    ]
    output["ai_llm_reviewer_status"] = [
        "pending" if index in selected else "not_candidate" for index in output.index
    ]
    output["ai_llm_reviewer_decision_effect"] = [
        HUMAN_CONTEXT_ONLY if index in selected else "" for index in output.index
    ]
    human_review_reasons = []
    for index in output.index:
        if index in selected:
            human_review_reasons.append(
                "ML requires review; LLM second opinion may provide evidence, "
                "but human remains final."
            )
        else:
            value = output.at[index, "human_review_reason"]
            human_review_reasons.append("" if pd.isna(value) else str(value))
    output["human_review_reason"] = human_review_reasons
    return output


def build_llm_reviewer_client(config: GeminiConfig) -> LLMReviewerClient:
    if config.provider == "openrouter":
        return OpenRouterAIClient(config)
    if config.provider == "google":
        return GeminiAIClient(config)
    if config.provider == "ollama":
        return OllamaAIClient(config)
    raise ValueError("AI_LLM_PROVIDER must be 'google', 'openrouter', or 'ollama'")


def apply_llm_second_opinions(
    frame: pd.DataFrame,
    *,
    client: LLMReviewerClient,
    config: LLMReviewerConfig = LLMReviewerConfig(),
) -> pd.DataFrame:
    """Call an LLM for selected rows and store advisory fields only."""

    output = add_llm_reviewer_candidate_columns(frame, config)
    candidates = output[output["ai_llm_reviewer_candidate"].eq("true")].index
    for index in candidates:
        metadata = publication_metadata(output.loc[index].to_dict(), fallback=index)
        try:
            result = client.classify(metadata)
            classification = result.classification
            output.at[index, "ai_llm_reviewer_status"] = "success"
            output.at[index, "ai_llm_reviewer_label"] = classification.label
            output.at[index, "ai_llm_reviewer_confidence"] = (
                f"{classification.confidence:.6f}"
            )
            output.at[index, "ai_llm_reviewer_category"] = classification.ai_category
            output.at[index, "ai_llm_reviewer_reason"] = classification.reason
            output.at[index, "ai_llm_reviewer_evidence"] = " | ".join(
                classification.evidence
            )
            output.at[index, "ai_llm_reviewer_model"] = config.model
            output.at[index, "ai_llm_reviewer_prompt_version"] = config.prompt_version
            output.at[index, "ai_llm_reviewer_processed_at"] = (
                datetime.now(UTC).isoformat()
            )
            output.at[index, "ai_llm_reviewer_error"] = ""
        except Exception as exc:  # noqa: BLE001 - row-level failures should not halt review queue
            output.at[index, "ai_llm_reviewer_status"] = "failed"
            output.at[index, "ai_llm_reviewer_error"] = str(exc)
            output.at[index, "ai_llm_reviewer_model"] = config.model
            output.at[index, "ai_llm_reviewer_prompt_version"] = config.prompt_version

    return output
