"""Print summary tables for a common-dataset CSV.

Reads the file in chunks so it works on the full merged dataset without loading
it into memory. Prints five tables:

    1. Dataset overview
    2. Column profile: coverage, distinct values, example
    3. Coverage by source dataset
    4. Value counts for key categorical columns
    5. Duplicate-column detection

Usage from the project root:
    python scripts/profile_common_dataset.py
    python scripts/profile_common_dataset.py --csv data/processed/common/common_publications_final.csv
    python scripts/profile_common_dataset.py --report-dir data/reports/profile

Use --report-dir to also write each table to CSV, and --value-counts to control
how many top values are shown per categorical column.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[1] if SCRIPT_PATH.parent.name == "scripts" else Path.cwd()
DEFAULT_CSV = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_deduplicated.csv"

BLANK_STRINGS = {"", "nan", "none", "null", "na", "n/a", "[]", "{}"}

# Columns worth a value-count table. Missing ones are skipped.
CATEGORICAL_COLUMNS = [
    "source_dataset",
    "type",
    "publication_year",
    "primary_field",
    "primary_domain",
    "oa_status",
    "language",
    "publisher",
    "journal",
    "source_type",
]

# Pairs checked for exact value equality, to find redundant columns.
DUPLICATE_CANDIDATES = [
    ("url", "landing_page_url"),
    ("journal", "container_title"),
    ("journal", "source_name"),
    ("container_title", "source_name"),
    ("type", "publication_type"),
    ("authors", "author_names"),
    ("issn", "issn_l"),
    ("cited_by_count", "is_referenced_by_count"),
    ("reference_count", "referenced_works_count"),
    ("publication_date", "published_date"),
    ("created_date", "published_date"),
]


def nonblank_mask(series: pd.Series) -> pd.Series:
    """Mark cells that hold a real value rather than a blank placeholder."""
    normalized = series.astype("string").str.strip().str.lower()
    return normalized.notna() & ~normalized.isin(BLANK_STRINGS)


def render_table(frame: pd.DataFrame, title: str, *, max_width: int = 60) -> str:
    """Render a DataFrame as an aligned text table."""
    if frame.empty:
        return f"\n{title}\n{'=' * len(title)}\n  (no rows)\n"

    display = frame.copy()
    for column in display.columns:
        display[column] = display[column].map(
            lambda value: format_cell(value, max_width=max_width)
        )

    widths = {
        column: max(len(str(column)), *(len(v) for v in display[column]))
        for column in display.columns
    }
    numeric = {
        column: pd.api.types.is_numeric_dtype(frame[column]) for column in frame.columns
    }

    def row_text(values: list[str]) -> str:
        cells = []
        for column, value in zip(display.columns, values):
            cells.append(
                value.rjust(widths[column]) if numeric[column] else value.ljust(widths[column])
            )
        return "  ".join(cells).rstrip()

    lines = [f"\n{title}", "=" * len(title)]
    lines.append(row_text([str(c) for c in display.columns]))
    lines.append("-" * min(sum(widths.values()) + 2 * (len(widths) - 1), 160))
    for _, row in display.iterrows():
        lines.append(row_text([row[column] for column in display.columns]))
    return "\n".join(lines) + "\n"


def format_cell(value: Any, *, max_width: int) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NA:
        return ""
    if isinstance(value, float):
        text = f"{value:,.2f}"
    elif isinstance(value, (int,)) and not isinstance(value, bool):
        text = f"{value:,}"
    else:
        text = str(value)
    text = " ".join(text.split())
    if len(text) > max_width:
        text = text[: max_width - 1] + "…"
    return text


class DatasetProfile:
    """Accumulates summary statistics across chunks of one CSV."""

    def __init__(self, *, value_counts: int, sample_distinct: int) -> None:
        self.value_counts = value_counts
        self.sample_distinct = sample_distinct
        self.columns: list[str] = []
        self.total_rows = 0
        self.nonblank: Counter[str] = Counter()
        self.distinct_sample: dict[str, set[str]] = defaultdict(set)
        self.example: dict[str, str] = {}
        self.byte_width: Counter[str] = Counter()
        self.source_totals: Counter[str] = Counter()
        self.source_nonblank: dict[str, Counter[str]] = defaultdict(Counter)
        self.category_counts: dict[str, Counter[str]] = defaultdict(Counter)
        self.pair_both: Counter[tuple[str, str]] = Counter()
        self.pair_equal: Counter[tuple[str, str]] = Counter()

    def add_chunk(self, chunk: pd.DataFrame) -> None:
        if not self.columns:
            self.columns = list(chunk.columns)
        self.total_rows += len(chunk)

        primary_source = None
        if "source_dataset" in chunk.columns:
            primary_source = (
                chunk["source_dataset"].astype("string").str.split(";").str[0].str.strip()
            )
            self.source_totals.update(primary_source.dropna().tolist())

        for column in self.columns:
            values = chunk[column]
            mask = nonblank_mask(values)
            count = int(mask.sum())
            self.nonblank[column] += count
            if not count:
                continue

            present = values[mask].astype(str)
            self.byte_width[column] += int(present.str.len().sum())

            if column not in self.example:
                self.example[column] = present.iloc[0]
            if len(self.distinct_sample[column]) < self.sample_distinct:
                self.distinct_sample[column].update(present.head(self.sample_distinct).tolist())
            if primary_source is not None:
                self.source_nonblank[column].update(primary_source[mask].dropna().tolist())

        for column in CATEGORICAL_COLUMNS:
            if column in chunk.columns:
                mask = nonblank_mask(chunk[column])
                self.category_counts[column].update(chunk.loc[mask, column].astype(str).tolist())

        for left, right in DUPLICATE_CANDIDATES:
            if left not in chunk.columns or right not in chunk.columns:
                continue
            left_values = chunk[left].astype("string").str.strip()
            right_values = chunk[right].astype("string").str.strip()
            both = nonblank_mask(chunk[left]) & nonblank_mask(chunk[right])
            self.pair_both[(left, right)] += int(both.sum())
            self.pair_equal[(left, right)] += int(
                (left_values[both] == right_values[both]).sum()
            )

    def overview_table(self, csv_path: Path) -> pd.DataFrame:
        size_mb = csv_path.stat().st_size / 1e6
        total_bytes = sum(self.byte_width.values()) or 1
        heaviest = self.byte_width.most_common(1)
        rows = [
            {"metric": "file", "value": str(csv_path)},
            {"metric": "file_size_mb", "value": f"{size_mb:,.1f}"},
            {"metric": "rows", "value": f"{self.total_rows:,}"},
            {"metric": "columns", "value": f"{len(self.columns):,}"},
        ]
        if heaviest:
            column, width = heaviest[0]
            rows.append(
                {
                    "metric": "widest_column",
                    "value": f"{column} ({100 * width / total_bytes:.1f}% of all text)",
                }
            )
        empty = [c for c in self.columns if not self.nonblank[c]]
        rows.append({"metric": "fully_empty_columns", "value": ", ".join(empty) or "none"})
        return pd.DataFrame(rows)

    def column_table(self) -> pd.DataFrame:
        total_bytes = sum(self.byte_width.values()) or 1
        rows = []
        for position, column in enumerate(self.columns, start=1):
            count = self.nonblank[column]
            rows.append(
                {
                    "pos": position,
                    "column": column,
                    "non_blank": count,
                    "coverage_pct": round(100 * count / self.total_rows, 2)
                    if self.total_rows
                    else 0.0,
                    "distinct_sample": len(self.distinct_sample[column]),
                    "pct_of_text": round(100 * self.byte_width[column] / total_bytes, 1),
                    "example": self.example.get(column, ""),
                }
            )
        return pd.DataFrame(rows)

    def source_table(self) -> pd.DataFrame:
        if not self.source_totals:
            return pd.DataFrame()
        sources = sorted(self.source_totals)
        rows = []
        for column in self.columns:
            row: dict[str, Any] = {"column": column}
            for source in sources:
                total = self.source_totals[source]
                hit = self.source_nonblank[column][source]
                row[source] = round(100 * hit / total, 1) if total else 0.0
            rows.append(row)
        return pd.DataFrame(rows)

    def category_tables(self) -> dict[str, pd.DataFrame]:
        tables: dict[str, pd.DataFrame] = {}
        for column, counts in self.category_counts.items():
            if not counts:
                continue
            total = sum(counts.values())
            rows = [
                {
                    "value": value,
                    "rows": count,
                    "pct_of_non_blank": round(100 * count / total, 2),
                }
                for value, count in counts.most_common(self.value_counts)
            ]
            frame = pd.DataFrame(rows)
            frame.attrs["distinct"] = len(counts)
            tables[column] = frame
        return tables

    def duplicate_table(self) -> pd.DataFrame:
        rows = []
        for pair, both in self.pair_both.items():
            if not both:
                continue
            equal = self.pair_equal[pair]
            pct = 100 * equal / both
            rows.append(
                {
                    "column_a": pair[0],
                    "column_b": pair[1],
                    "both_present": both,
                    "identical": equal,
                    "identical_pct": round(pct, 1),
                    "verdict": "EXACT DUPLICATE - drop one" if pct >= 99.9 else "keep both",
                }
            )
        frame = pd.DataFrame(rows)
        return frame.sort_values("identical_pct", ascending=False) if not frame.empty else frame


def build_profile(csv_path: Path, *, chunk_size: int, value_counts: int, sample_distinct: int) -> DatasetProfile:
    profile = DatasetProfile(value_counts=value_counts, sample_distinct=sample_distinct)
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size, dtype="object", low_memory=False):
        profile.add_chunk(chunk)
        print(f"  ...scanned {profile.total_rows:,} rows", flush=True)
    return profile


def write_report(report_dir: Path, tables: dict[str, pd.DataFrame]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        if not frame.empty:
            frame.to_csv(report_dir / f"{name}.csv", index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print summary tables for a common-dataset CSV.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="CSV file to profile.")
    parser.add_argument("--chunk-size", type=int, default=25_000, help="Rows read per chunk.")
    parser.add_argument("--value-counts", type=int, default=12, help="Top values per categorical column.")
    parser.add_argument("--sample-distinct", type=int, default=200, help="Cap on sampled distinct values.")
    parser.add_argument("--min-coverage", type=float, default=None, help="Only show columns at or below this coverage percent.")
    parser.add_argument("--report-dir", type=Path, default=None, help="Also write each table to CSV here.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.csv.exists():
        raise SystemExit(f"CSV not found: {args.csv}")

    print(f"Profiling {args.csv} ...", flush=True)
    profile = build_profile(
        args.csv,
        chunk_size=args.chunk_size,
        value_counts=args.value_counts,
        sample_distinct=args.sample_distinct,
    )

    column_table = profile.column_table().sort_values("coverage_pct")
    if args.min_coverage is not None:
        column_table = column_table.loc[column_table["coverage_pct"] <= args.min_coverage]

    print(render_table(profile.overview_table(args.csv), "1. DATASET OVERVIEW", max_width=90))
    print(render_table(column_table, "2. COLUMN PROFILE (lowest coverage first)"))

    source_table = profile.source_table()
    if not source_table.empty:
        print(render_table(source_table, "3. COVERAGE BY SOURCE DATASET (% of that source's rows)"))

    category_tables = profile.category_tables()
    for column, frame in category_tables.items():
        distinct = frame.attrs.get("distinct", len(frame))
        print(render_table(frame, f"4. VALUE COUNTS - {column} ({distinct:,} distinct)"))

    duplicate_table = profile.duplicate_table()
    if not duplicate_table.empty:
        print(render_table(duplicate_table, "5. DUPLICATE COLUMN DETECTION"))

    if args.report_dir:
        tables = {
            "overview": profile.overview_table(args.csv),
            "column_profile": profile.column_table(),
            "coverage_by_source": source_table,
            "duplicate_columns": duplicate_table,
        }
        tables.update({f"values_{c}": f for c, f in category_tables.items()})
        write_report(args.report_dir, tables)
        print(f"Wrote {len(tables)} tables to {args.report_dir}")


if __name__ == "__main__":
    main()
