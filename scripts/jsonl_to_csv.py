"""Convert Crossref JSONL to flat CSV."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def convert_to_csv(jsonl_path: Path, csv_path: Path, chunksize: int = 10000) -> int:
    """
    Convert JSONL to CSV using chunked reading for memory efficiency.

    Args:
        jsonl_path: Path to input JSONL file.
        csv_path: Path to output CSV file.
        chunksize: Number of records per chunk.

    Returns:
        Total records processed.
    """
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Input file not found: {jsonl_path}")

    csv_path.unlink(missing_ok=True)

    total = 0
    first_chunk = True

    try:
        for chunk in pd.read_json(jsonl_path, lines=True, chunksize=chunksize):
            chunk.to_csv(
                csv_path,
                mode="w" if first_chunk else "a",
                index=False,
                header=first_chunk,
                encoding="utf-8",
            )

            first_chunk = False
            total += len(chunk)

            logger.info(f"Processed {total} records...")

    except Exception as e:
        logger.error(f"Error during conversion: {e}")
        raise

    return total


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Convert Crossref JSONL to CSV.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/crossref/lk_works.jsonl"),
        help="Input JSONL path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/crossref/lk_works.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=10000,
        help="Chunk size for processing (records per chunk).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)

    total = convert_to_csv(args.input, args.output, chunksize=args.chunksize)
    print(f"Saved {total} records to {args.output}")


if __name__ == "__main__":
    main()
