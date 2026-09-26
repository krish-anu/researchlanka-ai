#!/usr/bin/env python3
"""Build hard-negative NON_AI training rows from reviewed false positives."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data/models/ai_relevance/validated_human_selection_xgboost_fast"
    / "false_positive_analysis/false_positive_ai_cases.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data/processed/ai/hard_negative_false_positive_non_ai.csv"
)

OUTPUT_COLUMNS = (
    "record_key",
    "label",
    "label_source",
    "hard_negative_category",
    "hard_negative_evidence",
    "title",
    "abstract",
    "keywords",
    "topics",
    "concepts",
    "primary_topic",
    "primary_subfield",
    "primary_field",
    "primary_domain",
    "doi",
    "openalex_id",
    "source_record_id",
)


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def first_present(row: pd.Series, *columns: str) -> str:
    for column in columns:
        if column in row:
            value = clean(row.get(column))
            if value:
                return value
    return ""


def record_key(row: pd.Series, index: int) -> str:
    for column, prefix in (
        ("publication_key", "publication"),
        ("record_key", "record"),
        ("doi", "doi"),
        ("openalex_id", "openalex"),
        ("source_record_id", "source"),
    ):
        value = clean(row.get(column))
        if value:
            return f"{prefix}:{value.casefold()}"
    title = clean(row.get("title")).casefold()
    year = clean(row.get("publication_year"))
    if title:
        return f"title_year:{' '.join(title.split())}:{year}"
    return f"hard_negative_row:{index}"


def build_hard_negative_dataset(input_csv: Path, output_csv: Path) -> int:
    frame = pd.read_csv(input_csv)
    rows: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        category = first_present(row, "manual_error_category", "error_category_auto")
        rows.append(
            {
                "record_key": record_key(row, int(index)),
                "label": "NON_AI",
                "label_source": "human_rejected_false_positive",
                "hard_negative_category": category,
                "hard_negative_evidence": first_present(
                    row,
                    "manual_notes",
                    "category_evidence_auto",
                    "text_excerpt",
                ),
                **{column: clean(row.get(column)) for column in OUTPUT_COLUMNS if column not in {
                    "record_key",
                    "label",
                    "label_source",
                    "hard_negative_category",
                    "hard_negative_evidence",
                }},
            }
        )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OUTPUT_COLUMNS).drop_duplicates("record_key").to_csv(
        output_csv,
        index=False,
    )
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert false-positive review cases into hard-negative NON_AI rows."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count = build_hard_negative_dataset(args.input, args.output)
    print(f"Wrote {count} hard-negative rows to {args.output}")


if __name__ == "__main__":
    main()
