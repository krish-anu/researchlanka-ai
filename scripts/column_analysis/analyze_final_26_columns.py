"""Analyze columns 51-76 of the 76-column common publications dataset.

Usage from the project root:
    python scripts/column_analysis/analyze_final_26_columns.py
    python scripts/column_analysis/analyze_final_26_columns.py --report-dir data/reports/column_analysis
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


FINAL_26_BLOCK = ColumnBlock(
    name="final_26",
    range_label="51-76",
    columns=COMMON_COLUMNS[50:],
    start_position=51,
    decisions={
        "oa_status": "keep",
        "is_oa": "keep",
        "cited_by_count": "rename to citation_count",
        "is_referenced_by_count": "move to count-audit sidecar",
        "reference_count": "keep",
        "referenced_works_count": "move to count-audit sidecar",
        "references_json": "move to reference sidecar",
        "concepts": "keep",
        "topics": "keep",
        "primary_topic": "keep",
        "primary_field": "keep",
        "primary_subfield": "keep",
        "primary_domain": "keep",
        "funder_name": "keep",
        "funder_doi": "keep: normalize DOI values",
        "funder_id": "rename to funder_identifier",
        "funder_award": "keep",
        "event_name": "drop from main: optional sidecar only",
        "event_acronym": "drop from main",
        "event_location": "drop from main: optional sidecar only",
        "event_start_date": "drop from main: optional sidecar only",
        "event_end_date": "drop from main: optional sidecar only",
        "event_sponsor": "drop from main",
        "source_set_specs": "keep",
        "raw_identifiers": "keep",
        "raw_source_json": "drop: empty/raw audit payload",
    },
    pair_checks=[
        ("cited_by_count", "is_referenced_by_count"),
        ("reference_count", "referenced_works_count"),
        ("topics", "primary_topic"),
        ("primary_field", "primary_domain"),
        ("funder_doi", "funder_id"),
        ("event_start_date", "event_end_date"),
    ],
)


def main() -> None:
    args = parse_args("Analyze columns 51-76 of the common dataset.")
    run_analysis(
        FINAL_26_BLOCK,
        csv_path=args.csv,
        chunk_size=args.chunk_size,
        report_dir=args.report_dir,
    )


if __name__ == "__main__":
    main()
