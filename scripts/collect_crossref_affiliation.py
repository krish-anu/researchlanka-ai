"""Collect Crossref works by author affiliation.

Recovery route for institutions whose own repository cannot be harvested
(kln is blocked by a WAF; sjp/kdu/wyb are down). Crossref indexes the
affiliation strings publishers deposit, so an institution's journal and
proceedings output is reachable even when its repository is not.

Crossref's ``query.affiliation`` is a fuzzy full-text match, so every
work is re-checked locally against ``--match`` and dropped unless one of
its affiliation strings really contains it. Without that filter a query
like "University of Kelaniya" matches on "University" alone and returns
millions of unrelated works.

The query lives in the registry as ``crossref_affiliation_query`` with an
optional ``crossref_affiliation_match`` override for the local check.

Examples:
    python scripts/collect_crossref_affiliation.py --id kln
    python scripts/collect_crossref_affiliation.py --id kln --max-records 200
    python scripts/collect_crossref_affiliation.py --query Kelaniya --match Kelaniya --id kln
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.collectors.crossref_collector import CrossrefCollector
from src.collectors.repository_registry import load_registry

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_EMAIL = "gishanchamith77@gmail.com"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Harvest Crossref works by affiliation.")
    parser.add_argument("--id", required=True, help="Registry id the results belong to, e.g. kln.")
    parser.add_argument(
        "--query",
        default=None,
        help="Crossref affiliation query. Default: the registry's crossref_affiliation_query.",
    )
    parser.add_argument(
        "--match",
        default=None,
        help="Substring every kept record must have in an affiliation string. Default: the query.",
    )
    parser.add_argument("--max-records", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--rows", type=int, default=100, help="Records per request. Default: 100")
    parser.add_argument(
        "--all-types",
        action="store_true",
        help="Keep every work type, not just journal/proceedings articles and preprints.",
    )
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Crossref polite-pool contact.")
    parser.add_argument("--output", type=Path, default=None, help="JSONL output path.")
    return parser.parse_args()


def affiliation_strings(work: dict) -> list[str]:
    return [
        affiliation.get("name", "")
        for author in (work.get("author") or [])
        for affiliation in (author.get("affiliation") or [])
        if isinstance(affiliation, dict)
    ]


def main() -> None:
    args = parse_args()

    target = next((t for t in load_registry() if t.id == args.id), None)
    if target is None:
        raise SystemExit(f"No repository target with id={args.id!r}.")

    query = args.query or target.extra.get("crossref_affiliation_query")
    if not query:
        raise SystemExit(
            f"No affiliation query for {args.id!r}. Pass --query or add "
            "crossref_affiliation_query to the registry entry."
        )
    match = (args.match or target.extra.get("crossref_affiliation_match") or query).lower()

    collector = CrossrefCollector(email=args.email)
    if args.all_types:
        collector.keep_types = None

    output_path = args.output or DEFAULT_RAW_DIR / target.id / "crossref_affiliation.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")

    print(f"Harvesting {target.id} ({target.name}) from Crossref, affiliation query {query!r}")
    print(f"Keeping only works with {match!r} in an affiliation string -> {output_path}")

    kept = 0
    dropped = 0
    try:
        with partial_path.open("w", encoding="utf-8") as output_file:
            for work in collector.iter_works(affiliation_query=query, rows=args.rows):
                if not any(match in name.lower() for name in affiliation_strings(work)):
                    dropped += 1
                    continue
                output_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                kept += 1
                if kept % 200 == 0:
                    print(f"Kept {kept} works ({dropped} dropped as non-matching)...")
                if args.max_records is not None and kept >= args.max_records:
                    break
    except requests.RequestException as exc:
        print(f"Request failed after {kept} kept works: {exc}")
        print(f"Partial harvest left in {partial_path}")
        raise SystemExit(1) from exc

    partial_path.replace(output_path)
    print(f"Saved {kept} works to {output_path} ({dropped} dropped as non-matching)")


if __name__ == "__main__":
    main()
