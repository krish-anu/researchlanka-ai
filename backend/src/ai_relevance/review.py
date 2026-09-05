"""Human-review export helpers for Gemini AI relevance labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.ai_relevance.config import DEFAULT_HUMAN_REVIEW_OUTPUT
from src.ai_relevance.fields import PRESERVED_METADATA_COLUMNS
from src.utils.io_utils import load_dataset, save_dataset


@dataclass(frozen=True)
class HumanReviewConfig:
    input_path: Path
    output_path: Path = DEFAULT_HUMAN_REVIEW_OUTPUT
    sample_size: int = 500
    random_seed: int = 42
    confidence_threshold: float = 0.75


HARD_NEGATIVE_TERMS = (
    "fuzzy topsis",
    "intuitionistic fuzzy",
    "topsis",
    " ahp ",
    "mcdm",
    "multi-criteria decision",
    "multi criteria decision",
    "decision-making",
    "decision making",
    "statistical regression",
    "mathematical optimization",
    "mathematical optimisation",
)
AI_METHOD_TERMS = (
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "neural network",
    "computer vision",
    "natural language processing",
    "reinforcement learning",
    "expert system",
    "intelligent agent",
    "trained model",
    "large language model",
    "chatgpt",
)


def _contains_any(text: pd.Series, terms: Iterable[str]) -> pd.Series:
    output = pd.Series(False, index=text.index)
    for term in terms:
        output = output | text.str.contains(term, case=False, regex=False, na=False)
    return output


def add_review_flags(frame: pd.DataFrame, *, confidence_threshold: float = 0.75) -> pd.DataFrame:
    """Add deterministic review flags for unreliable or high-risk LLM decisions."""

    output = frame.copy()
    text_columns = [
        column
        for column in (
            "title",
            "abstract",
            "keywords",
            "topics",
            "concepts",
            "primary_topic",
            "primary_subfield",
            "primary_field",
            "primary_domain",
            "ai_llm_reason",
            "ai_llm_evidence",
        )
        if column in output.columns
    ]
    if text_columns:
        text = output[text_columns].fillna("").astype(str).agg(" ".join, axis=1)
    else:
        text = pd.Series("", index=output.index)

    label = output.get("ai_llm_label", pd.Series("", index=output.index)).fillna("").astype(str)
    status = output.get("ai_llm_status", pd.Series("", index=output.index)).fillna("").astype(str)
    bucket = output.get("sampling_bucket", pd.Series("", index=output.index)).fillna("").astype(str)
    confidence = pd.to_numeric(output.get("ai_llm_confidence", ""), errors="coerce")

    explicit_review = label.eq("REVIEW")
    unsuccessful = status.ne("success")
    low_confidence = confidence.le(confidence_threshold) | confidence.isna()
    ambiguous_bucket = bucket.eq("borderline_ambiguous")
    hard_negative_text = _contains_any(text, HARD_NEGATIVE_TERMS)
    clear_ai_text = _contains_any(text, AI_METHOD_TERMS)
    possible_false_positive = label.eq("AI") & hard_negative_text & ~clear_ai_text

    reasons = []
    for index in output.index:
        row_reasons: list[str] = []
        if bool(explicit_review.loc[index]):
            row_reasons.append("model_label_review")
        if bool(unsuccessful.loc[index]):
            row_reasons.append("not_successful")
        if bool(low_confidence.loc[index]):
            row_reasons.append(f"confidence_below_{confidence_threshold:g}")
        if bool(ambiguous_bucket.loc[index]):
            row_reasons.append("borderline_sampling_bucket")
        if bool(possible_false_positive.loc[index]):
            row_reasons.append("possible_fuzzy_or_decision_method_false_positive")
        reasons.append("; ".join(row_reasons))

    output["needs_human_review"] = [bool(reason) for reason in reasons]
    output["review_reason"] = reasons
    return output


def build_human_review_sample(config: HumanReviewConfig) -> pd.DataFrame:
    """Create a reproducible review CSV with empty human label/note columns."""

    frame = add_review_flags(
        load_dataset(config.input_path),
        confidence_threshold=config.confidence_threshold,
    )
    review_queue = frame[frame["needs_human_review"]].copy()
    if not review_queue.empty:
        frame = review_queue

    if len(frame) <= config.sample_size:
        sample = frame.copy()
    else:
        pieces: list[pd.DataFrame] = []
        if "ai_llm_label" in frame.columns:
            for label in ("AI", "NON_AI", "REVIEW"):
                group = frame[frame["ai_llm_label"] == label]
                if not group.empty:
                    pieces.append(
                        group.sample(
                            n=min(max(config.sample_size // 8, 1), len(group)),
                            random_state=config.random_seed + len(pieces),
                        )
                    )
        if "ai_llm_confidence" in frame.columns:
            confidence = pd.to_numeric(frame["ai_llm_confidence"], errors="coerce")
            low = frame[confidence <= 0.65]
            if not low.empty:
                pieces.append(
                    low.sample(
                        n=min(max(config.sample_size // 5, 1), len(low)),
                        random_state=config.random_seed + 50,
                    )
                )
        current = pd.concat(pieces, ignore_index=False).drop_duplicates() if pieces else frame.head(0)
        remaining = frame.drop(index=current.index, errors="ignore")
        if len(current) < config.sample_size and not remaining.empty:
            current = pd.concat(
                [
                    current,
                    remaining.sample(
                        n=min(config.sample_size - len(current), len(remaining)),
                        random_state=config.random_seed + 100,
                    ),
                ],
                ignore_index=False,
            )
        sample = current.head(config.sample_size).copy()

    columns = [
        column
        for column in (
            "publication_id",
            *PRESERVED_METADATA_COLUMNS,
            "sampling_bucket",
            "ai_llm_label",
            "ai_llm_confidence",
            "ai_llm_category",
            "ai_llm_reason",
            "ai_llm_evidence",
            "ai_llm_status",
            "needs_human_review",
            "review_reason",
        )
        if column in sample.columns
    ]
    sample = sample[columns].copy()
    sample["human_label"] = ""
    sample["human_notes"] = ""
    save_dataset(sample, config.output_path)
    return sample
