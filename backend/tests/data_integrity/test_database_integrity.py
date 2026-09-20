"""Data and database integrity — core unit tests.

Run (from backend/):

    pytest tests/data_integrity -v
"""

from __future__ import annotations

from research_analytics.cleaning import (
    clean_record,
    is_valid_doi,
    normalize_doi,
    normalize_publication_year,
    normalize_title,
)
from research_analytics.config import CleaningConfig, DeduplicationConfig
from research_analytics.deduplication import find_duplicate_candidates
from src.database.final_schema import (
    FINAL_PUBLICATION_COLUMNS,
    FINAL_PUBLICATION_TABLE,
    INTEGER_COLUMNS,
)
from src.database.loader import build_final_publication_row, build_publication_key
from src.database.verify_database_schema import EXPECTED_TABLES


def test_doi_normalization_removes_https_prefix_and_lowercases():
    assert normalize_doi("https://doi.org/10.1000/ABC") == "10.1000/abc"
    assert normalize_doi("DOI: 10.1000/XYZ.") == "10.1000/xyz"


def test_invalid_doi_is_rejected_by_validator():
    assert is_valid_doi("not-a-doi") is False
    assert is_valid_doi("10.1000/valid-example") is True


def test_blank_doi_normalizes_to_none_not_empty_string():
    assert normalize_doi(None) is None
    assert normalize_doi("   ") is None


def test_title_normalization_preserves_meaningful_text_and_collapses_whitespace():
    cleaned = normalize_title("  Machine   Learning\nfor  Tea  ")
    assert cleaned == "Machine Learning for Tea"


def test_publication_year_extracted_from_date_string():
    assert normalize_publication_year("2024-03-15") == 2024
    assert normalize_publication_year("published in 2019 somewhere") == 2019
    assert normalize_publication_year("no-year") is None


def test_clean_record_preserves_authors_and_applies_doi_rule():
    record = {
        "doi": "https://doi.org/10.1000/ABC",
        "title": "  Sample Title ",
        "authors": "Alice; Bob",
        "publication_year": "2020",
    }
    cleaned = clean_record(record, CleaningConfig())
    assert cleaned["doi"] == "10.1000/abc"
    assert cleaned["authors"]
    assert cleaned["processing_status"] == "cleaned"
    assert "normalize_doi" in cleaned["_provenance"]["cleaning_rules_applied"]


def test_publication_key_is_stable_for_identical_doi():
    left = build_publication_key({"doi": "10.1000/abc"}, 1)
    right = build_publication_key({"doi": "10.1000/abc"}, 99)
    assert left == right == "doi:10.1000/abc"


def test_blank_doi_publication_keys_do_not_collide_across_sources():
    a = build_publication_key(
        {"source_dataset": "openalex", "source_record_id": "W1", "title": "Same"}, 1
    )
    b = build_publication_key(
        {"source_dataset": "crossref", "source_record_id": "W1", "title": "Same"}, 2
    )
    assert a != b


def test_final_row_builder_preserves_required_identity_fields():
    row = build_final_publication_row(
        {
            "doi": "10.1000/xyz",
            "title": "Identity Title",
            "publication_year": 2021,
            "authors": "A; B",
            "source_dataset": "openalex",
            "source_record_id": "W99",
        },
        7,
    )
    assert row["publication_key"].startswith("doi:")
    assert row["title"] == "Identity Title"
    assert row["doi"] == "10.1000/xyz"
    assert row["source_record_id"] == "W99"
    assert row.get("raw_record", {}).get("publication_year") == 2021


def test_final_publications_schema_declares_title_doi_and_author_columns():
    assert FINAL_PUBLICATION_TABLE == "final_publications"
    for column in ("title", "doi", "authors", "institutions"):
        assert column in FINAL_PUBLICATION_COLUMNS
    assert "publication_year" in INTEGER_COLUMNS


def test_expected_core_relational_tables_are_declared():
    required = {
        "final_publications",
        "authors",
        "institutions",
        "publications",
        "pipeline_runs",
        "data_quality_issues",
    }
    assert required.issubset(set(EXPECTED_TABLES))


def test_doi_duplicate_candidates_are_detected_for_merge():
    records = [
        {"doi": "10.1000/same", "title": "One", "publication_year": 2020, "authors": "A"},
        {
            "doi": "https://doi.org/10.1000/SAME",
            "title": "Two",
            "publication_year": 2021,
            "authors": "B",
        },
    ]
    candidates = find_duplicate_candidates(records, DeduplicationConfig())
    assert any(c.match_type == "doi" for c in candidates)
