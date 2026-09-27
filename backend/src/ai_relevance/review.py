"""Human-review export helpers for Gemini AI relevance labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.ai_relevance.borderline import borderline_false_positive_assessment
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
    active_learning: bool = True


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
    priority_column: str | None = None,
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
            sample = _priority_take(
                primary_group,
                n=primary_take,
                priority_column=priority_column,
                random_seed=random_seed + offset,
            )
            pieces.append(sample)
            used_indexes.update(sample.index)

        remaining = quota - primary_take
        if remaining > 0:
            fallback_group = fallback[
                (fallback["ai_llm_label"].fillna("").astype(str) == label)
                & ~fallback.index.isin(used_indexes)
            ]
            if not fallback_group.empty:
                sample = _priority_take(
                    fallback_group,
                    n=min(remaining, len(fallback_group)),
                    priority_column=priority_column,
                    random_seed=random_seed + offset + 100,
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
                    _priority_take(
                        remaining_frame,
                        n=min(sample_size - len(current), len(remaining_frame)),
                        priority_column=priority_column,
                        random_seed=random_seed + 200,
                    ),
                ],
                ignore_index=False,
            )
    return current.head(sample_size).copy()


def _priority_take(
    frame: pd.DataFrame,
    *,
    n: int,
    priority_column: str | None,
    random_seed: int,
    random_state: int | None = None,
) -> pd.DataFrame:
    if n <= 0:
        return frame.head(0)
    if priority_column and priority_column in frame.columns:
        return (
            frame.assign(_priority_tiebreaker=range(len(frame)))
            .sort_values(
                [priority_column, "_priority_tiebreaker"],
                ascending=[False, True],
                kind="mergesort",
            )
            .drop(columns=["_priority_tiebreaker"])
            .head(n)
            .copy()
        )
    return frame.sample(n=min(n, len(frame)), random_state=random_state or random_seed)


def _contains_any(text: pd.Series, terms: Iterable[str]) -> pd.Series:
    output = pd.Series(False, index=text.index)
    for term in terms:
        output = output | text.str.contains(term, case=False, regex=False, na=False)
    return output


def _numeric_probability(frame: pd.DataFrame) -> pd.Series:
    for column in (
        "ai_classification_confidence",
        "classifier_probability",
        "ai_llm_confidence",
    ):
        if column in frame.columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            if values.notna().any():
                return values.clip(0.0, 1.0)
    return pd.Series(pd.NA, index=frame.index, dtype="float64")


def _normalized_label_series(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.Series:
    for column in columns:
        if column in frame.columns:
            return (
                frame[column]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.casefold()
                .str.replace("_", "-", regex=False)
                .str.replace(" ", "-", regex=False)
            )
    return pd.Series("", index=frame.index)


def _combined_review_text(frame: pd.DataFrame) -> pd.Series:
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
        )
        if column in frame.columns
    ]
    if not text_columns:
        return pd.Series("", index=frame.index)
    return (
        frame[text_columns]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def _reviewed_mask(frame: pd.DataFrame) -> pd.Series:
    if "human_label" in frame.columns:
        labels = frame["human_label"].fillna("").astype(str).str.strip()
        return labels.isin({"AI", "NON_AI"})
    if "review_status" in frame.columns:
        statuses = frame["review_status"].fillna("").astype(str).str.strip()
        return statuses.isin({"human_accepted", "human_rejected"})
    return pd.Series(False, index=frame.index)


def _novelty_scores(frame: pd.DataFrame) -> pd.Series:
    text = _combined_review_text(frame)
    reviewed = _reviewed_mask(frame)
    if not reviewed.any():
        return pd.Series(1.0, index=frame.index)
    unreviewed = ~reviewed
    if not unreviewed.any():
        return pd.Series(0.0, index=frame.index)

    try:
        matrix = TfidfVectorizer(min_df=1).fit_transform(text)
    except ValueError:
        return pd.Series(1.0, index=frame.index)

    reviewed_positions = [position for position, value in enumerate(reviewed.tolist()) if value]
    unreviewed_positions = [
        position for position, value in enumerate(unreviewed.tolist()) if value
    ]
    similarities = cosine_similarity(
        matrix[unreviewed_positions],
        matrix[reviewed_positions],
    )
    novelty = pd.Series(0.0, index=frame.index)
    novelty.loc[unreviewed] = 1.0 - similarities.max(axis=1)
    return novelty.clip(0.0, 1.0)


def add_active_learning_priority(frame: pd.DataFrame) -> pd.DataFrame:
    """Score review rows by expected value for model improvement."""

    output = frame.copy()
    probability = _numeric_probability(output)
    uncertainty = (1.0 - (probability - 0.5).abs() * 2.0).clip(0.0, 1.0)
    uncertainty = uncertainty.fillna(1.0)

    model_label = _normalized_label_series(
        output,
        ("ai_classification_label", "classifier_decision", "ai_llm_label"),
    )
    llm_label = _normalized_label_series(output, ("ai_llm_label",))
    disagreement = (
        model_label.ne("")
        & llm_label.ne("")
        & model_label.ne(llm_label)
        & ~model_label.isin({"review", "uncertain"})
        & ~llm_label.isin({"review", "uncertain"})
    ).astype(float)
    disagreement = disagreement.where(model_label.ne("review") & llm_label.ne("review"), 0.5)

    novelty = _novelty_scores(output)
    borderline_scores: list[float] = []
    borderline_categories: list[str] = []
    for record in output.to_dict("records"):
        assessment = borderline_false_positive_assessment(record)
        borderline_categories.append(assessment.risk_category or "")
        if assessment.requires_review:
            borderline_scores.append(1.0)
        elif assessment.risk_category:
            borderline_scores.append(0.5)
        else:
            borderline_scores.append(0.0)

    output["review_priority_uncertainty"] = uncertainty.round(6)
    output["review_priority_disagreement"] = disagreement.round(6)
    output["review_priority_novelty"] = novelty.round(6)
    output["review_priority_borderline"] = pd.Series(
        borderline_scores,
        index=output.index,
    ).round(6)
    output["review_priority_borderline_category"] = borderline_categories
    output["review_priority"] = (
        output["review_priority_uncertainty"]
        + output["review_priority_disagreement"]
        + output["review_priority_novelty"]
        + output["review_priority_borderline"]
    ).round(6)
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
    if config.active_learning:
        full_frame = add_active_learning_priority(full_frame)
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
            priority_column="review_priority" if config.active_learning else None,
        )
    if config.active_learning and "review_priority" in sample.columns:
        sample = sample.sort_values(
            "review_priority",
            ascending=False,
            kind="mergesort",
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
            "review_priority",
            "review_priority_uncertainty",
            "review_priority_disagreement",
            "review_priority_novelty",
            "review_priority_borderline",
            "review_priority_borderline_category",
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
