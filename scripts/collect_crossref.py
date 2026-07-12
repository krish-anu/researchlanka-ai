"""
Inspect or collect works from Crossref.

Examples:
    python scripts/collect_crossref.py inspect --query lanka --limit 3

    python scripts/collect_crossref.py collect-lk \
        --query lanka \
        --query ceylon \
        --max-records 1000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.crossref_collector import CrossrefCollector
from src.preprocessing.crossref_normalizer import reduce_work

DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "crossref" / "lk_works.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or collect Crossref works")
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect Crossref response structure."
    )

    inspect_parser.add_argument(
        "--query",
        action="append",
        default=None,
        help=("Crossref affiliation query. Can be repeated."),
    )

    inspect_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of records to inspect",
    )


    inspect_parser.add_argument(
        "--email",
        default=None,
        help="Email for Crossref polite pool.",
    )

    collect_parser = subparsers.add_parser(
        "collect-lk",
        help="Collect Sri Lankan related Crossref works",
    )

    collect_parser.add_argument(
        "--query",
        action="append",
        default=None,
        help=("Crossref affiliation query. Can be repeated."),
    )

    collect_parser.add_argument(
        "--rows",
        type=int,
        default=100,
        help="Number of records per Crossref request.",
    )

    collect_parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Maximum number of records to collect.",
    )

    collect_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output JSONL path.",
    )

    collect_parser.add_argument(
        "--email",
        default=None,
        help="Email for Crossref polite pool.",
    )

    args = parser.parse_args()


    if args.query is None:
        if args.command == "inspect":
            args.query = ["lanka"]
        elif args.command == "collect-lk":
            args.query = ["lanka", "ceylon"]

    return args


def print_json(title: str, value: Any) -> None:

    print(f"\n## {title}")

    print(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        )
    )


def inspect_crossref(
    collector: CrossrefCollector,
    args: argparse.Namespace,
) -> None:

    for query in args.query:
        print(f"\nSearching Crossref with query: {query}")

        response = collector.fetch_works(
            affiliation_query=query,
            rows=args.limit,
        )

        items = response.get("message", {}).get("items", [])

        if not items:
            continue

        raw_work = items[0]


        print("\nRAW Crossref fields:")
        print(list(raw_work.keys()))

        normalized_work = reduce_work(raw_work)

        print("\nNORMALIZED fields:")
        print(list(normalized_work.keys()))


def collect_crossref(
    collector: CrossrefCollector,
    args: argparse.Namespace,
) -> None:

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    total = 0

    seen_dois = set()

    with args.output.open(
        "w",
        encoding="utf-8",
    ) as output_file:
        for query in args.query:
            print(f"\nCollecting query: {query}")
            remaining = None

            if args.max_records is not None:
                remaining = args.max_records - total

            if remaining <= 0:
                break

            for work in collector.iter_works(
                affiliation_query=query,
                rows=args.rows,
                max_records=remaining,
            ):
                doi = work.get("DOI")

                if doi:
                    doi_key = doi.casefold()

                    if doi_key in seen_dois:
                        continue

                    seen_dois.add(doi_key)

                output_file.write(
                    json.dumps(
                        work,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

                total += 1

                print(f"Collected {total} works...")

                if args.max_records and total >= args.max_records:
                    break

            if args.max_records and total >= args.max_records:
                break

    print(f"\nSaved {total} Crossref records to {args.output}")


def main() -> None:

    args = parse_args()

    if args.command is None:
        print("Please specify a command: inspect or collect-lk")
        return

    collector = CrossrefCollector(email=args.email)

    if args.command == "collect-lk":
        collect_crossref(
            collector,
            args,
        )
    else:
        inspect_crossref(
            collector,
            args,
        )

if __name__ == "__main__":
    
    main()
