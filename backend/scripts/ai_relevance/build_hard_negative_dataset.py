#!/usr/bin/env python3
"""Build hard-negative NON_AI training rows from reviewed false positives."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.hard_negatives import (  # noqa: E402
    OUTPUT_COLUMNS,
    build_hard_negative_frame,
)
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data/models/ai_relevance/validated_human_selection_xgboost_fast"
    / "false_positive_analysis/false_positive_ai_cases.csv"
)
DEFAULT_ARCHIVED_INPUT = (
    PROJECT_ROOT
    / "data/old_datasets_2026-09-30/backend/data/models/ai_relevance"
    / "old_artifacts_2026-09-30/validated_human_selection_xgboost_fast"
    / "false_positive_analysis/false_positive_ai_cases.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data/processed/ai/hard_negative_false_positive_non_ai.csv"
)


def resolve_input_path(input_csv: Path) -> Path:
    if input_csv.exists():
        return input_csv
    if input_csv == DEFAULT_INPUT and DEFAULT_ARCHIVED_INPUT.exists():
        return DEFAULT_ARCHIVED_INPUT
    raise FileNotFoundError(f"False-positive input CSV was not found: {input_csv}")


def build_hard_negative_dataset(input_csv: Path, output_csv: Path) -> int:
    input_csv = resolve_input_path(input_csv)
    frame = pd.read_csv(input_csv, dtype=str, keep_default_na=False, low_memory=False)
    frame["hard_negative"] = "true"
    if "label_source" not in frame.columns:
        frame["label_source"] = "human_rejected_false_positive"
    hard_negatives = build_hard_negative_frame(frame.to_dict("records"))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    hard_negatives.to_csv(output_csv, columns=list(OUTPUT_COLUMNS), index=False)
    return len(hard_negatives)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert false-positive review cases into hard-negative NON_AI rows."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count = build_hard_negative_dataset(args.input, args.output)
    print(f"Wrote {count} hard-negative rows to {args.output}")


if __name__ == "__main__":
    main()
