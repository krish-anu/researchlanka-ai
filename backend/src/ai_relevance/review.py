"""Human-review export helpers for Gemini AI relevance labels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def build_human_review_sample(config: HumanReviewConfig) -> pd.DataFrame:
    """Create a reproducible review CSV with empty human label/note columns."""

    frame = load_dataset(config.input_path)
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
        )
        if column in sample.columns
    ]
    sample = sample[columns].copy()
    sample["human_label"] = ""
    sample["human_notes"] = ""
    save_dataset(sample, config.output_path)
    return sample
