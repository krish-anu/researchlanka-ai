"""Build a columns-filtered publication dataset from finalized column decisions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = next(
    (parent for parent in SCRIPT_PATH.parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.build_final_common_dataset import FINAL_MAIN_COLUMNS


DEFAULT_INPUT_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_columns_filtered.csv"
)
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_columns_filtered_summary.csv"
)


def filter_to_finalized_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return only the finalized main-dataset columns, in finalized order."""
    missing_columns = [column for column in FINAL_MAIN_COLUMNS if column not in df.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Input dataset is missing finalized columns: {missing}")

    return df.loc[:, FINAL_MAIN_COLUMNS].copy()


def write_summary(
    output_path: Path,
    *,
    input_csv: Path,
    output_csv: Path,
    input_rows: int,
    input_columns: int,
    output_rows: int,
    output_columns: int,
) -> None:
    rows = [
        {"metric": "input_csv", "value": str(input_csv)},
        {"metric": "output_csv", "value": str(output_csv)},
        {"metric": "input_rows", "value": input_rows},
        {"metric": "input_columns", "value": input_columns},
        {"metric": "output_rows", "value": output_rows},
        {"metric": "output_columns", "value": output_columns},
        {"metric": "finalized_columns", "value": "; ".join(FINAL_MAIN_COLUMNS)},
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)


def build_columns_filtered_dataset(
    input_csv: Path,
    output_csv: Path,
    summary_csv: Path,
) -> pd.DataFrame:
    df = pd.read_csv(input_csv, dtype="object", low_memory=False)
    filtered = filter_to_finalized_columns(df)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(output_csv, index=False)
    write_summary(
        summary_csv,
        input_csv=input_csv,
        output_csv=output_csv,
        input_rows=len(df),
        input_columns=len(df.columns),
        output_rows=len(filtered),
        output_columns=len(filtered.columns),
    )

    return filtered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the columns-filtered publication dataset using finalized columns."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    filtered = build_columns_filtered_dataset(args.input_csv, args.output_csv, args.summary_csv)

    print("Done.")
    print(f"  Rows: {len(filtered):,}")
    print(f"  Columns: {len(filtered.columns):,}")
    print(f"  Columns-filtered dataset: {args.output_csv}")
    print(f"  Summary: {args.summary_csv}")


if __name__ == "__main__":
    main()
