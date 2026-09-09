#!/usr/bin/env python3
"""Compare AI-relevance model labels against human verification labels."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.human_verification_metrics import (  # noqa: E402
    calculate_human_verification_metrics,
    verified_label_from_human_verification,
)


DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "ai_llm_150_human_verification_qwen3_gemini_mode_prediction.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "ai_llm_150_human_verification_model_scores.csv"
)
DEFAULT_WIDE_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "ai_llm_150_human_verification_model_scores_wide.csv"
)


MODEL_COLUMNS = [
    ("Llama/Ollama", "ai_llm_label"),
    ("Qwen3-8B 4-bit", "Qwen3-8B 4-bit"),
    ("Gemini 3.8 Flash", "Gemini 3.8 Flash"),
    ("Mode prediction", "mode_prediction"),
]


def compare_scores(input_path: Path, output_path: Path, wide_output_path: Path) -> pd.DataFrame:
    frame = pd.read_csv(input_path)
    missing = [column for _, column in MODEL_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing prediction column(s): {', '.join(missing)}")
    if "human_label" not in frame.columns:
        raise ValueError("Missing required column: human_label")

    frame = frame.copy()
    frame["verified_ai_label"] = [
        verified_label_from_human_verification(model_label, human_verification)
        for model_label, human_verification in zip(frame["ai_llm_label"], frame["human_label"], strict=True)
    ]

    rows = []
    for model_name, column in MODEL_COLUMNS:
        metrics_frame = pd.DataFrame(
            {
                "ai_llm_label": frame[column],
                "human_label": frame["verified_ai_label"],
            }
        )
        metrics = calculate_human_verification_metrics(metrics_frame).as_dict()
        rows.append({"model": model_name, "prediction_column": column, **metrics})

    scores = pd.DataFrame(rows)
    ordered = [
        "model",
        "prediction_column",
        "total_rows",
        "verified_rows",
        "blank_human_label_rows",
        "model_review_rows",
        "model_review_rows_with_human_label",
        "evaluated_rows",
        "true_positive",
        "true_negative",
        "false_positive",
        "false_negative",
        "accuracy",
        "precision",
        "recall",
        "f1_score",
    ]
    scores = scores[ordered]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scores.to_csv(output_path, index=False)
    scores.set_index("model").drop(columns=["prediction_column"]).T.to_csv(wide_output_path)
    return scores


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--wide-output", type=Path, default=DEFAULT_WIDE_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scores = compare_scores(args.input, args.output, args.wide_output)
    print(scores.to_string(index=False))
    print()
    print(f"Wrote: {args.output}")
    print(f"Wrote: {args.wide_output}")


if __name__ == "__main__":
    main()
