#!/usr/bin/env python3
"""Extract publication abstracts as model-ready text data.

Run from the backend folder:

    python scripts/extraction/extract_publication_abstracts_for_model.py

The output keeps every non-empty publication abstract from the final dataset and
adds cleaned and normalized abstract text that can be used in a model pipeline.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import sys
import unicodedata
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "publication_abstracts_for_model_all_years.csv"
)

OUTPUT_FIELDS = [
    "record_number",
    "abstract",
    "abstract_clean",
    "abstract_normalized",
    "publication_year",
    "title",
    "type",
    "journal",
    "keywords",
    "primary_topic",
    "primary_field",
    "primary_subfield",
    "primary_domain",
    "doi",
    "openalex_id",
    "source_dataset",
    "source_institution_id",
    "source_record_id",
]

HTML_TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
PUNCTUATION_RE = re.compile(r"[^\w\s]")


def set_large_csv_field_limit() -> None:
    """Allow large abstract/metadata fields in the source CSV."""
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def clean_abstract(value: str) -> str:
    """Decode HTML/JATS fragments and collapse whitespace."""
    text = value or ""
    previous = None
    while previous != text:
        previous = text
        text = html.unescape(text)
    text = HTML_TAG_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_abstract(value: str) -> str:
    """Lowercase and remove accents/punctuation for matching or features."""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold()
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    return WHITESPACE_RE.sub(" ", normalized).strip()


def extract_abstracts(input_path: Path, deduplicate_abstracts: bool) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_abstracts: set[str] = set()

    with input_path.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        for source_index, row in enumerate(reader, start=1):
            abstract_clean = clean_abstract(row.get("abstract", ""))
            if not abstract_clean:
                continue

            abstract_normalized = normalize_abstract(abstract_clean)
            if deduplicate_abstracts and abstract_normalized in seen_abstracts:
                continue
            seen_abstracts.add(abstract_normalized)

            rows.append(
                {
                    "record_number": str(source_index),
                    "abstract": row.get("abstract", ""),
                    "abstract_clean": abstract_clean,
                    "abstract_normalized": abstract_normalized,
                    "publication_year": row.get("publication_year", ""),
                    "title": row.get("title", ""),
                    "type": row.get("type", ""),
                    "journal": row.get("journal", ""),
                    "keywords": row.get("keywords", ""),
                    "primary_topic": row.get("primary_topic", ""),
                    "primary_field": row.get("primary_field", ""),
                    "primary_subfield": row.get("primary_subfield", ""),
                    "primary_domain": row.get("primary_domain", ""),
                    "doi": row.get("doi", ""),
                    "openalex_id": row.get("openalex_id", ""),
                    "source_dataset": row.get("source_dataset", ""),
                    "source_institution_id": row.get("source_institution_id", ""),
                    "source_record_id": row.get("source_record_id", ""),
                }
            )

    return rows


def write_abstracts(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract publication abstracts for model training or inference."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input publication CSV. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output abstract CSV. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--deduplicate-abstracts",
        action="store_true",
        help="Keep only the first row for each normalized abstract.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_large_csv_field_limit()
    rows = extract_abstracts(args.input, deduplicate_abstracts=args.deduplicate_abstracts)
    write_abstracts(args.output, rows)
    print(f"Wrote {len(rows)} abstract rows to {args.output}")


if __name__ == "__main__":
    main()
