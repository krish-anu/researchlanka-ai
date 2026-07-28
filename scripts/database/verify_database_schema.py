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

        print(f"Schema OK: {len(EXPECTED_TABLES)} expected tables exist.")
        print(f"Foreign keys found: {foreign_key_count}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
