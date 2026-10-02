#!/usr/bin/env python3
"""Collect AI relevance experiment score CSVs into one comparison file."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_SEARCH_DIR = Path("data/models/ai_relevance")
DEFAULT_OUTPUT = Path("data/models/ai_relevance/all_model_scores.csv")


SCORE_FILES = (
    "validation_selection_leaderboard.csv",
    "model_comparison.csv",
    "sentence_transformer_comparison.csv",
    "transformer_comparison.csv",
)


def clean_metric_name(value: str) -> str:
    return value.replace("human_test_", "frozen_test_")


def normalize_frame(path: Path, frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [clean_metric_name(column) for column in out.columns]
    out.insert(0, "source_file", str(path))
    out.insert(0, "experiment_dir", str(path.parent))

    if "model_family" not in out.columns:
        out["model_family"] = path.parent.name

    for column in (
        "validation_accuracy",
        "validation_macro_f1",
        "validation_ai_precision",
        "validation_ai_recall",
        "validation_non_ai_recall",
        "frozen_test_accuracy",
        "frozen_test_macro_f1",
        "frozen_test_weighted_f1",
        "ai_precision",
        "ai_recall",
        "ai_f1",
        "non_ai_precision",
        "non_ai_recall",
        "non_ai_f1",
        "brier_score",
        "false_positives",
        "threshold",
        "human_weight",
    ):
        if column not in out.columns:
            out[column] = ""

    ordered = [
        "experiment_dir",
        "source_file",
        "model_family",
        "human_weight",
        "threshold",
        "validation_accuracy",
        "validation_macro_f1",
        "validation_ai_precision",
        "validation_ai_recall",
        "validation_non_ai_recall",
        "frozen_test_accuracy",
        "frozen_test_macro_f1",
        "frozen_test_weighted_f1",
        "ai_precision",
        "ai_recall",
        "ai_f1",
        "non_ai_precision",
        "non_ai_recall",
        "non_ai_f1",
        "brier_score",
        "false_positives",
    ]
    remaining = [column for column in out.columns if column not in ordered]
    return out[ordered + remaining]


def score_paths(search_dirs: Iterable[Path]) -> list[Path]:
    paths: list[Path] = []
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for filename in SCORE_FILES:
            paths.extend(sorted(search_dir.rglob(filename)))
    return sorted(dict.fromkeys(paths))


def collect_scores(search_dirs: Iterable[Path], output: Path) -> pd.DataFrame:
    frames = []
    for path in score_paths(search_dirs):
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, low_memory=False)
        if frame.empty:
            continue
        frames.append(normalize_frame(path, frame))

    if frames:
        combined = pd.concat(frames, ignore_index=True, sort=False)
    else:
        combined = pd.DataFrame(
            columns=[
                "experiment_dir",
                "source_file",
                "model_family",
                "validation_macro_f1",
                "frozen_test_macro_f1",
                "ai_precision",
                "ai_recall",
                "non_ai_recall",
            ]
        )

    sort_columns = [
        column
        for column in ("frozen_test_macro_f1", "validation_macro_f1", "ai_precision")
        if column in combined.columns
    ]
    for column in sort_columns:
        combined[f"__sort_{column}"] = pd.to_numeric(combined[column], errors="coerce")
    if sort_columns:
        combined = combined.sort_values(
            [f"__sort_{column}" for column in sort_columns],
            ascending=False,
            na_position="last",
        )
        combined = combined.drop(columns=[f"__sort_{column}" for column in sort_columns])

    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False)
    return combined


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search-dir",
        type=Path,
        action="append",
        default=None,
        help="Directory to scan recursively. Can be provided more than once.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    search_dirs = args.search_dir or [DEFAULT_SEARCH_DIR]
    combined = collect_scores(search_dirs, args.output)
    print(f"Wrote {len(combined)} rows to {args.output}")


if __name__ == "__main__":
    main()
