#!/usr/bin/env python3
"""Evaluate Gemini AI relevance labels against completed human labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.evaluation import (  # noqa: E402
    GeminiHumanEvaluationConfig,
    evaluate_gemini_against_human,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "reports" / "ai_relevance",
    )
    parser.add_argument("--run-name", default="gemini_ai_relevance")
    parser.add_argument("--include-human-review", action="store_true")
    args = parser.parse_args()
    metrics = evaluate_gemini_against_human(
        GeminiHumanEvaluationConfig(
            input_path=args.input,
            output_dir=args.output_dir,
            run_name=args.run_name,
            exclude_human_review=not args.include_human_review,
        )
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
