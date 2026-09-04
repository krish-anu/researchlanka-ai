"""Deterministic candidate sampling for AI relevance labelling."""

from __future__ import annotations

import re
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.ai_relevance.config import DEFAULT_CANDIDATE_OUTPUT, DEFAULT_PUBLICATIONS_INPUT
from src.ai_relevance.fields import (
    combined_evidence_text,
    present_metadata_columns,
    publication_id,
)
from src.utils.io_utils import load_dataset, save_dataset


AI_TERMS = (
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "neural network",
    "computer vision",
    "natural language processing",
    "reinforcement learning",
    "generative ai",
    "large language model",
    "transformer",
    "cnn",
    "rnn",
    "object detection",
    "image segmentation",
    "machine translation",
    "speech recognition",
    "expert system",
    "genetic algorithm",
    "chatgpt",
)
CROSS_DOMAIN_TERMS = (
    "medicine",
    "health",
    "agriculture",
    "education",
    "engineering",
    "environment",
    "business",
    "finance",
    "transport",
    "energy",
    "social science",
)
CS_HARD_NEGATIVE_TERMS = (
    "networking",
    "database",
    "operating system",
    "software engineering",
    "distributed system",
    "computer architecture",
    "cryptography",
    "protocol",
)
BORDERLINE_TERMS = (
    "prediction",
    "classification",
    "optimization",
    "optimisation",
    "automated",
    "intelligent",
    "recommendation",
    "data mining",
    "feature extraction",
    "decision support",
    "forecasting",
)


@dataclass(frozen=True)
class CandidateSamplingConfig:
    input_path: Path = DEFAULT_PUBLICATIONS_INPUT
    output_path: Path = DEFAULT_CANDIDATE_OUTPUT
    target_size: int = 5000
    random_seed: int = 42


def keyword_regex(terms: Iterable[str]) -> re.Pattern[str]:
    patterns = [re.escape(term).replace(r"\ ", r"\s+") for term in terms]
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(patterns) + r")(?![a-z0-9])", re.I)


AI_RE = keyword_regex(AI_TERMS)
CROSS_DOMAIN_RE = keyword_regex(CROSS_DOMAIN_TERMS)
CS_NEGATIVE_RE = keyword_regex(CS_HARD_NEGATIVE_TERMS)
BORDERLINE_RE = keyword_regex(BORDERLINE_TERMS)


