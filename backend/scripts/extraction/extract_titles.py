#!/usr/bin/env python3
"""
Extract title information (display title + normalized form for
filtering/matching).

Usage:
    python scripts/extraction/extract_titles.py --input path/to/dataset.csv --output outputs/title_info.csv
"""

import argparse
import sys
from pathlib import Path

# Allow `python scripts/extraction/<script>.py` from anywhere by putting the
# backend root (two levels up) on sys.path before importing `src.*`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.io_utils import load_dataset, save_dataset
from src.utils.title_utils import extract_title_batch


def main():
    parser = argparse.ArgumentParser(
        description="Extract and normalize title information."
    )
    parser.add_argument(
        "--input", required=True, help="Path to input dataset (CSV or Parquet)."
    )
    parser.add_argument(
        "--output", default="outputs/title_info.csv", help="Path to write results."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Optional chunk size for processing very large datasets.",
    )
    args = parser.parse_args()

    # extract_title reads title plus the optional subtitle/original_title.
    df = load_dataset(args.input, required_columns=["title"])
    result = extract_title_batch(df, batch_size=args.batch_size)

    combined = df.join(result, rsuffix="_extracted")
    save_dataset(combined, args.output)


if __name__ == "__main__":
    main()
