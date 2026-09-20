#!/usr/bin/env python3
"""Run Phase 1+2+3 suites, then write one unified report.

Usage (from backend/):

    python scripts/testing/run_all_phase_tests.py
    python scripts/testing/run_all_phase_tests.py -q
    PHASE3_SKIP_VITEST=1 python scripts/testing/run_all_phase_tests.py -q

Artifacts:
  - Per-phase under data/reports/phase{1,2,3}_*/
  - Unified under data/reports/unified_phase_tests/
  - Stable copies under data/processed/common/unified_testing_*
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "--skip-phase1",
        action="store_true",
        help="Reuse existing Phase 1 latest_* artifacts without re-running.",
    )
    parser.add_argument(
        "--skip-phase2",
        action="store_true",
        help="Reuse existing Phase 2 latest_* artifacts without re-running.",
    )
    parser.add_argument(
        "--skip-phase3",
        action="store_true",
        help="Reuse existing Phase 3 latest_* artifacts without re-running.",
    )
    parser.add_argument(
        "--combine-only",
        action="store_true",
        help="Only combine existing latest_* phase reports into the unified file.",
    )
    parser.add_argument(
        "--with-frontend",
        action="store_true",
        help="Forward --with-frontend to the Phase 3 runner.",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Extra args forwarded to each phase runner after --.",
    )
    return parser.parse_args()


def _run_phase(script_name: str, quiet: bool, extra: list[str], extra_flags: list[str] | None = None) -> int:
    cmd = [sys.executable, str(BACKEND_ROOT / "scripts" / "testing" / script_name)]
    if quiet:
        cmd.append("-q")
    if extra_flags:
        cmd.extend(extra_flags)
    if extra:
        cmd.extend(extra)
    print("\n===", " ".join(cmd), "===\n", flush=True)
    completed = subprocess.run(cmd, cwd=BACKEND_ROOT, check=False)
    return int(completed.returncode)


def main() -> int:
    args = parse_args()
    code = 0
    notes: list[str] = []

    if not args.combine_only:
        if not args.skip_phase1:
            phase_code = _run_phase(
                "run_phase1_pipeline_tests.py",
                args.quiet,
                args.pytest_args,
            )
            code = code or phase_code
            notes.append(f"phase1 exit={phase_code}")
        else:
            notes.append("phase1 skipped (reuse artifacts)")

        if not args.skip_phase2:
            phase_code = _run_phase(
                "run_phase2_ml_api_tests.py",
                args.quiet,
                args.pytest_args,
            )
            code = code or phase_code
            notes.append(f"phase2 exit={phase_code}")
        else:
            notes.append("phase2 skipped (reuse artifacts)")

        if not args.skip_phase3:
            flags = ["--with-frontend"] if args.with_frontend else None
            phase_code = _run_phase(
                "run_phase3_overall_tests.py",
                args.quiet,
                args.pytest_args,
                extra_flags=flags,
            )
            code = code or phase_code
            notes.append(f"phase3 exit={phase_code}")
        else:
            notes.append("phase3 skipped (reuse artifacts)")
    else:
        notes.append("combine-only mode")

    # Import after cwd is backend-friendly for package resolution.
    sys.path.insert(0, str(BACKEND_ROOT))
    from tests.reporting.unified_results import write_unified_report

    paths = write_unified_report(run_notes="; ".join(notes))
    print("\n=== Unified report written ===")
    for label, path in paths.items():
        print(f"{label}: {path}")

    # Submittable Word (.doc) report with TODO rows for outstanding work.
    try:
        import importlib.util

        doc_script = BACKEND_ROOT / "scripts" / "testing" / "generate_standard_test_report_doc.py"
        spec = importlib.util.spec_from_file_location("generate_standard_test_report_doc", doc_script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main()
    except Exception as exc:  # noqa: BLE001
        print(f"Word report generation skipped: {exc}")
    return code


if __name__ == "__main__":
    sys.exit(main())
