"""Load finalized publication records into PostgreSQL."""

from __future__ import annotations

import json
from datetime import date, datetime
from hashlib import sha1
from pathlib import Path
from typing import Any

from src.database.apply_database_migrations import (
    MIGRATIONS_DIR,
    applied_versions,
    apply_migration,
    ensure_schema_migrations_table,
)
from src.database.connection import get_connection
from src.database.final_schema import (
    BOOLEAN_COLUMNS,
    DATE_COLUMNS,
    FINAL_PUBLICATION_COLUMNS,
    FINAL_PUBLICATION_TABLE,
    INTEGER_COLUMNS,
    TIMESTAMPTZ_COLUMNS,
)
from src.pipeline.kaggle_merge_common_dataset import is_blank, normalize_doi


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "source_dataset": ("source_dataset", "source_name"),
    "source_record_id": ("source_record_id", "publication_id"),
    "url": ("url", "source_url"),
    "type": ("type", "publication_type"),
    "oa_status": ("oa_status", "open_access_status"),
    "authors": ("authors", "author_names"),
    "institutions": ("institutions", "national_institutions"),
}


def ensure_database_schema(connection: Any) -> None:
    """Apply pending SQL migrations using the repository migration table."""

    ensure_schema_migrations_table(connection)
    already_applied = applied_versions(connection)

    for path in sorted(Path(MIGRATIONS_DIR).glob("*.sql")):
        version = path.stem
        if version in already_applied:
            continue
        apply_migration(connection, path)
        connection.commit()


def load_final_publications(
    records: list[dict[str, Any]],
    *,
    connection: Any | None = None,
    database_url: str | None = None,
    ensure_schema: bool = True,
) -> int:
    """Upsert pipeline records into the finalized PostgreSQL publication table."""

    owns_connection = connection is None
    connection = connection or get_connection(database_url)

    try:
        if ensure_schema:
            ensure_database_schema(connection)

        rows = [
            build_final_publication_row(record, row_number)
            for row_number, record in enumerate(records, start=1)
        ]
        if not rows:
            if owns_connection:
                connection.commit()
            return 0

        values = [
            [
                row["publication_key"],
                *[row[column] for column in FINAL_PUBLICATION_COLUMNS],
                adapt_jsonb(row["raw_record"]),
            ]
            for row in rows
        ]
        with connection.cursor() as cursor:
            cursor.executemany(final_publications_upsert_sql(), values)

        if owns_connection:
            connection.commit()
        return len(rows)
    except Exception:
        if owns_connection:
            connection.rollback()
        raise
    finally:
        if owns_connection:
            connection.close()


def build_final_publication_row(record: dict[str, Any], row_number: int) -> dict[str, Any]:
    """Convert one pipeline record to the final PostgreSQL row shape."""

    row = {
        column: coerce_column_value(column, first_available_value(record, column))
        for column in FINAL_PUBLICATION_COLUMNS
    }

    doi = normalize_doi(row.get("doi"))
    row["doi"] = None if is_blank(doi) else str(doi)

    if is_blank(row.get("raw_identifiers")):
        row["raw_identifiers"] = build_raw_identifiers(row)

    row["publication_key"] = build_publication_key(row, row_number)
    row["raw_record"] = make_json_safe(record)
    return row


def first_available_value(record: dict[str, Any], column: str) -> Any:
    for source_column in (column, *COLUMN_ALIASES.get(column, ())):
        if source_column in record and not is_blank(record.get(source_column)):
            return record[source_column]
    return None


def coerce_column_value(column: str, value: Any) -> Any:
    if is_blank(value):
        return None
    if column in INTEGER_COLUMNS:
        return coerce_integer(value)
    if column in BOOLEAN_COLUMNS:
        return coerce_boolean(value)
    if column in DATE_COLUMNS:
        return coerce_date(value)
    if column in TIMESTAMPTZ_COLUMNS:
        return coerce_timestamp(value)
    return coerce_text(value)


def coerce_integer(value: Any) -> int | None:
    if is_blank(value):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def coerce_boolean(value: Any) -> bool | None:
    if is_blank(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"true", "t", "yes", "y", "1"}:
        return True
    if text in {"false", "f", "no", "n", "0"}:
        return False
    return None


def coerce_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = coerce_text(value)
    if text is None:
        return None
    candidate = text[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def coerce_timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    text = coerce_text(value)
    if text is None:
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return text


def coerce_text(value: Any) -> str | None:
    if is_blank(value):
        return None
    if isinstance(value, (list, tuple, set)):
        parts = [coerce_text(item) for item in value]
        return "; ".join(part for part in parts if part)
    if isinstance(value, dict):
        return json.dumps(make_json_safe(value), ensure_ascii=False, sort_keys=True)
    text = str(value).strip()
    return text or None


def build_raw_identifiers(row: dict[str, Any]) -> str | None:
    identifiers = [
        row.get("doi"),
        row.get("openalex_id"),
        row.get("source_record_id"),
    ]
    values = [str(value) for value in identifiers if not is_blank(value)]
    return "; ".join(dict.fromkeys(values)) or None


def build_publication_key(row: dict[str, Any], row_number: int) -> str:
    if not is_blank(row.get("doi")):
        return f"doi:{row['doi']}"
    if not is_blank(row.get("openalex_id")):
        return f"openalex:{row['openalex_id']}"
    if not is_blank(row.get("source_dataset")) and not is_blank(row.get("source_record_id")):
        return f"source:{row['source_dataset']}:{row['source_record_id']}"
    if not is_blank(row.get("title")):
        key_payload = json.dumps(
            {
                "title": str(row["title"]).casefold(),
                "publication_year": row.get("publication_year"),
            },
            sort_keys=True,
        )
        digest = sha1(key_payload.encode("utf-8")).hexdigest()[:16]
        return f"title:{digest}"
    return f"row:{row_number}"


def make_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [make_json_safe(item) for item in value]
    return str(value)


def adapt_jsonb(value: Any) -> Any:
    try:
        from psycopg.types.json import Jsonb
    except ImportError:
        return json.dumps(value, ensure_ascii=False)
    return Jsonb(value)


def final_publications_upsert_sql() -> str:
    insert_columns = [
        "publication_key",
        *FINAL_PUBLICATION_COLUMNS,
        "raw_record",
    ]
    placeholders = ", ".join(["%s"] * len(insert_columns))
    quoted_columns = ", ".join(quote_identifier(column) for column in insert_columns)
    update_assignments = ", ".join(
        f"{quote_identifier(column)} = EXCLUDED.{quote_identifier(column)}"
        for column in [*FINAL_PUBLICATION_COLUMNS, "raw_record"]
    )
    return (
        f"INSERT INTO {quote_identifier(FINAL_PUBLICATION_TABLE)} ({quoted_columns}) "
        f"VALUES ({placeholders}) "
        "ON CONFLICT (publication_key) DO UPDATE SET "
        f"{update_assignments}, updated_at = now()"
    )


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
