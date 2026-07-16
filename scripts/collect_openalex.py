"""Inspect or collect works from OpenAlex.

Examples:
    python scripts/collect_openalex.py --query "Sri Lanka" --limit 3 --raw
    python scripts/collect_openalex.py collect-lk --max-records 1000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.openalex_collector import (
    OpenAlexCollector,
    describe_value,
    work_has_author_from_country,
)


LK_COUNTRY_CODE = "LK"
LK_AUTHORSHIP_FILTER = "authorships.institutions.country_code:LK"
KAGGLE_WORKING_DIR = Path("/kaggle/working")
DEFAULT_OUTPUT_DIR = (
    KAGGLE_WORKING_DIR
    if KAGGLE_WORKING_DIR.exists()
    else PROJECT_ROOT / "data" / "raw" / "openalex"
)
DEFAULT_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / "lk_works.jsonl"


DEFAULT_FIELDS = [
    "id",
    "doi",
    "title",
    "display_name",
    "publication_year",
    "publication_date",
    "type",
    "cited_by_count",
    "authorships",
    "concepts",
    "primary_location",
    "open_access",
]


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--email",
        default=None,
        help="Optional email for the OpenAlex polite pool.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENALEX_API_KEY"),
        help=(
            "Optional OpenAlex API key. Defaults to OPENALEX_API_KEY, which can "
            "be set from Kaggle Secrets."
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or collect OpenAlex works.")
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Fetch a small sample and print its JSON structure.",
    )
    parser.add_argument(
        "--query",
        default="Sri Lanka",
        help="Search text to send to OpenAlex. Default: Sri Lanka",
    )
    parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help=(
            "OpenAlex filter, for example "
            "'from_publication_date:2024-01-01'. Can be passed multiple times."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of works to fetch. Default: 3",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print the full raw JSON response.",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Optional path to save the raw JSON response.",
    )
    add_common_args(parser)

    inspect_parser.add_argument(
        "--query",
        default="Sri Lanka",
        help="Search text to send to OpenAlex. Default: Sri Lanka",
    )
    inspect_parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help=(
            "OpenAlex filter, for example "
            "'from_publication_date:2024-01-01'. Can be passed multiple times."
        ),
    )
    inspect_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of works to fetch. Default: 3",
    )
    inspect_parser.add_argument(
        "--raw",
        action="store_true",
        help="Print the full raw JSON response.",
    )
    inspect_parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Optional path to save the raw JSON response.",
    )
    add_common_args(inspect_parser)

    collect_parser = subparsers.add_parser(
        "collect-lk",
        help=(
            "Collect full work records where at least one author has a "
            "Sri Lankan affiliation."
        ),
    )
    collect_parser.add_argument(
        "--filter",
        action="append",
        default=[LK_AUTHORSHIP_FILTER],
        help=(
            "OpenAlex filter. Default: authorships.institutions.country_code:LK. "
            "This keeps works where at least one authorship has an LK "
            "institution. Can be passed multiple times."
        ),
    )
    collect_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"JSONL output path. Default: {DEFAULT_OUTPUT_PATH}",
    )
    collect_parser.add_argument(
        "--per-page",
        type=int,
        default=100,
        help="Records per OpenAlex request. Default: 100",
    )
    collect_parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Optional safety limit for testing before collecting everything.",
    )
    collect_parser.add_argument(
        "--skip-local-lk-check",
        action="store_true",
        help=(
            "Skip the local safety check that keeps only records with at least "
            "one LK authorship/institution."
        ),
    )
    add_common_args(collect_parser)

    return parser.parse_args()


def print_json(title: str, value: Any) -> None:
    print(f"\n## {title}")
    print(json.dumps(value, indent=2, ensure_ascii=False))


def inspect_openalex(collector: OpenAlexCollector, args: argparse.Namespace) -> None:
    response = collector.fetch_works(
        search=args.query,
        filters=args.filter,
        per_page=args.limit,
    )

    results = response.get("results", [])

    print("OpenAlex response received")
    print(f"Top-level keys: {list(response.keys())}")
    print(f"Result count in this response: {len(results)}")

    print_json("Meta", response.get("meta", {}))

    if results:
        first_work = results[0]
        print(f"\nFirst work keys: {list(first_work.keys())}")

        preview = {key: first_work.get(key) for key in DEFAULT_FIELDS if key in first_work}
        print_json("First Work Preview", preview)
        print_json("First Work Shape", describe_value(first_work, max_depth=3))
    else:
        print("\nNo works returned for this query/filter.")

    if args.raw:
        print_json("Raw Response", response)

    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(
            json.dumps(response, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nSaved raw response to {args.save}")


def collect_lk_works(collector: OpenAlexCollector, args: argparse.Namespace) -> None:
    args.output.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    skipped = 0
    with args.output.open("w", encoding="utf-8") as output_file:
        for work in collector.iter_works(
            filters=args.filter,
            per_page=args.per_page,
        ):
            if args.max_records is not None and total >= args.max_records:
                break

            if not args.skip_local_lk_check and not work_has_author_from_country(
                work,
                LK_COUNTRY_CODE,
            ):
                skipped += 1
                continue

            output_file.write(json.dumps(work, ensure_ascii=False) + "\n")
            total += 1

            print(f"Collected {total} works...")

    print(f"Saved {total} full OpenAlex work records to {args.output}")
    if skipped:
        print(f"Skipped {skipped} records without a detectable LK authorship.")


def main() -> None:
    args = parse_args()
    collector = OpenAlexCollector(email=args.email, api_key=args.api_key)

    if args.command == "collect-lk":
        collect_lk_works(collector, args)
    else:
        inspect_openalex(collector, args)


if __name__ == "__main__":
    main()
