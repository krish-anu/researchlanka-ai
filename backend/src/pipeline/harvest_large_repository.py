"""Resiliently harvest a large repository that hits the DSpace/Spring
pagination bug seen on several Sri Lankan instances: ListRecords works
fine up to a certain resumptionToken depth, then returns HTTP 500 with
"No converter for [class java.util.LinkedHashMap]" and never recovers,
even on retry (confirmed not transient -- same request 500s repeatedly).

Workaround: OAI-PMH's from/until date filters let us slice the same
ListRecords query into smaller date ranges, each starting its own
pagination from page 1. If a given date range still hits the bug
(because too many records fall inside it), split that range in half and
retry each half recursively until it succeeds or hits a 1-day minimum.

Examples:
    python scripts/collection/harvest_large_repository.py --id cmb
    python scripts/collection/harvest_large_repository.py --id ruh --start-year 2016 --end-year 2026
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.collectors.http import create_retry_session
from src.collectors.oai_pmh_collector import OaiPmhCollector, OaiPmhError
from src.collectors.repository_registry import load_registry

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_START_YEAR = 2016
DEFAULT_END_YEAR = 2026
MAX_SPLIT_DEPTH = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resiliently harvest a large/buggy OAI-PMH repository.")
    parser.add_argument("--id", required=True, help="Repository target id from data/config/repositories.json.")
    parser.add_argument(
        "--start-year",
        type=int,
        default=DEFAULT_START_YEAR,
        help=f"Earliest OAI-PMH datestamp year. Default: {DEFAULT_START_YEAR}.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=DEFAULT_END_YEAR,
        help=f"Latest OAI-PMH datestamp year. Default: {DEFAULT_END_YEAR}.",
    )
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds.")
    parser.add_argument("--output", type=Path, default=None, help="JSONL output path.")
    return parser.parse_args()


def harvest_range(
    collector: OaiPmhCollector,
    *,
    from_date: date,
    until_date: date,
    output_file,
    seen_ids: set[str],
    depth: int = 0,
) -> tuple[int, list[str]]:
    """Harvest one date range. Returns (records_written, failed_ranges_description)."""

    indent = "  " * depth
    range_label = f"{from_date.isoformat()}..{until_date.isoformat()}"

    try:
        count = 0
        for record in collector.iter_records(
            from_date=from_date.isoformat(), until_date=until_date.isoformat()
        ):
            record_id = record.get("oai_identifier")
            if record_id and record_id in seen_ids:
                continue
            if record_id:
                seen_ids.add(record_id)
            output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
        print(f"{indent}{range_label}: {count} records")
        return count, []
    except OaiPmhError as exc:
        if exc.code == "noRecordsMatch":
            # Genuinely nothing in this slice -- not the pagination bug,
            # don't split further and don't count it as a failure.
            print(f"{indent}{range_label}: 0 records (none in range)")
            return 0, []
        error = exc
    except requests.RequestException as exc:
        error = exc

    if from_date >= until_date or depth >= MAX_SPLIT_DEPTH:
        print(f"{indent}{range_label}: FAILED, giving up ({error})")
        return 0, [range_label]

    span_days = (until_date - from_date).days
    midpoint = from_date + timedelta(days=span_days // 2)
    print(f"{indent}{range_label}: hit server error at this granularity, splitting at {midpoint.isoformat()}")

    count_a, failed_a = harvest_range(
        collector, from_date=from_date, until_date=midpoint, output_file=output_file,
        seen_ids=seen_ids, depth=depth + 1,
    )
    next_start = midpoint + timedelta(days=1)
    if next_start > until_date:
        return count_a, failed_a
    count_b, failed_b = harvest_range(
        collector, from_date=next_start, until_date=until_date, output_file=output_file,
        seen_ids=seen_ids, depth=depth + 1,
    )
    return count_a + count_b, failed_a + failed_b


def main() -> None:
    args = parse_args()

    target = next((t for t in load_registry() if t.id == args.id), None)
    if target is None:
        raise SystemExit(f"No repository target with id={args.id!r}.")
    if not target.oai_endpoint:
        raise SystemExit(f"Target {args.id!r} has no OAI endpoint on record.")

    verify_ssl = not target.extra.get("ssl_verify_failed", False)
    collector = OaiPmhCollector(
        base_url=target.oai_endpoint,
        timeout=args.timeout,
        verify_ssl=verify_ssl,
        session=create_retry_session(total_retries=1, backoff_factor=0.5),
    )

    output_path = args.output or DEFAULT_RAW_DIR / target.id / "oai_dc.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    from_date = date(args.start_year, 1, 1)
    until_date = date(args.end_year, 12, 31)

    print(f"Harvesting {target.id} ({target.name}) from {from_date} to {until_date} -> {output_path}")

    temp_output_path = output_path.with_name(f"{output_path.name}.tmp")

    seen_ids: set[str] = set()
    total = 0
    failed_ranges: list[str] = []
    with temp_output_path.open("w", encoding="utf-8") as output_file:
        for year in range(args.start_year, args.end_year + 1):
            year_from = max(from_date, date(year, 1, 1))
            year_until = min(until_date, date(year, 12, 31))
            count, year_failed_ranges = harvest_range(
                collector,
                from_date=year_from,
                until_date=year_until,
                output_file=output_file,
                seen_ids=seen_ids,
            )
            total += count
            failed_ranges.extend(year_failed_ranges)

    if total > 0 or not output_path.exists():
        temp_output_path.replace(output_path)
        print(f"\nSaved {total} unique records to {output_path}")
    else:
        temp_output_path.unlink()
        print(f"\nCollected 0 records; kept existing output at {output_path}")

    if failed_ranges:
        print(f"{len(failed_ranges)} date range(s) could not be harvested even at minimum granularity:")
        for r in failed_ranges:
            print(f"  - {r}")


if __name__ == "__main__":
    main()
