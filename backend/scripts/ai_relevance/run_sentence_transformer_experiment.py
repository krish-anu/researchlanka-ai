#!/usr/bin/env python3
"""Run sentence-transformer embedding classifiers on the frozen human AI set."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.embedding_experiment import (  # noqa: E402
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SELECTION_DIR,
    SentenceTransformerExperimentConfig,
    render_sentence_transformer_report,
    run_sentence_transformer_experiment,
)


def parse_classifiers(value: str) -> tuple[str, ...]:
    classifiers = tuple(item.strip() for item in value.split(",") if item.strip())
    if not classifiers:
        raise argparse.ArgumentTypeError("At least one classifier is required.")
    return classifiers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-dir", type=Path, default=DEFAULT_SELECTION_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--sentence-transformer-model",
        default="sentence-transformers/all-MiniLM-L6-v2",
    )
    parser.add_argument(
        "--classifiers",
        type=parse_classifiers,
        default=("logistic_regression",),
        help="Comma-separated classifiers: logistic_regression,xgboost",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--human-weight", type=float, default=3.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = run_sentence_transformer_experiment(
        SentenceTransformerExperimentConfig(
            selection_dir=args.selection_dir,
            output_dir=args.output_dir,
            sentence_transformer_model=args.sentence_transformer_model,
            classifiers=tuple(args.classifiers),
            batch_size=args.batch_size,
            random_state=args.random_state,
            human_weight=args.human_weight,
        )
    )
    comparison = pd.read_csv(summary["comparison_csv"])
    print(render_sentence_transformer_report(summary, comparison.to_dict(orient="records")), end="")


if __name__ == "__main__":
    main()
