#!/usr/bin/env python3
"""Extract publication titles as model-ready text data.

Run from the backend folder:

    python scripts/extraction/extract_publication_titles_for_model.py

The output keeps every non-empty publication title from the final dataset and
adds cleaned and normalized title text that can be used in a model pipeline.
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
    / "publication_titles_for_model_all_years.csv"
)

OUTPUT_FIELDS = [
    "record_number",
    "title",
    "title_clean",
    "title_normalized",
    "publication_year",
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

WHITESPACE_RE = re.compile(r"\s+")
PUNCTUATION_RE = re.compile(r"[^\w\s]")
HTML_TAG_RE = re.compile(r"<[^>]+>")


def set_large_csv_field_limit() -> None:
    """Allow large abstract/metadata fields in the source CSV."""
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def clean_title(value: str) -> str:
    """Decode HTML fragments and collapse whitespace for display/model input."""
    text = value or ""
    previous = None
    while previous != text:
        previous = text
        text = html.unescape(text)
    text = HTML_TAG_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_title(value: str) -> str:
    """Lowercase and remove accents/punctuation for matching or grouping."""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold()
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    return WHITESPACE_RE.sub(" ", normalized).strip()


def extract_titles(input_path: Path, deduplicate_titles: bool) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_titles: set[str] = set()

    with input_path.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        for source_index, row in enumerate(reader, start=1):
            title_clean = clean_title(row.get("title", ""))
            if not title_clean:
                continue

            title_normalized = normalize_title(title_clean)
            if deduplicate_titles and title_normalized in seen_titles:
                continue
            seen_titles.add(title_normalized)

            rows.append(
                {
                    "record_number": str(source_index),
                    "title": row.get("title", ""),
                    "title_clean": title_clean,
                    "title_normalized": title_normalized,
                    "publication_year": row.get("publication_year", ""),
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


def write_titles(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract publication titles for model training or inference."
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
        help=f"Output title CSV. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--deduplicate-titles",
        action="store_true",
        help="Keep only the first row for each normalized title.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_large_csv_field_limit()
    rows = extract_titles(args.input, deduplicate_titles=args.deduplicate_titles)
    write_titles(args.output, rows)
    print(f"Wrote {len(rows)} title rows to {args.output}")


if __name__ == "__main__":
    main()
