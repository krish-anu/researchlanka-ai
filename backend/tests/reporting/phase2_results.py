"""Structured Phase 2 (DB integrity / ML / API) test result reporting.

Writes:
  - CSV + Markdown + JSON suite summary
  - API test matrix table: Test ID | Endpoint | Scenario | Expected | Result
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE2_CATEGORIES = (
    "database_integrity",
    "classification",
    "nmf_topic_modeling",
    "semantic_search",
    "api",
)

DEFAULT_REPORT_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "reports" / "phase2_ml_api_tests"
)


@dataclass
class TestResultRow:
    test_id: str
    nodeid: str
    category: str
    outcome: str
    duration_seconds: float
    markers: str = ""
    message: str = ""
    file: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ApiMatrixRow:
    test_id: str
    endpoint: str
    scenario: str
    expected: str
    result: str = "PENDING"
    outcome: str = "pending"
    message: str = ""
    duration_seconds: float = 0.0


def infer_phase2_category(item: Any) -> str:
    marker_names = {marker.name for marker in getattr(item, "iter_markers", lambda: [])()}
    for category in PHASE2_CATEGORIES:
        if category in marker_names:
            return category
    if "api_matrix" in marker_names or "api" in marker_names:
        return "api"

    nodeid = str(getattr(item, "nodeid", "")).lower()
    mapping = {
        "database_integrity": ("database_integrity", "final_schema", "verify_database", "integrity"),
        "classification": ("classif", "hierarchical", "linear_svm", "logreg"),
        "nmf_topic_modeling": ("nmf", "topic_model", "topic_trend"),
        "semantic_search": ("semantic", "embedding", "similar"),
        "api": ("api_matrix", "/api/v1", "route_get", "fastapi"),
    }
    for category, needles in mapping.items():
        if any(needle in nodeid for needle in needles):
            return category
    return "uncategorized"


def write_phase2_report(
    rows: list[TestResultRow],
    *,
    api_matrix: list[ApiMatrixRow] | None = None,
    report_dir: Path | None = None,
    suite_name: str = "phase2_ml_api",
) -> dict[str, Path]:
    out_dir = Path(report_dir or DEFAULT_REPORT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"{suite_name}_{stamp}"

    csv_path = out_dir / f"{base}_results.csv"
    md_path = out_dir / f"{base}_report.md"
    json_path = out_dir / f"{base}_summary.json"
    matrix_csv = out_dir / f"{base}_api_matrix.csv"
    matrix_md = out_dir / f"{base}_api_matrix.md"

    latest_csv = out_dir / "latest_results.csv"
    latest_md = out_dir / "latest_report.md"
    latest_json = out_dir / "latest_summary.json"
    latest_matrix_csv = out_dir / "latest_api_matrix.csv"
    latest_matrix_md = out_dir / "latest_api_matrix.md"

    fieldnames = list(asdict(rows[0]).keys()) if rows else [
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
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    by_outcome = Counter(row.outcome for row in rows)
    by_category = Counter(row.category for row in rows)
    failed = [row for row in rows if row.outcome in {"failed", "error"}]
    passed = by_outcome.get("passed", 0)
    total = len(rows)
    pass_rate = (passed / total * 100.0) if total else 0.0

    category_rows: list[dict[str, Any]] = []
    for category in sorted(by_category):
        subset = [row for row in rows if row.category == category]
        cat_passed = sum(1 for row in subset if row.outcome == "passed")
        cat_failed = sum(1 for row in subset if row.outcome in {"failed", "error"})
        cat_skipped = sum(1 for row in subset if row.outcome == "skipped")
        category_rows.append(
            {
                "category": category,
                "total": len(subset),
                "passed": cat_passed,
                "failed": cat_failed,
                "skipped": cat_skipped,
                "pass_rate_pct": round((cat_passed / len(subset) * 100.0) if subset else 0.0, 2),
            }
        )

    matrix = list(api_matrix or [])
    matrix_summary = {
        "total": len(matrix),
        "passed": sum(1 for row in matrix if row.outcome == "passed"),
        "failed": sum(1 for row in matrix if row.outcome in {"failed", "error"}),
        "skipped": sum(1 for row in matrix if row.outcome == "skipped"),
    }

    summary = {
        "suite_name": suite_name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "passed": passed,
        "failed": by_outcome.get("failed", 0) + by_outcome.get("error", 0),
        "skipped": by_outcome.get("skipped", 0),
        "pass_rate_pct": round(pass_rate, 2),
        "by_category": category_rows,
        "api_matrix": matrix_summary,
        "failed_tests": [
            {"nodeid": row.nodeid, "category": row.category, "message": row.message[:500]}
            for row in failed
        ],
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Phase 2 — Database Integrity, ML & API Test Report",
        "",
        f"- **Suite:** `{suite_name}`",
        f"- **Generated (UTC):** {summary['generated_at_utc']}",
        f"- **Total tests:** {total}",
        f"- **Passed:** {passed}",
        f"- **Failed:** {summary['failed']}",
        f"- **Skipped:** {summary['skipped']}",
        f"- **Pass rate:** {summary['pass_rate_pct']}%",
        "",
        "## Results by category",
        "",
        "| Category | Total | Passed | Failed | Skipped | Pass rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in category_rows:
        lines.append(
            f"| {row['category']} | {row['total']} | {row['passed']} | "
            f"{row['failed']} | {row['skipped']} | {row['pass_rate_pct']}% |"
        )

    lines.extend(
        [
            "",
            "## Coverage intent (Phase 2)",
            "",
            "| Area | What is validated |",
            "|---|---|",
            "| Database integrity | Schema contract, required tables/columns, key uniqueness rules |",
            "| Classification | Hierarchical field→subfield training/inference contracts |",
            "| NMF topic modeling | k=25 trends, emerging/declining labels, topic API integration |",
            "| Semantic search | Embedding index search/related ranking contracts |",
            "| API | Endpoint matrix (Test ID / Endpoint / Scenario / Expected / Result) |",
            "",
            "## Detailed results",
            "",
            "| Category | Outcome | Duration (s) | Test |",
            "|---|---|---:|---|",
        ]
    )
    for row in sorted(rows, key=lambda item: (item.category, item.outcome, item.nodeid)):
        short = row.nodeid.split("::")[-1]
        lines.append(
            f"| {row.category} | {row.outcome} | {row.duration_seconds:.3f} | `{short}` |"
        )

    if failed:
        lines.extend(["", "## Failures", ""])
        for row in failed:
            lines.append(f"### `{row.nodeid}`")
            lines.append("")
            lines.append(f"- Category: `{row.category}`")
            lines.append(f"- Message: `{row.message[:800]}`")
            lines.append("")

    if matrix:
        lines.extend(
            [
                "",
                "## API test matrix summary",
                "",
                f"- Cases: {matrix_summary['total']}",
                f"- Passed: {matrix_summary['passed']}",
                f"- Failed: {matrix_summary['failed']}",
                f"- Skipped: {matrix_summary['skipped']}",
                "",
                f"Full matrix: `{matrix_md.name}` / `{matrix_csv.name}`",
                "",
            ]
        )

    lines.extend(
        [
            "## Artifacts",
            "",
            f"- CSV table: `{csv_path.name}`",
            f"- JSON summary: `{json_path.name}`",
            f"- This report: `{md_path.name}`",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    # API matrix files
    matrix_fields = [
        "test_id",
        "endpoint",
        "scenario",
        "expected",
        "result",
        "outcome",
        "message",
        "duration_seconds",
    ]
    with matrix_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=matrix_fields)
        writer.writeheader()
        for row in matrix:
            writer.writerow(asdict(row))

    matrix_lines = [
        "# Phase 2 API Test Matrix",
        "",
        f"- Generated (UTC): {summary['generated_at_utc']}",
        f"- Cases: {matrix_summary['total']}",
        f"- Passed: {matrix_summary['passed']}",
        f"- Failed: {matrix_summary['failed']}",
        f"- Skipped: {matrix_summary['skipped']}",
        "",
        "| Test ID | Endpoint | Scenario | Expected | Result |",
        "|---|---|---|---|---|",
    ]
    for row in matrix:
        result_cell = row.result if row.result else row.outcome.upper()
        matrix_lines.append(
            f"| {row.test_id} | `{row.endpoint}` | {row.scenario} | {row.expected} | **{result_cell}** |"
        )
    if not matrix:
        matrix_lines.append("| — | — | No API matrix cases recorded | — | — |")
    matrix_md.write_text("\n".join(matrix_lines) + "\n", encoding="utf-8")

    latest_csv.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_matrix_csv.write_text(matrix_csv.read_text(encoding="utf-8"), encoding="utf-8")
    latest_matrix_md.write_text(matrix_md.read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "csv": csv_path,
        "markdown": md_path,
        "json": json_path,
        "api_matrix_csv": matrix_csv,
        "api_matrix_markdown": matrix_md,
        "latest_csv": latest_csv,
        "latest_markdown": latest_md,
        "latest_json": latest_json,
        "latest_api_matrix_csv": latest_matrix_csv,
        "latest_api_matrix_markdown": latest_matrix_md,
    }
