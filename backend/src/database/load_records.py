"""Load publication record files into PostgreSQL."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import logging
import re
import sys
from collections.abc import Iterable, Iterator
from itertools import islice
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from src.database.connection import get_connection
from src.database.loader import (
    build_final_publication_row,
    coerce_boolean,
    coerce_integer,
    ensure_database_schema,
    load_final_publications,
    make_json_safe,
    quote_identifier,
)
from src.pipeline.kaggle_merge_common_dataset import is_blank, normalize_doi

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("auto", "csv", "json", "jsonl")
DEFAULT_BATCH_SIZE = 1_000
COUNTRY_CODES = {
    "sri lanka": "LK",
    "lk": "LK",
    "usa": "US",
    "united states": "US",
    "uk": "GB",
    "united kingdom": "GB",
    "australia": "AU",
    "canada": "CA",
    "china": "CN",
    "india": "IN",
    "japan": "JP",
    "france": "FR",
    "germany": "DE",
    "italy": "IT",
    "singapore": "SG",
    "malaysia": "MY",
    "bangladesh": "BD",
    "nepal": "NP",
    "thailand": "TH",
    "saudi arabia": "SA",
    "egypt": "EG",
}

DATABASE_LOAD_TABLES = (
    "final_publications",
    "data_sources",
    "source_records",
    "publications",
    "publication_sources",
    "countries",
    "institutions",
    "institution_aliases",
    "venues",
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
    "final_publication_references",
    "final_publication_count_audit",
)

COUNT_AUDIT_COLUMNS = (
    "citation_count",
    "is_referenced_by_count",
    "reference_count",
    "referenced_works_count",
    "citation_count_difference_oa_minus_crossref",
    "citation_count_divergence_flag",
    "reference_count_difference_oa_minus_crossref",
    "reference_count_divergence_flag",
)


def _short_log_value(value: Any, *, limit: int = 80) -> str:
    if is_blank(value):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def iter_record_file(
    path: Path, *, file_format: str = "auto"
) -> Iterator[dict[str, Any]]:
    """Yield publication records from a CSV, JSON array, or JSON Lines file."""

    selected_format = detect_format(path, file_format)
    if selected_format == "csv":
        yield from iter_csv_records(path)
        return
    if selected_format == "json":
        yield from iter_json_records(path)
        return
    if selected_format == "jsonl":
        yield from iter_jsonl_records(path)
        return
    raise ValueError(f"Unsupported input format: {file_format}")


def detect_format(path: Path, requested_format: str = "auto") -> str:
    """Return a supported file format from a user request and filename."""

    normalized = requested_format.casefold()
    if normalized != "auto":
        if normalized not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported input format: {requested_format}")
        return normalized

    suffix = path.suffix.casefold()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    raise ValueError(
        "Could not infer input format. Use --format csv, --format json, or --format jsonl."
    )


def iter_csv_records(path: Path) -> Iterator[dict[str, Any]]:
    # Some publication exports can include very large metadata fields; the
    # default csv module limit is too low for those rows and raises before we
    # can load any records into PostgreSQL.
    csv.field_size_limit(sys.maxsize)

    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            return
        for row in reader:
            yield {key: value for key, value in row.items() if key is not None}


def iter_json_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, list):
        for index, item in enumerate(payload, start=1):
            yield ensure_record(item, record_label=f"record {index}")
        return

    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        for index, item in enumerate(payload["records"], start=1):
            yield ensure_record(item, record_label=f"records[{index - 1}]")
        return

    raise ValueError(
        "JSON input must be a list of records or an object with a records list."
    )


def iter_jsonl_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            yield ensure_record(json.loads(text), record_label=f"line {line_number}")


def ensure_record(value: Any, *, record_label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected {record_label} to be a JSON object.")
    return value


def chunked(
    records: Iterable[dict[str, Any]], batch_size: int
) -> Iterator[list[dict[str, Any]]]:
    """Yield records in fixed-size batches."""

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1.")

    iterator = iter(records)
    while True:
        batch = list(islice(iterator, batch_size))
        if not batch:
            return
        yield batch


def load_record_file(
    path: Path,
    *,
    file_format: str = "auto",
    database_url: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    ensure_schema: bool = True,
    limit: int | None = None,
) -> int:
    """Load a record file into PostgreSQL in batches and return loaded row count."""

    records: Iterable[dict[str, Any]] = iter_record_file(path, file_format=file_format)
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be zero or greater.")
        records = islice(records, limit)

    connection = get_connection(database_url)
    try:
        total = 0
        for batch_number, batch in enumerate(chunked(records, batch_size), start=1):
            loaded = load_final_publications(
                batch,
                connection=connection,
                ensure_schema=ensure_schema and batch_number == 1,
            )
            connection.commit()
            total += loaded
        return total
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _split_text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = []
        for item in value:
            items.extend(_split_text_values(item))
        return items
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _normalize_code(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    compact = re.sub(r"[^A-Za-z]", "", text).upper()
    if len(compact) == 2:
        return compact
    lookup = COUNTRY_CODES.get(text.casefold())
    if lookup:
        return lookup
    lowered = text.casefold()
    for key, code in COUNTRY_CODES.items():
        if key in lowered:
            return code
    return None


class DatabaseLoadValidationError(RuntimeError):
    """Raised when the post-load table count check finds missing rows."""


def empty_load_counts() -> dict[str, int]:
    return {table: 0 for table in DATABASE_LOAD_TABLES}


def _mark_unique_count(
    counts: dict[str, int],
    seen: dict[str, set[Any]],
    table: str,
    key: Any,
) -> None:
    if key is None:
        return

    keys = seen.setdefault(table, set())
    if key in keys:
        return
    keys.add(key)
    counts[table] += 1


def _mark_row_count(counts: dict[str, int], table: str, increment: int = 1) -> None:
    if increment > 0:
        counts[table] += increment


def validate_loaded_database_tables(
    connection: Any,
    expected_counts: dict[str, int],
) -> dict[str, int]:
    """Verify every table expected to receive rows has at least that many rows."""

    actual_counts: dict[str, int] = {}
    failures: list[str] = []

    for table in DATABASE_LOAD_TABLES:
        expected = expected_counts.get(table, 0)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}")
            actual = int(cursor.fetchone()[0])
        actual_counts[table] = actual

        if expected > 0 and actual < expected:
            failures.append(f"{table}: expected at least {expected}, found {actual}")

    if failures:
        raise DatabaseLoadValidationError(
            "Database load validation failed; "
            + "; ".join(failures)
        )

    return actual_counts


def _upsert_country(
    connection: Any, country_code: str, country_name: str | None = None
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO countries (country_code, name)
            VALUES (%s, %s)
            ON CONFLICT (country_code) DO NOTHING
            """,
            (country_code, country_name or country_code),
        )


