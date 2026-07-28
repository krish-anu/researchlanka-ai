"""Analyze columns 26-50 of the 76-column common publications dataset.

Usage from the project root:
    python scripts/column_analysis/analyze_second_25_columns.py
    python scripts/column_analysis/analyze_second_25_columns.py --report-dir data/reports/column_analysis
"""

from __future__ import annotations

try:
    from analyze_first_25_columns import COMMON_COLUMNS, ColumnBlock, parse_args, run_analysis
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from scripts.column_analysis.analyze_first_25_columns import (
        COMMON_COLUMNS,
        ColumnBlock,
        parse_args,
        run_analysis,
    )


SECOND_25_BLOCK = ColumnBlock(
    name="second_25",
    range_label="26-50",
    columns=COMMON_COLUMNS[25:50],
    start_position=26,
    decisions={
        "author_orcids": "keep",
        "sri_lankan_authors": "keep: audit name quality",
        "contributors": "keep",
        "editors": "drop: too sparse",
        "institutions": "keep",
        "sri_lankan_institutions": "keep",
        "countries": "keep",
        "publisher": "keep: harmonize values",
        "publisher_location": "drop: too sparse",
        "journal": "keep: harmonize values",
        "container_title": "drop: duplicate of journal",
        "source_name": "drop: duplicate of journal",
        "source_type": "keep",
        "issn": "keep",
        "issn_l": "keep",
        "volume": "keep",
        "issue": "keep",
        "page": "drop: derivable from first_page/last_page",
        "first_page": "keep",
        "last_page": "keep",
        "article_number": "keep: validate before relying on it",
        "language": "keep: harmonize values",
        "rights": "drop: constant and sparse",
        "license": "keep",
        "license_url": "keep: normalize URLs",
    },
    pair_checks=[
        ("journal", "container_title"),
        ("journal", "source_name"),
        ("container_title", "source_name"),
        ("issn", "issn_l"),
        ("first_page", "page"),
        ("last_page", "page"),
        ("license", "license_url"),
    ],
)


def main() -> None:
    args = parse_args("Analyze columns 26-50 of the common dataset.")
    run_analysis(
        SECOND_25_BLOCK,
        csv_path=args.csv,
        chunk_size=args.chunk_size,
        report_dir=args.report_dir,
    )


if __name__ == "__main__":
    main()
