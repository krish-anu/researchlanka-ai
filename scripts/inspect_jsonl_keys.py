"""Inspect keys in a JSONL dataset without loading the full file.

Example:
    python scripts/inspect_jsonl_keys.py ~/Desktop/researchlanka-data/lk_works.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_NESTED_PATHS = [
    "ids",
    "open_access",
    "primary_location",
    "primary_location.source",
    "biblio",
    "primary_topic",
    "primary_topic.subfield",
    "primary_topic.field",
    "primary_topic.domain",
    "authorships[]",
    "authorships[].author",
    "authorships[].institutions[]",
    "authorships[].affiliations[]",
    "institutions[]",
    "concepts[]",
    "keywords[]",
    "topics[]",
    "funders[]",
    "awards[]",
    "sustainable_development_goals[]",
    "counts_by_year[]",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect JSONL keys from sample records.")
    parser.add_argument("input", type=Path, help="Path to the JSONL file.")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Number of records to inspect. Default: 5",
    )
    return parser.parse_args()


def load_sample(path: Path, sample_size: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    with path.expanduser().open("r", encoding="utf-8") as input_file:
        for line in input_file:
            if not line.strip():
                continue
            records.append(json.loads(line))
            if len(records) >= sample_size:
                break

    return records


def keys_for_path(records: list[dict[str, Any]], path: str) -> list[str]:
    keys: set[str] = set()

    for record in records:
        values: list[Any] = [record]
        for part in path.split("."):
            next_values: list[Any] = []
            is_list = part.endswith("[]")
            key = part[:-2] if is_list else part

            for value in values:
                if not isinstance(value, dict):
                    continue
                child = value.get(key)
                if is_list:
                    if isinstance(child, list):
                        next_values.extend(child)
                elif child is not None:
                    next_values.append(child)

            values = next_values

        for value in values:
            if isinstance(value, dict):
                keys.update(value.keys())

    return sorted(keys)


def main() -> None:
    args = parse_args()
    records = load_sample(args.input, args.sample_size)

    if not records:
        print("No records found.")
        return

    top_level_keys = sorted({key for record in records for key in record.keys()})

    print(f"Inspected records: {len(records)}")
    print("\nTop-level keys:")
    for key in top_level_keys:
        print(f"  - {key}")

    print("\nNested keys:")
    for path in DEFAULT_NESTED_PATHS:
        nested_keys = keys_for_path(records, path)
        if nested_keys:
            print(f"\n{path}:")
            for key in nested_keys:
                print(f"  - {key}")


if __name__ == "__main__":
    main()
