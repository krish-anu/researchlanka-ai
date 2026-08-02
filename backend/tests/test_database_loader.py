from datetime import datetime

from src.database.final_schema import FINAL_PUBLICATION_COLUMNS
from src.database.loader import (
    build_final_publication_row,
    final_publications_upsert_sql,
)
from src.pipeline.build_final_common_dataset import FINAL_MAIN_COLUMNS


def test_final_publication_columns_use_latest_final_dataset_contract():
    assert list(FINAL_PUBLICATION_COLUMNS) == FINAL_MAIN_COLUMNS
    assert len(FINAL_PUBLICATION_COLUMNS) == 56


def test_build_final_publication_row_maps_aliases_and_coerces_values():
    row = build_final_publication_row(
        {
            "source_name": "external_dataset",
            "publication_id": "pub-1",
            "source_url": "https://example.test/paper",
            "publication_type": "journal-article",
            "open_access_status": "gold",
            "doi": "https://doi.org/10.1000/ABC",
            "title": "A publication",
            "publication_year": "2024.0",
            "publication_date": "2024-01-15T00:00:00",
            "source_datestamp": datetime(2024, 1, 16, 12, 30),
            "authors": ["A. Author", "B. Author"],
            "institutions": ["University of Colombo", "University of Peradeniya"],
            "is_oa": "true",
            "citation_count": "7",
            "reference_count": "12",
        },
        row_number=1,
    )

    assert row["publication_key"] == "doi:10.1000/abc"
    assert row["source_dataset"] == "external_dataset"
    assert row["source_record_id"] == "pub-1"
    assert row["url"] == "https://example.test/paper"
    assert row["type"] == "journal-article"
    assert row["oa_status"] == "gold"
    assert row["doi"] == "10.1000/abc"
    assert row["publication_year"] == 2024
    assert row["publication_date"] == "2024-01-15"
    assert row["authors"] == "A. Author; B. Author"
    assert row["institutions"] == "University of Colombo; University of Peradeniya"
    assert row["is_oa"] is True
    assert row["citation_count"] == 7
    assert row["reference_count"] == 12


def test_build_final_publication_row_uses_nested_source_metadata_fallbacks():
    row = build_final_publication_row(
        {
            "source_name": "framework_dataset",
            "source_record_id": "pub-2",
            "doi": "10.1000/nested",
            "title": "Nested metadata publication",
            "source_specific_metadata": {
                "reference_count": "9",
                "publisher": "Nested Publisher",
            },
            "raw_record": {
                "publication_year": "2026",
            },
        },
        row_number=1,
    )

    assert row["reference_count"] == 9
    assert row["publisher"] == "Nested Publisher"
    assert row["publication_year"] == 2026


def test_final_publications_upsert_sql_includes_every_final_column():
    sql = final_publications_upsert_sql()

    assert 'INSERT INTO "final_publications"' in sql
    for column in FINAL_MAIN_COLUMNS:
        assert f'"{column}"' in sql
