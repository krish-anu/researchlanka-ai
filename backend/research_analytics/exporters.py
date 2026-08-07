"""Reusable file exports for framework outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from research_analytics.schema import STANDARD_PUBLICATION_FIELDS


def export_pipeline_outputs(
    *,
    output_dir: str | Path,
    cleaned_records: list[dict[str, Any]],
    deduplicated_records: list[dict[str, Any]],
    duplicate_candidates: list[dict[str, Any]],
    raw_records: list[dict[str, Any]] | None = None,
    invalid_records: list[dict[str, Any]] | None = None,
    validation_report: dict[str, Any] | None,
    analytics_summary: dict[str, Any] | None,
) -> None:
    """Write reusable CSV/JSON outputs without requiring a database."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_records_csv(output_dir / "cleaned_publications.csv", cleaned_records)
    _write_records_csv(output_dir / "deduplicated_publications.csv", deduplicated_records)
    _write_records_csv(output_dir / "national_publications.csv", deduplicated_records)
    _write_entity_csv(output_dir / "authors.csv", _authors(deduplicated_records), "author_name")
    _write_entity_csv(
        output_dir / "institutions.csv",
        _institutions(deduplicated_records),
        "institution_name",
    )
    _write_link_csv(
        output_dir / "publication_author_links.csv",
        _publication_links(deduplicated_records, "authors", "author_name"),
    )
    _write_link_csv(
        output_dir / "publication_institution_links.csv",
        _publication_links(deduplicated_records, "institutions", "institution_name"),
    )
    _write_entity_csv(
        output_dir / "research_categories.csv",
        _values(deduplicated_records, "categories"),
        "category",
    )
    _write_entity_csv(output_dir / "topics.csv", _values(deduplicated_records, "topics"), "topic")
    _write_link_csv(output_dir / "collaboration_edges.csv", _collaboration_edges(deduplicated_records))
    _write_match_csv(
        output_dir / "automatic_matches.csv",
        [
            candidate
            for candidate in duplicate_candidates
            if candidate.get("merge_decision") == "auto_merge"
        ],
    )
    _write_match_csv(
        output_dir / "manual_review_matches.csv",
        [
            candidate
            for candidate in duplicate_candidates
            if candidate.get("merge_decision") == "manual_review"
        ],
    )
    _write_match_csv(output_dir / "merge_report.csv", duplicate_candidates)
    _write_match_csv(output_dir / "non_matches.csv", [])
    _write_json(output_dir / "automatic_matches.json", duplicate_candidates)
    _write_json(output_dir / "source_records.json", raw_records or [])
    _write_json(output_dir / "processing_errors.json", invalid_records or [])
    _write_json(output_dir / "data_quality_report.json", validation_report or {})
    _write_data_quality_csv(output_dir / "data_quality_report.csv", validation_report or {})
    _write_json(output_dir / "analytics_summary.json", analytics_summary or {})
    _write_json(output_dir / "national_analytics_summary.json", analytics_summary or {})
    _write_json(
        output_dir / "processing_report.json",
        {
            "cleaned_record_count": len(cleaned_records),
            "deduplicated_record_count": len(deduplicated_records),
            "invalid_record_count": len(invalid_records or []),
            "removed_invalid_record_count": len(invalid_records or []),
            "removed_unusable_record_count": len(invalid_records or []),
            "duplicate_candidate_count": len(duplicate_candidates),
        },
    )


def _write_records_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = list(STANDARD_PUBLICATION_FIELDS)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_match_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "left_index",
        "right_index",
        "match_type",
        "confidence",
        "merge_decision",
        "score",
        "threshold",
        "reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def _write_entity_csv(path: Path, values: list[str], fieldname: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=[fieldname])
        writer.writeheader()
        for value in values:
            writer.writerow({fieldname: value})


def _write_link_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({field for row in rows for field in row}) or ["publication_id"]
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_data_quality_csv(path: Path, report: dict[str, Any]) -> None:
    rows = []
    for key, value in report.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            rows.append({"metric": key, "value": value})
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(rows)


def _authors(records: list[dict[str, Any]]) -> list[str]:
    return _values(records, "authors")


def _institutions(records: list[dict[str, Any]]) -> list[str]:
    values = _values(records, "national_institutions")
    return values or _values(records, "institutions")


def _values(records: list[dict[str, Any]], field: str) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for record in records:
        for value in _as_list(record.get(field)):
            if value not in seen:
                seen.add(value)
                values.append(value)
    return values


def _publication_links(
    records: list[dict[str, Any]],
    field: str,
    target_field: str,
) -> list[dict[str, Any]]:
    rows = []
    for index, record in enumerate(records):
        publication_id = record.get("publication_id") or record.get("source_record_id") or index
        for value in _as_list(record.get(field)):
            rows.append({"publication_id": publication_id, target_field: value})
    return rows


def _collaboration_edges(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        institutions = _as_list(record.get("national_institutions")) or _as_list(record.get("institutions"))
        for left_index, left in enumerate(institutions):
            for right in institutions[left_index + 1:]:
                rows.append(
                    {
                        "source": left,
                        "target": right,
                        "edge_type": record.get("collaboration_type") or "institution_collaboration",
                    }
                )
    return rows


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    text = str(value).strip()
    if not text:
        return []
    separator = ";" if ";" in text else ","
    return [item.strip() for item in text.split(separator) if item.strip()]
