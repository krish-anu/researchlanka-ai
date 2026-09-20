#!/usr/bin/env python3
"""Run Phase 2 database integrity / ML / API tests and write structured reports.

Usage (from backend/):

    python scripts/testing/run_phase2_ml_api_tests.py
    python scripts/testing/run_phase2_ml_api_tests.py --include-legacy
    python scripts/testing/run_phase2_ml_api_tests.py --report-dir data/reports/phase2_ml_api_tests

Artifacts:
  - latest_results.csv / latest_report.md / latest_summary.json
  - latest_api_matrix.csv / latest_api_matrix.md
    (Test ID | Endpoint | Scenario | Expected | Result)
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
        default=BACKEND_ROOT / "data" / "reports" / "phase2_ml_api_tests",
    )
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="Also run related existing ML/API/DB suites.",
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("pytest_args", nargs="*")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)

    targets = ["tests/phase2"]
    if args.include_legacy:
        targets.extend(
            [
                "tests/test_database_loader.py",
                "tests/test_hierarchical_linear_svm.py",
                "tests/test_classification_model_comparison.py",
                "tests/test_nmf_topic_endpoints.py",
                "tests/test_publication_text_embeddings.py",
                "tests/test_api_service.py",
                "tests/test_model_fastapi_endpoints.py",
            ]
        )

    pytest_args = [
        *targets,
        "--phase2-report",
        f"--phase2-report-dir={args.report_dir}",
    ]
    if not args.include_legacy:
        pytest_args = [
            "tests/phase2",
            "--phase2-report",
            f"--phase2-report-dir={args.report_dir}",
        ]
    if args.quiet:
        pytest_args.append("-q")
    pytest_args.extend(args.pytest_args)

    print("Running:", " ".join(pytest_args))
    code = pytest.main(pytest_args)
    print(f"\nReport: {args.report_dir / 'latest_report.md'}")
    print(f"API matrix: {args.report_dir / 'latest_api_matrix.md'}")
    print(f"CSV: {args.report_dir / 'latest_results.csv'}")
    return int(code)


if __name__ == "__main__":
    sys.exit(main())
