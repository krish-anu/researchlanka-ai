#!/usr/bin/env python3
"""Run Phase 3 overall application tests and write structured reports.

Usage (from backend/):

    python scripts/testing/run_phase3_overall_tests.py
    python scripts/testing/run_phase3_overall_tests.py --with-frontend
    python scripts/testing/run_phase3_overall_tests.py --report-dir data/reports/phase3_overall_tests

Artifacts:
  - latest_results.csv / latest_report.md / latest_summary.json
  - latest_security_matrix.csv / latest_security_matrix.md
    (Test ID | Endpoint | Scenario | Expected | Result)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = REPO_ROOT / "frontend"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=BACKEND_ROOT / "data" / "reports" / "phase3_overall_tests",
    )
    parser.add_argument(
        "--with-frontend",
        action="store_true",
        help="Also run frontend Vitest suite and print a summary line.",
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("pytest_args", nargs="*")
    return parser.parse_args()


def run_frontend_vitest() -> int:
    if not FRONTEND_ROOT.exists():
        print(f"Frontend root missing: {FRONTEND_ROOT}")
        return 1
    cmd = ["npm", "test", "--silent"]
    print("Running frontend:", " ".join(cmd), f"(cwd={FRONTEND_ROOT})")
    completed = subprocess.run(cmd, cwd=FRONTEND_ROOT, check=False)
    return int(completed.returncode)


def main() -> int:
    args = parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)

    pytest_args = [
        "tests/phase3",
        "--phase3-report",
        f"--phase3-report-dir={args.report_dir}",
    ]
    if args.quiet:
        pytest_args.append("-q")
    pytest_args.extend(args.pytest_args)

    print("Running:", " ".join(pytest_args))
    code = int(pytest.main(pytest_args))

    if args.with_frontend:
        frontend_code = run_frontend_vitest()
        code = code or frontend_code

    print(f"\nReport: {args.report_dir / 'latest_report.md'}")
    print(f"Security matrix: {args.report_dir / 'latest_security_matrix.md'}")
    print(f"CSV: {args.report_dir / 'latest_results.csv'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
