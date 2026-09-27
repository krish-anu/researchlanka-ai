#!/usr/bin/env python3
"""Run LLM second opinions only for difficult ML review rows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.config import GeminiConfig  # noqa: E402
from src.ai_relevance.llm_reviewer import (  # noqa: E402
    LLMReviewerConfig,
    add_llm_reviewer_candidate_columns,
    apply_llm_second_opinions,
    build_llm_reviewer_client,
)
from src.pipeline.refresh_policy import (  # noqa: E402
    DEFAULT_AUTO_AI_THRESHOLD,
    DEFAULT_AUTO_NON_AI_THRESHOLD,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-fraction", type=float, default=0.20)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--min-priority", type=float, default=0.0)
    parser.add_argument("--auto-ai-threshold", type=float, default=DEFAULT_AUTO_AI_THRESHOLD)
    parser.add_argument(
        "--auto-non-ai-threshold",
        type=float,
        default=DEFAULT_AUTO_NON_AI_THRESHOLD,
    )
    parser.add_argument(
        "--mark-only",
        action="store_true",
        help="Write pending LLM reviewer candidates without making LLM calls.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame = pd.read_csv(args.input, dtype="object", low_memory=False)
    gemini_config = GeminiConfig.from_env()
    reviewer_config = LLMReviewerConfig(
        max_fraction=args.max_fraction,
        max_records=args.max_records,
        min_priority=args.min_priority,
        auto_ai_threshold=args.auto_ai_threshold,
        auto_non_ai_threshold=args.auto_non_ai_threshold,
        model=gemini_config.model,
        prompt_version=gemini_config.prompt_version,
    )
    if args.mark_only:
        output = add_llm_reviewer_candidate_columns(frame, reviewer_config)
    else:
        output = apply_llm_second_opinions(
            frame,
            client=build_llm_reviewer_client(gemini_config),
            config=reviewer_config,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)

    counts = output["ai_llm_reviewer_status"].value_counts()
    print(
        "LLM reviewer second-opinion rows: "
        f"pending={int(counts.get('pending', 0))}, "
        f"success={int(counts.get('success', 0))}, "
        f"failed={int(counts.get('failed', 0))}, "
        f"not_candidate={int(counts.get('not_candidate', 0))}"
    )
    print(f"Output: {args.output}")
    print("LLM labels are advisory only; ai_classification_label is unchanged.")


if __name__ == "__main__":
    main()
