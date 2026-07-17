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
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.openalex_collector import (
    CSV_COLUMNS,
    LK_AUTHORSHIP_FILTER,
    OpenAlexCollector,
    build_filters,
    country_codes,
    work_to_row,
)


LOCAL_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "openalex"
KAGGLE_OUTPUT_DIR = Path("/kaggle/working")


def default_output_dir() -> Path:
    """Choose a writable default output directory for Kaggle or local runs."""
    override = os.getenv("OPENALEX_OUTPUT_DIR")
    if override:
        return Path(override)
    if KAGGLE_OUTPUT_DIR.is_dir() and os.access(KAGGLE_OUTPUT_DIR, os.W_OK):
        return KAGGLE_OUTPUT_DIR
    return LOCAL_OUTPUT_DIR


DEFAULT_OUTPUT_DIR = default_output_dir()
DEFAULT_JSONL_OUTPUT = DEFAULT_OUTPUT_DIR / "openalex_sri_lanka_works.jsonl"
DEFAULT_CSV_OUTPUT = DEFAULT_OUTPUT_DIR / "openalex_sri_lanka_works.csv"


def default_progress_output(jsonl_output: Path) -> Path:
    """Store resume metadata beside the JSONL output by default."""
    return jsonl_output.with_suffix(f"{jsonl_output.suffix}.progress.json")


def load_progress(path: Path) -> dict:
    """Load and validate the JSON progress metadata used by --resume."""
    with path.open("r", encoding="utf-8") as progress_file:
        progress = json.load(progress_file)
    if not isinstance(progress, dict):
        raise ValueError(f"Progress metadata must be a JSON object: {path}")
    return progress


