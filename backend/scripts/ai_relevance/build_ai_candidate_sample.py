#!/usr/bin/env python3
"""Build the AI relevance candidate sample from the final publication dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ai_relevance.sampling import CandidateSamplingConfig, build_candidate_sample  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "ai" / "ai_llm_5000_candidates.csv",
    )
    parser.add_argument("--target-size", type=int, default=5000)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
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


if __name__ == "__main__":
    main()
