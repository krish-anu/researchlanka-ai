"""Collect SLJOL (Sri Lanka Journals Online) article metadata via
Crossref, using the platform's DOI prefix 10.4038.

sljol.info itself blocks scripted access (WAF); Crossref's public API is
the sanctioned route to the same bibliographic metadata. See
docs/DATA_COLLECTION.md and the registry notes for background.

Examples:
    python scripts/collect_sljol.py --email you@example.com --max-records 50
    python scripts/collect_sljol.py --email you@example.com
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.collectors.crossref_collector import CrossrefPrefixCollector

SLJOL_DOI_PREFIX = "10.4038"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "sljol" / "crossref_works.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect SLJOL metadata via Crossref (prefix 10.4038).")
    parser.add_argument("--email", default=None, help="Email for the Crossref polite pool (recommended).")
    parser.add_argument("--max-records", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--rows", type=int, default=500, help="Records per request (max 1000). Default: 500")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help=f"JSONL output path. Default: {DEFAULT_OUTPUT_PATH}")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    collector = CrossrefPrefixCollector(
        prefix=SLJOL_DOI_PREFIX,
        email=args.email,
        rows=args.rows,
    )

    try:
        total_available = collector.total_works()
    except requests.RequestException as exc:
        raise SystemExit(f"Could not reach Crossref: {exc}") from exc

    print(f"Crossref reports {total_available} works under prefix {SLJOL_DOI_PREFIX}.")
    print(f"Collecting -> {args.output}")

    total = 0
    try:
        with args.output.open("w", encoding="utf-8") as output_file:
            for work in collector.iter_works(max_records=args.max_records):
                output_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                total += 1
                if total % 1000 == 0:
                    print(f"Collected {total} works...")
    except requests.RequestException as exc:
        print(f"Request failed after {total} works: {exc}")
        print(f"Saved {total} works collected before the error to {args.output}")
        raise SystemExit(1) from exc

    print(f"Saved {total} works to {args.output}")


if __name__ == "__main__":
    main()
