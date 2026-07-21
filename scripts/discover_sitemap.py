"""Discover item URLs via sitemap for repositories where OAI-PMH is
unavailable or blocked.

Examples:
    python scripts/discover_sitemap.py --id kln --max-urls 20
    python scripts/discover_sitemap.py --url https://dl.ucsc.cmb.ac.lk/jspui --max-urls 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.repository_registry import load_registry
from src.collectors.sitemap_collector import SitemapCollector

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover item URLs via a repository's sitemap.")
    parser.add_argument("--id", default=None, help="Repository target id from data/config/repositories.json.")
    parser.add_argument("--url", default=None, help="Repository base URL. Overrides --id.")
    parser.add_argument("--max-urls", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout in seconds.")
    parser.add_argument("--output", type=Path, default=None, help="JSONL output path.")
    return parser.parse_args()


def resolve_repository_url(args: argparse.Namespace) -> tuple[str, str]:
    if args.url:
        return args.url, "custom"

    if not args.id:
        raise SystemExit("Provide --id <target> or --url <repository-url>.")

    target = next((t for t in load_registry() if t.id == args.id), None)
    if target is None:
        raise SystemExit(f"No repository target with id={args.id!r}.")
    if not target.repository_url:
        raise SystemExit(f"Target {args.id!r} has no repository_url on record.")

    return target.repository_url, target.id


def main() -> None:
    args = parse_args()
    repository_url, output_id = resolve_repository_url(args)

    collector = SitemapCollector(repository_url=repository_url, timeout=args.timeout)
    print(f"Discovering item URLs via sitemap for {repository_url}...")

    entrypoints = collector.find_sitemap_entrypoints()
    if not entrypoints:
        print("No sitemap_index.xml or sitemap.xml found at the repository root.")
        return
    print(f"Found sitemap entrypoint(s): {entrypoints}")

    item_urls = collector.iter_item_urls(max_urls=args.max_urls)
    print(f"Discovered {len(item_urls)} item URLs.")

    output_path = args.output or DEFAULT_RAW_DIR / output_id / "sitemap_urls.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        for url in item_urls:
            output_file.write(json.dumps({"url": url}, ensure_ascii=False) + "\n")

    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
