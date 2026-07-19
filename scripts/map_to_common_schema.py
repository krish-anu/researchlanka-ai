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

from src.collectors.schema_mapping import map_oai_dc_record

DEFAULT_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "repositories"


def map_one(institution_id: str) -> int:
    raw_path = DEFAULT_RAW_DIR / institution_id / "oai_dc.jsonl"
    if not raw_path.exists():
        print(f"Skipping {institution_id}: no raw file at {raw_path}")
        return 0

    output_path = DEFAULT_PROCESSED_DIR / f"{institution_id}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    skipped_deleted = 0
    with raw_path.open(encoding="utf-8") as raw_file, output_path.open(
        "w", encoding="utf-8"
    ) as output_file:
        for line in raw_file:
            record = json.loads(line)
            mapped = map_oai_dc_record(record, institution_id=institution_id)
            if mapped.get("deleted"):
                skipped_deleted += 1
                continue
            output_file.write(json.dumps(mapped, ensure_ascii=False) + "\n")
            total += 1

    note = f" ({skipped_deleted} deleted skipped)" if skipped_deleted else ""
    print(f"{institution_id}: mapped {total} records -> {output_path}{note}")
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
        if p.is_dir() and (p / "oai_dc.jsonl").exists()
    )
    if not ids:
        print("No harvested oai_dc.jsonl files found under data/raw/.")
        return

    total = 0
    for institution_id in ids:
        total += map_one(institution_id)
    print(f"\nMapped {total} total records across {len(ids)} institutions.")


if __name__ == "__main__":
    main()
