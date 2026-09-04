#!/usr/bin/env python3
"""Export a reproducible human-review sample from Gemini predictions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.review import HumanReviewConfig, build_human_review_sample  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "ai" / "ai_human_review_sample.csv",
    )
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--random-seed", type=int, default=42)
    args = parser.parse_args()
    frame = build_human_review_sample(
        HumanReviewConfig(
            input_path=args.input,
            output_path=args.output,
            sample_size=args.sample_size,
            random_seed=args.random_seed,
        )
    )
    print(f"Wrote {len(frame)} human-review rows to {args.output}")


if __name__ == "__main__":
    main()
