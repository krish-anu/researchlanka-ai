#!/usr/bin/env python3
"""Extract publication keywords as model-ready text data.

Run from the backend folder:

    python scripts/extraction/extract_publication_keywords_for_model.py

The output keeps every publication with non-empty keywords from the final
dataset and adds cleaned, deduplicated, normalized keyword text for model use.
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
    / "publication_keywords_for_model_all_years.csv"
)

OUTPUT_FIELDS = [
    "record_number",
    "keywords",
    "keywords_clean",
    "keywords_normalized",
    "keyword_count",
    "publication_year",
    "title",
    "abstract",
    "type",
    "journal",
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
KEYWORD_SEPARATOR_RE = re.compile(r"\s*(?:;|\||,)\s*")


def set_large_csv_field_limit() -> None:
    """Allow large abstract/metadata fields in the source CSV."""
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def clean_keyword(value: str) -> str:
    """Decode HTML entities and collapse keyword whitespace."""
    text = value or ""
    previous = None
    while previous != text:
        previous = text
        text = html.unescape(text)
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_keyword(value: str) -> str:
    """Lowercase and remove accents/punctuation for stable model features."""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold()
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    return WHITESPACE_RE.sub(" ", normalized).strip()


def split_keywords(value: str) -> list[str]:
    text = clean_keyword(value)
    if not text:
        return []
    keywords: list[str] = []
    seen: set[str] = set()
    for item in KEYWORD_SEPARATOR_RE.split(text):
        keyword = clean_keyword(item)
        if not keyword:
            continue
        key = normalize_keyword(keyword)
        if not key or key in seen:
            continue
        seen.add(key)
        keywords.append(keyword)
    return keywords


def normalize_keywords(value: str) -> str:
    return "; ".join(normalize_keyword(keyword) for keyword in split_keywords(value))


def clean_keywords(value: str) -> str:
    return "; ".join(split_keywords(value))


def extract_keywords(input_path: Path, deduplicate_keyword_sets: bool) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_keyword_sets: set[str] = set()

    with input_path.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        for source_index, row in enumerate(reader, start=1):
            keywords = split_keywords(row.get("keywords", ""))
            if not keywords:
                continue

            keywords_clean = "; ".join(keywords)
            keywords_normalized = "; ".join(normalize_keyword(keyword) for keyword in keywords)
            if deduplicate_keyword_sets and keywords_normalized in seen_keyword_sets:
                continue
            seen_keyword_sets.add(keywords_normalized)

            rows.append(
                {
                    "record_number": str(source_index),
                    "keywords": row.get("keywords", ""),
                    "keywords_clean": keywords_clean,
                    "keywords_normalized": keywords_normalized,
                    "keyword_count": str(len(keywords)),
                    "publication_year": row.get("publication_year", ""),
                    "title": row.get("title", ""),
                    "abstract": row.get("abstract", ""),
                    "type": row.get("type", ""),
                    "journal": row.get("journal", ""),
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


def write_keywords(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract publication keywords for model training or inference."
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
        help=f"Output keyword CSV. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--deduplicate-keyword-sets",
        action="store_true",
        help="Keep only the first row for each normalized keyword set.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_large_csv_field_limit()
    rows = extract_keywords(
        args.input,
        deduplicate_keyword_sets=args.deduplicate_keyword_sets,
    )
    write_keywords(args.output, rows)
    print(f"Wrote {len(rows)} keyword rows to {args.output}")


if __name__ == "__main__":
    main()
