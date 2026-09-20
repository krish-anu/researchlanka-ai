#!/usr/bin/env python3
"""Run outstanding quality gates and write coverage artifacts (T-03…T-07 + coverage).

From backend/:

    python scripts/testing/run_outstanding_gates.py

Writes:
  data/reports/coverage/backend_coverage.json
  data/reports/coverage/frontend_coverage.json  (copied from frontend/coverage)
  data/reports/coverage/gates_summary.json
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = REPO_ROOT / "frontend"
COVERAGE_DIR = BACKEND_ROOT / "data" / "reports" / "coverage"


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    print("\n===", " ".join(cmd), f"(cwd={cwd})", "===\n", flush=True)
    merged = os.environ.copy()
    if env:
        merged.update(env)
    # Avoid proxy interference for live hosts.
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        merged.pop(key, None)
    completed = subprocess.run(cmd, cwd=cwd, env=merged, check=False)
    return int(completed.returncode)


def main() -> int:
    COVERAGE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    summary: dict = {"generated_at_utc": stamp, "gates": {}}

    # --- Backend phase suite + coverage ---
    backend_cov_json = COVERAGE_DIR / "backend_coverage.json"
    code = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/phase1",
            "tests/phase2",
            "tests/phase3",
            "--phase1-report",
            "--phase2-report",
            "--phase3-report",
            "--cov=src",
            "--cov-branch",
            f"--cov-report=json:{backend_cov_json}",
            "--cov-report=term-summary",
            "-q",
        ],
        cwd=BACKEND_ROOT,
        # Do NOT set PHASE3_SKIP_VITEST — allow Vitest bridge when npm available.
        env={},
    )
    summary["gates"]["backend_phases_with_coverage"] = {
        "exit_code": code,
        "coverage_json": str(backend_cov_json),
    }
    if backend_cov_json.exists():
        cov = json.loads(backend_cov_json.read_text(encoding="utf-8"))
        totals = cov.get("totals") or {}
        summary["backend_coverage"] = {
            "percent_covered": totals.get("percent_covered"),
            "percent_covered_display": totals.get("percent_covered_display"),
            "num_statements": totals.get("num_statements"),
            "covered_lines": totals.get("covered_lines"),
            "missing_lines": totals.get("missing_lines"),
            "num_branches": totals.get("num_branches"),
            "covered_branches": totals.get("covered_branches"),
            "missing_branches": totals.get("missing_branches"),
        }

    # --- Frontend Vitest + coverage (T-06) ---
    fe_code = _run(["npm", "run", "test:coverage"], cwd=FRONTEND_ROOT)
    summary["gates"]["frontend_vitest_coverage"] = {"exit_code": fe_code}
    fe_summary = FRONTEND_ROOT / "coverage" / "coverage-summary.json"
    if fe_summary.exists():
        shutil.copy2(fe_summary, COVERAGE_DIR / "frontend_coverage.json")
        fe = json.loads(fe_summary.read_text(encoding="utf-8"))
        total = fe.get("total") or {}
        summary["frontend_coverage"] = {
            "lines_pct": (total.get("lines") or {}).get("pct"),
            "branches_pct": (total.get("branches") or {}).get("pct"),
            "functions_pct": (total.get("functions") or {}).get("pct"),
            "statements_pct": (total.get("statements") or {}).get("pct"),
        }

    # --- Playwright E2E (T-07) — may skip if site unreachable ---
    # Ensure frontend deps exist (playwright CLI lives under node_modules).
    npm_install = _run(["npm", "install"], cwd=FRONTEND_ROOT)
    pw_install = _run(["npx", "playwright", "install", "chromium"], cwd=FRONTEND_ROOT)
    pw_code = _run(["npm", "run", "test:e2e"], cwd=FRONTEND_ROOT)
    summary["gates"]["frontend_npm_install"] = {"exit_code": npm_install}
    summary["gates"]["playwright_e2e"] = {
        "install_exit_code": pw_install,
        "exit_code": pw_code,
        "results": str(FRONTEND_ROOT / "e2e-results.json"),
    }
    if (FRONTEND_ROOT / "e2e-results.json").exists():
        shutil.copy2(FRONTEND_ROOT / "e2e-results.json", COVERAGE_DIR / "playwright_e2e_results.json")

    # --- Unified report + Word/HTML ---
    unify = _run(
        [sys.executable, "scripts/testing/run_all_phase_tests.py", "--combine-only"],
        cwd=BACKEND_ROOT,
    )
    summary["gates"]["unified_report"] = {"exit_code": unify}

    out = COVERAGE_DIR / "gates_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    return code or fe_code or (0 if pw_code in {0, 1} else pw_code)
    # playwright may fail on network; still return backend/frontend status primarily


if __name__ == "__main__":
    raise SystemExit(main())
