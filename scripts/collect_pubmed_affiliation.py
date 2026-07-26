"""Collect PubMed records by author affiliation.

Recovery route for institutions whose repository cannot be harvested
(kln). PubMed's ``[Affiliation]`` search is exact, so unlike the Crossref
route no local re-filtering is needed -- ``--match`` is available anyway
for queries broadened by hand.

The query lives in the registry as ``pubmed_affiliation_query``.

Examples:
    python scripts/collect_pubmed_affiliation.py --id kln
    python scripts/collect_pubmed_affiliation.py --id kln --max-records 50
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.collectors.pubmed_collector import PubmedCollector
from src.collectors.repository_registry import load_registry

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_EMAIL = "gishanchamith77@gmail.com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest PubMed records by affiliation.")
    parser.add_argument("--id", required=True, help="Registry id the results belong to, e.g. kln.")
    parser.add_argument(
        "--query",
        default=None,
        help="PubMed query. Default: the registry's pubmed_affiliation_query.",
    )
    parser.add_argument(
        "--match",
        default=None,
        help="Optional substring an affiliation string must contain to be kept.",
    )
    parser.add_argument(
        "--match-regex",
        default=None,
        help=(
            "Case-insensitive regex an affiliation must match. Takes precedence over "
            "--match. Needed where the institution's name is also a place name: "
            r"'Sabaragamuwa' alone matches a provincial health office and an 1895 "
            "colonial medical officer."
        ),
    )
    parser.add_argument("--max-records", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="NCBI contact address.")
    parser.add_argument("--api-key", default=None, help="Optional NCBI API key (higher rate limit).")
    parser.add_argument("--output", type=Path, default=None, help="JSONL output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    target = next((t for t in load_registry() if t.id == args.id), None)
    if target is None:
        raise SystemExit(f"No repository target with id={args.id!r}.")

    query = args.query or target.extra.get("pubmed_affiliation_query")
    if not query:
        raise SystemExit(
            f"No PubMed query for {args.id!r}. Pass --query or add "
            "pubmed_affiliation_query to the registry entry."
        )
    match = (args.match or target.extra.get("pubmed_affiliation_match") or "").lower()
    pattern_source = args.match_regex or target.extra.get("pubmed_affiliation_regex")
    pattern = re.compile(pattern_source, re.IGNORECASE) if pattern_source else None

    collector = PubmedCollector(email=args.email, api_key=args.api_key)
    output_path = args.output or DEFAULT_RAW_DIR / target.id / "pubmed_works.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")

    print(f"Harvesting {target.id} ({target.name}) from PubMed, query {query!r}")

    try:
        pmids = collector.search_ids(query, max_records=args.max_records)
        print(f"PubMed reports {len(pmids)} matching records; fetching full records...")

        kept = 0
        dropped = 0
        with partial_path.open("w", encoding="utf-8") as output_file:
            for record in collector.iter_records(pmids):
                affiliations = record.get("affiliations", [])
                if pattern is not None:
                    kept_by_filter = any(pattern.search(a) for a in affiliations)
                elif match:
                    kept_by_filter = any(match in a.lower() for a in affiliations)
                else:
                    kept_by_filter = True
                if not kept_by_filter:
                    dropped += 1
                    continue
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                kept += 1
                if kept % 500 == 0:
                    print(f"Collected {kept} records...")
    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        print(f"Partial harvest left in {partial_path}")
        raise SystemExit(1) from exc

    partial_path.replace(output_path)
    note = f" ({dropped} dropped as non-matching)" if dropped else ""
    print(f"Saved {kept} records to {output_path}{note}")


if __name__ == "__main__":
    main()
