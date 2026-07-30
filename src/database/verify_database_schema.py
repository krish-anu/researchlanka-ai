"""Verify the ResearchLanka PostgreSQL schema exists."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "src").is_dir()),
    Path.cwd(),
)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import get_connection
from src.database.final_schema import FINAL_PUBLICATION_COLUMNS, FINAL_PUBLICATION_TABLE

EXPECTED_TABLES = [
    "countries",
    "institutions",
    "institution_aliases",
    "data_sources",
    "source_records",
    "venues",
    "publications",
    "publication_sources",
    "authors",
    "publication_authors",
    "author_affiliations",
    "publication_countries",
    "keywords",
    "publication_keywords",
    "research_topics",
    "publication_topics",
    "funders",
    "publication_funders",
    "events",
    "publication_events",
    "publication_references",
    "publication_locations",
    "pipeline_runs",
    "data_quality_issues",
    "final_publications",
    "final_publication_references",
    "final_publication_count_audit",
]


def main() -> None:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )
            existing_tables = {row[0] for row in cursor.fetchall()}

            cursor.execute(
                """
                SELECT count(*)
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND constraint_type = 'FOREIGN KEY'
                """
            )
            foreign_key_count = cursor.fetchone()[0]

        missing = [table for table in EXPECTED_TABLES if table not in existing_tables]
        if missing:
            raise SystemExit(f"Missing tables: {', '.join(missing)}")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position
                """,
                (FINAL_PUBLICATION_TABLE,),
            )
            final_columns = [row[0] for row in cursor.fetchall()]

        expected_final_columns = ["publication_key", *FINAL_PUBLICATION_COLUMNS]
        missing_final_columns = [
            column for column in expected_final_columns if column not in final_columns
        ]
        if missing_final_columns:
            raise SystemExit(
                "Missing final_publications columns: "
                + ", ".join(missing_final_columns)
            )

        print(f"Schema OK: {len(EXPECTED_TABLES)} expected tables exist.")
        print(f"Final publication columns found: {len(FINAL_PUBLICATION_COLUMNS)}")
        print(f"Foreign keys found: {foreign_key_count}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
