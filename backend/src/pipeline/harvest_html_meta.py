"""Harvest a legacy DSpace repository by crawling item pages' meta tags.

Last-resort route for repositories with a dead OAI index, no REST API,
and no sitemap (currently the two Jaffna instances -- see registry).

Examples:
    python scripts/collection/harvest_html_meta.py --id jfn_research --max-records 20
    python scripts/collection/harvest_html_meta.py --id jfn_research
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

from src.collectors.html_meta_collector import HtmlMetaCollector
from src.collectors.repository_registry import load_registry

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest item metadata from DSpace HTML pages.")
    parser.add_argument("--id", required=True, help="Repository target id from data/config/repositories.json.")
    parser.add_argument("--max-records", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests in seconds. Default: 0.5")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds.")
    parser.add_argument("--output", type=Path, default=None, help="JSONL output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    target = next((t for t in load_registry() if t.id == args.id), None)
    if target is None:
        raise SystemExit(f"No repository target with id={args.id!r}.")

    base_url = target.extra.get("browse_url") or target.repository_url
    if not base_url:
        raise SystemExit(f"Target {args.id!r} has no browse_url/repository_url on record.")

    collector = HtmlMetaCollector(
        base_url=base_url,
        timeout=args.timeout,
        delay=args.delay,
    )

    output_path = args.output or DEFAULT_RAW_DIR / target.id / "html_meta.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Harvesting {target.id} ({target.name}) via HTML meta tags -> {output_path}")

    total = 0
    with output_path.open("w", encoding="utf-8") as output_file:
        for item in collector.iter_items(max_records=args.max_records):
            output_file.write(json.dumps(item, ensure_ascii=False) + "\n")
            total += 1
            if total % 200 == 0:
                print(f"Collected {total} items...")

    print(f"Saved {total} items to {output_path}")


if __name__ == "__main__":
    main()
