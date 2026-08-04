"""Map harvested repository records into the common publication schema.

Examples:
    python scripts/processing/map_to_common_schema.py --id uom
    python scripts/processing/map_to_common_schema.py --all
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

from src.collectors.schema_mapping import (
    map_crossref_record,
    map_dspace_rest_record,
    map_html_meta_record,
    map_oai_dc_record,
)

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "repositories"
RAW_ROUTE_FILENAMES = ("oai_dc.jsonl", "rest_items.jsonl", "html_meta.jsonl", "crossref_works.jsonl")
AUTO_DISCOVERY_EXCLUDED_IDS = {"sljol"}


def _count_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def discover_raw_institution_ids(
    raw_dir: Path = DEFAULT_RAW_DIR,
    *,
    excluded_ids: set[str] = AUTO_DISCOVERY_EXCLUDED_IDS,
) -> list[str]:
    """Return repository ids with raw route files for --all mapping.

    SLJOL is collected via Crossref, but it is a standalone merge source
    (`sljol.csv`), not part of the repository aggregate.
    """

    if not raw_dir.exists():
        return []

    return sorted(
        path.name
        for path in raw_dir.iterdir()
        if path.is_dir()
        and path.name not in excluded_ids
        and any((path / filename).exists() for filename in RAW_ROUTE_FILENAMES)
    )


def map_one(institution_id: str) -> int:
    """Map one institution's raw data into the common schema.

    An institution may have been harvested via up to three routes (OAI-DC,
    DSpace REST, HTML meta-tag crawl); uses whichever captured the most
    records -- several hosts have a broken/partial OAI route where another
    route got further (uwu, cmb, jfn_*). Never merges routes, to avoid
    duplicating the same items.
    """

    candidates = [
        (DEFAULT_RAW_DIR / institution_id / "oai_dc.jsonl", map_oai_dc_record, "oai"),
        (DEFAULT_RAW_DIR / institution_id / "rest_items.jsonl", map_dspace_rest_record, "rest"),
        (DEFAULT_RAW_DIR / institution_id / "html_meta.jsonl", map_html_meta_record, "html"),
        (DEFAULT_RAW_DIR / institution_id / "crossref_works.jsonl", map_crossref_record, "crossref"),
    ]
    counted = [
        (path.exists() and _count_lines(path) or 0, path, mapper, kind)
        for path, mapper, kind in candidates
    ]

    best_count, raw_path, mapper, source_kind = max(counted, key=lambda c: c[0])

    if best_count == 0:
        if not any(path.exists() for _, path, _, _ in counted):
            print(f"Skipping {institution_id}: no raw files under {DEFAULT_RAW_DIR / institution_id}")
        else:
            print(f"{institution_id}: mapped 0 records (raw files empty)")
        return 0

    output_path = DEFAULT_PROCESSED_DIR / f"{institution_id}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    skipped_deleted = 0
    with raw_path.open(encoding="utf-8") as raw_file, output_path.open(
        "w", encoding="utf-8"
    ) as output_file:
        for line in raw_file:
            if not line.strip():
                continue
            record = json.loads(line)
            mapped = mapper(record, institution_id=institution_id)
            if mapped.get("deleted"):
                skipped_deleted += 1
                continue
            output_file.write(json.dumps(mapped, ensure_ascii=False) + "\n")
            total += 1

    note = f" ({skipped_deleted} deleted skipped)" if skipped_deleted else ""
    print(f"{institution_id}: mapped {total} records via {source_kind} -> {output_path}{note}")
    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Map raw OAI-DC records into the common schema.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", default=None, help="Single institution id to map.")
    group.add_argument("--all", action="store_true", help="Map every institution with raw data on disk.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.id:
        map_one(args.id)
        return

    if not DEFAULT_RAW_DIR.exists():
        print(f"No raw data directory at {DEFAULT_RAW_DIR}")
        return

    ids = discover_raw_institution_ids()
    if not ids:
        print("No harvested raw files found under data/raw/.")
        return

    total = 0
    for institution_id in ids:
        total += map_one(institution_id)
    print(f"\nMapped {total} total records across {len(ids)} institutions.")


if __name__ == "__main__":
    main()
