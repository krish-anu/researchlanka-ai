"""Tests for Google Maps-assisted institution location confirmation."""

from __future__ import annotations

import csv
from pathlib import Path

from src.pipeline.apply_google_maps_location_evidence import apply_evidence_to_registry
from src.quality.confirm_institution_locations_google_maps import (
    MapsResult,
    candidate_names_from_affiliation,
    evidence_row,
)


REGISTRY_FIELDNAMES = [
    "institution_id",
    "preferred_name",
    "alternative_name",
    "country_code",
    "ror_id",
    "parent_institution_id",
    "institution_type",
    "source_institution_id",
]


def test_candidate_extraction_cleans_crossref_affiliations() -> None:
    assert candidate_names_from_affiliation(
        "Quantity Surveyor, Dept. of Building Economics, Univ. of Moratuwa, "
        "Moratuwa 10400, Sri Lanka (corresponding author)"
    ) == ["Univ. of Moratuwa"]
    assert candidate_names_from_affiliation(
        "Department of Paediatrics Faculty of Medicine University of Kelaniya Ragama Sri Lanka"
    ) == ["University of Kelaniya"]


def test_evidence_row_confirms_strong_sri_lanka_title_match() -> None:
    row = evidence_row(
        "Univ. of Moratuwa",
        [
            MapsResult(
                title="University of Moratuwa",
                category="University",
                address="Bandaranayake Mawatha, Moratuwa, Sri Lanka",
                latitude="6.7951",
                longitude="79.9009",
                website="https://uom.lk",
                place_id="moratuwa",
            )
        ],
    )

    assert row["status"] == "confirmed"
    assert row["evidence_reason"] == "title_similarity_and_sri_lanka_location"


def test_evidence_row_keeps_broad_or_partial_matches_for_review() -> None:
    partial_match = evidence_row(
        "Centre for Dengue Research",
        [
            MapsResult(
                title="Centre For Research",
                category="Research institute",
                address="Colombo, Sri Lanka",
                latitude="6.9271",
                longitude="79.8612",
                website="",
                place_id="research",
            )
        ],
    )
    broad_candidate = evidence_row(
        "Sri Lanka Institute",
        [
            MapsResult(
                title="Sri Lanka Institute of Architects",
                category="Institute",
                address="Colombo, Sri Lanka",
                latitude="6.9271",
                longitude="79.8612",
                website="",
                place_id="architects",
            )
        ],
    )

    assert partial_match["status"] == "review"
    assert partial_match["evidence_reason"] == "sri_lanka_location_but_weak_title_match"
    assert broad_candidate["status"] == "review"
    assert broad_candidate["evidence_reason"] == "sri_lanka_location_but_candidate_too_broad"


def test_apply_evidence_adds_only_safe_aliases(tmp_path: Path) -> None:
    registry_csv = tmp_path / "institutions.csv"
    evidence_csv = tmp_path / "evidence.csv"
    report_csv = tmp_path / "report.csv"

    write_csv(
        registry_csv,
        REGISTRY_FIELDNAMES,
        [
            {
                "institution_id": "LK001",
                "preferred_name": "University of Moratuwa",
                "alternative_name": "University of Moratuwa",
                "country_code": "LK",
                "institution_type": "university",
            },
            {
                "institution_id": "LK002",
                "preferred_name": "Other University",
                "alternative_name": "Other University",
                "country_code": "LK",
                "institution_type": "university",
            },
        ],
    )
    write_csv(
        evidence_csv,
        [
            "candidate_name",
            "matched_title",
            "status",
            "confidence",
        ],
        [
            {
                "candidate_name": "Moratuwa University",
                "matched_title": "University of Moratuwa",
                "status": "confirmed",
                "confidence": "1.00",
            },
            {
                "candidate_name": "Other University",
                "matched_title": "University of Moratuwa",
                "status": "confirmed",
                "confidence": "1.00",
            },
            {
                "candidate_name": "School of Environment",
                "matched_title": "University of Moratuwa",
                "status": "review",
                "confidence": "0.80",
            },
            {
                "candidate_name": "Unknown Institute",
                "matched_title": "Unknown Institute",
                "status": "confirmed",
                "confidence": "0.95",
            },
        ],
    )

    result = apply_evidence_to_registry(
        evidence_csv=evidence_csv,
        registry_csv=registry_csv,
        report_csv=report_csv,
        statuses={"confirmed"},
        min_confidence=0.65,
        dry_run=False,
    )

    registry_rows = read_csv(registry_csv)
    report_rows = read_csv(report_csv)

    assert result == {"evidence_rows": 4, "aliases_added": 1, "skipped_rows": 3}
    assert any(
        row["institution_id"] == "LK001" and row["alternative_name"] == "Moratuwa University"
        for row in registry_rows
    )
    assert report_rows[0]["action"] == "add_alias"
    assert report_rows[1]["reason"] == "alias_conflicts_with:LK002"
    assert report_rows[2]["reason"] == "status_not_selected"
    assert report_rows[3]["reason"] == "matched_title_not_in_registry"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
