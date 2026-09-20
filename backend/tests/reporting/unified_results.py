"""Combine Phase 1/2/3 structured reports into one unified artifact.

Mirrors the data/processed/common summary style: a single Markdown document,
CSV table, and JSON summary that you can archive next to pipeline outputs.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = BACKEND_ROOT / "data" / "reports" / "unified_phase_tests"
DEFAULT_COMMON_DIR = BACKEND_ROOT / "data" / "processed" / "common"

PHASE_REPORT_DIRS = {
    "phase1": BACKEND_ROOT / "data" / "reports" / "phase1_pipeline_tests",
    "phase2": BACKEND_ROOT / "data" / "reports" / "phase2_ml_api_tests",
    "phase3": BACKEND_ROOT / "data" / "reports" / "phase3_overall_tests",
}

# Explicit residual gaps (tests not yet automated, or requiring live envs).
COVERAGE_GAPS: list[dict[str, str]] = [
    {
        "area": "Deployed site (EC2 / production URL)",
        "status": "partial",
        "detail": (
            "Live HTTP tests in tests/phase3/test_phase3_deployed_site.py use "
            "RESEARCHLANKA_DEPLOYED_BASE_URL + credentials from gitignored .env. "
            "They auto-skip when the host cannot reach the EC2 IP."
        ),
        "action": (
            "From a machine that can open http://YOUR_HOST:3000, run "
            "`PHASE3_SKIP_VITEST=1 python scripts/testing/run_all_phase_tests.py -q`."
        ),
    },
    {
        "area": "Live Postgres + API soak",
        "status": "missing",
        "detail": (
            "In-process Phase 2/3 API tests now load real rows from "
            "common_publications_final.csv. Direct Postgres soak still needs a reachable DATABASE_URL."
        ),
        "action": "If the EC2 Postgres port is reachable, set DATABASE_URL in .env and add a soak job.",
    },
    {
        "area": "Dagster UI / `dg dev` materialization",
        "status": "partial",
        "detail": (
            "Phase 1 Dagster tests cover job/asset wiring and package layout. "
            "Full asset materialization in a running Dagster webserver / dg dev session "
            "is not automated."
        ),
        "action": (
            "In backend/dagster-quickstart run `uv run dg dev`, materialize "
            "researchlanka_all_assets_job (or a subset), and archive Dagster run logs."
        ),
    },
    {
        "area": "Browser E2E (Playwright)",
        "status": "missing",
        "detail": "No Playwright/Cypress suite in CI; Vitest + service-layer integration is the current gate.",
        "action": "Add Playwright smoke for login, search, publication detail, and admin gate.",
    },
    {
        "area": "Admin incremental API auth",
        "status": "documented_risk",
        "detail": (
            "POST /api/v1/admin/incremental/run has no API-key of its own; production relies on "
            "private Docker network + Next.js capability checks."
        ),
        "action": "Do not publish the API port; optionally add token auth before exposing API publicly.",
    },
    {
        "area": "dagster-quickstart package tests",
        "status": "missing",
        "detail": "backend/dagster-quickstart/tests/ only has an empty package init.",
        "action": "Keep using backend/tests/phase1 Dagster tests; add package-local tests if the project splits.",
    },
]


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def collect_phase_artifacts(
    phase_dirs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Read latest_* artifacts written by each phase reporter."""

    dirs = phase_dirs or PHASE_REPORT_DIRS
    phases: dict[str, Any] = {}
    combined_rows: list[dict[str, Any]] = []

    for phase, report_dir in dirs.items():
        summary = _load_json(report_dir / "latest_summary.json")
        rows = _load_csv_rows(report_dir / "latest_results.csv")
        for row in rows:
            combined_rows.append({"phase": phase, **row})
        phases[phase] = {
            "report_dir": str(report_dir),
            "summary": summary,
            "result_count": len(rows),
            "latest_report_md": str(report_dir / "latest_report.md"),
            "latest_results_csv": str(report_dir / "latest_results.csv"),
            "present": summary is not None or bool(rows),
        }

        # Optional matrices
        if phase == "phase2":
            phases[phase]["api_matrix_md"] = str(report_dir / "latest_api_matrix.md")
            phases[phase]["api_matrix_present"] = (report_dir / "latest_api_matrix.md").exists()
        if phase == "phase3":
            phases[phase]["security_matrix_md"] = str(report_dir / "latest_security_matrix.md")
            phases[phase]["security_matrix_present"] = (
                report_dir / "latest_security_matrix.md"
            ).exists()

    return {"phases": phases, "rows": combined_rows}


