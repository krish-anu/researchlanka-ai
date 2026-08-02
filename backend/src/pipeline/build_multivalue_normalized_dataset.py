"""Normalize semicolon-separated multi-value columns and write item sidecars."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.build_final_common_dataset import build_publication_key


DEFAULT_INPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_language_normalized.csv"
)
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_multivalue_normalized.csv"
)
DEFAULT_ITEMS_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "publication_multivalue_items_2016_2026.csv"
)
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_multivalue_normalized_summary.csv"
)

MULTI_VALUE_COLUMNS = [
    "authors",
    "keywords",
    "institutions",
    "countries",
    "concepts",
    "topics",
    "funder_name",
    "source_dataset",
]

LOWERCASE_ITEM_COLUMNS = {"keywords", "source_dataset"}
UPPERCASE_ITEM_COLUMNS = {"countries"}


def clean_text(value: Any) -> str | None:
    if pd.isna(value):
        return None

    text = " ".join(str(value).split()).strip()
    return text or None


def normalize_multivalue_item(column: str, value: Any) -> str | None:
    text = clean_text(value)
    if text is None:
        return None

    if column in LOWERCASE_ITEM_COLUMNS:
        return text.lower()
    if column in UPPERCASE_ITEM_COLUMNS:
        return text.upper()

    return text


def split_multivalue_cell(value: Any) -> list[str]:
    text = clean_text(value)
    if text is None:
        return []

    return [part.strip() for part in text.split(";") if part.strip()]


def normalize_multivalue_cell(column: str, value: Any) -> Any:
    seen: set[str] = set()
    output: list[str] = []

    for raw_item in split_multivalue_cell(value):
        item = normalize_multivalue_item(column, raw_item)
        if item is None:
            continue

        key = item.casefold()
        if key in seen:
            continue

        seen.add(key)
        output.append(item)

    return "; ".join(output) if output else pd.NA


def normalize_multivalue_columns(
    df: pd.DataFrame,
    *,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    normalized = df.copy()
    selected_columns = columns or MULTI_VALUE_COLUMNS

    missing_columns = [column for column in selected_columns if column not in normalized.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Input dataset is missing multi-value columns: {missing}")

    for column in selected_columns:
        normalized[column] = normalized[column].map(lambda value, col=column: normalize_multivalue_cell(col, value))

    return normalized


def multivalue_summary_rows(before: pd.DataFrame, after: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for column in MULTI_VALUE_COLUMNS:
        before_present = before[column].map(clean_text).notna()
        after_present = after[column].map(clean_text).notna()
        item_counts = after.loc[after_present, column].map(lambda value: len(split_multivalue_cell(value)))

        rows.append(
            {
                "column": column,
                "present_rows_before": int(before_present.sum()),
                "present_rows_after": int(after_present.sum()),
                "rows_with_multiple_values_after": int((item_counts > 1).sum()) if len(item_counts) else 0,
                "total_items_after": int(item_counts.sum()) if len(item_counts) else 0,
                "distinct_items_after": int(
                    pd.Series(
                        [
                            item
                            for value in after.loc[after_present, column]
                            for item in split_multivalue_cell(value)
                        ]
                    ).nunique()
                ),
            }
        )

    return rows


def write_multivalue_items_sidecar(
    df: pd.DataFrame,
    output_path: Path,
    *,
    columns: list[str] | None = None,
) -> int:
    selected_columns = columns or MULTI_VALUE_COLUMNS
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "publication_key",
        "publication_row_number",
        "source_record_id",
        "doi",
        "column",
        "item_index",
        "item",
    ]

    row_count = 0
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for row_number, row in enumerate(df.itertuples(index=False), start=1):
            row_series = pd.Series(dict(zip(df.columns, row, strict=True)))
            publication_key = build_publication_key(row_series, row_number)

            for column in selected_columns:
                for item_index, item in enumerate(split_multivalue_cell(row_series.get(column)), start=1):
                    writer.writerow(
                        {
                            "publication_key": publication_key,
                            "publication_row_number": row_number,
                            "source_record_id": row_series.get("source_record_id", pd.NA),
                            "doi": row_series.get("doi", pd.NA),
                            "column": column,
                            "item_index": item_index,
                            "item": item,
                        }
                    )
                    row_count += 1

    return row_count


def build_multivalue_normalized_dataset(
    input_csv: Path,
    output_csv: Path,
    items_csv: Path,
    summary_csv: Path,
) -> tuple[pd.DataFrame, int]:
    df = pd.read_csv(input_csv, dtype="object", low_memory=False)
    normalized = normalize_multivalue_columns(df)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_csv, index=False)
    item_rows = write_multivalue_items_sidecar(normalized, items_csv)

    summary = pd.DataFrame(
        [
            {"metric": "input_csv", "value": str(input_csv)},
            {"metric": "output_csv", "value": str(output_csv)},
            {"metric": "items_csv", "value": str(items_csv)},
            {"metric": "input_rows", "value": len(df)},
            {"metric": "input_columns", "value": len(df.columns)},
            {"metric": "output_rows", "value": len(normalized)},
            {"metric": "output_columns", "value": len(normalized.columns)},
            {"metric": "multi_value_item_rows", "value": item_rows},
            {"metric": "normalized_columns", "value": "; ".join(MULTI_VALUE_COLUMNS)},
            {
                "metric": "normalization_rule",
                "value": "split on semicolon; strip/collapse spaces; deduplicate case-insensitively; keywords/source_dataset lowercase; countries uppercase",
            },
        ]
    )
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_csv, index=False)

    details_csv = summary_csv.with_name(summary_csv.stem.replace("_summary", "_details") + ".csv")
    pd.DataFrame(multivalue_summary_rows(df, normalized)).to_csv(details_csv, index=False)

    return normalized, item_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize semicolon-separated multi-value columns and write an exploded item sidecar."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--items-csv", type=Path, default=DEFAULT_ITEMS_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    normalized, item_rows = build_multivalue_normalized_dataset(
        args.input_csv,
        args.output_csv,
        args.items_csv,
        args.summary_csv,
    )

    print("Done.")
    print(f"  Rows: {len(normalized):,}")
    print(f"  Columns: {len(normalized.columns):,}")
    print(f"  Multi-value item rows: {item_rows:,}")
    print(f"  Multi-value normalized dataset: {args.output_csv}")
    print(f"  Multi-value item sidecar: {args.items_csv}")
    print(f"  Summary: {args.summary_csv}")


if __name__ == "__main__":
    main()
