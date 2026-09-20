#!/usr/bin/env python3
"""Run Master Test Plan SW Testing with real pytest terminal output.

From backend/:

    python sw_testing/run.py              # all suites
    python sw_testing/run.py ui           # UI only
    python sw_testing/run.py preprocessing
    python sw_testing/run.py --list

Uses pytest's native coloured reporter (green PASSED, red FAILED, timings),
and writes:
  data/reports/sw_testing/sw_testing_results.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SW_ROOT = Path(__file__).resolve().parent
SUITE_DIR = SW_ROOT / "software_testing"
OUT_DIR = BACKEND_ROOT / "data" / "reports" / "sw_testing"

os.environ.setdefault("PY_COLORS", "1")
os.environ.setdefault("FORCE_COLOR", "1")

# suite key -> (label, test file name)
SUITES: dict[str, tuple[str, str]] = {
    "integrity": (
        "3.1.1 Data and Database Integrity (live/sample extras)",
        "test_data_database_integrity.py",
    ),
    "preprocessing": (
        "3.1.2 Preprocessing unit tests",
        "test_preprocessing_unit.py",
    ),
    "deploy": (
        "3.1.10 Deployment and CI/CD",
        "test_deployment_cicd.py",
    ),
    "config": (
        "3.1.11 Configuration and Compatibility",
        "test_configuration_compatibility.py",
    ),
}

ALIASES: dict[str, str] = {
    "all": "all",
    "db": "integrity",
    "database": "integrity",
    "pre": "preprocessing",
    "prep": "preprocessing",
    "cicd": "deploy",
    "deployment": "deploy",
    "compatibility": "config",
}

CATEGORY_BY_FILE = {filename: label for label, filename in SUITES.values()}


class _CsvCollector:
    """Silent plugin: collect outcomes for CSV + category summary."""

    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.by_category: Counter[str] = Counter()
        self.failed_by_category: Counter[str] = Counter()

    def pytest_collection_modifyitems(self, items):  # noqa: ANN001
        self.total = len(items)

    def pytest_runtest_logreport(self, report):  # noqa: ANN001
        if report.when != "call" and not (report.when == "setup" and report.skipped):
            return
        if report.when == "setup" and report.passed:
            return

        nodeid = report.nodeid
        display = (
            nodeid[nodeid.index("sw_testing/") :]
            if "sw_testing/" in nodeid
            else nodeid
        )
        filename = Path(display.split("::", 1)[0]).name
        category = CATEGORY_BY_FILE.get(filename, "unmapped")

        if report.passed and report.when == "call":
            outcome = "passed"
            self.passed += 1
            self.by_category[category] += 1
        elif report.failed:
            outcome = "failed"
            self.failed += 1
            self.failed_by_category[category] += 1
        elif report.skipped:
            outcome = "skipped"
            self.skipped += 1
        else:
            return

        message = str(report.longrepr)[:500] if report.longrepr else ""
        self.rows.append(
            {
                "category": category,
                "nodeid": display,
                "outcome": outcome,
                "duration_seconds": f"{getattr(report, 'duration', 0):.6f}",
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


def _resolve_targets(names: list[str]) -> list[Path]:
    if not names or names == ["all"]:
        return [SUITE_DIR]

    paths: list[Path] = []
    unknown: list[str] = []
    for raw in names:
        key = ALIASES.get(raw.lower(), raw.lower())
        if key == "all":
            return [SUITE_DIR]
        if key not in SUITES:
            unknown.append(raw)
            continue
        _label, filename = SUITES[key]
        path = SUITE_DIR / filename
        if path not in paths:
            paths.append(path)
    if unknown:
        known = ", ".join(sorted(SUITES))
        raise SystemExit(
            f"Unknown suite(s): {', '.join(unknown)}\n"
            f"Known suites: {known}\n"
            f"Aliases: {', '.join(sorted(ALIASES))}"
        )
    return paths


def _print_list() -> None:
    print("Available suites (run separately or together):\n")
    print(f"  {'key':<16} {'aliases / notes'}")
    print(f"  {'-'*16} {'-'*40}")
    print(f"  {'all':<16} run every suite (default)")
    for key, (label, filename) in SUITES.items():
        aliases = [a for a, target in ALIASES.items() if target == key]
        alias_txt = f"aliases: {', '.join(aliases)}" if aliases else ""
        print(f"  {key:<16} {label}")
        print(f"  {'':<16} file: {filename}  {alias_txt}")
    print()
    print("Examples:")
    print("  python sw_testing/run.py")
    print("  python sw_testing/run.py ui")
    print("  python sw_testing/run.py preprocessing")
    print("  python sw_testing/run.py ml security")
    print("  pytest tests/data_integrity -v")
    print("  pytest tests/data_collection_etl -v")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ResearchLanka Master Test Plan SW Testing runner",
    )
    parser.add_argument(
        "suites",
        nargs="*",
        default=["all"],
        help="Suite keys to run (default: all). Use --list to see options.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available suites and exit",
    )
    args = parser.parse_args(argv)

    if args.list:
        _print_list()
        return 0

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    targets = _resolve_targets(args.suites)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    collector = _CsvCollector()

    selected = (
        "all"
        if targets == [SUITE_DIR]
        else ", ".join(args.suites)
    )

    print()
    print("=" * 78)
    print(" ResearchLanka — Master Test Plan SW Testing")
    print(f" Selected: {selected}")
    print("=" * 78)
    print()

    code = pytest.main(
        [
            *[str(path) for path in targets],
            "-v",
            "--color=yes",
            "--tb=short",
            "-ra",
        ],
        plugins=[collector],
    )

    suffix = "all" if targets == [SUITE_DIR] else "_".join(
        ALIASES.get(s.lower(), s.lower()) for s in args.suites
    )
    csv_path = OUT_DIR / (
        "sw_testing_results.csv"
        if suffix == "all"
        else f"sw_testing_results_{suffix}.csv"
    )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "category",
                "nodeid",
                "outcome",
                "duration_seconds",
                "message",
                "timestamp",
            ],
        )
        writer.writeheader()
        writer.writerows(collector.rows)

    # Always refresh the combined latest pointer when running all.
    if suffix == "all":
        latest = OUT_DIR / "sw_testing_results.csv"
        if csv_path != latest:
            latest.write_bytes(csv_path.read_bytes())

    print()
    print("-" * 78)
    print(
        f" summary: total={collector.total}  passed={collector.passed}  "
        f"failed={collector.failed}  skipped={collector.skipped}"
    )
    if collector.by_category:
        print(" passed by category:")
        for category, count in sorted(collector.by_category.items()):
            print(f"   {category}: {count}")
    if collector.failed_by_category:
        print(" failed by category:")
        for category, count in collector.failed_by_category.items():
            print(f"   {category}: {count}")
    print(f" results CSV: {csv_path}")
    print("=" * 78)
    print()
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
