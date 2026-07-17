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
    build_filters,
    work_to_row,
)


DEFAULT_OUTPUT_DIR = Path("/kaggle/working")
DEFAULT_JSONL_OUTPUT = DEFAULT_OUTPUT_DIR / "openalex_sri_lanka_works.jsonl"
DEFAULT_CSV_OUTPUT = DEFAULT_OUTPUT_DIR / "openalex_sri_lanka_works.csv"


def default_progress_output(jsonl_output: Path) -> Path:
    return jsonl_output.with_suffix(f"{jsonl_output.suffix}.progress.json")


def load_progress(path: Path) -> dict:
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
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    progress = {
        "next_cursor": next_cursor,
        "records_saved": records_saved,
        "filters": filters,
    }
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as progress_file:
        json.dump(progress, progress_file, indent=2)
        progress_file.write("\n")
    temp_path.replace(path)


def read_existing_jsonl_state(path: Path) -> tuple[set[str], int]:
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
        if progress.get("filters") != filters:
            raise SystemExit(
                "Cannot resume: current filters do not match saved progress filters."
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
        save_progress(
            progress_output,
            next_cursor=start_cursor,
            records_saved=total,
            filters=filters,
        )

    collector = OpenAlexCollector(email=args.email, api_key=args.api_key)
    csv_file = None
    writer = None
    output_mode = "a" if args.resume else "w"
    csv_mode = "a" if args.resume else "w"
    stop_requested = False

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
            )
            for page in pages:
                for work in page.works:
                    if args.max_records is not None and total >= args.max_records:
                        stop_requested = True
                        break

                    openalex_id = str(work.get("id", ""))
                    if args.resume and openalex_id and openalex_id in existing_ids:
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


if __name__ == "__main__":
    main()
