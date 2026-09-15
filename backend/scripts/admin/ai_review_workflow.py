#!/usr/bin/env python
"""Operate the ResearchLanka AI review workflow."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.services.ai_review import (
    assign_initial_pending,
    backfill_review_records,
    parse_reviewers,
    validate_final_dataset,
    with_connection,
    write_csv_snapshot,
)
from src.api.services.ai_review_sheets import reconcile_sheet, run_sync_worker_once


def cmd_backfill(_args: argparse.Namespace) -> dict:
    return with_connection(
        lambda connection: {
            "backfill": backfill_review_records(connection),
            "assignment": assign_initial_pending(connection, parse_reviewers()),
        }
    )


def cmd_assign(_args: argparse.Namespace) -> dict:
    return with_connection(
        lambda connection: assign_initial_pending(connection, parse_reviewers())
    )


def cmd_reconcile_sheets(_args: argparse.Namespace) -> dict:
    return with_connection(reconcile_sheet)


def cmd_validate(_args: argparse.Namespace) -> dict:
    return with_connection(validate_final_dataset)


def cmd_snapshot(args: argparse.Namespace) -> dict:
    return with_connection(lambda connection: write_csv_snapshot(connection, Path(args.output_dir)))


def cmd_worker(args: argparse.Namespace) -> dict:
    if args.once:
        return with_connection(lambda connection: run_sync_worker_once(connection, limit=args.limit))
    totals = {"claimed": 0, "succeeded": 0, "failed": 0}
    while True:
        result = with_connection(lambda connection: run_sync_worker_once(connection, limit=args.limit))
        for key in totals:
            totals[key] += int(result.get(key) or 0)
        print(json.dumps(result, sort_keys=True), flush=True)
        time.sleep(args.poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    backfill = sub.add_parser("backfill", help="Idempotently create review records and initial assignments.")
    backfill.set_defaults(func=cmd_backfill)

    assign = sub.add_parser("assign", help="Assign unassigned pending reviews to configured reviewers.")
    assign.set_defaults(func=cmd_assign)

    reconcile = sub.add_parser("reconcile-sheets", help="Rewrite worksheets from current PostgreSQL state.")
    reconcile.set_defaults(func=cmd_reconcile_sheets)

    validate = sub.add_parser("validate-final-dataset", help="Report final dataset completeness issues.")
    validate.set_defaults(func=cmd_validate)

    snapshot = sub.add_parser("snapshot", help="Write a dated CSV snapshot and Dataset Guide.")
    snapshot.add_argument("--output-dir", default="outputs/ai-review-snapshots")
    snapshot.set_defaults(func=cmd_snapshot)

    worker = sub.add_parser("worker", help="Run the PostgreSQL-backed Sheets sync worker.")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--limit", type=int, default=10)
    worker.add_argument("--poll-seconds", type=int, default=30)
    worker.set_defaults(func=cmd_worker)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
