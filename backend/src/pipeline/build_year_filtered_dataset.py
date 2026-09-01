"""Build a publication dataset filtered to an inclusive publication-year range."""

from __future__ import annotations

import argparse
import sys
from datetime import date
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


DEFAULT_START_YEAR = 2016
DEFAULT_END_YEAR = date.today().year
DEFAULT_YEAR_SUFFIX = f"{DEFAULT_START_YEAR}_{DEFAULT_END_YEAR}"
DEFAULT_INPUT_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / f"common_publications_final_{DEFAULT_YEAR_SUFFIX}.csv"
)
DEFAULT_SUMMARY_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / f"common_publications_final_{DEFAULT_YEAR_SUFFIX}_summary.csv"
)


def year_filter_counts(
    df: pd.DataFrame,
    *,
    start_year: int = DEFAULT_START_YEAR,
    end_year: int = DEFAULT_END_YEAR,
) -> dict[str, int]:
    end_year = min(end_year, DEFAULT_END_YEAR)
    if "publication_year" not in df.columns:
        raise ValueError("Input dataset must include a publication_year column.")

    years = pd.to_numeric(df["publication_year"], errors="coerce")
    missing_or_invalid = years.isna()

    return {
        "input_rows": len(df),
        "kept_rows": int(years.between(start_year, end_year, inclusive="both").sum()),
        "dropped_before_start_year": int((years < start_year).sum()),
        "dropped_after_end_year": int((years > end_year).sum()),
        "dropped_missing_or_invalid_year": int(missing_or_invalid.sum()),
    }


def filter_by_publication_year(
    df: pd.DataFrame,
    *,
    start_year: int = DEFAULT_START_YEAR,
    end_year: int = DEFAULT_END_YEAR,
) -> pd.DataFrame:
    end_year = min(end_year, DEFAULT_END_YEAR)
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year.")

    if "publication_year" not in df.columns:
        raise ValueError("Input dataset must include a publication_year column.")

    years = pd.to_numeric(df["publication_year"], errors="coerce")
    keep_mask = years.between(start_year, end_year, inclusive="both")
    return df.loc[keep_mask].copy()


def write_summary(
    output_path: Path,
    *,
    input_csv: Path,
    output_csv: Path,
    start_year: int,
    end_year: int,
    counts: dict[str, Any],
    output_columns: int,
) -> None:
    rows = [
        {"metric": "input_csv", "value": str(input_csv)},
        {"metric": "output_csv", "value": str(output_csv)},
        {"metric": "start_year", "value": start_year},
        {"metric": "end_year", "value": end_year},
        {"metric": "output_columns", "value": output_columns},
        *[{"metric": metric, "value": value} for metric, value in counts.items()],
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output_path, index=False)


def build_year_filtered_dataset(
    input_csv: Path,
    output_csv: Path,
    summary_csv: Path,
    *,
    start_year: int = DEFAULT_START_YEAR,
    end_year: int = DEFAULT_END_YEAR,
) -> pd.DataFrame:
    end_year = min(end_year, DEFAULT_END_YEAR)
    df = pd.read_csv(input_csv, dtype="object", low_memory=False)
    counts = year_filter_counts(df, start_year=start_year, end_year=end_year)
    filtered = filter_by_publication_year(df, start_year=start_year, end_year=end_year)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(output_csv, index=False)
    write_summary(
        summary_csv,
        input_csv=input_csv,
        output_csv=output_csv,
        start_year=start_year,
        end_year=end_year,
        counts=counts,
        output_columns=len(filtered.columns),
    )

    return filtered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a publication dataset filtered to an inclusive year range."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    filtered = build_year_filtered_dataset(
        args.input_csv,
        args.output_csv,
        args.summary_csv,
        start_year=args.start_year,
        end_year=args.end_year,
    )

    print("Done.")
    print(f"  Year range: {args.start_year}-{args.end_year}")
    print(f"  Rows: {len(filtered):,}")
    print(f"  Columns: {len(filtered.columns):,}")
    print(f"  Year-filtered dataset: {args.output_csv}")
    print(f"  Summary: {args.summary_csv}")


if __name__ == "__main__":
    main()
