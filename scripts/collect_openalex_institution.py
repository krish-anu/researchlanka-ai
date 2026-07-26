"""Collect every OpenAlex work affiliated with one registry institution.

Complements the repository harvest rather than replacing it: institutional
repositories mostly hold theses, conference papers and locally published
work, while OpenAlex holds the DOI-bearing journal output (with citation
counts, OA status and topics) that the repositories never deposited. The
two populations overlap only partly -- see scripts/compare_repository_openalex.py.

The institution's OpenAlex id lives in the registry as
``openalex_institution_id`` (data/config/repositories.json). The filter
uses ``lineage`` rather than ``id`` so that faculty/hospital sub-institutions
recorded under the university are included.

Examples:
    python scripts/collect_openalex_institution.py --id cmb
    python scripts/collect_openalex_institution.py --id pdn --max-records 500
    python scripts/collect_openalex_institution.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.collectors.openalex_collector import OpenAlexCollector
from src.collectors.repository_registry import load_registry

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_EMAIL = "gishanchamith77@gmail.com"
PER_PAGE = 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Harvest all OpenAlex works for a registry institution."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", default=None, help="Registry id, e.g. cmb.")
    group.add_argument(
        "--all",
        action="store_true",
        help="Every registry entry that has an openalex_institution_id.",
    )
    parser.add_argument("--max-records", type=int, default=None, help="Safety limit for testing.")
    parser.add_argument("--from-year", type=int, default=None, help="Earliest publication year.")
    parser.add_argument("--to-year", type=int, default=None, help="Latest publication year.")
    parser.add_argument(
        "--email",
        default=DEFAULT_EMAIL,
        help="Contact email for the OpenAlex polite pool.",
    )
    return parser.parse_args()


def collect_one(
    target,
    *,
    email: str,
    max_records: int | None = None,
    from_year: int | None = None,
    to_year: int | None = None,
) -> int:
    """Harvest one institution's works into data/raw/<id>/openalex_works.jsonl."""

    openalex_id = target.extra.get("openalex_institution_id")
    if not openalex_id:
        print(f"Skipping {target.id}: no openalex_institution_id in the registry.")
        return 0

    filters = [f"authorships.institutions.lineage:{openalex_id}"]
    if from_year is not None or to_year is not None:
        start = from_year if from_year is not None else "*"
        end = to_year if to_year is not None else "*"
        filters.append(f"publication_year:{start}-{end}")

    collector = OpenAlexCollector(email=email)
    output_path = DEFAULT_RAW_DIR / target.id / "openalex_works.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Harvesting {target.id} ({target.name}) from OpenAlex {openalex_id} -> {output_path}")

    cursor: str | None = "*"
    seen: set[str] = set()
    total = 0
    api_count: int | None = None

    try:
        with output_path.open("w", encoding="utf-8") as output_file:
            while cursor:
                payload = collector.fetch_works(filters=filters, cursor=cursor, per_page=PER_PAGE)
                meta = payload.get("meta") or {}
                if api_count is None:
                    api_count = meta.get("count")
                    print(f"OpenAlex reports {api_count} works for this institution.")

                results = payload.get("results") or []
                if not results:
                    break

                for work in results:
                    work_id = work.get("id")
                    if not work_id or work_id in seen:
                        continue
                    if max_records is not None and total >= max_records:
                        cursor = None
                        break
                    seen.add(work_id)
                    output_file.write(json.dumps(work, ensure_ascii=False) + "\n")
                    total += 1

                if cursor is None:
                    break
                if total and total % 2000 < PER_PAGE:
                    print(f"Collected {total} works...")

                next_cursor = meta.get("next_cursor")
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor
    except requests.RequestException as exc:
        print(f"Request failed after {total} works: {exc}")
        print(f"Kept the {total} works collected before the error in {output_path}")
        raise SystemExit(1) from exc

    reported = f" of {api_count} reported" if api_count is not None else ""
    print(f"Saved {total}{reported} works to {output_path}")
    return total


def main() -> None:
    args = parse_args()
    targets = load_registry()

    if args.id:
        target = next((t for t in targets if t.id == args.id), None)
        if target is None:
            raise SystemExit(f"No repository target with id={args.id!r}.")
        selected = [target]
    else:
        selected = [t for t in targets if t.extra.get("openalex_institution_id")]
        if not selected:
            raise SystemExit("No registry entries carry an openalex_institution_id.")

    total = 0
    for target in selected:
        total += collect_one(
            target,
            email=args.email,
            max_records=args.max_records,
            from_year=args.from_year,
            to_year=args.to_year,
        )

    if len(selected) > 1:
        print(f"\nCollected {total} works across {len(selected)} institutions.")


if __name__ == "__main__":
    main()
