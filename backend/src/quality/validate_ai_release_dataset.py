"""Validate the AI-only publication dataset before release.

This module is intentionally conservative: it does not decide that a dataset is
publishable, because human verification and license review still sit outside
automatic checks. It produces the concrete evidence needed for that decision.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.io_utils import load_dataset, save_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "common_publications_final_2016_2026_ai_only.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "reports" / "ai_release_validation"

REQUIRED_COLUMNS = (
    "title",
    "publication_date",
    "source_dataset",
    "source_record_id",
    "ai_classification_label",
    "ai_classification_confidence",
    "ai_classification_model",
)
OPTIONAL_RELEASE_COLUMNS = (
    "openalex_id",
    "doi",
    "abstract",
    "authors",
    "institutions",
    "sri_lankan_authors",
    "sri_lankan_institutions",
    "countries",
    "license",
    "license_url",
    "oa_status",
    "primary_domain",
    "primary_field",
    "primary_subfield",
    "primary_topic",
    "type",
    "language",
)


@dataclass(frozen=True)
class AIReleaseValidationConfig:
    input_path: Path = DEFAULT_INPUT
    output_dir: Path = DEFAULT_OUTPUT_DIR
    current_year: int = datetime.now(UTC).year
    duplicate_sample_size: int = 100


def _non_blank(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().ne("")


def _first_year(series: pd.Series) -> pd.Series:
    extracted = series.fillna("").astype(str).str.extract(r"(\d{4})", expand=False)
    return pd.to_numeric(extracted, errors="coerce")


def _normalize_title(value: object) -> str:
    text = "" if pd.isna(value) else str(value).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _issue(check: str, status: str, count: int, details: str) -> dict[str, Any]:
    return {"check": check, "status": status, "count": int(count), "details": details}


def _coverage(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for column in [*REQUIRED_COLUMNS, *OPTIONAL_RELEASE_COLUMNS]:
        if column not in frame.columns:
            rows.append(
                {
                    "field": column,
                    "present": False,
                    "available_rows": 0,
                    "total_rows": len(frame),
                    "available_percent": 0.0,
                    "release_role": "required" if column in REQUIRED_COLUMNS else "optional",
                }
            )
            continue
        available = int(_non_blank(frame[column]).sum())
        rows.append(
            {
                "field": column,
                "present": True,
                "available_rows": available,
                "total_rows": len(frame),
                "available_percent": round((available / len(frame) * 100) if len(frame) else 0.0, 2),
                "release_role": "required" if column in REQUIRED_COLUMNS else "optional",
            }
        )
    return pd.DataFrame(rows)


def _duplicate_rows(frame: pd.DataFrame, key_columns: list[str], reason: str) -> pd.DataFrame:
    if any(column not in frame.columns for column in key_columns):
        return frame.head(0).copy()
    keyed = frame.copy()
    for column in key_columns:
        keyed[column] = keyed[column].fillna("").astype(str).str.strip()
    keyed = keyed[keyed[key_columns].ne("").all(axis=1)].copy()
    if keyed.empty:
        return keyed
    return keyed[keyed.duplicated(key_columns, keep=False)].assign(duplicate_reason=reason)


def _distribution(frame: pd.DataFrame, column: str, limit: int = 50) -> pd.DataFrame:
    if column not in frame.columns:
        return pd.DataFrame(columns=["column", "value", "rows"])
    counts = frame[column].fillna("").astype(str).replace("", "(blank)").value_counts().head(limit)
    return pd.DataFrame(
        [{"column": column, "value": value, "rows": int(rows)} for value, rows in counts.items()]
    )


def validate_ai_release_dataset(config: AIReleaseValidationConfig) -> dict[str, Any]:
    frame = load_dataset(config.input_path)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    issues: list[dict[str, Any]] = []
    coverage = _coverage(frame)
    missing_required = coverage[(coverage["release_role"] == "required") & ~coverage["present"]]
    issues.append(
        _issue(
            "required_columns_present",
            "pass" if missing_required.empty else "fail",
            len(missing_required),
            ", ".join(missing_required["field"].tolist()) or "all required columns present",
        )
    )

    for column in REQUIRED_COLUMNS:
        if column in frame.columns:
            blank_count = int((~_non_blank(frame[column])).sum())
            issues.append(
                _issue(
                    f"required_field_not_blank:{column}",
                    "pass" if blank_count == 0 else "fail",
                    blank_count,
                    "blank required values",
                )
            )

    if "ai_classification_label" in frame.columns:
        label = frame["ai_classification_label"].fillna("").astype(str).str.strip().str.upper()
        non_ai_rows = int(label.ne("AI").sum())
        issues.append(
            _issue(
                "final_release_labels_are_ai",
                "pass" if non_ai_rows == 0 else "fail",
                non_ai_rows,
                "rows where ai_classification_label is not AI",
            )
        )

    if "ai_classification_confidence" in frame.columns:
        confidence = pd.to_numeric(frame["ai_classification_confidence"], errors="coerce")
        invalid_confidence = int((confidence.isna() | confidence.lt(0) | confidence.gt(1)).sum())
        issues.append(
            _issue(
                "ai_confidence_range",
                "pass" if invalid_confidence == 0 else "fail",
                invalid_confidence,
                "missing or outside [0, 1]",
            )
        )

    if "publication_date" in frame.columns:
        year = _first_year(frame["publication_date"])
        invalid_year = int((year.isna() | year.lt(1500) | year.gt(config.current_year)).sum())
        issues.append(
            _issue(
                "publication_year_range",
                "pass" if invalid_year == 0 else "fail",
                invalid_year,
                f"missing, before 1500, or after {config.current_year}",
            )
        )

    for column in ("reference_count", "citation_count"):
        if column in frame.columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            invalid = int(values.lt(0).fillna(False).sum())
            issues.append(
                _issue(
                    f"non_negative_numeric:{column}",
                    "pass" if invalid == 0 else "fail",
                    invalid,
                    "negative values",
                )
            )

    if "needs_manual_review" in frame.columns:
        review = frame["needs_manual_review"].fillna("").astype(str).str.strip().str.casefold()
        unresolved = int(review.isin({"true", "1", "yes", "y"}).sum())
        issues.append(
            _issue(
                "sri_lanka_manual_review_resolved",
                "pass" if unresolved == 0 else "review_required",
                unresolved,
                "rows still marked needs_manual_review",
            )
        )

    lk_evidence_columns = [
        column
        for column in (
            "sri_lankan_authors",
            "sri_lankan_institutions",
            "countries",
            "ownership_evidence",
        )
        if column in frame.columns
    ]
    if lk_evidence_columns:
        evidence_text = frame[lk_evidence_columns].fillna("").astype(str).agg(" ".join, axis=1)
        has_lk_evidence = evidence_text.str.contains("sri lanka|sri_lanka|lk", case=False, regex=True, na=False)
        missing_lk_evidence = int((~has_lk_evidence).sum())
        issues.append(
            _issue(
                "sri_lanka_evidence_available",
                "pass" if missing_lk_evidence == 0 else "review_required",
                missing_lk_evidence,
                "rows without obvious Sri Lanka evidence text",
            )
        )

    duplicate_frames = []
    if "openalex_id" in frame.columns:
        duplicate_frames.append(_duplicate_rows(frame, ["openalex_id"], "duplicate_openalex_id"))
    if "doi" in frame.columns:
        duplicate_frames.append(_duplicate_rows(frame, ["doi"], "duplicate_doi"))
    if {"title", "publication_date"}.issubset(frame.columns):
        title_year = frame.copy()
        title_year["normalized_title"] = title_year["title"].map(_normalize_title)
        title_year["publication_year"] = _first_year(title_year["publication_date"]).fillna("").astype(str)
        duplicate_frames.append(
            _duplicate_rows(title_year, ["normalized_title", "publication_year"], "duplicate_title_year")
        )

    duplicates = (
        pd.concat([item for item in duplicate_frames if not item.empty], ignore_index=True)
        if any(not item.empty for item in duplicate_frames)
        else pd.DataFrame()
    )
    duplicate_count = len(duplicates)
    issues.append(
        _issue(
            "duplicate_candidates",
            "pass" if duplicate_count == 0 else "review_required",
            duplicate_count,
            "rows sharing OpenAlex ID, DOI, or normalized title/year",
        )
    )

    license_columns = [column for column in ("license", "license_url", "oa_status", "is_oa") if column in frame.columns]
    if license_columns:
        license_text = frame[license_columns].fillna("").astype(str).agg(" ".join, axis=1)
        missing_license = int((~_non_blank(license_text)).sum())
        issues.append(
            _issue(
                "license_metadata_available",
                "pass" if missing_license == 0 else "review_required",
                missing_license,
                "rows without license/OA metadata",
            )
        )

    distributions = pd.concat(
        [
            _distribution(frame, column)
            for column in (
                "publication_date",
                "source_dataset",
                "primary_domain",
                "primary_field",
                "type",
                "language",
                "license",
                "oa_status",
            )
        ],
        ignore_index=True,
    )

    issue_frame = pd.DataFrame(issues)
    save_dataset(coverage, config.output_dir / "field_completeness.csv")
    save_dataset(issue_frame, config.output_dir / "quality_gates.csv")
    save_dataset(distributions, config.output_dir / "distribution_summary.csv")
    if not duplicates.empty:
        duplicate_sample = duplicates.head(config.duplicate_sample_size)
        save_dataset(duplicate_sample, config.output_dir / "duplicate_candidates_sample.csv")

    summary = {
        "input_path": str(config.input_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "quality_gates": issue_frame["status"].value_counts().to_dict(),
        "failed_gates": issue_frame[issue_frame["status"].eq("fail")]["check"].tolist(),
        "review_required_gates": issue_frame[issue_frame["status"].eq("review_required")]["check"].tolist(),
        "outputs": {
            "field_completeness": str(config.output_dir / "field_completeness.csv"),
            "quality_gates": str(config.output_dir / "quality_gates.csv"),
            "distribution_summary": str(config.output_dir / "distribution_summary.csv"),
            "duplicate_candidates_sample": str(config.output_dir / "duplicate_candidates_sample.csv"),
        },
    }
    (config.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (config.output_dir / "README.md").write_text(_render_markdown(summary, issue_frame), encoding="utf-8")
    return summary


def _render_markdown(summary: dict[str, Any], issues: pd.DataFrame) -> str:
    lines = [
        "# AI Release Validation",
        "",
        f"Input: `{summary['input_path']}`",
        f"Rows: {summary['rows']}",
        f"Generated: {summary['generated_at']}",
        "",
        "## Quality gates",
        "",
        "| Check | Status | Count | Details |",
        "| --- | --- | ---: | --- |",
    ]
    for row in issues.to_dict(orient="records"):
        lines.append(f"| {row['check']} | {row['status']} | {row['count']} | {row['details']} |")
    lines.extend(
        [
            "",
            "## Publication decision",
            "",
            "Do not publish as v1.0 until all `fail` gates are fixed and all `review_required` gates are either resolved or explicitly accepted in the release notes.",
            "Human AI-relevance and Sri Lanka-relevance audit labels must be completed separately before final publication.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the AI-only publication release dataset.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--current-year", type=int, default=datetime.now(UTC).year)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = validate_ai_release_dataset(
        AIReleaseValidationConfig(
            input_path=args.input,
            output_dir=args.output_dir,
            current_year=args.current_year,
        )
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
