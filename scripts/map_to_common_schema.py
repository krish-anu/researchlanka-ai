"""Map harvested OAI-DC records (data/raw/<id>/oai_dc.jsonl) into the
project's common publication-metadata schema.

Examples:
    python scripts/map_to_common_schema.py --id uom
    python scripts/map_to_common_schema.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.collectors.schema_mapping import (
    map_dspace_rest_record,
    map_html_meta_record,
    map_oai_dc_record,
)

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "repositories"


def _count_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


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

    ids = sorted(
        p.name
        for p in DEFAULT_RAW_DIR.iterdir()
        if p.is_dir()
        and ((p / "oai_dc.jsonl").exists() or (p / "rest_items.jsonl").exists())
    )
    if not ids:
        print("No harvested oai_dc.jsonl or rest_items.jsonl files found under data/raw/.")
        return

    total = 0
    for institution_id in ids:
        total += map_one(institution_id)
    print(f"\nMapped {total} total records across {len(ids)} institutions.")


if __name__ == "__main__":
    main()