def _upsert_institution(
    connection: Any, institution_name: str, country_code: str | None
) -> str:
    institution_name = institution_name.strip()
    _upsert_country(connection, country_code or "LK", country_code or "LK")
    institution_id = f"institution:{hashlib.sha1(institution_name.casefold().encode('utf-8')).hexdigest()[:16]}"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO institutions (institution_id, country_code, preferred_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (institution_id) DO UPDATE SET
                preferred_name = EXCLUDED.preferred_name,
                country_code = EXCLUDED.country_code
            """,
            (institution_id, country_code or "LK", institution_name),
        )
    return institution_id


def _upsert_author(connection: Any, display_name: str) -> str:
    author_id = str(uuid5(NAMESPACE_URL, f"author:{display_name.strip()}"))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO authors (author_id, display_name)
            VALUES (%s, %s)
            ON CONFLICT (author_id) DO NOTHING
            """,
            (author_id, display_name.strip()),
        )
    return author_id


def _upsert_keyword(connection: Any, keyword_text: str) -> str:
    keyword_id = str(uuid5(NAMESPACE_URL, f"keyword:{keyword_text.strip()}"))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO keywords (keyword_id, keyword_text)
            VALUES (%s, %s)
            ON CONFLICT (keyword_id) DO NOTHING
            """,
            (keyword_id, keyword_text.strip()),
        )
    return keyword_id


def _upsert_institution_alias(
    connection: Any, institution_id: str, alias_name: str
) -> None:
    alias_name = alias_name.strip()
    if not alias_name:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO institution_aliases (institution_id, alias_name)
            VALUES (%s, %s)
            ON CONFLICT (institution_id, alias_name) DO NOTHING
            """,
            (institution_id, alias_name),
        )


def _upsert_venue(connection: Any, record: dict[str, Any]) -> str | None:
    venue_name = (
        record.get("journal")
        or record.get("publisher")
        or record.get("source_type")
        or ""
    ).strip()
    if not venue_name:
        return None
    venue_id = str(uuid5(NAMESPACE_URL, f"venue:{venue_name.lower()}"))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO venues (
                venue_id,
                venue_name,
                venue_type,
                publisher,
                issn,
                issn_l
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (venue_id) DO NOTHING
            """,
            (
                venue_id,
                venue_name,
                "journal" if record.get("journal") else None,
                record.get("publisher"),
                record.get("issn"),
                record.get("issn_l"),
            ),
        )
    return venue_id


def _upsert_topic(connection: Any, topic_name: str, topic_level: str) -> str:
    topic_name = topic_name.strip()
    if not topic_name:
        raise ValueError("topic_name cannot be blank")
    topic_id = str(uuid5(NAMESPACE_URL, f"topic:{topic_level}:{topic_name.lower()}"))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO research_topics (topic_id, topic_name, topic_level)
            VALUES (%s, %s, %s)
            ON CONFLICT (topic_id) DO NOTHING
            """,
            (topic_id, topic_name, topic_level),
        )
    return topic_id


