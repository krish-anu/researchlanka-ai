"""Harvest an OAI-PMH repository one set at a time.

This is useful for DSpace instances where global ListRecords pagination is
broken but smaller set-scoped ListRecords calls still work.

Examples:
    python scripts/collection/harvest_oai_by_set.py --id seu
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.collectors.schema_mapping import has_oai_dc_doi
from src.collectors.oai_pmh_collector import OaiPmhCollector, OaiPmhError
from src.collectors.repository_registry import load_registry

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest OAI-PMH records set by set.")
    parser.add_argument("--id", required=True, help="Repository target id from data/config/repositories.json.")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds.")
    parser.add_argument("--max-sets", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--output", type=Path, default=None, help="JSONL output path.")
    return parser.parse_args()


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
    )

    output_path = args.output or DEFAULT_RAW_DIR / target.id / "oai_dc.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Listing OAI sets for {target.id} ({target.name})")
    set_specs = list(collector.iter_set_specs())
    if args.max_sets is not None:
        set_specs = set_specs[: args.max_sets]
    print(f"Harvesting {len(set_specs)} sets -> {output_path}")

    seen_ids: set[str] = set()
    total = 0
    skipped_missing_doi = 0
    failed_sets: list[str] = []

    with output_path.open("w", encoding="utf-8") as output_file:
        for index, set_spec in enumerate(set_specs, start=1):
            set_count = 0
            try:
                for record in collector.iter_records(set_spec=set_spec):
                    record_id = record.get("oai_identifier")
                    if record_id and record_id in seen_ids:
                        continue
                    if record_id:
                        seen_ids.add(record_id)
                    if not has_oai_dc_doi(record):
                        skipped_missing_doi += 1
                        continue
                    output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                    set_count += 1
                    total += 1
            except OaiPmhError as exc:
                if exc.code == "noRecordsMatch":
                    print(f"[{index}/{len(set_specs)}] {set_spec}: 0 records")
                    continue
                failed_sets.append(set_spec)
                print(f"[{index}/{len(set_specs)}] {set_spec}: failed ({exc})")
                continue
            except requests.RequestException as exc:
                failed_sets.append(set_spec)
                print(f"[{index}/{len(set_specs)}] {set_spec}: failed ({exc})")
                continue

            print(f"[{index}/{len(set_specs)}] {set_spec}: {set_count} new records")

    print(f"\nSaved {total} unique records to {output_path}")
    if skipped_missing_doi:
        print(f"Skipped {skipped_missing_doi} records without a valid DOI.")
    if failed_sets:
        print(f"{len(failed_sets)} set(s) failed:")
        for set_spec in failed_sets:
            print(f"  - {set_spec}")

if __name__ == "__main__":
    main()
