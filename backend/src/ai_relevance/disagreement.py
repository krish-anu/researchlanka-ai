"""Lightweight primary/secondary AI relevance model disagreement checks."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ModelVote:
    label: str
    ai_probability: float | None


@dataclass(frozen=True)
class DisagreementResult:
    requires_review: bool
    reason: str | None
    secondary_vote: ModelVote | None
    probability_gap: float | None


def normalized_label(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("_", "-").replace(" ", "-")
    if text in {"ai", "artificial-intelligence"}:
        return "AI"
    if text in {"non-ai", "nonai", "not-ai"}:
        return "non-AI"
    if text in {"review", "manual-review", "uncertain"}:
        return "review"
    return "review"


def label_from_probability(
    score: float,
    *,
    ai_threshold: float,
    non_ai_threshold: float,
) -> str:
    if score >= ai_threshold:
        return "AI"
    if score <= non_ai_threshold:
        return "non-AI"
    return "review"


def ai_class_index(model: Any) -> int | None:
    for index, label in enumerate(getattr(model, "classes_", ())):
        normalized = str(label).strip().casefold().replace("_", "-").replace(" ", "-")
        if normalized in {"ai", "artificial-intelligence"}:
            return index
    return None


def ai_probability_scores(model: Any, text: pd.Series) -> list[float | None]:
    if text.empty:
        return []
    ai_index = ai_class_index(model)
    if hasattr(model, "predict_proba") and ai_index is not None:
        return [float(row[ai_index]) for row in model.predict_proba(text)]
    if hasattr(model, "decision_function") and ai_index is not None:
        classes = list(getattr(model, "classes_", ()))
        if len(classes) != 2:
            return [None for _ in range(len(text))]
        margins = model.decision_function(text)
        scores_for_second_class = [
            1.0 / (1.0 + math.exp(-float(margin))) for margin in margins
        ]
        if ai_index == 1:
            return scores_for_second_class
        return [1.0 - score for score in scores_for_second_class]
    return [None for _ in range(len(text))]


def model_votes(
    model: Any,
    text: pd.Series,
    *,
    ai_threshold: float,
    non_ai_threshold: float,
) -> list[ModelVote]:
    probabilities = ai_probability_scores(model, text)
    predicted = list(model.predict(text)) if hasattr(model, "predict") else [None] * len(text)
    votes: list[ModelVote] = []
    for prediction, probability in zip(predicted, probabilities, strict=True):
        if probability is None:
            votes.append(ModelVote(label=normalized_label(prediction), ai_probability=None))
        else:
            votes.append(
                ModelVote(
                    label=label_from_probability(
                        probability,
                        ai_threshold=ai_threshold,
                        non_ai_threshold=non_ai_threshold,
                    ),
                    ai_probability=float(probability),
                )
            )
    return votes


def disagreement_result(
    *,
    primary_label: str,
    primary_probability: float | None,
    secondary_vote: ModelVote | None,
    probability_gap_threshold: float = 0.35,
) -> DisagreementResult:
    if secondary_vote is None:
        return DisagreementResult(False, None, None, None)
    gap = (
        abs(float(primary_probability) - float(secondary_vote.ai_probability))
        if primary_probability is not None and secondary_vote.ai_probability is not None
        else None
    )
    primary = normalized_label(primary_label)
    secondary = normalized_label(secondary_vote.label)
    if {primary, secondary} == {"AI", "non-AI"}:
        return DisagreementResult(
            True,
            f"model_disagreement:{primary}_vs_{secondary}",
            secondary_vote,
            gap,
        )
    if gap is not None and gap >= probability_gap_threshold:
        return DisagreementResult(
            True,
            f"model_probability_gap:{gap:.3f}",
            secondary_vote,
            gap,
        )
    return DisagreementResult(False, None, secondary_vote, gap)
