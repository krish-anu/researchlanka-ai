"""Convert common-schema repository records (data/processed/repositories/*.jsonl,
produced by map_to_common_schema.py) into a flat CSV file.

By default combines every institution's JSONL file into one CSV. Pass a
single file as --input to convert just one institution.

Examples:
    python scripts/convert_repositories_jsonl_to_csv.py
    python scripts/convert_repositories_jsonl_to_csv.py --input data/processed/repositories/uom.jsonl --output data/processed/uom.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "processed" / "repositories"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "repositories_combined.csv"

CSV_COLUMNS = [
    "source_institution_id",
    "source_record_id",
    "source_datestamp",
    "title",
    "authors",
    "contributors",
    "abstract",
    "keywords",
    "publication_date",
    "publication_year",
    "publication_type",
    "publisher",
    "journal",
    "language",
    "rights",
    "doi",
    "url",
    "source_set_specs",
    "raw_identifiers",
]


def unique_join(values: Any, separator: str = "; ") -> str:
    if not isinstance(values, list):
        return "" if values is None else str(values)

    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return separator.join(cleaned)


def record_to_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_institution_id": record.get("source_institution_id"),
        "source_record_id": record.get("source_record_id"),
        "source_datestamp": record.get("source_datestamp"),
        "title": record.get("title"),
        "authors": unique_join(record.get("authors")),
        "contributors": unique_join(record.get("contributors")),
        "abstract": record.get("abstract"),
        "keywords": unique_join(record.get("keywords")),
        "publication_date": record.get("publication_date"),
        "publication_year": record.get("publication_year"),
        "publication_type": record.get("publication_type"),
        "publisher": record.get("publisher"),
        "journal": record.get("journal"),
        "language": record.get("language"),
        "rights": record.get("rights"),
        "doi": record.get("doi"),
        "url": record.get("url"),
        "source_set_specs": unique_join(record.get("source_set_specs")),
        "raw_identifiers": unique_join(record.get("raw_identifiers")),
    }


def iter_input_files(input_arg: Path | None) -> Iterable[Path]:
    if input_arg is None:
        return sorted(DEFAULT_INPUT_DIR.glob("*.jsonl"))
    if input_arg.is_dir():
        return sorted(input_arg.glob("*.jsonl"))
    return [input_arg]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert common-schema repository JSONL to CSV.")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=f"JSONL file or directory of JSONL files. Default: every file in {DEFAULT_INPUT_DIR}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output CSV path. Default: {DEFAULT_OUTPUT_PATH}",
    )
    return parser.parse_args()


def convert(input_files: list[Path], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for input_path in input_files:
            with input_path.open(encoding="utf-8") as input_file:
                for line_number, line in enumerate(input_file, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise ValueError(f"Invalid JSON in {input_path} line {line_number}: {error}") from error

                    writer.writerow(record_to_row(record))
                    total += 1

    return total


def main() -> None:
    args = parse_args()
    input_files = list(iter_input_files(args.input))

    if not input_files:
        print(f"No JSONL files found for input {args.input or DEFAULT_INPUT_DIR}.")
        return

    total = convert(input_files, args.output)
    print(f"Converted {total} records from {len(input_files)} file(s) -> {args.output}")


if __name__ == "__main__":
    main()
