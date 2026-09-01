"""Large-scale OAI-PMH harvest across every confirmed-live repository target.

Runs the same collection as harvest_oai.py, but for every harvestable
target in the registry in one pass, and keeps going if one institution
fails (e.g. NSF's currently-empty OAI index) instead of aborting the
whole run. Writes one JSONL file per institution plus a combined summary
report.

Examples:
    python scripts/collection/harvest_all.py --max-records-per-target 500
    python scripts/collection/harvest_all.py --phase phase_1 --max-records-per-target 200
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.collectors.oai_pmh_collector import OaiPmhCollector, OaiPmhError
from src.collectors.repository_registry import harvestable_targets, load_registry

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "reports"
DEFAULT_MAX_RECORDS_PER_TARGET = 2000
DEFAULT_START_YEAR = 2016
DEFAULT_END_YEAR = date.today().year


@dataclass
class HarvestOutcome:
    id: str
    name: str
    record_count: int = 0
    status: str = "ok"  # ok | empty | error | skipped_existing
    error: str | None = None
    output_path: str | None = None


def parse_id_filter(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip().casefold() for part in value.split(",") if part.strip()}


def filter_targets(targets, *, include_ids: set[str], exclude_ids: set[str]):
    return [
        target
        for target in targets
        if (not include_ids or target.id.casefold() in include_ids)
        and target.id.casefold() not in exclude_ids
    ]


def raw_oai_output_path(target) -> Path:
    return DEFAULT_RAW_DIR / target.id / "oai_dc.jsonl"


def skip_existing_outcome(target) -> HarvestOutcome | None:
    output_path = raw_oai_output_path(target)
    if not output_path.exists():
        return None
    with output_path.open(encoding="utf-8") as file:
        existing_records = sum(1 for line in file if line.strip())
    if existing_records <= 0:
        return None
    return HarvestOutcome(
        id=target.id,
        name=target.name,
        record_count=existing_records,
        status="skipped_existing",
        error="Existing raw JSONL reused.",
        output_path=str(output_path),
    )


def harvest_one(
    target,
    *,
    max_records: int | None,
    timeout: int,
    from_date: str | None = None,
    until_date: str | None = None,
    progress_callback: Callable[[int], None] | None = None,
    progress_interval: int = 500,
) -> HarvestOutcome:
    output_path = DEFAULT_RAW_DIR / target.id / "oai_dc.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    verify_ssl = not target.extra.get("ssl_verify_failed", False)
    collector = OaiPmhCollector(base_url=target.oai_endpoint, timeout=timeout, verify_ssl=verify_ssl)
    total = 0

    try:
        with output_path.open("w", encoding="utf-8") as output_file:
            for record in collector.iter_records(
                max_records=max_records,
                from_date=from_date,
                until_date=until_date,
            ):
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += 1
                if progress_callback and progress_interval > 0 and total % progress_interval == 0:
                    progress_callback(total)
    except OaiPmhError as exc:
        # e.g. noRecordsMatch: a live, reachable endpoint with nothing to give
        # right now. Not a crash -- record it and move on to the next target.
        return HarvestOutcome(
            id=target.id,
            name=target.name,
            record_count=total,
            status="empty" if total == 0 else "ok",
            error=str(exc),
            output_path=str(output_path),
        )
    except requests.RequestException as exc:
        return HarvestOutcome(
            id=target.id,
            name=target.name,
            record_count=total,
            status="error",
            error=str(exc),
            output_path=str(output_path),
        )

    return HarvestOutcome(
        id=target.id,
        name=target.name,
        record_count=total,
        status="ok" if total > 0 else "empty",
        output_path=str(output_path),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest every confirmed-live repository target.")
    parser.add_argument("--phase", default=None, help="Only harvest targets in this phase, e.g. phase_1.")
    parser.add_argument(
        "--include-ids",
        default=None,
        help="Comma-separated target ids to harvest, e.g. uom,cmb,sliit.",
    )
    parser.add_argument(
        "--exclude-ids",
        default=None,
        help="Comma-separated target ids to skip, e.g. seu,sltc,ruh.",
    )
    parser.add_argument(
        "--max-records-per-target",
        type=int,
        default=DEFAULT_MAX_RECORDS_PER_TARGET,
        help=f"Safety cap per institution. Default: {DEFAULT_MAX_RECORDS_PER_TARGET}. Use 0 for no cap (full harvest).",
    )
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between institutions, in seconds.")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Reuse non-empty data/raw/<id>/oai_dc.jsonl files instead of re-harvesting them.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Harvest different repositories in parallel. Default: 1.",
    )
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    max_records = None if args.max_records_per_target == 0 else args.max_records_per_target
    start_year = max(args.start_year, DEFAULT_START_YEAR)
    end_year = min(args.end_year, DEFAULT_END_YEAR)
    from_date = f"{start_year}-01-01"
    until_date = f"{end_year}-12-31"
    include_ids = parse_id_filter(args.include_ids)
    exclude_ids = parse_id_filter(args.exclude_ids)

    targets = filter_targets(
        harvestable_targets(load_registry(), phase=args.phase),
        include_ids=include_ids,
        exclude_ids=exclude_ids,
    )
    if not targets:
        print("No harvestable targets found.")
        return

    outcomes: list[HarvestOutcome] = []
    workers = min(max(args.workers, 1), len(targets))

    def harvest_or_skip(target) -> HarvestOutcome:
        if args.skip_existing:
            existing_outcome = skip_existing_outcome(target)
            if existing_outcome is not None:
                return existing_outcome
        return harvest_one(
            target,
            max_records=max_records,
            timeout=args.timeout,
            from_date=from_date,
            until_date=until_date,
        )

    if workers == 1:
        for i, target in enumerate(targets):
            print(f"[{i + 1}/{len(targets)}] Harvesting {target.id} ({target.name})...")
            outcome = harvest_or_skip(target)
            outcomes.append(outcome)
            print(f"  -> {outcome.status}: {outcome.record_count} records" + (f" ({outcome.error})" if outcome.error else ""))
            if i < len(targets) - 1:
                time.sleep(args.delay)
    else:
        print(f"Harvesting {len(targets)} targets with {workers} workers...")
        outcomes_by_id: dict[str, HarvestOutcome] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_by_target = {
                executor.submit(harvest_or_skip, target): target for target in targets
            }
            for future in as_completed(future_by_target):
                target = future_by_target[future]
                try:
                    outcome = future.result()
                except Exception as exc:  # pragma: no cover - defensive guard
                    outcome = HarvestOutcome(
                        id=target.id,
                        name=target.name,
                        record_count=0,
                        status="error",
                        error=str(exc),
                        output_path=str(raw_oai_output_path(target)),
                    )
                outcomes_by_id[target.id] = outcome
                print(
                    f"  -> {target.id}: {outcome.status}: {outcome.record_count} records"
                    + (f" ({outcome.error})" if outcome.error else "")
                )
        outcomes = [
            outcomes_by_id[target.id]
            for target in targets
            if target.id in outcomes_by_id
        ]

    print(f"\n{'ID':<16}{'Status':<18}{'Records':<10}Notes")
    print("-" * 78)
    total_records = 0
    for outcome in outcomes:
        total_records += outcome.record_count
        note = (outcome.error or "")[:50]
        print(f"{outcome.id:<16}{outcome.status:<18}{outcome.record_count:<10}{note}")

    yielded_count = sum(1 for o in outcomes if o.status in {"ok", "skipped_existing"})
    skipped_count = sum(1 for o in outcomes if o.status == "skipped_existing")
    print(
        f"\n{yielded_count}/{len(outcomes)} targets yielded or reused records. "
        f"{total_records} total records available."
    )
    if skipped_count:
        print(f"{skipped_count} target(s) reused existing raw JSONL files.")

    DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = DEFAULT_REPORT_DIR / f"harvest_summary_{timestamp}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_records_per_target": max_records,
        "from_date": from_date,
        "until_date": until_date,
        "target_count": len(outcomes),
        "total_records": total_records,
        "results": [asdict(o) for o in outcomes],
    }
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved harvest summary to {report_path}")


if __name__ == "__main__":
    main()
