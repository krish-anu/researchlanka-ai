#!/usr/bin/env python3
"""
Extract author information (collapses authors/author_names into one
canonical field per record).

Usage:
    python scripts/extract_authors.py --input path/to/dataset.csv --output outputs/author_info.csv
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.io_utils import load_dataset, save_dataset
from utils.author_utils import extract_authors_batch


def main():
    parser = argparse.ArgumentParser(
        description="Extract and normalize author information."
    )
    parser.add_argument(
        "--input", required=True, help="Path to input dataset (CSV or Parquet)."
    )
    parser.add_argument(
        "--output", default="outputs/author_info.csv", help="Path to write results."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Optional chunk size for processing very large datasets.",
    )
    args = parser.parse_args()

    df = load_dataset(args.input, check_full_schema=True)
    result = extract_authors_batch(df, batch_size=args.batch_size)

    combined = df.join(result, rsuffix="_extracted")
    save_dataset(combined, args.output)


if __name__ == "__main__":
    main()