def _upsert_funder(
    connection: Any,
    funder_name: str,
    *,
    funder_doi: str | None = None,
    funder_identifier: str | None = None,
) -> str | None:
    name = funder_name.strip() if funder_name else ""
    if not name:
        return None
    funder_doi = None if is_blank(funder_doi) else str(funder_doi).strip()
    funder_identifier = (
        None if is_blank(funder_identifier) else str(funder_identifier).strip()
    )
    funder_id = str(uuid5(NAMESPACE_URL, f"funder:{name.lower()}"))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT funder_id
            FROM funders
            WHERE funder_id = %s
               OR funder_doi = %s
               OR funder_identifier = %s
            ORDER BY
                CASE
                    WHEN funder_doi = %s THEN 0
                    WHEN funder_identifier = %s THEN 1
                    WHEN funder_id = %s THEN 2
                    ELSE 3
                END
            LIMIT 1
            """,
            (
                funder_id,
                funder_doi,
                funder_identifier,
                funder_doi,
                funder_identifier,
                funder_id,
            ),
        )
        existing = cursor.fetchone()
        if existing is not None:
            existing_id = str(existing[0])
            cursor.execute(
                """
                UPDATE funders
                SET
                    funder_name = %s,
                    funder_doi = CASE
                        WHEN funder_doi IS NULL
                         AND %s::text IS NOT NULL
                         AND NOT EXISTS (
                            SELECT 1 FROM funders
                            WHERE funder_doi = %s AND funder_id <> %s
                         )
                        THEN %s
                        ELSE funder_doi
                    END,
                    funder_identifier = CASE
                        WHEN funder_identifier IS NULL
                         AND %s::text IS NOT NULL
                         AND NOT EXISTS (
                            SELECT 1 FROM funders
                            WHERE funder_identifier = %s AND funder_id <> %s
                         )
                        THEN %s
                        ELSE funder_identifier
                    END
                WHERE funder_id = %s
                """,
                (
                    name,
                    funder_doi,
                    funder_doi,
                    existing_id,
                    funder_doi,
                    funder_identifier,
                    funder_identifier,
                    existing_id,
                    funder_identifier,
                    existing_id,
                ),
            )
            return existing_id

        cursor.execute(
            """
            INSERT INTO funders (funder_id, funder_name, funder_doi, funder_identifier)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (funder_id) DO NOTHING
            """,
            (funder_id, name, funder_doi, funder_identifier),
        )
    return funder_id


def _upsert_event(connection: Any, record: dict[str, Any]) -> str | None:
    event_name = (record.get("event_name") or record.get("conference") or "").strip()
    if not event_name:
        return None
    event_id = str(uuid5(NAMESPACE_URL, f"event:{event_name.lower()}"))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO events (
                event_id,
                event_name,
                event_acronym,
                event_location,
                event_start_date,
                event_end_date,
                event_sponsor
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
            """,
            (
                event_id,
                event_name,
                record.get("event_acronym"),
                record.get("event_location"),
                record.get("event_start_date"),
                record.get("event_end_date"),
                record.get("event_sponsor"),
            ),
        )
    return event_id


def _parse_structured_value(value: str) -> Any:
    text = value.strip()
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text)
        except (json.JSONDecodeError, ValueError, SyntaxError):
            continue
    return text


