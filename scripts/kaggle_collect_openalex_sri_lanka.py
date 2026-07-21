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
import logging
import os
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.openalex_collector import (
    DEFAULT_FROM_YEAR,
    DEFAULT_TO_YEAR,
    LK_AUTHORSHIP_FILTER,
    OpenAlexCollector,
    build_filters,
)
from src.preprocessing.openalex_normalizer import (
    CSV_COLUMNS,
    country_codes,
    openalex_work_id,
    work_to_row,
)
from src.utils.doi import normalize_doi
from src.utils.file_naming import dataset_filename


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
DEFAULT_JSONL_OUTPUT = DEFAULT_OUTPUT_DIR / dataset_filename(
    "openalex",
    "sri_lanka",
    "works",
    "jsonl",
)
DEFAULT_CSV_OUTPUT = DEFAULT_OUTPUT_DIR / dataset_filename(
    "openalex",
    "sri_lanka",
    "works",
    "csv",
)
DEFAULT_PARQUET_OUTPUT = DEFAULT_OUTPUT_DIR / dataset_filename(
    "openalex",
    "sri_lanka",
    "works",
    "parquet",
)
DEFAULT_DOI_CONFLICTS_OUTPUT = DEFAULT_OUTPUT_DIR / dataset_filename(
    "openalex",
    "sri_lanka",
    "doi_conflicts",
    "csv",
)
DEFAULT_PAGINATION_OUTPUT = DEFAULT_OUTPUT_DIR / dataset_filename(
    "openalex",
    "sri_lanka",
    "pagination_audit",
    "json",
)
DEFAULT_LOG_LEVEL = os.getenv("OPENALEX_LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

logger = logging.getLogger(__name__)

DOI_CONFLICT_COLUMNS = [
    "doi",
    "openalex_id_count",
    "record_count",
    "openalex_ids",
    "titles",
    "publication_years",
]


def setup_logging(level: str, log_file: Path | None = None) -> None:
    """Configure console logging and optionally mirror logs to a file."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=log_level,
        format=LOG_FORMAT,
        handlers=handlers,
        force=True,
    )


def default_progress_output(jsonl_output: Path) -> Path:
    """Store resume metadata beside the JSONL output by default."""
    return jsonl_output.with_suffix(f"{jsonl_output.suffix}.progress.json")


def default_pagination_output(jsonl_output: Path) -> Path:
    """Store pagination audit metadata beside custom JSONL outputs."""
    return jsonl_output.with_name("openalex_sri_lanka_pagination_audit.json")


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


def load_pagination_events(path: Path) -> list[dict[str, object]]:
    """Load existing pagination events so resume runs keep one audit trail."""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as audit_file:
        audit = json.load(audit_file)
    if not isinstance(audit, dict):
        return []
    events = audit.get("pages")
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def pagination_event_from_page(
    page,
    *,
    global_page_number: int,
    records_saved: int,
    records_skipped: int,
) -> dict[str, object]:
    """Create one serializable audit row for a fetched OpenAlex cursor page."""
    return {
        "page_number": global_page_number,
        "run_page_number": page.page_number,
        "cursor": page.cursor,
        "next_cursor": page.next_cursor,
        "fetched_count": page.fetched_count,
        "kept_count": len(page.works),
        "skipped_count": page.skipped_count,
        "records_saved_total": records_saved,
        "records_skipped_total": records_skipped,
        "api_total_count": page.api_total_count,
        "estimated_total_pages": page.estimated_total_pages,
        "progress_percent": page.progress_percent,
        "db_response_time_ms": page.db_response_time_ms,
        "filters": page.filters,
    }


def write_pagination_audit_report(
    path: Path,
    *,
    pages: list[dict[str, object]],
    filters: list[str],
    strict_lk_only: bool,
    records_saved: int,
    records_skipped: int,
    next_cursor: str | None,
    status: str,
) -> None:
    """Write page-by-page pagination monitoring and validation results."""
    path.parent.mkdir(parents=True, exist_ok=True)
    latest_page = pages[-1] if pages else {}
    audit = {
        "status": status,
        "pages_fetched": len(pages),
        "records_saved": records_saved,
        "records_skipped": records_skipped,
        "next_cursor": next_cursor,
        "filters": filters,
        "strict_lk_only": strict_lk_only,
        "api_total_count": latest_page.get("api_total_count"),
        "estimated_total_pages": latest_page.get("estimated_total_pages"),
        "progress_percent": latest_page.get("progress_percent"),
        "pages": pages,
    }
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as audit_file:
        json.dump(audit, audit_file, indent=2, ensure_ascii=False)
        audit_file.write("\n")
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
            if isinstance(work, dict):
                work_id = openalex_work_id(work)
                if work_id is not None:
                    openalex_ids.add(work_id)

    return openalex_ids, records_saved


def rebuild_csv_from_jsonl(jsonl_output: Path, csv_output: Path) -> None:
    """Regenerate the flat CSV from raw JSONL before appending resumed records."""
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    with csv_output.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for row in iter_flat_rows_from_jsonl(jsonl_output):
            writer.writerow(row)


def iter_flat_rows_from_jsonl(jsonl_output: Path):
    """Yield flattened OpenAlex rows from raw JSONL records."""
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
                yield work_to_row(work)


def write_parquet_from_jsonl(jsonl_output: Path, parquet_output: Path) -> int:
    """Write flattened OpenAlex rows to Parquet and return the row count."""
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires pandas and a Parquet engine such as pyarrow."
        ) from exc

    rows = []
    for row in iter_flat_rows_from_jsonl(jsonl_output):
        parquet_row = dict(row)
        publication_date = parquet_row.get("publication_date")
        if publication_date:
            parquet_row["publication_date"] = date.fromisoformat(str(publication_date))
        rows.append(parquet_row)

    dataframe = pd.DataFrame(rows, columns=CSV_COLUMNS)
    parquet_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        dataframe.to_parquet(parquet_output, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires pyarrow or fastparquet. "
            "Install project requirements before writing Parquet."
        ) from exc
    return len(dataframe)


def is_blank(value: object) -> bool:
    """Treat None and whitespace-only strings as missing report values."""
    return value is None or str(value).strip() == ""


def collect_doi_conflicts(jsonl_output: Path) -> list[dict[str, object]]:
    """Find normalized DOIs attached to more than one distinct OpenAlex ID."""
    doi_records: dict[str, list[dict[str, object]]] = defaultdict(list)

    if not jsonl_output.exists():
        return []

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

            openalex_id = openalex_work_id(work)
            doi = normalize_doi(work.get("doi"))
            if openalex_id is None or doi is None:
                continue

            doi_records[doi].append(
                {
                    "openalex_id": openalex_id,
                    "title": work.get("title") or work.get("display_name"),
                    "publication_year": work.get("publication_year"),
                }
            )

    conflicts: list[dict[str, object]] = []
    for doi, records in sorted(doi_records.items()):
        openalex_ids = sorted(
            {str(record["openalex_id"]) for record in records if record.get("openalex_id")}
        )
        if len(openalex_ids) <= 1:
            continue

        titles = unique_preserving_order(record.get("title") for record in records)
        years = unique_preserving_order(record.get("publication_year") for record in records)
        conflicts.append(
            {
                "doi": doi,
                "openalex_id_count": len(openalex_ids),
                "record_count": len(records),
                "openalex_ids": "; ".join(openalex_ids),
                "titles": "; ".join(titles),
                "publication_years": "; ".join(years),
            }
        )

    return conflicts


def unique_preserving_order(values: object) -> list[str]:
    """Return unique non-blank string values in first-seen order."""
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if is_blank(value):
            continue
        text = str(value).strip()
        if text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def write_doi_conflict_report(jsonl_output: Path, csv_output: Path) -> int:
    """Write a separate CSV for DOI conflicts and return the conflict count."""
    conflicts = collect_doi_conflicts(jsonl_output)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    with csv_output.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=DOI_CONFLICT_COLUMNS)
        writer.writeheader()
        writer.writerows(conflicts)
    return len(conflicts)


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
    retracted_record_count = 0
    doi_conflict_count = len(collect_doi_conflicts(jsonl_output))

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

                openalex_id = openalex_work_id(work)
                if openalex_id is not None:
                    openalex_ids[openalex_id] += 1

                doi = work.get("doi")
                if is_blank(doi):
                    missing_doi_count += 1
                else:
                    normalized_doi = normalize_doi(doi)
                    if normalized_doi is None:
                        missing_doi_count += 1
                    else:
                        dois[normalized_doi] += 1

                if is_blank(work.get("title")) and is_blank(work.get("display_name")):
                    missing_title_count += 1
                if work.get("is_retracted") is True:
                    retracted_record_count += 1

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
        "retracted_record_count": retracted_record_count,
        "doi_conflict_count": doi_conflict_count,
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
    print(f"  Retracted records: {report['retracted_record_count']:,}")
    print(f"  Duplicate OpenAlex IDs: {report['duplicate_openalex_ids']:,}")
    print(f"  Duplicate DOI count: {report['duplicate_doi_count']:,}")
    print(f"  DOI conflicts: {report['doi_conflict_count']:,}")
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
        "--parquet-output",
        type=Path,
        default=DEFAULT_PARQUET_OUTPUT,
        help=f"Cleaned Parquet output path. Default: {DEFAULT_PARQUET_OUTPUT}",
    )
    parser.add_argument(
        "--doi-conflicts-output",
        type=Path,
        default=DEFAULT_DOI_CONFLICTS_OUTPUT,
        help=f"Separate DOI conflict report path. Default: {DEFAULT_DOI_CONFLICTS_OUTPUT}",
    )
    parser.add_argument(
        "--pagination-output",
        type=Path,
        default=DEFAULT_PAGINATION_OUTPUT,
        help=f"Pagination audit JSON path. Default: {DEFAULT_PAGINATION_OUTPUT}",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Only save JSONL; do not save the flat CSV.",
    )
    parser.add_argument(
        "--no-parquet",
        action="store_true",
        help="Do not write the cleaned Parquet output.",
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
        default=DEFAULT_FROM_YEAR,
        help=f"First publication year. Default: {DEFAULT_FROM_YEAR}.",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=DEFAULT_TO_YEAR,
        help=f"Final publication year. Default: {DEFAULT_TO_YEAR}.",
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
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=DEFAULT_LOG_LEVEL,
        help=f"Logging verbosity. Default: {DEFAULT_LOG_LEVEL}.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional path to also write collection logs.",
    )
    args, _unknown = parser.parse_known_args()
    return args


def main() -> None:
    """Run collection, resume handling, output writing, and final reporting."""
    args = parse_args()
    setup_logging(
        getattr(args, "log_level", DEFAULT_LOG_LEVEL),
        getattr(args, "log_file", None),
    )
    progress_output = args.progress_output or default_progress_output(args.jsonl_output)
    pagination_output = getattr(
        args,
        "pagination_output",
        default_pagination_output(args.jsonl_output),
    )
    filters = build_filters(
        args.filter,
        from_year=args.from_year,
        to_year=args.to_year,
    )
    start_cursor = "*"
    existing_ids: set[str] = set()
    total = 0
    pagination_events = load_pagination_events(pagination_output) if args.resume else []
    logger.info(
        "Starting OpenAlex collection jsonl_output=%s csv_output=%s resume=%s filters=%s strict_lk_only=%s",
        args.jsonl_output,
        args.csv_output,
        args.resume,
        filters,
        args.strict_lk_only,
    )

    if args.resume:
        if not progress_output.exists():
            logger.error("Cannot resume because progress metadata is missing: %s", progress_output)
            raise SystemExit(
                f"Cannot resume: progress metadata not found: {progress_output}"
            )
        if not args.jsonl_output.exists():
            logger.error("Cannot resume because JSONL output is missing: %s", args.jsonl_output)
            raise SystemExit(f"Cannot resume: JSONL output not found: {args.jsonl_output}")

        progress = load_progress(progress_output)
        # A resumed job must match the original query shape to avoid mixing
        # incompatible result sets into the same raw and flat output files.
        if progress.get("filters") != filters:
            logger.error("Cannot resume because saved filters do not match current filters")
            raise SystemExit(
                "Cannot resume: current filters do not match saved progress filters."
            )
        if bool(progress.get("strict_lk_only", False)) != args.strict_lk_only:
            logger.error("Cannot resume because strict LK-only setting does not match")
            raise SystemExit(
                "Cannot resume: strict LK-only setting does not match saved progress."
            )

        start_cursor = progress.get("next_cursor")
        if start_cursor is None:
            logger.info("Collection already completed according to %s", progress_output)
            return

        existing_ids, total = read_existing_jsonl_state(args.jsonl_output)
        total = max(total, int(progress.get("records_saved", 0)))
        logger.info(
            "Resuming OpenAlex collection start_cursor=%s existing_records=%s",
            start_cursor,
            total,
        )
        if not args.no_csv:
            rebuild_csv_from_jsonl(args.jsonl_output, args.csv_output)
            logger.info("Rebuilt CSV from existing JSONL before resume: %s", args.csv_output)

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
        write_pagination_audit_report(
            pagination_output,
            pages=pagination_events,
            filters=filters,
            strict_lk_only=args.strict_lk_only,
            records_saved=total,
            records_skipped=0,
            next_cursor=start_cursor,
            status="started",
        )

    collector = OpenAlexCollector(email=args.email, api_key=args.api_key)
    csv_file = None
    writer = None
    output_mode = "a" if args.resume else "w"
    csv_mode = "a" if args.resume else "w"
    stop_requested = False
    records_skipped = 0
    last_next_cursor: str | None = start_cursor

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

                    openalex_id = openalex_work_id(work)
                    if openalex_id is None:
                        records_skipped += 1
                        continue
                    # If a crash happened after writing a record but before
                    # advancing the cursor, resume may see that record again.
                    if openalex_id in existing_ids:
                        records_skipped += 1
                        continue

                    jsonl_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                    if writer is not None:
                        writer.writerow(work_to_row(work))
                    existing_ids.add(openalex_id)
                    total += 1
                    saved_progress = (
                        f"{min(total / page.api_total_count * 100, 100.0):.1f}%"
                        if page.api_total_count
                        else "n/a"
                    )
                    logger.info(
                        "Saved Sri Lankan-affiliated work number=%s progress=%s api_total=%s",
                        f"{total:,}",
                        saved_progress,
                        f"{page.api_total_count:,}" if page.api_total_count else "n/a",
                    )

                jsonl_file.flush()
                if csv_file is not None:
                    csv_file.flush()

                last_next_cursor = page.cursor if stop_requested else page.next_cursor
                save_progress(
                    progress_output,
                    next_cursor=last_next_cursor,
                    records_saved=total,
                    filters=filters,
                    strict_lk_only=args.strict_lk_only,
                )
                pagination_events.append(
                    pagination_event_from_page(
                        page,
                        global_page_number=len(pagination_events) + 1,
                        records_saved=total,
                        records_skipped=records_skipped,
                    )
                )
                write_pagination_audit_report(
                    pagination_output,
                    pages=pagination_events,
                    filters=filters,
                    strict_lk_only=args.strict_lk_only,
                    records_saved=total,
                    records_skipped=records_skipped,
                    next_cursor=last_next_cursor,
                    status="partial" if last_next_cursor else "complete",
                )
                if stop_requested:
                    break
    finally:
        if csv_file is not None:
            csv_file.close()

    logger.info("Saved %s records to %s", f"{total:,}", args.jsonl_output)
    if not args.no_csv:
        logger.info("Saved flat CSV to %s", args.csv_output)
    if not getattr(args, "no_parquet", False):
        parquet_output = getattr(args, "parquet_output", DEFAULT_PARQUET_OUTPUT)
        parquet_count = write_parquet_from_jsonl(args.jsonl_output, parquet_output)
        logger.info("Saved %s records to %s", f"{parquet_count:,}", parquet_output)
    doi_conflicts_output = getattr(
        args,
        "doi_conflicts_output",
        DEFAULT_DOI_CONFLICTS_OUTPUT,
    )
    doi_conflict_count = write_doi_conflict_report(
        args.jsonl_output,
        doi_conflicts_output,
    )
    logger.info(
        "Saved %s DOI conflicts to %s",
        f"{doi_conflict_count:,}",
        doi_conflicts_output,
    )
    logger.info("Saved progress metadata to %s", progress_output)
    write_pagination_audit_report(
        pagination_output,
        pages=pagination_events,
        filters=filters,
        strict_lk_only=args.strict_lk_only,
        records_saved=total,
        records_skipped=records_skipped,
        next_cursor=last_next_cursor,
        status="partial" if last_next_cursor else "complete",
    )
    logger.info("Saved pagination audit to %s", pagination_output)
    print_collection_report(
        collect_quality_report(
            args.jsonl_output,
            records_skipped=records_skipped,
        )
    )


if __name__ == "__main__":
    main()
