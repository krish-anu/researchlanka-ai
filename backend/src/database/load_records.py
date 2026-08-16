"""Load publication record files into PostgreSQL."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
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
    ensure_database_schema,
    load_final_publications,
)

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
    funder_id = str(uuid5(NAMESPACE_URL, f"funder:{name.lower()}"))
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO funders (funder_id, funder_name, funder_doi, funder_identifier)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (funder_id) DO UPDATE SET
                funder_name = EXCLUDED.funder_name,
                funder_doi = EXCLUDED.funder_doi,
                funder_identifier = EXCLUDED.funder_identifier
            """,
            (funder_id, name, funder_doi or None, funder_identifier or None),
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
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (publication_id) DO NOTHING
            """,
            (
                publication_id,
                landing_page_url,
                pdf_url,
                source_name,
                source_type,
                license_value,
                version_value,
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
                normalized.get("title"),
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
    connection: Any, record: dict[str, Any], publication_key: str
) -> None:
    source_dataset = str(record.get("source_dataset") or "unknown")
    source_record_id = str(
        record.get("source_record_id")
        or record.get("publication_id")
        or publication_key
    )
    source_institution_id = _resolve_source_institution_id(
        connection,
        record.get("source_institution_id"),
    )

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

    countries = []
    for value in _split_text_values(record.get("countries")):
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

    institutions = []
    for value in _split_text_values(record.get("institutions")):
        if value:
            institutions.append(value)
            institution_id = _upsert_institution(
                connection, value, countries[0] if countries else "LK"
            )
            _upsert_institution_alias(connection, institution_id, value)

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

    for concept_name in _split_text_values(record.get("concepts")):
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

    funder_names = _split_text_values(record.get("funder_name"))
    funder_dois = _split_text_values(record.get("funder_doi"))
    funder_identifiers = _split_text_values(record.get("funder_identifier"))
    funder_awards = _split_text_values(record.get("funder_award"))
    for index, funder_name in enumerate(funder_names):
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

    references_payload = record.get("references_json")
    if isinstance(references_payload, str):
        try:
            refs = json.loads(references_payload)
        except json.JSONDecodeError:
            refs = []
    elif isinstance(references_payload, list):
        refs = references_payload
    else:
        refs = []
    for index, reference in enumerate(refs, start=1):
        if isinstance(reference, dict):
            _upsert_publication_reference(connection, publication_id, index, reference)

    _upsert_publication_location(connection, publication_id, record)

    authors = _split_text_values(record.get("authors"))
    for author_position, author_name in enumerate(authors, start=1):
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

    for keyword_text in _split_text_values(record.get("keywords")):
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

    records: Iterable[dict[str, Any]] = iter_record_file(path, file_format=file_format)
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be zero or greater.")
        records = islice(records, limit)

    connection = get_connection(database_url)
    counts = {
        "final_publications": 0,
        "source_records": 0,
        "countries": 0,
        "institutions": 0,
        "authors": 0,
        "keywords": 0,
        "publication_authors": 0,
        "publication_keywords": 0,
        "publication_countries": 0,
        "venues": 0,
        "institution_aliases": 0,
        "research_topics": 0,
        "publication_topics": 0,
        "funders": 0,
        "publication_funders": 0,
        "events": 0,
        "publication_events": 0,
        "publication_references": 0,
        "publication_locations": 0,
    }
    try:
        if ensure_schema:
            ensure_database_schema(connection)
        total_records = 0
        for batch_number, batch in enumerate(chunked(records, batch_size), start=1):
            loaded = load_final_publications(
                batch,
                connection=connection,
                ensure_schema=False,
            )
            counts["final_publications"] += loaded
            total_records += len(batch)
            for row_index, record in enumerate(batch, start=1):
                publication_key = build_final_publication_row(
                    record, (batch_number - 1) * batch_size + row_index
                )["publication_key"]
                _populate_relational_tables(connection, record, publication_key)
                counts["source_records"] += 1
                counts["countries"] += len(
                    {
                        code
                        for value in _split_text_values(record.get("countries"))
                        if (code := _normalize_code(value))
                    }
                )
                counts["institutions"] += len(
                    {
                        _upsert_institution(connection, value, "LK")
                        for value in _split_text_values(record.get("institutions"))
                        if value
                    }
                )
                counts["authors"] += len(
                    {
                        _upsert_author(connection, value)
                        for value in _split_text_values(record.get("authors"))
                        if value
                    }
                )
                counts["keywords"] += len(
                    {
                        _upsert_keyword(connection, value)
                        for value in _split_text_values(record.get("keywords"))
                        if value
                    }
                )
                counts["publication_authors"] += len(
                    _split_text_values(record.get("authors"))
                )
                counts["publication_keywords"] += len(
                    _split_text_values(record.get("keywords"))
                )
                counts["publication_countries"] += len(
                    {
                        code
                        for value in _split_text_values(record.get("countries"))
                        if (code := _normalize_code(value))
                    }
                )
                if record.get("journal") or record.get("publisher"):
                    counts["venues"] += 1
                if record.get("institutions"):
                    counts["institution_aliases"] += len(
                        _split_text_values(record.get("institutions"))
                    )
                if (
                    record.get("primary_topic")
                    or record.get("primary_field")
                    or record.get("primary_subfield")
                    or record.get("primary_domain")
                    or record.get("concepts")
                ):
                    counts["research_topics"] += len(
                        {
                            item
                            for item in _split_text_values(record.get("concepts"))
                            + [
                                value
                                for value in (
                                    record.get("primary_domain"),
                                    record.get("primary_field"),
                                    record.get("primary_subfield"),
                                    record.get("primary_topic"),
                                )
                                if value
                            ]
                        }
                    )
                    counts["publication_topics"] += len(
                        {
                            item
                            for item in _split_text_values(record.get("concepts"))
                            + [
                                value
                                for value in (
                                    record.get("primary_domain"),
                                    record.get("primary_field"),
                                    record.get("primary_subfield"),
                                    record.get("primary_topic"),
                                )
                                if value
                            ]
                        }
                    )
                if record.get("funder_name"):
                    counts["funders"] += len(
                        _split_text_values(record.get("funder_name"))
                    )
                    counts["publication_funders"] += len(
                        _split_text_values(record.get("funder_name"))
                    )
                if (
                    record.get("event_name")
                    or record.get("event_acronym")
                    or record.get("conference")
                ):
                    counts["events"] += 1
                    counts["publication_events"] += 1
                references_payload = record.get("references_json")
                if isinstance(references_payload, str):
                    try:
                        refs = json.loads(references_payload)
                    except json.JSONDecodeError:
                        refs = []
                elif isinstance(references_payload, list):
                    refs = references_payload
                else:
                    refs = []
                if refs:
                    counts["publication_references"] += len(refs)
                if (
                    record.get("url")
                    or record.get("pdf_url")
                    or record.get("landing_page_url")
                ):
                    counts["publication_locations"] += 1
            connection.commit()
        return counts
    except Exception:
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