def _split_reference_text(value: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(value):
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "[{":
            depth += 1
            continue
        if char in "]}":
            depth = max(0, depth - 1)
            continue
        if char == ";" and depth == 0:
            chunk = value[start:index].strip()
            if chunk:
                chunks.append(chunk)
            start = index + 1

    final_chunk = value[start:].strip()
    if final_chunk:
        chunks.append(final_chunk)
    return chunks


def _reference_items_from_payload(value: Any) -> list[Any]:
    if is_blank(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]

    text = str(value).strip()
    parsed = _parse_structured_value(text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        return [parsed]

    return [_parse_structured_value(chunk) for chunk in _split_reference_text(text)]


def _reference_field(reference: Any, *names: str) -> Any:
    if not isinstance(reference, dict):
        return None
    for name in names:
        value = reference.get(name)
        if not is_blank(value):
            return value
    return None


def _normalized_reference_doi(reference: Any) -> str | None:
    doi = normalize_doi(_reference_field(reference, "reference_doi", "DOI", "doi"))
    return None if is_blank(doi) else str(doi)


def _upsert_publication_reference(
    connection: Any,
    publication_id: str,
    reference_index: int,
    reference_data: dict[str, Any],
) -> None:
    reference_doi = reference_data.get("reference_doi") or reference_data.get("doi")
    reference_title = reference_data.get("reference_title") or reference_data.get(
        "title"
    )
    reference_author = reference_data.get("reference_author") or reference_data.get(
        "author"
    )
    reference_year = reference_data.get("reference_year") or reference_data.get("year")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO publication_references (
                publication_id,
                reference_index,
                reference_doi,
                reference_title,
                reference_author,
                reference_year,
                raw_reference_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (publication_id, reference_index) DO NOTHING
            """,
            (
                publication_id,
                reference_index,
                reference_doi,
                reference_title,
                reference_author,
                reference_year,
                json.dumps(reference_data, ensure_ascii=False),
            ),
        )


def _upsert_final_publication_reference(
    connection: Any,
    *,
    publication_key: str,
    row_number: int,
    record: dict[str, Any],
    reference_index: int,
    reference_data: Any,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO final_publication_references (
                publication_key,
                publication_row_number,
                source_dataset,
                source_record_id,
                doi,
                reference_index,
                reference_doi,
                reference_title,
                reference_author,
                reference_year,
                raw_reference_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (publication_key, reference_index) DO UPDATE SET
                publication_row_number = EXCLUDED.publication_row_number,
                source_dataset = EXCLUDED.source_dataset,
                source_record_id = EXCLUDED.source_record_id,
                doi = EXCLUDED.doi,
                reference_doi = EXCLUDED.reference_doi,
                reference_title = EXCLUDED.reference_title,
                reference_author = EXCLUDED.reference_author,
                reference_year = EXCLUDED.reference_year,
                raw_reference_json = EXCLUDED.raw_reference_json
            """,
            (
                publication_key,
                row_number,
                record.get("source_dataset"),
                record.get("source_record_id"),
                record.get("doi"),
                reference_index,
                _normalized_reference_doi(reference_data),
                _reference_field(
                    reference_data,
                    "reference_title",
                    "article-title",
                    "volume-title",
                    "title",
                    "unstructured",
                ),
                _reference_field(reference_data, "reference_author", "author"),
                coerce_integer(
                    _reference_field(reference_data, "reference_year", "year")
                ),
                json.dumps(make_json_safe(reference_data), ensure_ascii=False),
            ),
        )


def _numeric_difference(left: int | None, right: int | None) -> int | None:
    if left is None or right is None:
        return None
    return left - right


def _count_audit_payload(
    record: dict[str, Any],
    normalized: dict[str, Any],
) -> dict[str, Any] | None:
    citation_count = coerce_integer(
        record.get("citation_count")
        if not is_blank(record.get("citation_count"))
        else record.get("cited_by_count", normalized.get("citation_count"))
    )
    is_referenced_by_count = coerce_integer(record.get("is_referenced_by_count"))
    reference_count = coerce_integer(
        record.get("reference_count", normalized.get("reference_count"))
    )
    referenced_works_count = coerce_integer(record.get("referenced_works_count"))

    citation_difference = coerce_integer(
        record.get(
            "citation_count_difference_oa_minus_crossref",
            normalized.get("citation_count_difference_oa_minus_crossref"),
        )
    )
    if citation_difference is None:
        citation_difference = _numeric_difference(
            citation_count, is_referenced_by_count
        )

    reference_difference = coerce_integer(
        record.get(
            "reference_count_difference_oa_minus_crossref",
            normalized.get("reference_count_difference_oa_minus_crossref"),
        )
    )
    if reference_difference is None:
        reference_difference = _numeric_difference(
            referenced_works_count, reference_count
        )

    citation_flag = coerce_boolean(
        record.get(
            "citation_count_divergence_flag",
            normalized.get("citation_count_divergence_flag"),
        )
    )
    if citation_flag is None and citation_difference is not None:
        citation_flag = abs(citation_difference) >= 10

    reference_flag = coerce_boolean(
        record.get(
            "reference_count_divergence_flag",
            normalized.get("reference_count_divergence_flag"),
        )
    )
    if reference_flag is None and reference_difference is not None:
        reference_flag = abs(reference_difference) >= 1

    payload = {
        "citation_count": citation_count,
        "is_referenced_by_count": is_referenced_by_count,
        "reference_count": reference_count,
        "referenced_works_count": referenced_works_count,
        "citation_count_difference_oa_minus_crossref": citation_difference,
        "citation_count_divergence_flag": citation_flag,
        "reference_count_difference_oa_minus_crossref": reference_difference,
        "reference_count_divergence_flag": reference_flag,
    }
    if all(is_blank(payload[column]) for column in COUNT_AUDIT_COLUMNS):
        return None
    return payload


def _upsert_final_publication_count_audit(
    connection: Any,
    *,
    publication_key: str,
    row_number: int,
    record: dict[str, Any],
    normalized: dict[str, Any],
) -> bool:
    payload = _count_audit_payload(record, normalized)
    if payload is None:
        return False

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO final_publication_count_audit (
                publication_key,
                publication_row_number,
                source_dataset,
                source_record_id,
                doi,
                title,
                citation_count,
                is_referenced_by_count,
                reference_count,
                referenced_works_count,
                citation_count_difference_oa_minus_crossref,
                citation_count_divergence_flag,
                reference_count_difference_oa_minus_crossref,
                reference_count_divergence_flag
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (publication_key) DO UPDATE SET
                publication_row_number = EXCLUDED.publication_row_number,
                source_dataset = EXCLUDED.source_dataset,
                source_record_id = EXCLUDED.source_record_id,
                doi = EXCLUDED.doi,
                title = EXCLUDED.title,
                citation_count = EXCLUDED.citation_count,
                is_referenced_by_count = EXCLUDED.is_referenced_by_count,
                reference_count = EXCLUDED.reference_count,
                referenced_works_count = EXCLUDED.referenced_works_count,
                citation_count_difference_oa_minus_crossref = EXCLUDED.citation_count_difference_oa_minus_crossref,
                citation_count_divergence_flag = EXCLUDED.citation_count_divergence_flag,
                reference_count_difference_oa_minus_crossref = EXCLUDED.reference_count_difference_oa_minus_crossref,
                reference_count_divergence_flag = EXCLUDED.reference_count_divergence_flag
            """,
            (
                publication_key,
                row_number,
                normalized.get("source_dataset"),
                normalized.get("source_record_id"),
                normalized.get("doi"),
                normalized.get("title"),
                payload["citation_count"],
                payload["is_referenced_by_count"],
                payload["reference_count"],
                payload["referenced_works_count"],
                payload["citation_count_difference_oa_minus_crossref"],
                payload["citation_count_divergence_flag"],
                payload["reference_count_difference_oa_minus_crossref"],
                payload["reference_count_divergence_flag"],
            ),
        )
    return True


def _upsert_publication_location(
    connection: Any, publication_id: str, record: dict[str, Any]
) -> None:
    landing_page_url = record.get("url") or record.get("landing_page_url")
    pdf_url = record.get("pdf_url")
    source_name = record.get("source_dataset") or "dataset"
    source_type = record.get("source_type") or "dataset"
    license_value = record.get("license")
    version_value = record.get("version")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO publication_locations (
                publication_id,
                landing_page_url,
                pdf_url,
                source_name,
                source_type,
                license,
                version
            )
            SELECT %s, %s, %s, %s, %s, %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM publication_locations WHERE publication_id = %s
            )
            """,
            (
                publication_id,
                landing_page_url,
                pdf_url,
                source_name,
                source_type,
                license_value,
                version_value,
                publication_id,
            ),
        )


def _resolve_source_institution_id(
    connection: Any, source_institution_id: Any
) -> str | None:
    if source_institution_id is None:
        return None

    if (
        isinstance(source_institution_id, (list, tuple, set))
        and not source_institution_id
    ):
        return None

    value = str(source_institution_id).strip()
    if not value or value in {"()", "[]", "{}", "nil", "null", "none"}:
        return None

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT institution_id FROM institutions WHERE institution_id = %s",
            (value,),
        )
        if cursor.fetchone() is not None:
            return value

    if value.startswith("institution:"):
        return None

    return _upsert_institution(connection, value, "LK")


def _upsert_source_record(
    connection: Any,
    *,
    source_dataset: str,
    source_record_id: str,
    raw_payload: dict[str, Any],
    source_institution_id: str | None,
) -> str:
    source_id = str(uuid5(NAMESPACE_URL, f"source:{source_dataset}"))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO data_sources (source_id, source_name, source_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (source_name) DO NOTHING
            """,
            (source_id, source_dataset, "dataset"),
        )
        cursor.execute(
            "SELECT source_id FROM data_sources WHERE source_name = %s",
            (source_dataset,),
        )
        source_id = str(cursor.fetchone()[0])
        source_record_uuid = str(
            uuid5(NAMESPACE_URL, f"source_record:{source_dataset}:{source_record_id}")
        )
        cursor.execute(
            """
            INSERT INTO source_records (
                source_record_uuid,
                source_id,
                source_institution_id,
                source_record_id,
                raw_payload
            )
            VALUES (%s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (source_record_uuid) DO NOTHING
            """,
            (
                source_record_uuid,
                source_id,
                source_institution_id,
                source_record_id,
                json.dumps(raw_payload, ensure_ascii=False),
            ),
        )
        return source_record_uuid


def _upsert_publication(
    connection: Any,
    publication_key: str,
    record: dict[str, Any],
) -> str:
    publication_id = str(uuid5(NAMESPACE_URL, publication_key))
    normalized = build_final_publication_row(record, 1)
    title = publication_required_title(normalized, publication_key)
    if is_blank(normalized.get("title")):
        logger.warning(
            "Publication %s has no title; using fallback title=%s",
            publication_key,
            title,
        )
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO publications (
                publication_id,
                doi,
                openalex_id,
                title,
                abstract,
                publication_year,
                publication_date,
                publication_type,
                language,
                landing_page_url,
                pdf_url
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (publication_id) DO NOTHING
            """,
            (
                publication_id,
                normalized.get("doi"),
                normalized.get("openalex_id"),
                title,
                normalized.get("abstract"),
                normalized.get("publication_year"),
                normalized.get("publication_date"),
                normalized.get("type"),
                normalized.get("language"),
                normalized.get("url"),
                normalized.get("pdf_url"),
            ),
        )
    return publication_id


def publication_required_title(
    normalized: dict[str, Any], publication_key: str
) -> str:
    title = normalized.get("title")
    if not is_blank(title):
        return str(title)

    for label, column in (
        ("doi", "doi"),
        ("openalex", "openalex_id"),
        ("source", "source_record_id"),
    ):
        value = normalized.get(column)
        if not is_blank(value):
            return f"Untitled publication ({label}:{value})"

    return f"Untitled publication ({publication_key})"


def _link_publication_record(
    connection: Any,
    *,
    publication_id: str,
    source_record_uuid: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO publication_sources (
                publication_source_id,
                publication_id,
                source_record_uuid,
                source_priority,
                is_primary_source
            )
            VALUES (gen_random_uuid(), %s, %s, 0, true)
            ON CONFLICT (publication_id, source_record_uuid) DO NOTHING
            """,
            (publication_id, source_record_uuid),
        )


def _populate_relational_tables(
    connection: Any,
    record: dict[str, Any],
    publication_key: str,
    row_number: int,
) -> None:
    normalized = build_final_publication_row(record, row_number)
    source_dataset = str(record.get("source_dataset") or "unknown")
    source_record_id = str(
        record.get("source_record_id")
        or record.get("publication_id")
        or publication_key
    )
    log_prefix = f"Row {row_number} key={publication_key}"
    logger.info(
        "%s: relational load start title=%s source_dataset=%s source_record_id=%s",
        log_prefix,
        _short_log_value(record.get("title")),
        _short_log_value(source_dataset),
        _short_log_value(source_record_id),
    )
    source_institution_id = _resolve_source_institution_id(
        connection,
        record.get("source_institution_id"),
    )

    logger.info("%s: loading source_records/publications links", log_prefix)
    source_record_uuid = _upsert_source_record(
        connection,
        source_dataset=source_dataset,
        source_record_id=source_record_id,
        raw_payload=record,
        source_institution_id=source_institution_id,
    )
    publication_id = _upsert_publication(connection, publication_key, record)
    _link_publication_record(
        connection, publication_id=publication_id, source_record_uuid=source_record_uuid
    )
    logger.info("%s: source_records/publications links done", log_prefix)

    countries = []
    country_values = _split_text_values(record.get("countries"))
    logger.info("%s: loading countries count=%s", log_prefix, len(country_values))
    for value in country_values:
        country_code = _normalize_code(value)
        if country_code:
            countries.append(country_code)
            _upsert_country(connection, country_code, value)
    if countries:
        for country_code in sorted(set(countries)):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO publication_countries (publication_id, country_code)
                    VALUES (%s, %s)
                    ON CONFLICT (publication_id, country_code) DO NOTHING
                    """,
                    (publication_id, country_code),
                )
    logger.info(
        "%s: countries done linked=%s",
        log_prefix,
        len(set(countries)),
    )

    institutions = []
    institution_values = _split_text_values(record.get("institutions"))
    logger.info(
        "%s: loading institutions count=%s",
        log_prefix,
        len(institution_values),
    )
    for value in institution_values:
        if value:
            institutions.append(value)
            institution_id = _upsert_institution(
                connection, value, countries[0] if countries else "LK"
            )
            _upsert_institution_alias(connection, institution_id, value)
    logger.info(
        "%s: institutions done linked=%s",
        log_prefix,
        len(institutions),
    )

    logger.info("%s: loading venue", log_prefix)
    venue_id = _upsert_venue(connection, record)
    if venue_id:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE publications
                SET venue_id = %s
                WHERE publication_id = %s
                """,
                (venue_id, publication_id),
            )
    logger.info("%s: venue done loaded=%s", log_prefix, bool(venue_id))

    primary_topic_count = len(
        [
            record.get(field_name)
            for field_name in (
                "primary_domain",
                "primary_field",
                "primary_subfield",
                "primary_topic",
            )
            if not is_blank(record.get(field_name))
        ]
    )
    concept_values = _split_text_values(record.get("concepts"))
    logger.info(
        "%s: loading topics primary=%s concepts=%s",
        log_prefix,
        primary_topic_count,
        len(concept_values),
    )
    for topic_level, field_name in (
        ("domain", "primary_domain"),
        ("field", "primary_field"),
        ("subfield", "primary_subfield"),
        ("topic", "primary_topic"),
    ):
        topic_name = (record.get(field_name) or "").strip()
        if not topic_name:
            continue
        topic_id = _upsert_topic(connection, topic_name, topic_level)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO publication_topics (publication_id, topic_id, is_primary)
                VALUES (%s, %s, %s)
                ON CONFLICT (publication_id, topic_id) DO NOTHING
                """,
                (publication_id, topic_id, field_name == "primary_topic"),
            )

    for concept_name in concept_values:
        concept_id = _upsert_topic(connection, concept_name, "concept")
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO publication_topics (publication_id, topic_id, is_primary)
                VALUES (%s, %s, false)
                ON CONFLICT (publication_id, topic_id) DO NOTHING
                """,
                (publication_id, concept_id),
            )
    logger.info("%s: topics done", log_prefix)

    funder_names = _split_text_values(record.get("funder_name"))
    funder_dois = _split_text_values(record.get("funder_doi"))
    funder_identifiers = _split_text_values(record.get("funder_identifier"))
    funder_awards = _split_text_values(record.get("funder_award"))
    logger.info("%s: loading funders count=%s", log_prefix, len(funder_names))
    for index, funder_name in enumerate(funder_names):
        logger.info(
            "%s: funder %s/%s name=%s",
            log_prefix,
            index + 1,
            len(funder_names),
            _short_log_value(funder_name),
        )
        funder_id = _upsert_funder(
            connection,
            funder_name,
            funder_doi=funder_dois[index] if index < len(funder_dois) else None,
            funder_identifier=(
                funder_identifiers[index] if index < len(funder_identifiers) else None
            ),
        )
        if not funder_id:
            continue
        award_number = funder_awards[index] if index < len(funder_awards) else None
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO publication_funders (publication_funder_id, publication_id, funder_id, award_number)
                VALUES (gen_random_uuid(), %s, %s, %s)
                ON CONFLICT (publication_id, funder_id, award_number) DO NOTHING
                """,
                (publication_id, funder_id, award_number),
            )
    logger.info("%s: funders done", log_prefix)

    logger.info("%s: loading event", log_prefix)
    event_id = _upsert_event(connection, record)
    if event_id:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO publication_events (publication_event_id, publication_id, event_id)
                VALUES (gen_random_uuid(), %s, %s)
                ON CONFLICT (publication_id, event_id) DO NOTHING
                """,
                (publication_id, event_id),
            )
    logger.info("%s: event done loaded=%s", log_prefix, bool(event_id))

    refs = _reference_items_from_payload(record.get("references_json"))
    logger.info("%s: loading references count=%s", log_prefix, len(refs))
    for index, reference in enumerate(refs, start=1):
        logger.info(
            "%s: reference %s/%s",
            log_prefix,
            index,
            len(refs),
        )
        _upsert_final_publication_reference(
            connection,
            publication_key=publication_key,
            row_number=row_number,
            record=record,
            reference_index=index,
            reference_data=reference,
        )
        if isinstance(reference, dict):
            _upsert_publication_reference(connection, publication_id, index, reference)
    logger.info("%s: references done", log_prefix)

    logger.info("%s: loading publication_locations/count_audit", log_prefix)
    _upsert_publication_location(connection, publication_id, record)
    _upsert_final_publication_count_audit(
        connection,
        publication_key=publication_key,
        row_number=row_number,
        record=record,
        normalized=normalized,
    )
    logger.info("%s: publication_locations/count_audit done", log_prefix)

    authors = _split_text_values(record.get("authors"))
    logger.info(
        "%s: loading authors count=%s affiliations_per_author=%s",
        log_prefix,
        len(authors),
        len(institutions),
    )
    for author_position, author_name in enumerate(authors, start=1):
        logger.info(
            "%s: author %s/%s name=%s affiliations=%s",
            log_prefix,
            author_position,
            len(authors),
            _short_log_value(author_name),
            len(institutions),
        )
        author_id = _upsert_author(connection, author_name)
        publication_author_id = str(
            uuid5(NAMESPACE_URL, f"publication-author:{publication_key}:{author_name}")
        )
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO publication_authors (
                    publication_author_id,
                    publication_id,
                    author_id,
                    author_position,
                    raw_author_name
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (publication_author_id) DO NOTHING
                """,
                (
                    publication_author_id,
                    publication_id,
                    author_id,
                    author_position,
                    author_name,
                ),
            )
        for institution_name in institutions:
            institution_id = _upsert_institution(
                connection,
                institution_name,
                countries[0] if countries else "LK",
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO author_affiliations (
                        affiliation_id,
                        publication_author_id,
                        institution_id,
                        country_code
                    )
                    VALUES (gen_random_uuid(), %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        publication_author_id,
                        institution_id,
                        countries[0] if countries else "LK",
                    ),
                )
        logger.info(
            "%s: author %s/%s done",
            log_prefix,
            author_position,
            len(authors),
        )
    logger.info("%s: authors done", log_prefix)

    keyword_values = _split_text_values(record.get("keywords"))
    logger.info("%s: loading keywords count=%s", log_prefix, len(keyword_values))
    for index, keyword_text in enumerate(keyword_values, start=1):
        logger.info(
            "%s: keyword %s/%s text=%s",
            log_prefix,
            index,
            len(keyword_values),
            _short_log_value(keyword_text),
        )
        keyword_id = _upsert_keyword(connection, keyword_text)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO publication_keywords (publication_id, keyword_id)
                VALUES (%s, %s)
                ON CONFLICT (publication_id, keyword_id) DO NOTHING
                """,
                (publication_id, keyword_id),
            )
    logger.info("%s: keywords done", log_prefix)
    logger.info("%s: relational load done", log_prefix)


def _institution_id_for_name(institution_name: str) -> str:
    digest = hashlib.sha1(
        institution_name.strip().casefold().encode("utf-8")
    ).hexdigest()[:16]
    return f"institution:{digest}"


def _uuid_key(prefix: str, *parts: Any) -> str:
    payload = prefix + ":" + ":".join(str(part) for part in parts)
    return str(uuid5(NAMESPACE_URL, payload))


def _funder_identity_key(
    funder_name: str,
    funder_doi: str | None,
    funder_identifier: str | None,
) -> tuple[str, str]:
    if not is_blank(funder_doi):
        return ("doi", str(funder_doi).strip())
    if not is_blank(funder_identifier):
        return ("identifier", str(funder_identifier).strip())
    return ("name", funder_name.strip().casefold())


def _track_expected_load_counts(
    counts: dict[str, int],
    seen: dict[str, set[Any]],
    record: dict[str, Any],
    publication_key: str,
    row_number: int,
) -> None:
    normalized = build_final_publication_row(record, row_number)
    publication_id = str(uuid5(NAMESPACE_URL, publication_key))
    source_dataset = str(record.get("source_dataset") or "unknown")
    source_record_id = str(
        record.get("source_record_id")
        or record.get("publication_id")
        or publication_key
    )
    source_record_uuid = _uuid_key(
        "source_record", source_dataset, source_record_id
    )

    _mark_unique_count(counts, seen, "final_publications", publication_key)
    _mark_unique_count(counts, seen, "data_sources", source_dataset)
    _mark_unique_count(counts, seen, "source_records", source_record_uuid)
    _mark_unique_count(counts, seen, "publications", publication_id)
    _mark_unique_count(
        counts,
        seen,
        "publication_sources",
        (publication_id, source_record_uuid),
    )
    _mark_unique_count(counts, seen, "publication_locations", publication_id)

    countries = {
        code
        for value in _split_text_values(record.get("countries"))
        if (code := _normalize_code(value))
    }
    institutions = [
        value
        for value in _split_text_values(record.get("institutions"))
        if value
    ]
    if institutions and not countries:
        countries.add("LK")

    for country_code in countries:
        _mark_unique_count(counts, seen, "countries", country_code)
        _mark_unique_count(
            counts,
            seen,
            "publication_countries",
            (publication_id, country_code),
        )

    for institution_name in institutions:
        institution_id = _institution_id_for_name(institution_name)
        _mark_unique_count(counts, seen, "institutions", institution_id)
        _mark_unique_count(
            counts,
            seen,
            "institution_aliases",
            (institution_id, institution_name.strip()),
        )

    venue_name = (
        record.get("journal")
        or record.get("publisher")
        or record.get("source_type")
        or ""
    ).strip()
    if venue_name:
        _mark_unique_count(
            counts,
            seen,
            "venues",
            _uuid_key("venue", venue_name.lower()),
        )

    authors = _split_text_values(record.get("authors"))
    for author_name in authors:
        author_id = _uuid_key("author", author_name.strip())
        publication_author_id = _uuid_key(
            "publication-author", publication_key, author_name
        )
        _mark_unique_count(counts, seen, "authors", author_id)
        _mark_unique_count(
            counts,
            seen,
            "publication_authors",
            publication_author_id,
        )
        _mark_row_count(counts, "author_affiliations", len(institutions))

    for keyword_text in _split_text_values(record.get("keywords")):
        keyword_id = _uuid_key("keyword", keyword_text.strip())
        _mark_unique_count(counts, seen, "keywords", keyword_id)
        _mark_unique_count(
            counts,
            seen,
            "publication_keywords",
            (publication_id, keyword_id),
        )

    topic_keys: set[tuple[str, str]] = set()
    for topic_level, field_name in (
        ("domain", "primary_domain"),
        ("field", "primary_field"),
        ("subfield", "primary_subfield"),
        ("topic", "primary_topic"),
    ):
        topic_name = (record.get(field_name) or "").strip()
        if topic_name:
            topic_keys.add((topic_level, topic_name))
    topic_keys.update(
        ("concept", concept_name)
        for concept_name in _split_text_values(record.get("concepts"))
    )
    for topic_level, topic_name in topic_keys:
        topic_id = _uuid_key("topic", topic_level, topic_name.lower())
        _mark_unique_count(counts, seen, "research_topics", topic_id)
        _mark_unique_count(
            counts,
            seen,
            "publication_topics",
            (publication_id, topic_id),
        )

    funder_names = _split_text_values(record.get("funder_name"))
    funder_dois = _split_text_values(record.get("funder_doi"))
    funder_identifiers = _split_text_values(record.get("funder_identifier"))
    funder_awards = _split_text_values(record.get("funder_award"))
    for index, funder_name in enumerate(funder_names):
        funder_key = _funder_identity_key(
            funder_name,
            funder_dois[index] if index < len(funder_dois) else None,
            funder_identifiers[index] if index < len(funder_identifiers) else None,
        )
        award_number = funder_awards[index] if index < len(funder_awards) else None
        _mark_unique_count(counts, seen, "funders", funder_key)
        _mark_unique_count(
            counts,
            seen,
            "publication_funders",
            (publication_id, funder_key, award_number),
        )

    event_name = (record.get("event_name") or record.get("conference") or "").strip()
    if event_name:
        event_id = _uuid_key("event", event_name.lower())
        _mark_unique_count(counts, seen, "events", event_id)
        _mark_unique_count(
            counts,
            seen,
            "publication_events",
            (publication_id, event_id),
        )

    refs = _reference_items_from_payload(record.get("references_json"))
    for reference_index, reference in enumerate(refs, start=1):
        _mark_unique_count(
            counts,
            seen,
            "final_publication_references",
            (publication_key, reference_index),
        )
        if isinstance(reference, dict):
            _mark_unique_count(
                counts,
                seen,
                "publication_references",
                (publication_id, reference_index),
            )

    if _count_audit_payload(record, normalized) is not None:
        _mark_unique_count(
            counts,
            seen,
            "final_publication_count_audit",
            publication_key,
        )


def load_full_database_dataset(
    path: Path,
    *,
    file_format: str = "auto",
    database_url: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    ensure_schema: bool = True,
    limit: int | None = None,
) -> dict[str, int]:
    """Populate the normalized PostgreSQL schema from a final dataset file."""

    logger.info(
        "Starting full database load from %s with batch_size=%s", path, batch_size
    )

    records: Iterable[dict[str, Any]] = iter_record_file(
        path, file_format=file_format
    )
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be zero or greater.")
        records = islice(records, limit)
        logger.info("Applying limit=%s before loading", limit)

    connection = get_connection(database_url)
    counts = empty_load_counts()
    seen: dict[str, set[Any]] = {}
    try:
        if ensure_schema:
            logger.info("Ensuring database schema is present before loading")
            ensure_database_schema(connection)
        total_records = 0
        for batch_number, batch in enumerate(chunked(records, batch_size), start=1):
            logger.info(
                "Processing batch %s with %s records", batch_number, len(batch)
            )
            logger.info("Batch %s: upserting final_publications", batch_number)
            load_final_publications(
                batch,
                connection=connection,
                ensure_schema=False,
            )
            logger.info(
                "Batch %s: final_publications upsert done; loading relational tables",
                batch_number,
            )
            total_records += len(batch)
            for row_index, record in enumerate(batch, start=1):
                row_number = (batch_number - 1) * batch_size + row_index
                publication_key = build_final_publication_row(
                    record, row_number
                )["publication_key"]
                logger.info(
                    "Batch %s record %s/%s global_row=%s start key=%s title=%s",
                    batch_number,
                    row_index,
                    len(batch),
                    row_number,
                    publication_key,
                    _short_log_value(record.get("title")),
                )
                _populate_relational_tables(
                    connection,
                    record,
                    publication_key,
                    row_number,
                )
                _track_expected_load_counts(
                    counts,
                    seen,
                    record,
                    publication_key,
                    row_number,
                )
                logger.info(
                    "Batch %s record %s/%s global_row=%s done key=%s",
                    batch_number,
                    row_index,
                    len(batch),
                    row_number,
                    publication_key,
                )

                if row_index % 100 == 0 or row_index == len(batch):
                    logger.info(
                        "Batch %s progress: %s/%s records processed",
                        batch_number,
                        row_index,
                        len(batch),
                    )
            connection.commit()
            logger.info(
                "Batch %s complete: total_processed=%s final_publications=%s "
                "source_records=%s authors=%s keywords=%s",
                batch_number,
                total_records,
                counts["final_publications"],
                counts["source_records"],
                counts["authors"],
                counts["keywords"],
            )
        actual_counts = validate_loaded_database_tables(connection, counts)
        logger.info(
            "Database load table validation passed. Actual table counts: %s",
            actual_counts,
        )
        logger.info("Completed full database load. Expected counts: %s", counts)
        return counts
    except Exception:
        logger.exception("Full database load failed while processing records")
        connection.rollback()
        raise
    finally:
        connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load CSV, JSON, or JSONL publication records into PostgreSQL.",
    )
    parser.add_argument("path", type=Path, help="Input CSV, JSON, or JSONL file.")
    parser.add_argument(
        "--format",
        choices=SUPPORTED_FORMATS,
        default="auto",
        help="Input file format. Defaults to inferring from the filename.",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL URL. Defaults to DATABASE_URL from .env or the project default.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of records to upsert per transaction. Defaults to {DEFAULT_BATCH_SIZE}.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Load only the first N records, useful for smoke tests.",
    )
    parser.add_argument(
        "--no-ensure-schema",
        action="store_true",
        help="Skip applying pending database migrations before loading.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        loaded = load_record_file(
            args.path,
            file_format=args.format,
            database_url=args.database_url,
            batch_size=args.batch_size,
            ensure_schema=not args.no_ensure_schema,
            limit=args.limit,
        )
    except Exception as exc:
        raise SystemExit(f"Failed to load records: {exc}") from exc

    print(f"Loaded {loaded} records into PostgreSQL.")


if __name__ == "__main__":
    main(sys.argv[1:])
