#!/usr/bin/env python3
"""Run Phase 1 ETL/data-integration tests and write structured reports.

Usage (from backend/):

    python scripts/testing/run_phase1_pipeline_tests.py
    python scripts/testing/run_phase1_pipeline_tests.py --include-legacy
    python scripts/testing/run_phase1_pipeline_tests.py --report-dir data/reports/phase1_pipeline_tests

Reports are written to CSV (machine table), Markdown (human document), and JSON
(summary) under the report directory. ``latest_*`` copies are always refreshed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=BACKEND_ROOT / "data" / "reports" / "phase1_pipeline_tests",
        help="Where to write CSV/Markdown/JSON results.",
    )
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="Also run related existing tests (author, institution, dedup, loader, framework).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Pass -q to pytest.",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Extra args forwarded to pytest.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_dir = args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    targets = ["tests/phase1"]
    if args.include_legacy:
        targets.extend(
            [
                "tests/test_author_disambiguation.py",
                "tests/test_institution_normalization.py",
                "tests/test_deduplication_thresholds.py",
                "tests/test_database_loader.py",
                "tests/test_normalize_doi.py",
                "tests/test_crossref_normalizer.py",
                "tests/test_build_final_common_dataset.py",
                "tests/test_kaggle_merge_common_dataset.py",
                "tests/test_research_analytics_framework.py",
            ]
        )

    pytest_args = [
        *targets,
        "--phase1-report",
        f"--phase1-report-dir={report_dir}",
        "-m",
        "phase1 or cleaning or preprocessing or transforming or deduplication "
        "or disambiguation or entity_resolution or e2e_ingestion or dagster or database",
    ]
    # When targeting phase1/ only, marker filter can be relaxed — still collect all phase1 files.
    if not args.include_legacy:
        pytest_args = [
            "tests/phase1",
            "--phase1-report",
            f"--phase1-report-dir={report_dir}",
        ]
    if args.quiet:
        pytest_args.append("-q")
    pytest_args.extend(args.pytest_args)

    print("Running:", " ".join(pytest_args))
    code = pytest.main(pytest_args)
    latest = report_dir / "latest_report.md"
    if latest.exists():
        print(f"\nReport: {latest}")
        print(f"CSV:    {report_dir / 'latest_results.csv'}")
        print(f"JSON:   {report_dir / 'latest_summary.json'}")
    return int(code)


if __name__ == "__main__":
    sys.exit(main())
