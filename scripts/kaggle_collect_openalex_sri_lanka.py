"""Kaggle-ready OpenAlex collector for Sri Lankan-affiliated works.

Run in Kaggle:
    python kaggle_collect_openalex_sri_lanka.py --max-records 1000

This script keeps a work when at least one authorship has a Sri Lankan
affiliation in OpenAlex. OpenAlex provides affiliation countries, not author
nationality, so "Sri Lankan author" here means an author with country code LK
or an LK institution in that work's authorship metadata.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.openalex_collector import (
    CSV_COLUMNS,
    LK_AUTHORSHIP_FILTER,
    OpenAlexCollector,
    work_to_row,
)


DEFAULT_OUTPUT_DIR = Path("/kaggle/working")
DEFAULT_JSONL_OUTPUT = DEFAULT_OUTPUT_DIR / "openalex_sri_lanka_works.jsonl"
DEFAULT_CSV_OUTPUT = DEFAULT_OUTPUT_DIR / "openalex_sri_lanka_works.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect OpenAlex works with at least one Sri Lankan affiliation."
    )
    parser.add_argument(
        "--jsonl-output",
        type=Path,
        default=DEFAULT_JSONL_OUTPUT,
        help=f"Raw JSONL output path. Default: {DEFAULT_JSONL_OUTPUT}",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=DEFAULT_CSV_OUTPUT,
        help=f"Flat CSV output path. Default: {DEFAULT_CSV_OUTPUT}",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Only save JSONL; do not save the flat CSV.",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[LK_AUTHORSHIP_FILTER],
        help=(
            "OpenAlex filter. Default: authorships.institutions.country_code:LK. "
            "Can be passed multiple times."
        ),
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        help="Optional first publication year, for example 2015.",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=None,
        help="Optional final publication year, for example 2025.",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=200,
        help="Records per OpenAlex request. Default: 200",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Optional safety limit for testing before collecting everything.",
    )
    parser.add_argument(
        "--email",
        default=None,
        help="Optional email for OpenAlex request metadata.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENALEX_API_KEY"),
        help="Optional OpenAlex API key. Defaults to OPENALEX_API_KEY.",
    )
    args, _unknown = parser.parse_known_args()
    return args


def main() -> None:
    args = parse_args()
    args.jsonl_output.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_csv:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)

    collector = OpenAlexCollector(email=args.email, api_key=args.api_key)
    total = 0
    csv_file = None
    writer = None

    try:
        if not args.no_csv:
            csv_file = args.csv_output.open("w", encoding="utf-8", newline="")
            writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
            writer.writeheader()

        with args.jsonl_output.open("w", encoding="utf-8") as jsonl_file:
            works = collector.iter_sri_lankan_works(
                filters=args.filter,
                from_year=args.from_year,
                to_year=args.to_year,
                per_page=args.per_page,
                max_records=args.max_records,
            )
            for work in works:
                jsonl_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                if writer is not None:
                    writer.writerow(work_to_row(work))
                total += 1
                if total % 100 == 0:
                    print(f"Saved {total:,} Sri Lankan-affiliated works...")
    finally:
        if csv_file is not None:
            csv_file.close()

    print(f"Saved {total:,} records to {args.jsonl_output}")
    if not args.no_csv:
        print(f"Saved flat CSV to {args.csv_output}")


if __name__ == "__main__":
    main()
