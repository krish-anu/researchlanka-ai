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

SLJOL_DOI_PREFIX = "10.4038"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "sljol" / "crossref_works.jsonl"
DEFAULT_AUDIT_PATH = PROJECT_ROOT / "data" / "raw" / "sljol" / "crossref_collection_audit.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect SLJOL metadata via Crossref (prefix 10.4038).")
    parser.add_argument("--email", default=None, help="Email for the Crossref polite pool (recommended).")
    parser.add_argument("--max-records", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--rows", type=int, default=500, help="Records per request (max 1000). Default: 500")
    parser.add_argument("--from-year", type=int, default=1900, help="First publication year to collect.")
    parser.add_argument("--until-year", type=int, default=2026, help="Final publication year to collect.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help=f"JSONL output path. Default: {DEFAULT_OUTPUT_PATH}")
    parser.add_argument("--audit-output", type=Path, default=DEFAULT_AUDIT_PATH, help=f"Collection audit path. Default: {DEFAULT_AUDIT_PATH}")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

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
    seen_dois: set[str] = set()
    audit_rows: list[dict[str, object]] = []
    try:
        with args.output.open("w", encoding="utf-8") as output_file:
            for year in range(args.from_year, args.until_year + 1):
                if args.max_records is not None and total >= args.max_records:
                    break
                for filters, label in _date_slices_for_year(collector, year):
                    if args.max_records is not None and total >= args.max_records:
                        break
                    available = collector.total_works(filters=filters)
                    if available == 0:
                        continue

                    slice_saved = 0
                    before = total
                    remaining = None
                    if args.max_records is not None:
                        remaining = args.max_records - total

                    for work in collector.iter_works(max_records=remaining, filters=filters):
                        doi = (work.get("DOI") or work.get("doi") or "").casefold()
                        if doi and doi in seen_dois:
                            continue
                        if doi:
                            seen_dois.add(doi)
                        output_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                        total += 1
                        slice_saved += 1
                        if total % 1000 == 0:
                            print(f"Collected {total} works...")
                        if args.max_records is not None and total >= args.max_records:
                            break

                    audit_rows.append(
                        {
                            "slice": label,
                            "filters": filters,
                            "crossref_total": available,
                            "saved": slice_saved,
                            "duplicates_skipped": max(available - slice_saved, 0)
                            if total == before + slice_saved
                            else None,
                        }
                    )
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
                "from_year": args.from_year,
                "until_year": args.until_year,
                "slices": audit_rows,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Saved {total} works to {args.output}")
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
