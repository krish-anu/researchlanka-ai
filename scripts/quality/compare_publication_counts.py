"""Compare publication counts across input sources.

This report complements the common-dataset merge summary by making source
coverage comparison a dedicated, repeatable step.
"""

from __future__ import annotations

import argparse
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

from scripts.processing.kaggle_merge_common_dataset import (
    EXPECTED_FILES,
    is_blank,
    normalize_crossref,
    normalize_openalex,
    normalize_repository_like,
    normalize_title_key,
)


DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "raw" / "Datasets" / "Final Datasets"
DEFAULT_OUTPUT_CSV = (
    PROJECT_ROOT / "data" / "processed" / "common" / "publication_counts_by_source.csv"
)
DEFAULT_SOURCE_ORDER = ["openalex", "crossref", "repositories_combined", "sljol"]


def find_input_file(input_dir: Path, filename: str) -> Path:
    """Return the expected source file path or raise a clear error."""
    path = Path(input_dir) / filename
    if path.exists():
        return path

    raise FileNotFoundError(f"Could not find {filename} in {input_dir}")


def default_input_paths(input_dir: Path) -> dict[str, Path]:
    """Build default source paths from the common-dataset expected files."""
    return {
        source_dataset: find_input_file(input_dir, EXPECTED_FILES[source_dataset])
        for source_dataset in DEFAULT_SOURCE_ORDER
    }


def load_normalized_source(
    source_dataset: str,
    path: Path,
    *,
    sample_rows: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load one raw source CSV and normalize it into common publication fields."""
    raw = pd.read_csv(path, dtype="object", low_memory=False, nrows=sample_rows)
    raw.columns = [str(column).strip() for column in raw.columns]

    if source_dataset == "openalex":
        normalized = normalize_openalex(raw, include_raw_json=False)
    elif source_dataset == "crossref":
        normalized = normalize_crossref(raw, include_raw_json=False)
    elif source_dataset in {"repositories_combined", "sljol"}:
        normalized = normalize_repository_like(
            raw,
            source_dataset=source_dataset,
            include_raw_json=False,
        )
    else:
        raise ValueError(f"Unsupported source dataset: {source_dataset}")

    return raw, normalized


def nonblank_values(values: pd.Series) -> pd.Series:
    """Return nonblank values from a Series after normalizing pandas NA handling."""
    return values.loc[values.map(lambda value: not is_blank(value))]


def duplicate_stats(values: pd.Series) -> dict[str, int]:
    """Calculate unique and duplicate counts for an already-normalized value series."""
    cleaned = nonblank_values(values)
    counts = cleaned.value_counts(dropna=False)
    duplicate_counts = counts.loc[counts > 1]

    return {
        "non_missing": int(len(cleaned)),
        "unique_count": int(len(counts)),
        "duplicate_values": int(len(duplicate_counts)),
        "duplicate_records": int(duplicate_counts.sum()) if not duplicate_counts.empty else 0,
    }


def estimate_unique_publications(
    *,
    total_records: int,
    doi_stats: dict[str, int],
    title_stats: dict[str, int],
) -> tuple[int, str]:
    """Estimate unique publications using DOI when coverage is sufficient."""
    if total_records == 0:
        return 0, "no_records"

    doi_coverage = doi_stats["non_missing"] / total_records
    if doi_coverage >= 0.5:
        no_doi_records = total_records - doi_stats["non_missing"]
        return (
            doi_stats["unique_count"] + no_doi_records,
            "unique_doi + no_doi_records",
        )

    if title_stats["unique_count"] > 0:
        return title_stats["unique_count"], "unique_normalized_titles"

    return total_records, "total_records_no_identifiers"


def source_count_row(
    source_dataset: str,
    path: Path,
    *,
    sample_rows: int | None = None,
) -> dict[str, Any]:
    """Build one source-count comparison row."""
    raw, normalized = load_normalized_source(source_dataset, path, sample_rows=sample_rows)
    total_records = len(raw)
    doi_stats = duplicate_stats(normalized["doi"])
    title_keys = normalized["title"].map(normalize_title_key)
    title_stats = duplicate_stats(title_keys)
    estimated_unique, method = estimate_unique_publications(
        total_records=total_records,
        doi_stats=doi_stats,
        title_stats=title_stats,
    )

    doi_coverage = (doi_stats["non_missing"] / total_records * 100) if total_records else 0.0
    title_coverage = (title_stats["non_missing"] / total_records * 100) if total_records else 0.0

    return {
        "source_dataset": source_dataset,
        "input_file": str(path),
        "total_records": int(total_records),
        "total_columns": int(raw.shape[1]),
        "doi_non_missing": doi_stats["non_missing"],
        "doi_coverage_pct": round(doi_coverage, 2),
        "unique_doi_count": doi_stats["unique_count"],
        "duplicate_doi_values": doi_stats["duplicate_values"],
        "duplicate_doi_records": doi_stats["duplicate_records"],
        "title_non_missing": title_stats["non_missing"],
        "title_coverage_pct": round(title_coverage, 2),
        "unique_title_count": title_stats["unique_count"],
        "duplicate_title_values": title_stats["duplicate_values"],
        "duplicate_title_records": title_stats["duplicate_records"],
        "estimated_unique_publications": int(estimated_unique),
        "estimation_method": method,
    }


def compare_publication_counts(
    input_paths: dict[str, Path],
    *,
    sample_rows: int | None = None,
) -> pd.DataFrame:
    """Compare raw and estimated unique publication counts across sources."""
    rows = [
        source_count_row(source_dataset, Path(path), sample_rows=sample_rows)
        for source_dataset, path in input_paths.items()
    ]
    return pd.DataFrame(rows)


def write_publication_count_report(report: pd.DataFrame, output_csv: Path) -> Path:
    """Write the publication count comparison CSV."""
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_csv, index=False)
    return output_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare publication counts from each source dataset.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing the expected source CSV files.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=DEFAULT_OUTPUT_CSV,
        help="Path to write the publication count comparison CSV.",
    )
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=None,
        help="Read only the first N rows from each source, for quick checks.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_paths = default_input_paths(args.input_dir)
    report = compare_publication_counts(input_paths, sample_rows=args.sample_rows)
    output_csv = write_publication_count_report(report, args.output_csv)

    print(report.to_string(index=False))
    print(f"\nSaved -> {output_csv}")


if __name__ == "__main__":
    main()