def add_sampling_features(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["publication_id"] = [
        publication_id(record, index) for index, record in output.iterrows()
    ]
    output["_ai_evidence_text"] = [
        combined_evidence_text(record) for _, record in output.iterrows()
    ]
    return output


def _sample_bucket(
    frame: pd.DataFrame,
    mask: pd.Series,
    *,
    target: int,
    bucket: str,
    selected_ids: set[str],
    random_seed: int,
) -> pd.DataFrame:
    eligible = frame[mask & ~frame["publication_id"].isin(selected_ids)].copy()
    if eligible.empty or target <= 0:
        return eligible.head(0)
    sampled = eligible.sample(
        n=min(target, len(eligible)),
        random_state=random_seed,
        replace=False,
    ).copy()
    sampled["sampling_bucket"] = bucket
    selected_ids.update(sampled["publication_id"].astype(str))
    return sampled


def _stratified_random_fill(
    frame: pd.DataFrame,
    *,
    target: int,
    selected_ids: set[str],
    random_seed: int,
) -> pd.DataFrame:
    eligible = frame[~frame["publication_id"].isin(selected_ids)].copy()
    if eligible.empty or target <= 0:
        return eligible.head(0)

    strat_col = "primary_field" if "primary_field" in eligible.columns else "primary_domain"
    if strat_col not in eligible.columns:
        sampled = eligible.sample(n=min(target, len(eligible)), random_state=random_seed)
    else:
        eligible["_stratum"] = eligible[strat_col].fillna("").astype(str)
        groups = eligible.groupby("_stratum", dropna=False)
        per_group = max(1, target // max(len(groups), 1))
        pieces = [
            group.sample(n=min(per_group, len(group)), random_state=random_seed)
            for _, group in groups
        ]
        sampled = pd.concat(pieces, ignore_index=False) if pieces else eligible.head(0)
        if len(sampled) < target:
            remaining = eligible.drop(index=sampled.index, errors="ignore")
            if not remaining.empty:
                sampled = pd.concat(
                    [
                        sampled,
                        remaining.sample(
                            n=min(target - len(sampled), len(remaining)),
                            random_state=random_seed,
                        ),
                    ],
                    ignore_index=False,
                )
        sampled = sampled.drop(columns=["_stratum"], errors="ignore")

    sampled = sampled.head(target).copy()
    sampled["sampling_bucket"] = "field_stratified_random"
    selected_ids.update(sampled["publication_id"].astype(str))
    return sampled


def build_candidate_sample(
    config: CandidateSamplingConfig = CandidateSamplingConfig(),
) -> pd.DataFrame:
    """Build a reproducible, deduplicated candidate set for later Gemini labelling."""

    frame = load_dataset(config.input_path)
    working = add_sampling_features(frame)
    text = working["_ai_evidence_text"]
    primary_field = working.get("primary_field", pd.Series("", index=working.index)).fillna("")
    primary_domain = working.get("primary_domain", pd.Series("", index=working.index)).fillna("")

    selected_ids: set[str] = set()
    pieces: list[pd.DataFrame] = []
    bucket_targets = [
        ("openalex_topic_concept_ai", 1500),
        ("strong_ai_text", 1000),
        ("cross_domain_ai", 500),
        ("computer_science_hard_negative", 500),
        ("borderline_ambiguous", 500),
    ]

    masks = {
        "openalex_topic_concept_ai": (
            working.get("topics", pd.Series("", index=working.index)).fillna("").str.contains(AI_RE)
            | working.get("concepts", pd.Series("", index=working.index)).fillna("").str.contains(AI_RE)
            | working.get("primary_topic", pd.Series("", index=working.index)).fillna("").str.contains(AI_RE)
        ),
        "strong_ai_text": text.str.contains(AI_RE),
        "cross_domain_ai": text.str.contains(AI_RE)
        & (text.str.contains(CROSS_DOMAIN_RE) | primary_field.str.contains(CROSS_DOMAIN_RE)),
        "computer_science_hard_negative": (
            primary_field.str.contains("Computer Science", case=False, na=False)
            | primary_domain.str.contains("Computer Science", case=False, na=False)
            | text.str.contains(CS_NEGATIVE_RE)
        )
        & ~text.str.contains(AI_RE),
        "borderline_ambiguous": text.str.contains(BORDERLINE_RE) & ~text.str.contains(AI_RE),
    }

    for offset, (bucket, target) in enumerate(bucket_targets):
        pieces.append(
            _sample_bucket(
                working,
                masks[bucket],
                target=target,
                bucket=bucket,
                selected_ids=selected_ids,
                random_seed=config.random_seed + offset,
            )
        )

    selected_so_far = sum(len(piece) for piece in pieces)
    pieces.append(
        _stratified_random_fill(
            working,
            target=max(config.target_size - selected_so_far, 0),
            selected_ids=selected_ids,
            random_seed=config.random_seed + 100,
        )
    )

    output = pd.concat(pieces, ignore_index=True) if pieces else working.head(0)
    output = output.drop_duplicates(subset=["publication_id"], keep="first")
    output = output.head(config.target_size).copy()
    output = output.drop(columns=["_ai_evidence_text"], errors="ignore")
    ordered_columns = [
        "publication_id",
        *present_metadata_columns(list(output.columns)),
        "sampling_bucket",
    ]
    remaining = [column for column in output.columns if column not in ordered_columns]
    output = output[[*dict.fromkeys(ordered_columns), *remaining]]
    save_dataset(output, config.output_path)
    return output


def select_first_test_records(
    candidates: pd.DataFrame,
    *,
    limit: int = 10,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Select exactly ``limit`` diverse rows from a candidate frame."""

    if limit <= 0:
        raise ValueError("limit must be positive")
    if len(candidates) < limit:
        raise ValueError(f"Need at least {limit} candidate rows, found {len(candidates)}")

    selected: list[pd.DataFrame] = []
    used_ids: set[str] = set()
    if "sampling_bucket" in candidates.columns:
        for _, group in candidates.groupby("sampling_bucket", sort=True):
            if len(selected) >= limit:
                break
            row = group[~group["publication_id"].isin(used_ids)].sample(
                n=1,
                random_state=random_seed + len(selected),
            )
            selected.append(row)
            used_ids.update(row["publication_id"].astype(str))

    selected_frame = (
        pd.concat(selected, ignore_index=False) if selected else candidates.head(0)
    )
    if len(selected_frame) < limit:
        remaining = candidates[~candidates["publication_id"].isin(used_ids)]
        fill = remaining.sample(
            n=limit - len(selected_frame),
            random_state=random_seed + 999,
            replace=False,
        )
        selected_frame = pd.concat([selected_frame, fill], ignore_index=False)

    selected_frame = selected_frame.drop_duplicates(subset=["publication_id"]).head(limit)
    if len(selected_frame) != limit:
        raise ValueError(f"Selected {len(selected_frame)} records, expected {limit}")
    return selected_frame.copy().reset_index(drop=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build AI relevance candidate sample.")
    parser.add_argument("--input", type=Path, default=DEFAULT_PUBLICATIONS_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_CANDIDATE_OUTPUT)
    parser.add_argument("--target-size", type=int, default=5000)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    frame = build_candidate_sample(
        CandidateSamplingConfig(
            input_path=args.input,
            output_path=args.output,
            target_size=args.target_size,
            random_seed=args.random_seed,
        )
    )
    print(f"Wrote {len(frame)} AI relevance candidates to {args.output}")
    print(frame["sampling_bucket"].value_counts().to_string())
