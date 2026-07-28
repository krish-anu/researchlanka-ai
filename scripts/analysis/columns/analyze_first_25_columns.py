"""Analyze columns 1-25 of the 76-column common publications dataset.

This file also holds the shared column-block profiling engine used by the
second-25 and final-26 wrappers, keeping the folder to the three requested
analysis files.

Usage from the project root:
    python scripts/analysis/columns/analyze_first_25_columns.py
    python scripts/analysis/columns/analyze_first_25_columns.py --report-dir data/reports/column_analysis
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
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

from scripts.processing.kaggle_merge_common_dataset import COMMON_COLUMNS  # noqa: E402


DEFAULT_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_deduplicated.csv"
BLANK_STRINGS = {"", "nan", "none", "null", "na", "n/a", "[]", "{}"}


@dataclass(frozen=True)
class ColumnBlock:
    name: str
    range_label: str
    columns: list[str]
    start_position: int
    decisions: dict[str, str]
    pair_checks: list[tuple[str, str]]


FIRST_25_BLOCK = ColumnBlock(
    name="first_25",
    range_label="1-25",
    columns=COMMON_COLUMNS[:25],
    start_position=1,
    decisions={
        "source_dataset": "keep",
        "source_institution_id": "keep",
        "source_record_id": "keep",
        "source_datestamp": "keep",
        "openalex_id": "keep",
        "doi": "keep",
        "url": "keep",
        "landing_page_url": "drop: duplicate of url",
        "pdf_url": "keep",
        "title": "keep",
        "subtitle": "drop: too sparse",
        "original_title": "drop: too sparse",
        "abstract": "keep",
        "keywords": "keep",
        "publication_year": "keep: validate year range",
        "publication_date": "keep",
        "created_date": "drop from main: no coverage beyond publication_date",
        "published_date": "drop from main: no coverage beyond publication_date",
        "type": "keep: harmonize values",
        "subtype": "drop: too sparse",
        "publication_type": "drop: duplicate of type",
        "authors": "keep",
        "author_count": "keep",
        "author_names": "drop: duplicate of authors",
        "author_affiliations": "keep",
    },
    pair_checks=[
        ("url", "landing_page_url"),
        ("publication_date", "created_date"),
        ("publication_date", "published_date"),
        ("created_date", "published_date"),
        ("type", "publication_type"),
        ("authors", "author_names"),
    ],
)


def nonblank_mask(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.lower()
    return normalized.notna() & ~normalized.isin(BLANK_STRINGS)


def clean_example(value: Any, *, width: int = 100) -> str:
    if value is None or value is pd.NA:
        return ""
    return " ".join(str(value).split())[:width]


def profile_columns(
    csv_path: Path,
    block: ColumnBlock,
    *,
    chunk_size: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    usecols = list(dict.fromkeys(["source_dataset", *block.columns]))
    total_rows = 0
    present_counts: Counter[str] = Counter()
    distinct_values: dict[str, set[str]] = defaultdict(set)
    multivalue_counts: Counter[str] = Counter()
    examples: dict[str, str] = {}
    source_totals: Counter[str] = Counter()
    source_present: dict[str, Counter[str]] = defaultdict(Counter)
    pair_both: Counter[tuple[str, str]] = Counter()
    pair_equal: Counter[tuple[str, str]] = Counter()
    pair_left_only: Counter[tuple[str, str]] = Counter()
    pair_right_only: Counter[tuple[str, str]] = Counter()

    for chunk in pd.read_csv(
        csv_path,
        usecols=usecols,
        dtype="object",
        chunksize=chunk_size,
        low_memory=False,
    ):
        total_rows += len(chunk)
        primary_source = chunk["source_dataset"].astype("string").str.split(";").str[0].str.strip()
        source_totals.update(primary_source.dropna().tolist())

        for column in block.columns:
            mask = nonblank_mask(chunk[column])
            present_counts[column] += int(mask.sum())
            source_present[column].update(primary_source[mask].dropna().tolist())
            present = chunk.loc[mask, column].astype(str)
            distinct_values[column].update(present.tolist())
            multivalue_counts[column] += int(present.str.contains(";", regex=False).sum())
            if column not in examples and not present.empty:
                examples[column] = clean_example(present.iloc[0])

        for left, right in block.pair_checks:
            left_mask = nonblank_mask(chunk[left])
            right_mask = nonblank_mask(chunk[right])
            both = left_mask & right_mask
            pair_both[(left, right)] += int(both.sum())
            pair_equal[(left, right)] += int(
                (
                    chunk.loc[both, left].astype("string").str.strip()
                    == chunk.loc[both, right].astype("string").str.strip()
                ).sum()
            )
            pair_left_only[(left, right)] += int((left_mask & ~right_mask).sum())
            pair_right_only[(left, right)] += int((~left_mask & right_mask).sum())

    profile = build_profile_table(
        block,
        total_rows=total_rows,
        present_counts=present_counts,
        distinct_values=distinct_values,
        multivalue_counts=multivalue_counts,
        examples=examples,
    )
    source_coverage = build_source_coverage_table(block, source_totals, source_present)
    duplicate_checks = build_pair_check_table(
        block.pair_checks,
        pair_both=pair_both,
        pair_equal=pair_equal,
        pair_left_only=pair_left_only,
        pair_right_only=pair_right_only,
    )
    overview = pd.DataFrame(
        [
            {"metric": "csv", "value": str(csv_path)},
            {"metric": "rows", "value": total_rows},
            {"metric": "columns_analyzed", "value": len(block.columns)},
            {"metric": "column_range", "value": block.range_label},
        ]
    )

    return overview, profile, source_coverage, duplicate_checks


def build_profile_table(
    block: ColumnBlock,
    *,
    total_rows: int,
    present_counts: Counter[str],
    distinct_values: dict[str, set[str]],
    multivalue_counts: Counter[str],
    examples: dict[str, str],
) -> pd.DataFrame:
    rows = []
    for offset, column in enumerate(block.columns):
        present = present_counts[column]
        multivalue_pct = 100 * multivalue_counts[column] / present if present else 0.0
        rows.append(
            {
                "pos": block.start_position + offset,
                "column": column,
                "present": present,
                "coverage_pct": round(100 * present / total_rows, 2) if total_rows else 0.0,
                "missing": total_rows - present,
                "distinct": len(distinct_values[column]),
                "multivalue_present_pct": round(multivalue_pct, 1),
                "decision": block.decisions[column],
                "example": examples.get(column, ""),
            }
        )
    return pd.DataFrame(rows)


def build_source_coverage_table(
    block: ColumnBlock,
    source_totals: Counter[str],
    source_present: dict[str, Counter[str]],
) -> pd.DataFrame:
    rows = []
    for column in block.columns:
        row = {"column": column}
        for source, total in source_totals.items():
            row[source] = round(100 * source_present[column][source] / total, 1) if total else 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def build_pair_check_table(
    pair_checks: list[tuple[str, str]],
    *,
    pair_both: Counter[tuple[str, str]],
    pair_equal: Counter[tuple[str, str]],
    pair_left_only: Counter[tuple[str, str]],
    pair_right_only: Counter[tuple[str, str]],
) -> pd.DataFrame:
    rows = []
    for pair in pair_checks:
        both = pair_both[pair]
        rows.append(
            {
                "left_column": pair[0],
                "right_column": pair[1],
                "both_present": both,
                "equal_when_both_pct": round(100 * pair_equal[pair] / both, 2) if both else 0.0,
                "left_only": pair_left_only[pair],
                "right_only": pair_right_only[pair],
            }
        )
    return pd.DataFrame(rows)


def print_table(frame: pd.DataFrame, title: str) -> None:
    print(f"\n{title}")
    print("=" * len(title))
    print(frame.to_string(index=False))


def write_reports(report_dir: Path, block_name: str, tables: dict[str, pd.DataFrame]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.to_csv(report_dir / f"{block_name}_{name}.csv", index=False)


def run_analysis(
    block: ColumnBlock,
    *,
    csv_path: Path,
    chunk_size: int,
    report_dir: Path | None,
) -> None:
    overview, profile, source_coverage, duplicate_checks = profile_columns(
        csv_path,
        block,
        chunk_size=chunk_size,
    )
    tables = {
        "overview": overview,
        "profile": profile,
        "source_coverage": source_coverage,
        "duplicate_checks": duplicate_checks,
    }

    for title, frame in [
        ("Overview", overview),
        ("Column Profile", profile),
        ("Coverage By Primary Source", source_coverage),
        ("Duplicate And Redundancy Checks", duplicate_checks),
    ]:
        print_table(frame, title)

    if report_dir:
        write_reports(report_dir, block.name, tables)
        print(f"\nWrote reports to {report_dir}")


def parse_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--chunk-size", type=int, default=25_000)
    parser.add_argument("--report-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args("Analyze columns 1-25 of the common dataset.")
    run_analysis(
        FIRST_25_BLOCK,
        csv_path=args.csv,
        chunk_size=args.chunk_size,
        report_dir=args.report_dir,
    )


if __name__ == "__main__":
    main()
