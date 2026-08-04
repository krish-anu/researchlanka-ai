"""Common publication schema and field-mapping helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

STANDARD_PUBLICATION_FIELDS = (
    "publication_id",
    "source_name",
    "source_record_id",
    "doi",
    "title",
    "normalized_title",
    "abstract",
    "publication_year",
    "publication_date",
    "publication_type",
    "language",
    "journal",
    "publisher",
    "authors",
    "institutions",
    "countries",
    "keywords",
    "categories",
    "topics",
    "citation_count",
    "open_access_status",
    "source_url",
    "collected_at",
    "national_association",
    "collaboration_type",
    "national_institution_ids",
    "national_institutions",
    "resolved_institutions",
    "unresolved_institutions",
    "source_specific_metadata",
    "raw_record",
    "processing_status",
)


def empty_publication_record() -> dict[str, Any]:
    """Create an empty record that follows the standard publication schema."""

    return {field: None for field in STANDARD_PUBLICATION_FIELDS}


def map_to_standard_schema(
    raw_record: dict[str, Any],
    column_mapping: dict[str, str] | None = None,
    *,
    source_name: str | None = None,
    raw_filename: str | None = None,
    adapter_version: str = "1.0",
    mapping_version: str = "1.0",
    transformation_version: str = "standard-schema-v1",
) -> dict[str, Any]:
    """Map arbitrary source fields into the framework publication schema."""

    column_mapping = column_mapping or {}
    mapped = empty_publication_record()
    source_specific_metadata: dict[str, Any] = {}

    for source_field, value in raw_record.items():
        target_field = column_mapping.get(source_field, source_field)
        if target_field in mapped:
            mapped[target_field] = value
        else:
            source_specific_metadata[source_field] = value

    if source_name and not mapped.get("source_name"):
        mapped["source_name"] = source_name
    if not mapped.get("collected_at"):
        mapped["collected_at"] = datetime.now(timezone.utc).isoformat()
    mapped["source_specific_metadata"] = source_specific_metadata
    mapped["raw_record"] = raw_record
    mapped["processing_status"] = "transformed"

    mapped["_provenance"] = {
        "raw_filename": raw_filename,
        "adapter_version": adapter_version,
        "mapping_version": mapping_version,
        "transformation_version": transformation_version,
    }
    return mapped