def save_progress(
    path: Path,
    *,
    next_cursor: str | None,
    records_saved: int,
    filters: list[str],
    strict_lk_only: bool = False,
) -> None:
    """Write resume metadata atomically so interrupted writes do not corrupt it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    progress = {
        "next_cursor": next_cursor,
        "records_saved": records_saved,
        "filters": filters,
        "strict_lk_only": strict_lk_only,
    }
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as progress_file:
        json.dump(progress, progress_file, indent=2)
        progress_file.write("\n")
    temp_path.replace(path)


def read_existing_jsonl_state(path: Path) -> tuple[set[str], int]:
    """Read existing output IDs and row count before appending during resume."""
    openalex_ids: set[str] = set()
    records_saved = 0

    if not path.exists():
        return openalex_ids, records_saved

    with path.open("r", encoding="utf-8") as jsonl_file:
        for line in jsonl_file:
            if not line.strip():
                continue
            records_saved += 1
            try:
                work = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(work, dict) and work.get("id"):
                openalex_ids.add(str(work["id"]))

    return openalex_ids, records_saved


def rebuild_csv_from_jsonl(jsonl_output: Path, csv_output: Path) -> None:
    """Regenerate the flat CSV from raw JSONL before appending resumed records."""
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    with csv_output.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        if not jsonl_output.exists():
            return

        with jsonl_output.open("r", encoding="utf-8") as jsonl_file:
            for line in jsonl_file:
                if not line.strip():
                    continue
                try:
                    work = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(work, dict):
                    writer.writerow(work_to_row(work))


def is_blank(value: object) -> bool:
    """Treat None and whitespace-only strings as missing report values."""
    return value is None or str(value).strip() == ""


def collect_quality_report(
    jsonl_output: Path,
    *,
    records_skipped: int,
) -> dict[str, object]:
    """Summarize quality metrics from the final raw JSONL output."""
    openalex_ids: Counter[str] = Counter()
    dois: Counter[str] = Counter()
    years: list[int] = []
    countries: set[str] = set()
    total_saved = 0
    missing_doi_count = 0
    missing_title_count = 0

    if jsonl_output.exists():
        with jsonl_output.open("r", encoding="utf-8") as jsonl_file:
            for line in jsonl_file:
                if not line.strip():
                    continue
                try:
                    work = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(work, dict):
                    continue

                total_saved += 1

                openalex_id = work.get("id")
                if not is_blank(openalex_id):
                    openalex_ids[str(openalex_id).strip()] += 1

                doi = work.get("doi")
                if is_blank(doi):
                    missing_doi_count += 1
                else:
                    dois[str(doi).strip().lower()] += 1

                if is_blank(work.get("title")) and is_blank(work.get("display_name")):
                    missing_title_count += 1

                year = work.get("publication_year")
                if isinstance(year, int):
                    years.append(year)
                elif isinstance(year, str) and year.isdigit():
                    years.append(int(year))

                for country_code in country_codes(work).split("; "):
                    if country_code:
                        countries.add(country_code)

    year_range = None
    if years:
        year_range = f"{min(years)}-{max(years)}"

    return {
        "total_saved": total_saved,
        "records_skipped": records_skipped,
        "missing_doi_count": missing_doi_count,
        "missing_title_count": missing_title_count,
        "duplicate_openalex_ids": sum(
            1 for count in openalex_ids.values() if count > 1
        ),
        "duplicate_doi_count": sum(1 for count in dois.values() if count > 1),
        "year_range": year_range,
        "countries_found": sorted(countries),
    }


def print_collection_report(report: dict[str, object]) -> None:
    """Print a compact human-readable collection quality report."""
    countries = report["countries_found"]
    countries_text = "; ".join(countries) if isinstance(countries, list) else ""

    print("Collection report:")
    print(f"  Total saved: {report['total_saved']:,}")
    print(f"  Records skipped: {report['records_skipped']:,}")
    print(f"  Missing DOI count: {report['missing_doi_count']:,}")
    print(f"  Missing title count: {report['missing_title_count']:,}")
    print(f"  Duplicate OpenAlex IDs: {report['duplicate_openalex_ids']:,}")
    print(f"  Duplicate DOI count: {report['duplicate_doi_count']:,}")
    print(f"  Year range: {report['year_range'] or 'n/a'}")
    print(f"  Countries found: {countries_text or 'n/a'}")


def parse_args() -> argparse.Namespace:
    """Parse CLI flags while tolerating unknown notebook/Kaggle arguments."""
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
        "--resume",
        action="store_true",
        help="Resume from saved progress metadata and append to existing outputs.",
    )
    parser.add_argument(
        "--progress-output",
        type=Path,
        default=None,
        help=(
            "Progress metadata path. Default: JSONL output path with "
            ".progress.json appended."
        ),
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
        "--strict-lk-only",
        action="store_true",
        help="Keep only works whose detected affiliation country-code set is exactly LK.",
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
    """Run collection, resume handling, output writing, and final reporting."""
    args = parse_args()
    progress_output = args.progress_output or default_progress_output(args.jsonl_output)
    filters = build_filters(
        args.filter,
        from_year=args.from_year,
        to_year=args.to_year,
    )
    start_cursor = "*"
    existing_ids: set[str] = set()
    total = 0

    if args.resume:
        if not progress_output.exists():
            raise SystemExit(
                f"Cannot resume: progress metadata not found: {progress_output}"
            )
        if not args.jsonl_output.exists():
            raise SystemExit(f"Cannot resume: JSONL output not found: {args.jsonl_output}")

        progress = load_progress(progress_output)
        # A resumed job must match the original query shape to avoid mixing
        # incompatible result sets into the same raw and flat output files.
        if progress.get("filters") != filters:
            raise SystemExit(
                "Cannot resume: current filters do not match saved progress filters."
            )
        if bool(progress.get("strict_lk_only", False)) != args.strict_lk_only:
            raise SystemExit(
                "Cannot resume: strict LK-only setting does not match saved progress."
            )

        start_cursor = progress.get("next_cursor")
        if start_cursor is None:
            print(f"Collection already completed according to {progress_output}")
            return

        existing_ids, total = read_existing_jsonl_state(args.jsonl_output)
        total = max(total, int(progress.get("records_saved", 0)))
        if not args.no_csv:
            rebuild_csv_from_jsonl(args.jsonl_output, args.csv_output)

    args.jsonl_output.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_csv:
        args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    if not args.resume:
        # Create metadata before the first request so even early failures have
        # enough state for a later --resume run.
        save_progress(
            progress_output,
            next_cursor=start_cursor,
            records_saved=total,
            filters=filters,
            strict_lk_only=args.strict_lk_only,
        )

    collector = OpenAlexCollector(email=args.email, api_key=args.api_key)
    csv_file = None
    writer = None
    output_mode = "a" if args.resume else "w"
    csv_mode = "a" if args.resume else "w"
    stop_requested = False
    records_skipped = 0

    try:
        if not args.no_csv:
            csv_file = args.csv_output.open(csv_mode, encoding="utf-8", newline="")
            writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
            if not args.resume:
                writer.writeheader()

        with args.jsonl_output.open(output_mode, encoding="utf-8") as jsonl_file:
            pages = collector.iter_sri_lankan_work_pages(
                filters=args.filter,
                from_year=args.from_year,
                to_year=args.to_year,
                per_page=args.per_page,
                start_cursor=start_cursor,
                strict_lk_only=args.strict_lk_only,
            )
            for page in pages:
                records_skipped += page.skipped_count
                for work in page.works:
                    if args.max_records is not None and total >= args.max_records:
                        stop_requested = True
                        break

                    openalex_id = str(work.get("id", ""))
                    # If a crash happened after writing a record but before
                    # advancing the cursor, resume may see that record again.
                    if args.resume and openalex_id and openalex_id in existing_ids:
                        records_skipped += 1
                        continue

                    jsonl_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                    if writer is not None:
                        writer.writerow(work_to_row(work))
                    if openalex_id:
                        existing_ids.add(openalex_id)
                    total += 1
                    if total % 100 == 0:
                        print(f"Saved {total:,} Sri Lankan-affiliated works...")

                jsonl_file.flush()
                if csv_file is not None:
                    csv_file.flush()

                save_progress(
                    progress_output,
                    next_cursor=page.cursor if stop_requested else page.next_cursor,
                    records_saved=total,
                    filters=filters,
                    strict_lk_only=args.strict_lk_only,
                )
                if stop_requested:
                    break
    finally:
        if csv_file is not None:
            csv_file.close()

    print(f"Saved {total:,} records to {args.jsonl_output}")
    if not args.no_csv:
        print(f"Saved flat CSV to {args.csv_output}")
    print(f"Saved progress metadata to {progress_output}")
    print_collection_report(
        collect_quality_report(
            args.jsonl_output,
            records_skipped=records_skipped,
        )
    )


if __name__ == "__main__":
    main()
