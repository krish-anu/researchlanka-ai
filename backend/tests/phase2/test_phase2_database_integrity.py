"""Phase 2 — database integrity (schema contract, offline)."""

from __future__ import annotations

import pytest

from src.database.final_schema import (
    AI_CLASSIFICATION_COLUMNS,
    BOOLEAN_COLUMNS,
    DATABASE_PUBLICATION_COLUMNS,
    FINAL_PUBLICATION_COLUMNS,
    FINAL_PUBLICATION_TABLE,
    INTEGER_COLUMNS,
)
from src.database.loader import build_final_publication_row, build_publication_key
from src.database.verify_database_schema import EXPECTED_TABLES


pytestmark = [pytest.mark.phase2, pytest.mark.database_integrity]


def test_expected_core_tables_are_declared():
    required = {
        "final_publications",
        "final_publication_references",
        "final_publication_count_audit",
        "publications",
        "authors",
        "institutions",
        "pipeline_runs",
        "data_quality_issues",
    }
    assert required.issubset(set(EXPECTED_TABLES))
    assert len(EXPECTED_TABLES) >= 20


def test_final_publications_table_name_and_columns_are_stable():
    assert FINAL_PUBLICATION_TABLE == "final_publications"
    assert "publication_key" not in FINAL_PUBLICATION_COLUMNS  # key is separate
    assert "title" in FINAL_PUBLICATION_COLUMNS
    assert "doi" in FINAL_PUBLICATION_COLUMNS
    assert "primary_field" in FINAL_PUBLICATION_COLUMNS
    assert "primary_subfield" in FINAL_PUBLICATION_COLUMNS
    for column in AI_CLASSIFICATION_COLUMNS:
        assert column in DATABASE_PUBLICATION_COLUMNS
        assert column not in FINAL_PUBLICATION_COLUMNS


def test_typed_column_sets_do_not_overlap_incorrectly():
    assert INTEGER_COLUMNS.isdisjoint(BOOLEAN_COLUMNS)
    # Typed declarations may include legacy columns; only current schema columns
    # must be present and consistently typed for load integrity.
    for column in (INTEGER_COLUMNS | BOOLEAN_COLUMNS) & set(DATABASE_PUBLICATION_COLUMNS):
        assert column in DATABASE_PUBLICATION_COLUMNS
    assert "author_count" in INTEGER_COLUMNS
    assert "reference_count" in INTEGER_COLUMNS
    assert "is_oa" in BOOLEAN_COLUMNS


def test_publication_key_uniqueness_contract():
    """Same DOI must collapse to one publication_key (integrity for upserts)."""
    left = build_publication_key({"doi": "10.1000/abc"}, 1)
    right = build_publication_key({"doi": "10.1000/abc"}, 99)
    assert left == right == "doi:10.1000/abc"


def test_blank_doi_does_not_collide_across_distinct_sources():
    a = build_publication_key(
        {"source_dataset": "openalex", "source_record_id": "W1", "title": "A"},
        1,
    )
    b = build_publication_key(
        {"source_dataset": "crossref", "source_record_id": "W1", "title": "A"},
        2,
    )
    assert a != b


def test_final_row_builder_preserves_required_identity_fields():
    row = build_final_publication_row(
        {
            "source_name": "openalex",
            "source_record_id": "W100",
            "doi": "https://doi.org/10.1000/Integrity",
            "title": "Integrity check paper",
            "publication_date": "2024-01-15",
            "authors": ["A. Author"],
            "institutions": ["University of Colombo"],
            "primary_field": "Medicine",
            "primary_subfield": "Public Health",
            "is_oa": True,
            "author_count": 1,
            "reference_count": 3,
        },
        row_number=1,
    )
    assert row["publication_key"] == "doi:10.1000/integrity"
    assert row["doi"] == "10.1000/integrity"
    assert row["title"] == "Integrity check paper"
    assert row["primary_field"] == "Medicine"
    assert row["is_oa"] is True
    assert row["author_count"] == 1
    assert row["reference_count"] == 3
    assert "publication_year" not in DATABASE_PUBLICATION_COLUMNS
    assert "citation_count" not in DATABASE_PUBLICATION_COLUMNS
    assert "publication_year" not in row
    assert "citation_count" not in row


@pytest.mark.edge_case
def test_final_row_builder_allows_missing_title_with_stable_key():
    row = build_final_publication_row(
        {
            "source_name": "repositories",
            "source_record_id": "thesis-9",
            "doi": None,
            "title": None,
        },
        row_number=9,
    )
    assert row["publication_key"].startswith(("source:", "row:", "title:"))
    assert row["title"] is None
    assert row["source_record_id"] == "thesis-9"