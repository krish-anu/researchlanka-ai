"""Collect SLJOL (Sri Lanka Journals Online) article metadata via
Crossref, using the platform's DOI prefix 10.4038.

sljol.info itself blocks scripted access (WAF); Crossref's public API is
the sanctioned route to the same bibliographic metadata. See
docs/DATA_COLLECTION.md and the registry notes for background.

Examples:
    python scripts/collection/collect_sljol.py --email you@example.com --max-records 50
    python scripts/collection/collect_sljol.py --email you@example.com
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.collectors.crossref_collector import CrossrefPrefixCollector
from src.preprocessing.crossref_normalizer import first_author_is_from_sri_lanka
from src.utils.doi import is_valid_doi, normalize_doi

SLJOL_DOI_PREFIX = "10.4038"
DEFAULT_FROM_YEAR = 2016
DEFAULT_UNTIL_YEAR = date.today().year
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "sljol" / "crossref_works.jsonl"
DEFAULT_AUDIT_PATH = PROJECT_ROOT / "data" / "raw" / "sljol" / "crossref_collection_audit.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect SLJOL metadata via Crossref (prefix 10.4038).")
    parser.add_argument("--email", default=None, help="Email for the Crossref polite pool (recommended).")
    parser.add_argument("--max-records", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--rows", type=int, default=500, help="Records per request (max 1000). Default: 500")
    parser.add_argument(
        "--from-year",
        type=int,
        default=DEFAULT_FROM_YEAR,
        help=f"First publication year. Default: {DEFAULT_FROM_YEAR}",
    )
    parser.add_argument(
        "--until-year",
        type=int,
        default=DEFAULT_UNTIL_YEAR,
        help=f"Final publication year. Default: {DEFAULT_UNTIL_YEAR}",
    )
    parser.add_argument(
        "--no-date-slicing",
        action="store_true",
        help="Use one prefix cursor scan instead of recursive publication-date windows.",
    )
    parser.add_argument(
        "--require-first-author-lk",
        action="store_true",
        help="Keep only records where Crossref identifies a Sri Lankan first-author affiliation.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help=f"JSONL output path. Default: {DEFAULT_OUTPUT_PATH}")
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT_PATH, help=f"Collection audit path. Default: {DEFAULT_AUDIT_PATH}")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    from_year = max(args.from_year, DEFAULT_FROM_YEAR)
    until_year = min(args.until_year, DEFAULT_UNTIL_YEAR)

    collector = CrossrefPrefixCollector(
        prefix=SLJOL_DOI_PREFIX,
        email=args.email,
        rows=args.rows,
    )

    try:
        total_available = collector.total_works()
    except requests.RequestException as exc:
        raise SystemExit(f"Could not reach Crossref: {exc}") from exc

    print(f"Crossref reports {total_available} works under prefix {SLJOL_DOI_PREFIX}.")
    print(f"Collecting -> {args.output}")

    total = 0
    skipped_first_author = 0
    skipped_missing_doi = 0
    seen_dois: set[str] = set()
    audit_rows: list[dict[str, object]] = []
    try:
        with args.output.open("w", encoding="utf-8") as output_file:
            works = (
                collector.iter_works(
                    max_records=args.max_records,
                    start_year=from_year,
                    end_year=until_year,
                )
                if args.no_date_slicing
                else collector.iter_works_by_publication_date(
                    start_year=from_year,
                    end_year=until_year,
                    max_records=args.max_records,
                )
            )
            for work in works:
                doi = work.get("DOI")
                doi_key = normalize_doi(doi)
                if doi_key is None or not is_valid_doi(doi_key):
                    skipped_missing_doi += 1
                    continue
                if doi_key in seen_dois:
                    continue
                seen_dois.add(doi_key)
                if (
                    args.require_first_author_lk
                    and not first_author_is_from_sri_lanka(work)
                ):
                    skipped_first_author += 1
                    continue
                output_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                total += 1
                if total % 1000 == 0:
                    print(f"Collected {total} works...")
    except requests.RequestException as exc:
        print(f"Request failed after {total} works: {exc}")
        print(f"Saved {total} works collected before the error to {args.output}")
        raise SystemExit(1) from exc

    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(
        json.dumps(
            {
                "source": "sljol_via_crossref",
                "doi_prefix": SLJOL_DOI_PREFIX,
                "collection_date": date.today().isoformat(),
                "reported_total": total_available,
                "saved_total": total,
                "skipped_first_author_not_lk": skipped_first_author,
                "skipped_missing_doi": skipped_missing_doi,
                "from_year": from_year,
                "until_year": until_year,
                "slices": audit_rows,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Saved {total} works to {args.output}")
    if skipped_first_author:
        print(f"Skipped {skipped_first_author} works without first-author LK evidence.")
    if skipped_missing_doi:
        print(f"Skipped {skipped_missing_doi} works without a valid DOI.")
    print(f"Saved audit to {args.audit_output}")


def _date_slices_for_year(
    collector: CrossrefPrefixCollector,
    year: int,
) -> list[tuple[list[str], str]]:
    year_filters = [f"from-pub-date:{year}-01-01", f"until-pub-date:{year}-12-31"]
    total = collector.total_works(filters=year_filters)
    if total <= collector.rows:
        return [(year_filters, str(year))]
    slices = []
    for month in range(1, 13):
        start = f"{year}-{month:02d}-01"
        end_day = _month_end_day(year, month)
        end = f"{year}-{month:02d}-{end_day:02d}"
        slices.append(
            (
                [f"from-pub-date:{start}", f"until-pub-date:{end}"],
                f"{year}-{month:02d}",
            )
        )
    return slices


def _month_end_day(year: int, month: int) -> int:
    if month == 2:
        return 29 if _is_leap_year(year) else 28
    if month in {4, 6, 9, 11}:
        return 30
    return 31


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


if __name__ == "__main__":
    main()
