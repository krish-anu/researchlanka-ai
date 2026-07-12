"""Inspect or collect works from OpenAlex.

Examples:
    python scripts/collect_openalex.py --query "Sri Lanka" --limit 3 --raw
    python scripts/collect_openalex.py collect-lk --max-records 1000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# from src.collectors.openalex_collector import OpenAlexCollector, describe_value
from src.collectors.openalex_collector import OpenAlexCollector
from src.utils.schema import describe_value


LK_INSTITUTION_FILTER = "institutions.country_code:LK"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "openalex" / "lk_works.jsonl"


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
        help="Collect full work records for Sri Lankan institution papers.",
    )
    collect_parser.add_argument(
        "--filter",
        action="append",
        default=[LK_INSTITUTION_FILTER],
        help=(
            "OpenAlex filter. Default: institutions.country_code:LK. "
            "Can be passed multiple times."
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
        default=200,
        help="Records per OpenAlex request. Default: 200",
    )
    collect_parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Optional safety limit for testing before collecting everything.",
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
    with args.output.open("w", encoding="utf-8") as output_file:
        for work in collector.iter_works(
            filters=args.filter,
            per_page=args.per_page,
            max_records=args.max_records,
        ):
            output_file.write(json.dumps(work, ensure_ascii=False) + "\n")
            total += 1

            print(f"Collected {total} works...")

    print(f"Saved {total} full OpenAlex work records to {args.output}")


def main() -> None:
    args = parse_args()
    collector = OpenAlexCollector(email=args.email)

    if args.command == "collect-lk":
        collect_lk_works(collector, args)
    else:
        inspect_openalex(collector, args)


if __name__ == "__main__":
    main()