def write_unified_report(
    *,
    report_dir: Path | None = None,
    common_dir: Path | None = None,
    phase_dirs: dict[str, Path] | None = None,
    run_notes: str = "",
) -> dict[str, Path]:
    """Write unified CSV/MD/JSON under reports/ and a copy under data/processed/common."""

    out_dir = Path(report_dir or DEFAULT_REPORT_DIR)
    common_out = Path(common_dir or DEFAULT_COMMON_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    common_out.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    collected = collect_phase_artifacts(phase_dirs)
    phases = collected["phases"]
    rows: list[dict[str, Any]] = collected["rows"]

    totals = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "xfailed": 0}
    phase_summaries: list[dict[str, Any]] = []
    for phase_name, payload in phases.items():
        summary = payload.get("summary") or {}
        phase_row = {
            "phase": phase_name,
            "present": payload["present"],
            "total": int(summary.get("total", payload.get("result_count", 0)) or 0),
            "passed": int(summary.get("passed", 0) or 0),
            "failed": int(summary.get("failed", 0) or 0),
            "skipped": int(summary.get("skipped", 0) or 0),
            "xfailed": int(summary.get("xfailed", 0) or 0),
            "pass_rate_pct": float(summary.get("pass_rate_pct", 0.0) or 0.0),
            "suite_name": summary.get("suite_name", phase_name),
            "generated_at_utc": summary.get("generated_at_utc"),
        }
        if not summary and payload.get("result_count"):
            # Derive from CSV when summary JSON is missing.
            outcomes = [str(r.get("outcome", "")).lower() for r in rows if r.get("phase") == phase_name]
            phase_row["passed"] = outcomes.count("passed")
            phase_row["failed"] = outcomes.count("failed") + outcomes.count("error")
            phase_row["skipped"] = outcomes.count("skipped")
            phase_row["xfailed"] = outcomes.count("xfailed")
            phase_row["total"] = len(outcomes)
            phase_row["pass_rate_pct"] = (
                round(phase_row["passed"] / phase_row["total"] * 100.0, 2)
                if phase_row["total"]
                else 0.0
            )
        phase_summaries.append(phase_row)
        for key in ("total", "passed", "failed", "skipped", "xfailed"):
            totals[key] += phase_row[key]

    overall_pass_rate = (
        round(totals["passed"] / totals["total"] * 100.0, 2) if totals["total"] else 0.0
    )

    summary_doc: dict[str, Any] = {
        "suite_name": "unified_phase_tests",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "totals": {**totals, "pass_rate_pct": overall_pass_rate},
        "phases": phase_summaries,
        "coverage_gaps": COVERAGE_GAPS,
        "run_notes": run_notes,
        "phase_artifacts": {
            name: {
                "report_dir": payload["report_dir"],
                "present": payload["present"],
                "latest_report_md": payload.get("latest_report_md"),
            }
            for name, payload in phases.items()
        },
    }

    base = f"unified_phase_tests_{stamp}"
    csv_path = out_dir / f"{base}_results.csv"
    md_path = out_dir / f"{base}_report.md"
    json_path = out_dir / f"{base}_summary.json"
    latest_csv = out_dir / "latest_results.csv"
    latest_md = out_dir / "latest_report.md"
    latest_json = out_dir / "latest_summary.json"

    fieldnames = [
        "phase",
        "test_id",
        "nodeid",
        "category",
        "outcome",
        "duration_seconds",
        "markers",
        "message",
        "file",
        "timestamp",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    json_path.write_text(json.dumps(summary_doc, indent=2), encoding="utf-8")

    lines = [
        "# ResearchLanka Unified Phase Test Report",
        "",
        f"- **Suite:** `unified_phase_tests`",
        f"- **Generated (UTC):** {summary_doc['generated_at_utc']}",
        f"- **Total tests (all phases):** {totals['total']}",
        f"- **Passed:** {totals['passed']}",
        f"- **Failed:** {totals['failed']}",
        f"- **Skipped:** {totals['skipped']}",
        f"- **Pass rate:** {overall_pass_rate}%",
        "",
    ]
    if run_notes:
        lines.extend(["## Run notes", "", run_notes, ""])

    lines.extend(
        [
            "## Phase roll-up",
            "",
            "| Phase | Present | Total | Passed | Failed | Skipped | Pass rate |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in phase_summaries:
        lines.append(
            f"| {row['phase']} | {'yes' if row['present'] else 'NO'} | {row['total']} | "
            f"{row['passed']} | {row['failed']} | {row['skipped']} | {row['pass_rate_pct']}% |"
        )

    lines.extend(
        [
            "",
            "## Coverage gaps / remaining work",
            "",
            "| Area | Status | Detail | Action |",
            "|---|---|---|---|",
        ]
    )
    for gap in COVERAGE_GAPS:
        lines.append(
            f"| {gap['area']} | `{gap['status']}` | {gap['detail']} | {gap['action']} |"
        )

    lines.extend(
        [
            "",
            "## Per-phase artifact pointers",
            "",
        ]
    )
    for name, payload in phases.items():
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"- Report dir: `{payload['report_dir']}`")
        lines.append(f"- Latest MD: `{payload.get('latest_report_md')}`")
        if name == "phase2":
            lines.append(f"- API matrix: `{payload.get('api_matrix_md')}`")
        if name == "phase3":
            lines.append(f"- Security matrix: `{payload.get('security_matrix_md')}`")
        lines.append("")

    failed_rows = [
        row
        for row in rows
        if str(row.get("outcome", "")).lower() in {"failed", "error"}
    ]
    if failed_rows:
        lines.extend(["## Failures (all phases)", ""])
        for row in failed_rows:
            lines.append(
                f"- `{row.get('phase')}` / `{row.get('nodeid')}` — "
                f"{str(row.get('message', ''))[:300]}"
            )
        lines.append("")

    skipped_rows = [row for row in rows if str(row.get("outcome", "")).lower() == "skipped"]
    if skipped_rows:
        lines.extend(["## Skipped (all phases)", ""])
        for row in skipped_rows[:80]:
            lines.append(
                f"- `{row.get('phase')}` / `{row.get('nodeid')}` — "
                f"{str(row.get('message', ''))[:200]}"
            )
        if len(skipped_rows) > 80:
            lines.append(f"- … and {len(skipped_rows) - 80} more")
        lines.append("")

    lines.extend(
        [
            "## Artifacts",
            "",
            f"- Unified CSV: `{csv_path.name}`",
            f"- Unified JSON: `{json_path.name}`",
            f"- Unified Markdown: `{md_path.name}`",
            f"- Common copy: `data/processed/common/unified_testing_report.md`",
            "",
        ]
    )
    md_text = "\n".join(lines)
    md_path.write_text(md_text, encoding="utf-8")

    latest_csv.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")

    # data/processed/common style copies (stable names, like merge summaries)
    common_md = common_out / "unified_testing_report.md"
    common_csv = common_out / "unified_testing_results.csv"
    common_json = common_out / "unified_testing_summary.json"
    common_log = common_out / "unified_testing_run_log.txt"
    common_md.write_text(md_text, encoding="utf-8")
    common_csv.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    common_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    common_log.write_text(
        "\n".join(
            [
                "ResearchLanka unified phase testing log",
                f"Created at: {summary_doc['generated_at_utc']}",
                f"Total: {totals['total']}",
                f"Passed: {totals['passed']}",
                f"Failed: {totals['failed']}",
                f"Skipped: {totals['skipped']}",
                f"Pass rate: {overall_pass_rate}%",
                f"Report dir: {out_dir}",
                "",
                "Phase presence:",
                *[
                    f"- {row['phase']}: present={row['present']} "
                    f"passed={row['passed']}/{row['total']}"
                    for row in phase_summaries
                ],
                "",
                "Coverage gaps:",
                *[f"- [{gap['status']}] {gap['area']}" for gap in COVERAGE_GAPS],
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "csv": csv_path,
        "markdown": md_path,
        "json": json_path,
        "latest_csv": latest_csv,
        "latest_markdown": latest_md,
        "latest_json": latest_json,
        "common_markdown": common_md,
        "common_csv": common_csv,
        "common_json": common_json,
        "common_log": common_log,
    }
