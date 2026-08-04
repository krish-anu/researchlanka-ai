"""Harvest publication records from a Sri Lankan repository via OAI-PMH.

Examples:
    python scripts/collection/harvest_oai.py --list
    python scripts/collection/harvest_oai.py --id nsf --max-records 20
    python scripts/collection/harvest_oai.py --id uom --set col_123456789_1
    python scripts/collection/harvest_oai.py --endpoint https://dl.nsf.gov.lk/server/oai/request --output data/raw/nsf/oai_dc.jsonl
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

from src.collectors.oai_pmh_collector import OaiPmhCollector, OaiPmhError
from src.collectors.repository_registry import harvestable_targets, load_registry

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest records from an OAI-PMH endpoint.")
    parser.add_argument("--id", default=None, help="Repository target id from data/config/repositories.json.")
    parser.add_argument("--endpoint", default=None, help="OAI-PMH base URL. Overrides --id.")
    parser.add_argument("--list", action="store_true", help="List harvestable target ids and exit.")
    parser.add_argument("--set", dest="set_spec", default=None, help="Optional OAI setSpec to restrict harvesting.")
    parser.add_argument("--from", dest="from_date", default=None, help="Optional OAI 'from' date (YYYY-MM-DD).")
    parser.add_argument("--until", dest="until_date", default=None, help="Optional OAI 'until' date (YYYY-MM-DD).")
    parser.add_argument("--metadata-prefix", default="oai_dc", help="Metadata format to request. Default: oai_dc")
    parser.add_argument("--max-records", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds.")
    parser.add_argument("--output", type=Path, default=None, help="JSONL output path.")
    return parser.parse_args()


def list_targets() -> None:
    targets = harvestable_targets(load_registry())
    print(f"{'id':<16}{'phase':<12}{'name'}")
    print("-" * 70)
    for target in targets:
        print(f"{target.id:<16}{target.phase:<12}{target.name}")


def resolve_endpoint(args: argparse.Namespace) -> tuple[str, str, bool]:
    """Return (endpoint, output_id, verify_ssl) for either --endpoint or --id."""

    if args.endpoint:
        return args.endpoint, "custom", True

    if not args.id:
        raise SystemExit("Provide --id <target> or --endpoint <url> (see --list).")

    target = next((t for t in load_registry() if t.id == args.id), None)
    if target is None:
        raise SystemExit(f"No repository target with id={args.id!r}. Use --list to see options.")
    if not target.oai_endpoint:
        raise SystemExit(f"Target {args.id!r} has no OAI endpoint on record.")

    verify_ssl = not target.extra.get("ssl_verify_failed", False)
    return target.oai_endpoint, target.id, verify_ssl


def main() -> None:
    args = parse_args()

    if args.list:
        list_targets()
        return

    endpoint, output_id, verify_ssl = resolve_endpoint(args)
    output_path = args.output or DEFAULT_RAW_DIR / output_id / "oai_dc.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not verify_ssl:
        print(f"Note: {output_id} has a known-broken TLS certificate; disabling certificate verification for this host only.")

    collector = OaiPmhCollector(
        base_url=endpoint,
        verify_ssl=verify_ssl,
        metadata_prefix=args.metadata_prefix,
        timeout=args.timeout,
    )

    print(f"Harvesting {endpoint} -> {output_path}")

    total = 0
    try:
        with output_path.open("w", encoding="utf-8") as output_file:
            for record in collector.iter_records(
                set_spec=args.set_spec,
                from_date=args.from_date,
                until_date=args.until_date,
                max_records=args.max_records,
            ):
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += 1
                if total % 50 == 0:
                    print(f"Collected {total} records...")
    except OaiPmhError as exc:
        print(f"OAI-PMH error after {total} records: {exc}")
        print(f"Saved {total} records collected before the error to {output_path}")
        raise SystemExit(1) from exc
    except requests.RequestException as exc:
        print(f"Request failed after {total} records: {exc}")
        print(f"Saved {total} records collected before the error to {output_path}")
        raise SystemExit(1) from exc

    print(f"Saved {total} records to {output_path}")


if __name__ == "__main__":
    main()
