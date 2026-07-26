"""Harvest items from a DSpace 7/8 repository via its REST API.

Use for instances whose OAI-PMH index is empty/stale but whose public
discover endpoint serves real content (pdn, nsf, busl -- see registry
notes).

Examples:
    python scripts/harvest_dspace_rest.py --id pdn
    python scripts/harvest_dspace_rest.py --id nsf --max-records 200
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.collectors.dspace_rest_collector import DspaceRestCollector
from src.collectors.repository_registry import load_registry

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest a DSpace 7/8 repository via REST.")
    parser.add_argument("--id", required=True, help="Repository target id from data/config/repositories.json.")
    parser.add_argument("--max-records", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--page-size", type=int, default=100, help="Items per request. Default: 100")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds.")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Seconds between pages. Raise it for hosts that drop connections (uwu).",
    )
    parser.add_argument("--output", type=Path, default=None, help="JSONL output path.")
    parser.add_argument(
        "--embed-bitstreams",
        action="store_true",
        help="Also collect the file listing (PDF and extracted-text URLs). Slower, larger responses.",
    )
    parser.add_argument(
        "--no-embeds",
        action="store_true",
        help="Metadata only: skip the owning collection (department) embed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    target = next((t for t in load_registry() if t.id == args.id), None)
    if target is None:
        raise SystemExit(f"No repository target with id={args.id!r}.")
    if not target.rest_api_endpoint:
        raise SystemExit(f"Target {args.id!r} has no rest_api_endpoint on record.")

    verify_ssl = not target.extra.get("ssl_verify_failed", False)

    embeds: tuple[str, ...] = () if args.no_embeds else ("owningCollection",)
    if args.embed_bitstreams:
        embeds = embeds + ("bundles/bitstreams",)

    collector = DspaceRestCollector(
        api_base_url=target.rest_api_endpoint,
        timeout=args.timeout,
        page_size=args.page_size,
        delay=args.delay,
        verify_ssl=verify_ssl,
        embeds=embeds,
    )

    output_path = args.output or DEFAULT_RAW_DIR / target.id / "rest_items.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        total_available = collector.total_items()
    except requests.RequestException as exc:
        raise SystemExit(f"Could not reach REST API: {exc}") from exc

    print(f"Harvesting {target.id} ({target.name}) via REST -> {output_path}")
    print(f"Repository reports {total_available} total items.")

    # Harvest into a sibling .partial file and swap it in only on success.
    # These hosts drop connections mid-run (uwu did so at item 6,800 and
    # again at item 0), and writing straight to the final path meant a
    # failed retry truncated a good previous harvest to nothing.
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")

    total = 0
    try:
        with partial_path.open("w", encoding="utf-8") as output_file:
            for item in collector.iter_items(max_records=args.max_records):
                output_file.write(json.dumps(item, ensure_ascii=False) + "\n")
                total += 1
                if total % 500 == 0:
                    print(f"Collected {total} items...")
    except requests.RequestException as exc:
        print(f"Request failed after {total} items: {exc}")
        print(f"Partial harvest left in {partial_path}")
        if output_path.exists():
            print(f"Previous harvest at {output_path} left untouched.")
        raise SystemExit(1) from exc

    partial_path.replace(output_path)
    print(f"Saved {total} items to {output_path}")


if __name__ == "__main__":
    main()
