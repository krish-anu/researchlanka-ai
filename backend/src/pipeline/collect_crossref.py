"""
Inspect or collect works from Crossref.

Examples:
    python scripts/collection/collect_crossref.py inspect --query lanka --limit 3

    python scripts/collection/collect_crossref.py collect-lk \
        --query lanka \
        --query ceylon \
        --max-records 1000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.crossref_collector import CrossrefCollector
from src.preprocessing.crossref_normalizer import reduce_work
from src.utils.file_naming import dataset_filename

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "crossref"
DEFAULT_FROM_YEAR = 2016
DEFAULT_UNTIL_YEAR = 2026
DEFAULT_AFFILIATION_QUERIES = ("sri lanka", "lanka", "ceylon")
DEFAULT_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / dataset_filename(
    "crossref",
    "sri_lanka",
    "works",
    "jsonl",
)
DEFAULT_ENRICHED_OUTPUT_PATH = DEFAULT_OUTPUT_DIR / dataset_filename(
    "crossref",
    "sri_lanka",
    "works",
    "jsonl",
    variant="doi_enriched",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or collect Crossref works")
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect Crossref response structure.",
    )
    inspect_parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="Crossref affiliation query. Can be repeated.",
    )
    inspect_parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of records to inspect.",
    )
    inspect_parser.add_argument(
        "--email",
        default=None,
        help="Email for Crossref polite pool.",
    )

    collect_parser = subparsers.add_parser(
        "collect-lk",
        help="Collect Sri Lankan related Crossref works.",
    )
    collect_parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="Crossref affiliation query. Can be repeated.",
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
    collect_parser.add_argument(
        "--from-year",
        type=int,
        default=DEFAULT_FROM_YEAR,
        help=f"Start publication year. Default: {DEFAULT_FROM_YEAR}.",
    )
    collect_parser.add_argument(
        "--until-year",
        type=int,
        default=DEFAULT_UNTIL_YEAR,
        help=f"End publication year. Default: {DEFAULT_UNTIL_YEAR}.",
    )
    collect_parser.add_argument(
        "--include-all-authorships",
        action="store_true",
        help="Disable the default first-author Sri Lanka affiliation filter.",
    )

    enrich_parser = subparsers.add_parser(
        "enrich-dois",
        help="Fetch Crossref metadata using DOI list.",
    )
    enrich_parser.add_argument(
        "--workers",
        type=int,
        default=20,
        help="Number of parallel DOI requests",
    )
    enrich_parser.add_argument(
        "--email",
        default=None,
        help="Email for Crossref polite pool.",
    )
    enrich_parser.add_argument("--doi-file", type=Path, required=True)
    enrich_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ENRICHED_OUTPUT_PATH,
        help="Output JSONL path.",
    )

    args = parser.parse_args()

    if args.command == "inspect" and args.query is None:
        args.query = ["sri lanka"]
    elif args.command == "collect-lk" and args.query is None:
        args.query = list(DEFAULT_AFFILIATION_QUERIES)

    return args


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
    date_filters = [
        f"from-pub-date:{args.from_year}-01-01",
        f"until-pub-date:{args.until_year}-12-31",
    ]

    with args.output.open("w", encoding="utf-8") as output_file:
        for query in args.query:
            print(f"\nCollecting query: {query}")
            remaining = None

            if args.max_records is not None:
                remaining = args.max_records - total

            if remaining is not None and remaining <= 0:
                break

            for work in collector.iter_works(
                affiliation_query=query,
                filters=date_filters,
                rows=args.rows,
                max_records=remaining,
                require_first_author_lk=not args.include_all_authorships,
            ):
                doi = work.get("DOI")

                if doi:
                    doi_key = doi.casefold()

                    if doi_key in seen_dois:
                        continue

                    seen_dois.add(doi_key)

                output_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                total += 1

                print(f"Collected {total} works...")

                if args.max_records and total >= args.max_records:
                    break

            if args.max_records and total >= args.max_records:
                break

    print(f"\nSaved {total} Crossref records to {args.output}")


def enrich_from_dois(
    collector: CrossrefCollector,
    doi_file: Path,
    output: Path,
    workers: int = 20,
) -> None:
    """
    Enrich metadata using DOI list from Crossref.

    Uses parallel DOI retrieval from CrossrefCollector.iter_doi_works()
    """

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing_dois = set()

    files_to_check = [
        DEFAULT_OUTPUT_PATH,
        output,
    ]

    # Load already collected DOIs to avoid duplicates
    for file_path in files_to_check:
        if not file_path.exists():
            continue

        with file_path.open(
            "r",
            encoding="utf-8",
        ) as f:
            for line in f:
                try:
                    record = json.loads(line)
                except Exception:
                    continue

                doi = record.get("DOI") or record.get("doi")

                if doi:
                    existing_dois.add(doi.casefold())

    # Load DOI list
    with doi_file.open(
        "r",
        encoding="utf-8",
    ) as f:
        dois = [line.strip() for line in f if line.strip()]

    found = 0
    skipped = 0

    with output.open(
        "a",
        encoding="utf-8",
    ) as out:
        for normalized in collector.iter_doi_works(
            dois,
            workers=workers,
        ):
            doi = normalized.get("DOI")

            # Remove duplicates
            if doi and doi.casefold() in existing_dois:
                skipped += 1
                continue

            out.write(
                json.dumps(
                    normalized,
                    ensure_ascii=False,
                )
                + "\n"
            )

            found += 1

            if doi:
                existing_dois.add(doi.casefold())

            if found % 100 == 0:
                print(f"Saved: {found} | Skipped duplicates: {skipped}")

    print(f"\nDOI enrichment completed")
    print(f"New records: {found}")
    print(f"Duplicates skipped: {skipped}")

  
def main() -> None:
    args = parse_args()

    if args.command is None:
        print("Please specify a command: inspect, collect-lk, or enrich-dois")
        return

    collector = CrossrefCollector(email=args.email)

    if args.command == "collect-lk":
        collect_crossref(
            collector,
            args,
        )
    elif args.command == "enrich-dois":
        enrich_from_dois(
            collector,
            args.doi_file,
            args.output,
            workers=args.workers,
        )
    else:
        inspect_crossref(
            collector,
            args,
        )


if __name__ == "__main__":
    main()
