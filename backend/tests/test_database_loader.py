from datetime import datetime

from src.database.final_schema import (
    AI_CLASSIFICATION_COLUMNS,
    DATABASE_PUBLICATION_COLUMNS,
    FINAL_PUBLICATION_COLUMNS,
)
from src.database.loader import (
    build_final_publication_row,
    canonicalize_existing_publication_key,
    final_publication_values,
    final_publications_upsert_sql,
)
from src.pipeline.build_final_common_dataset import FINAL_MAIN_COLUMNS


def test_final_publication_columns_use_latest_final_dataset_contract():
    assert list(FINAL_PUBLICATION_COLUMNS) == FINAL_MAIN_COLUMNS
    assert len(FINAL_PUBLICATION_COLUMNS) == len(FINAL_MAIN_COLUMNS)
    assert "ownership_decision" in FINAL_PUBLICATION_COLUMNS
    assert "ownership_reason" in FINAL_PUBLICATION_COLUMNS
    assert "ai_classification_label" not in FINAL_PUBLICATION_COLUMNS
    assert list(DATABASE_PUBLICATION_COLUMNS) == [
        *FINAL_MAIN_COLUMNS,
        *AI_CLASSIFICATION_COLUMNS,
    ]


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
            "publication_date": "2024-01-15T00:00:00",
            "source_datestamp": datetime(2024, 1, 16, 12, 30),
            "authors": ["A. Author", "B. Author"],
            "institutions": ["University of Colombo", "University of Peradeniya"],
            "is_oa": "true",
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
    assert row["publication_date"] == "2024-01-15"
    assert row["authors"] == "A. Author; B. Author"
    assert row["institutions"] == "University of Colombo; University of Peradeniya"
    assert row["is_oa"] is True
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
        },
        row_number=1,
    )

    assert row["reference_count"] == 9
    assert row["publisher"] == "Nested Publisher"


def test_final_publications_upsert_sql_includes_every_final_column():
    sql = final_publications_upsert_sql()

    assert 'INSERT INTO "final_publications"' in sql
    for column in [*FINAL_MAIN_COLUMNS, *AI_CLASSIFICATION_COLUMNS]:
        assert f'"{column}"' in sql


def test_canonicalize_existing_publication_key_updates_older_identifier_key():
    class Cursor:
        def __init__(self):
            self.queries = []

        def execute(self, query, args):
            self.queries.append((query, args))

        def fetchall(self):
            return [("openalex:https://openalex.org/W1",)]

    cursor = Cursor()
    row = build_final_publication_row(
        {
            "doi": "10.1000/new",
            "openalex_id": "https://openalex.org/W1",
            "title": "Updated paper",
        },
        row_number=1,
    )

    canonicalize_existing_publication_key(cursor, row)

    assert cursor.queries[0][1] == [
        "doi:10.1000/new",
        "10.1000/new",
        "https://openalex.org/W1",
    ]
    assert "UPDATE \"final_publications\"" in cursor.queries[1][0]
    assert cursor.queries[1][1] == (
        "doi:10.1000/new",
        "openalex:https://openalex.org/W1",
    )


def test_canonicalize_existing_publication_key_rejects_ambiguous_matches():
    class Cursor:
        def execute(self, query, args):
            return None

        def fetchall(self):
            return [("doi:10.1000/new",), ("openalex:https://openalex.org/W1",)]

    row = build_final_publication_row(
        {
            "doi": "10.1000/new",
            "openalex_id": "https://openalex.org/W1",
            "title": "Ambiguous paper",
        },
        row_number=1,
    )

    try:
        canonicalize_existing_publication_key(Cursor(), row)
    except ValueError as exc:
        assert "multiple existing final_publications rows" in str(exc)
    else:
        raise AssertionError("Expected ambiguous publication matches to fail")


def test_final_publication_values_matches_upsert_column_order():
    row = build_final_publication_row({"title": "A publication"}, row_number=1)
    values = final_publication_values(row)

    assert values[0] == row["publication_key"]
    assert len(values) == 1 + len(DATABASE_PUBLICATION_COLUMNS) + 1
