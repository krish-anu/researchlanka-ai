"""Apply PostgreSQL database migrations."""

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

MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"


def ensure_schema_migrations_table(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )


def applied_versions(connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cursor.fetchall()}


def apply_migration(connection, path: Path) -> None:
    version = path.stem
    sql = path.read_text(encoding="utf-8")

    with connection.cursor() as cursor:
        cursor.execute(sql)
        cursor.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s)",
            (version,),
        )


def main() -> None:
    migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_paths:
        raise SystemExit(f"No migrations found in {MIGRATIONS_DIR}")

    connection = get_connection()
    try:
        ensure_schema_migrations_table(connection)
        already_applied = applied_versions(connection)

        applied_count = 0
        for path in migration_paths:
            version = path.stem
            if version in already_applied:
                print(f"Skipping already-applied migration: {version}")
                continue

            apply_migration(connection, path)
            connection.commit()
            applied_count += 1
            print(f"Applied migration: {version}")

        if applied_count == 0:
            print("Database schema is already up to date.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
