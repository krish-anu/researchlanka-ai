#!/usr/bin/env python3
"""Collect rough backend line coverage via stdlib trace (no pytest-cov needed).

Writes data/reports/coverage/backend_coverage_trace.json
"""

from __future__ import annotations

import json
import linecache
import os
import runpy
import sys
import trace
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = BACKEND_ROOT / "src"
OUT_DIR = BACKEND_ROOT / "data" / "reports" / "coverage"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(BACKEND_ROOT)
    sys.path.insert(0, str(BACKEND_ROOT))

    tracer = trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])

    def _run():
        # Import pytest and run phase suites.
        import pytest

        return pytest.main(
            [
                "tests/phase1",
                "tests/phase2",
                "tests/phase3",
                "--phase1-report",
                "--phase2-report",
                "--phase3-report",
                "-q",
                "-p",
                "no:cacheprovider",
            ]
        )

    result = tracer.runfunc(_run)
    results = tracer.results()

    statements = 0
    covered = 0
    per_file: dict[str, dict] = {}
    for (filename, lineno), count in results.counts.items():
        path = Path(filename)
        try:
            path.resolve().relative_to(SRC_ROOT.resolve())
        except ValueError:
            continue
        if path.suffix != ".py":
            continue
        key = str(path.resolve().relative_to(BACKEND_ROOT.resolve()))
        entry = per_file.setdefault(key, {"covered_lines": set(), "executed": 0})
        if count > 0:
            entry["covered_lines"].add(lineno)
            entry["executed"] += count

    # Approximate statements = max line number seen with source lines that look executable.
    for key, entry in per_file.items():
        abs_path = BACKEND_ROOT / key
        total_lines = 0
        for i, line in enumerate(abs_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            total_lines += 1
        covered_n = len(entry["covered_lines"])
        statements += total_lines
        covered += min(covered_n, total_lines)
        entry["statements"] = total_lines
        entry["covered"] = min(covered_n, total_lines)
        entry["covered_lines"] = sorted(entry["covered_lines"])

    pct = round((covered / statements * 100.0), 2) if statements else 0.0
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tool": "stdlib.trace (approximate line coverage over phase1/2/3 run)",
        "pytest_exit_code": int(result or 0),
        "totals": {
            "num_statements": statements,
            "covered_lines": covered,
            "percent_covered": pct,
            "num_branches": None,
            "covered_branches": None,
            "note": "Branch % not available without pytest-cov/coverage.py",
        },
        "files_sampled": len(per_file),
    }
    out = OUT_DIR / "backend_coverage.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload["totals"], indent=2))
    print(f"Wrote {out}")
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())
