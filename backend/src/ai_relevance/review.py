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


def _label_quotas(
    frame: pd.DataFrame,
    *,
    sample_size: int,
    label_order: tuple[str, ...] = ("AI", "NON_AI", "REVIEW"),
) -> dict[str, int]:
    """Allocate a near-even sample quota across available LLM labels."""

    if "ai_llm_label" not in frame.columns or sample_size <= 0:
        return {}

    counts = frame["ai_llm_label"].fillna("").astype(str).value_counts().to_dict()
    labels = [label for label in label_order if counts.get(label, 0) > 0]
    labels.extend(sorted(label for label, count in counts.items() if count > 0 and label not in labels))
    if not labels:
        return {}

    quotas = {label: 0 for label in labels}
    remaining = min(sample_size, sum(int(counts[label]) for label in labels))
    active = labels.copy()
    while remaining > 0 and active:
        share = max(remaining // len(active), 1)
        next_active: list[str] = []
        for label in active:
            capacity = int(counts[label]) - quotas[label]
            take = min(share, capacity, remaining)
            quotas[label] += take
            remaining -= take
            if quotas[label] < int(counts[label]):
                next_active.append(label)
            if remaining == 0:
                break
        active = next_active
    return quotas


def _balanced_label_sample(
    frame: pd.DataFrame,
    *,
    sample_size: int,
    random_seed: int,
    fallback_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Sample rows with balanced LLM labels, preferring rows from ``frame``."""

    quotas = _label_quotas(fallback_frame if fallback_frame is not None else frame, sample_size=sample_size)
    if not quotas:
        return frame.sample(n=min(sample_size, len(frame)), random_state=random_seed)

    pieces: list[pd.DataFrame] = []
    used_indexes: set[object] = set()
    fallback = fallback_frame if fallback_frame is not None else frame
    for offset, (label, quota) in enumerate(quotas.items()):
        if quota <= 0:
            continue
        primary_group = frame[frame["ai_llm_label"].fillna("").astype(str) == label]
        primary_take = min(quota, len(primary_group))
        if primary_take:
            sample = primary_group.sample(n=primary_take, random_state=random_seed + offset)
            pieces.append(sample)
            used_indexes.update(sample.index)

        remaining = quota - primary_take
        if remaining > 0:
            fallback_group = fallback[
                (fallback["ai_llm_label"].fillna("").astype(str) == label)
                & ~fallback.index.isin(used_indexes)
            ]
            if not fallback_group.empty:
                sample = fallback_group.sample(
                    n=min(remaining, len(fallback_group)),
                    random_state=random_seed + offset + 100,
                )
                pieces.append(sample)
                used_indexes.update(sample.index)

    current = pd.concat(pieces, ignore_index=False).drop_duplicates() if pieces else frame.head(0)
    if len(current) < sample_size:
        remaining_frame = fallback.drop(index=current.index, errors="ignore")
        if not remaining_frame.empty:
            current = pd.concat(
                [
                    current,
                    remaining_frame.sample(
                        n=min(sample_size - len(current), len(remaining_frame)),
                        random_state=random_seed + 200,
                    ),
                ],
                ignore_index=False,
            )
    return current.head(sample_size).copy()


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

    full_frame = add_review_flags(
        load_dataset(config.input_path),
        confidence_threshold=config.confidence_threshold,
    )
    frame = full_frame
    review_queue = full_frame[full_frame["needs_human_review"]].copy()
    if not review_queue.empty:
        frame = review_queue

    if len(frame) <= config.sample_size:
        sample = frame.copy()
    else:
        sample = _balanced_label_sample(
            frame,
            sample_size=config.sample_size,
            random_seed=config.random_seed,
            fallback_frame=full_frame,
        )

    columns = [
        column
        for column in (
            "publication_id",
            "ai_llm_label",
            "human_label",
            "human_notes",
            *PRESERVED_METADATA_COLUMNS,
            "sampling_bucket",
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
    if "human_label" not in sample.columns:
        sample["human_label"] = ""
    if "human_notes" not in sample.columns:
        sample["human_notes"] = ""
    review_columns = ["publication_id", "ai_llm_label", "human_label", "human_notes"]
    sample = sample[review_columns + [column for column in sample.columns if column not in review_columns]]
    save_dataset(sample, config.output_path)
    return sample
