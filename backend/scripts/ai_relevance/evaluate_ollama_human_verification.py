#!/usr/bin/env python3
"""Evaluate Ollama labels against the human verification CSV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.human_verification_metrics import (  # noqa: E402
    load_and_calculate_human_verification_metrics,
)


DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "ai"
    / "Human Verification Dataset - ai_llm_150_human_verification_ollama_kaggle.csv"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()

    metrics = load_and_calculate_human_verification_metrics(args.input)

    print(f"Input: {args.input}")
    print(f"Total rows: {metrics.total_rows}")
    print(f"Verified rows: {metrics.verified_rows}")
    print(f"Blank human_label rows: {metrics.blank_human_label_rows}")
    print(f"Model REVIEW rows: {metrics.model_review_rows}")
    print(f"Model REVIEW rows with human label: {metrics.model_review_rows_with_human_label}")
    print(f"Evaluated AI/NON_AI rows: {metrics.evaluated_rows}")
    print()
    print("Confusion matrix, positive class = AI")
    print(f"TP: {metrics.true_positive}")
    print(f"TN: {metrics.true_negative}")
    print(f"FP: {metrics.false_positive}")
    print(f"FN: {metrics.false_negative}")
    print()
    print(f"Accuracy:  {metrics.accuracy:.4f} ({metrics.accuracy:.2%})")
    print(f"Precision: {metrics.precision:.4f} ({metrics.precision:.2%})")
    print(f"Recall:    {metrics.recall:.4f} ({metrics.recall:.2%})")
    print(f"F1 Score:  {metrics.f1_score:.4f} ({metrics.f1_score:.2%})")


if __name__ == "__main__":
    main()
