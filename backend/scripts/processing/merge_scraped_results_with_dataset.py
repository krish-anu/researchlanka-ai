"""Merge scraped title/abstract/keyword results into the current dataset.

The script is intentionally conservative: by default it only fills missing
values in the current dataset and preserves the current dataset schema.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CURRENT_DATASET = (
    PROJECT_ROOT / "researchlanka-ai-dataset" / "data" / "researchlanka_ai_publications_v1.0.csv"
)
DEFAULT_SCRAPED_RESULTS = (
    PROJECT_ROOT
    / "backend"
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_analysis_ready.csv"
)
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT
    / "backend"
    / "data"
    / "processed"
    / "common"
    / "abstract_fetched.csv"
)
DEFAULT_SUMMARY_JSON = (
    PROJECT_ROOT
    / "backend"
    / "data"
    / "results"
    / "scraped_results_dataset_merge_summary.json"
)
MERGE_COLUMNS = ("title", "abstract", "keywords")
MATCH_KEYS = ("doi", "openalex_id", "source_record_id")
BLANK_VALUES = {"", "nan", "none", "null", "na", "n/a", "[]", "{}"}


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if pd.isna(value):
        return True
    return str(value).strip().casefold() in BLANK_VALUES


def normalize_doi(value: Any) -> str:
    if is_blank(value):
        return ""
    text = str(value).strip().casefold()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text.strip()


def normalize_text_key(value: Any) -> str:
    if is_blank(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def clean_value(value: Any) -> str:
    if is_blank(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def normalized_key(column: str, value: Any) -> str:
    if column == "doi":
        return normalize_doi(value)
    return normalize_text_key(value)


def choose_best_scraped_record(group: pd.DataFrame) -> pd.Series:
    """Pick the scraped row with the most usable scraped metadata."""
    scores = group.apply(
        lambda row: sum(0 if is_blank(row.get(column)) else 1 for column in MERGE_COLUMNS),
        axis=1,
    )
    return group.loc[scores.idxmax()]


def build_lookup(scraped: pd.DataFrame, key_column: str) -> dict[str, dict[str, str]]:
    available_columns = [column for column in MERGE_COLUMNS if column in scraped.columns]
    rows = scraped[[key_column, *available_columns]].copy()
    rows["_merge_key"] = rows[key_column].map(lambda value: normalized_key(key_column, value))
    rows = rows[rows["_merge_key"] != ""]
    if rows.empty:
        return {}

    best_rows = rows.groupby("_merge_key", sort=False, dropna=False).apply(choose_best_scraped_record)
    lookup: dict[str, dict[str, str]] = {}
    for merge_key, row in best_rows.iterrows():
        lookup[str(merge_key)] = {
            column: clean_value(row.get(column)) for column in available_columns if not is_blank(row.get(column))
        }
    return lookup


def merge_scraped_results(
    *,
    current_dataset: Path,
    scraped_results: Path,
    output_csv: Path,
    summary_json: Path,
    overwrite_existing: bool = False,
) -> dict[str, Any]:
    current = pd.read_csv(current_dataset, dtype=str, keep_default_na=False)
    scraped = pd.read_csv(scraped_results, dtype=str, keep_default_na=False)

    missing_scraped_columns = [column for column in MERGE_COLUMNS if column not in scraped.columns]
    merge_columns = [column for column in MERGE_COLUMNS if column in current.columns and column in scraped.columns]
    if not merge_columns:
        raise ValueError("No compatible title/abstract/keyword columns were found to merge.")

    lookups = {
        key: build_lookup(scraped, key)
        for key in MATCH_KEYS
        if key in current.columns and key in scraped.columns
    }
    if not lookups:
        raise ValueError("No compatible merge keys were found. Expected DOI, OpenAlex ID, or source record ID.")

    updates_by_column = {column: 0 for column in merge_columns}
    matches_by_key = {key: 0 for key in lookups}
    rows_touched: set[int] = set()

    for row_index, row in current.iterrows():
        matched_values: dict[str, str] | None = None
        matched_key: str | None = None
        for key, lookup in lookups.items():
            merge_key = normalized_key(key, row.get(key))
            if merge_key and merge_key in lookup:
                matched_values = lookup[merge_key]
                matched_key = key
                break

        if not matched_values or matched_key is None:
            continue

        row_changed = False
        for column in merge_columns:
            scraped_value = matched_values.get(column, "")
            if is_blank(scraped_value):
                continue
            current_is_blank = is_blank(row.get(column))
            if current_is_blank or overwrite_existing:
                if clean_value(row.get(column)) != scraped_value:
                    current.at[row_index, column] = scraped_value
                    updates_by_column[column] += 1
                    row_changed = True

        if row_changed:
            matches_by_key[matched_key] += 1
            rows_touched.add(row_index)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    current.to_csv(output_csv, index=False)

    summary = {
        "current_dataset": str(current_dataset),
        "scraped_results": str(scraped_results),
        "output_csv": str(output_csv),
        "overwrite_existing": overwrite_existing,
        "current_rows": int(len(current)),
        "scraped_rows": int(len(scraped)),
        "rows_touched": int(len(rows_touched)),
        "updates_by_column": updates_by_column,
        "changed_rows_by_match_key": matches_by_key,
        "missing_scraped_columns": missing_scraped_columns,
    }

    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge scraped title, abstract, and keyword values into the current dataset."
    )
    parser.add_argument("--current-dataset", type=Path, default=DEFAULT_CURRENT_DATASET)
    parser.add_argument("--scraped-results", type=Path, default=DEFAULT_SCRAPED_RESULTS)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY_JSON)
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Replace existing title/abstract/keyword values instead of only filling blanks.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = merge_scraped_results(
        current_dataset=args.current_dataset,
        scraped_results=args.scraped_results,
        output_csv=args.output_csv,
        summary_json=args.summary_json,
        overwrite_existing=args.overwrite_existing,
    )
    print("Done.")
    print(f"  Rows touched: {summary['rows_touched']:,}")
    print(f"  Updates by column: {summary['updates_by_column']}")
    print(f"  Output CSV: {summary['output_csv']}")
    print(f"  Summary JSON: {args.summary_json}")


if __name__ == "__main__":
    main()
