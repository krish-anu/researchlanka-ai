"""Structured Phase 1 ETL test result reporting.

Writes CSV + Markdown (+ JSON summary) whenever Phase 1 tests finish.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE1_CATEGORIES = (
    "cleaning",
    "preprocessing",
    "transforming",
    "deduplication",
    "disambiguation",
    "entity_resolution",
    "e2e_ingestion",
    "dagster",
    "database",
)

DEFAULT_REPORT_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "reports" / "phase1_pipeline_tests"
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


def infer_category(item: Any) -> str:
    """Infer Phase 1 category from pytest markers or path/name."""

    marker_names = {marker.name for marker in getattr(item, "iter_markers", lambda: [])()}
    for category in PHASE1_CATEGORIES:
        if category in marker_names:
            return category

    nodeid = str(getattr(item, "nodeid", "")).lower()
    path = nodeid
    mapping = {
        "cleaning": ("clean", "text_cleaning", "normalize_doi", "normalize_title"),
        "preprocessing": ("preprocess", "normalizer", "language_normalized", "multivalue"),
        "transforming": ("transform", "map_to_common", "jsonl_to_csv"),
        "deduplication": ("dedup", "duplicate"),
        "disambiguation": ("disambigu", "author"),
        "entity_resolution": ("entity", "institution", "resolut", "affiliation"),
        "e2e_ingestion": ("e2e", "ingestion", "pipeline", "end_to_end"),
        "dagster": ("dagster",),
        "database": ("database", "loader", "load_records"),
    }
    for category, needles in mapping.items():
        if any(needle in path for needle in needles):
            return category
    return "uncategorized"


def write_phase1_report(
    rows: list[TestResultRow],
    *,
    report_dir: Path | None = None,
    suite_name: str = "phase1_etl_pipeline",
) -> dict[str, Path]:
    """Persist structured tables and a human-readable Markdown document."""

    out_dir = Path(report_dir or DEFAULT_REPORT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"{suite_name}_{stamp}"

    csv_path = out_dir / f"{base}_results.csv"
    md_path = out_dir / f"{base}_report.md"
    json_path = out_dir / f"{base}_summary.json"
    latest_csv = out_dir / "latest_results.csv"
    latest_md = out_dir / "latest_report.md"
    latest_json = out_dir / "latest_summary.json"

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
    skipped = [row for row in rows if row.outcome == "skipped"]
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

    summary = {
        "suite_name": suite_name,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "passed": passed,
        "failed": by_outcome.get("failed", 0) + by_outcome.get("error", 0),
        "skipped": by_outcome.get("skipped", 0),
        "xfailed": by_outcome.get("xfailed", 0),
        "pass_rate_pct": round(pass_rate, 2),
        "by_category": category_rows,
        "failed_tests": [
            {"nodeid": row.nodeid, "category": row.category, "message": row.message[:500]}
            for row in failed
        ],
    }

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Phase 1 ETL / Data Integration Pipeline Test Report",
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

    if skipped:
        lines.extend(["", "## Skipped", ""])
        for row in skipped:
            lines.append(f"- `{row.nodeid}` — {row.message[:200]}")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- CSV table: `{csv_path.name}`",
            f"- JSON summary: `{json_path.name}`",
            f"- This report: `{md_path.name}`",
            "",
            "## Coverage intent (Phase 1)",
            "",
            "| Area | What is validated |",
            "|---|---|",
            "| Cleaning | DOI/title/date/null/whitespace normalization and edge cases |",
            "| Preprocessing | Text cleaning, source normalizers, analysis-ready prep |",
            "| Transforming | Config-driven field transforms and schema mapping |",
            "| Deduplication | DOI / title-year / fuzzy matches and merge decisions |",
            "| Disambiguation | Author name/ORCID clustering and review paths |",
            "| Entity resolution | Institution registry matching and national enrichment |",
            "| E2E ingestion | Collect → transform → validate → clean → resolve → dedupe → export/load |",
            "| Dagster | Asset/job wiring for the ResearchLanka pipeline |",
            "| Database | Final row construction and upsert contract |",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    latest_csv.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_json.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")

    return {
        "csv": csv_path,
        "markdown": md_path,
        "json": json_path,
        "latest_csv": latest_csv,
        "latest_markdown": latest_md,
        "latest_json": latest_json,
    }
