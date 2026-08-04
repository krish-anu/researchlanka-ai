"""Response shaping helpers for API resources."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from typing import Any

from src.api.constants import API_VERSION, ARRAY_FIELDS, DATASET_STAGE


def publication_summary(row: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_row(row)
    return {
        "publication_key": normalized.get("publication_key"),
        "title": normalized.get("title"),
        "doi": normalized.get("doi"),
        "publication_year": normalized.get("publication_year"),
        "type": normalized.get("type"),
        "authors": normalized.get("authors", []),
        "institutions": normalized.get("institutions", []),
        "journal": normalized.get("journal"),
        "publisher": normalized.get("publisher"),
        "citation_count": normalized.get("citation_count"),
        "reference_count": normalized.get("reference_count"),
        "is_oa": normalized.get("is_oa"),
        "oa_status": normalized.get("oa_status"),
        "primary_field": normalized.get("primary_field"),
        "primary_subfield": normalized.get("primary_subfield"),
        "source_dataset": normalized.get("source_dataset", []),
        "quality_flags": quality_flags(normalized),
    }


def publication_detail(row: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_row(row)
    return {
        **publication_summary(row),
        "abstract": normalized.get("abstract"),
        "openalex_id": normalized.get("openalex_id"),
        "url": normalized.get("url"),
        "pdf_url": normalized.get("pdf_url"),
        "publication_date": normalized.get("publication_date"),
        "author_orcids": normalized.get("author_orcids", []),
        "sri_lankan_authors": normalized.get("sri_lankan_authors"),
        "sri_lankan_institutions": normalized.get("sri_lankan_institutions", []),
        "countries": normalized.get("countries", []),
        "venue": {
            "journal": normalized.get("journal"),
            "publisher": normalized.get("publisher"),
            "issn": normalized.get("issn", []),
            "issn_l": normalized.get("issn_l"),
            "volume": normalized.get("volume"),
            "issue": normalized.get("issue"),
            "pages": {
                "first": normalized.get("first_page"),
                "last": normalized.get("last_page"),
                "article_number": normalized.get("article_number"),
            },
        },
        "access": {
            "is_oa": normalized.get("is_oa"),
            "oa_status": normalized.get("oa_status"),
            "license": normalized.get("license"),
            "license_url": normalized.get("license_url"),
        },
        "impact": {
            "citation_count": normalized.get("citation_count"),
            "reference_count": normalized.get("reference_count"),
            "citation_count_difference_oa_minus_crossref": normalized.get(
                "citation_count_difference_oa_minus_crossref"
            ),
            "citation_count_divergence_flag": normalized.get("citation_count_divergence_flag"),
            "reference_count_difference_oa_minus_crossref": normalized.get(
                "reference_count_difference_oa_minus_crossref"
            ),
            "reference_count_divergence_flag": normalized.get("reference_count_divergence_flag"),
        },
        "classification": {
            "concepts": normalized.get("concepts", []),
            "topics": normalized.get("topics", []),
            "primary_topic": normalized.get("primary_topic"),
            "primary_field": normalized.get("primary_field"),
            "primary_subfield": normalized.get("primary_subfield"),
            "primary_domain": normalized.get("primary_domain"),
        },
        "funding": {
            "funder_name": normalized.get("funder_name", []),
            "funder_doi": normalized.get("funder_doi", []),
            "funder_identifier": normalized.get("funder_identifier", []),
            "funder_award": normalized.get("funder_award", []),
        },
        "provenance": {
            "source_dataset": normalized.get("source_dataset", []),
            "source_institution_id": normalized.get("source_institution_id"),
            "source_record_id": normalized.get("source_record_id"),
            "source_datestamp": normalized.get("source_datestamp"),
            "raw_identifiers": normalized.get("raw_identifiers"),
            "raw_record_available": bool(normalized.get("raw_record")),
        },
    }


def list_response(
    rows: list[Any],
    *,
    page: int,
    page_size: int,
    total: int,
    filters: dict[str, Any] | None = None,
    facets: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "data": normalize_value(rows),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": math.ceil(total / page_size) if page_size else 0,
        },
        "meta": meta or {"api_version": API_VERSION, "dataset_stage": DATASET_STAGE},
    }
    if filters is not None:
        payload["filters"] = {"applied": filters}
    if facets is not None:
        payload["facets"] = normalize_value(facets)
    return payload


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: split_semicolon_value(value) if key in ARRAY_FIELDS else normalize_value(value)
        for key, value in dict(row).items()
    }


def split_semicolon_value(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [normalize_value(item) for item in value if item not in (None, "")]
    return [part.strip() for part in str(value).split(";") if part.strip()]


def quality_flags(row: dict[str, Any]) -> list[str]:
    flags = []
    if not row.get("doi"):
        flags.append("missing_doi")
    if not row.get("abstract"):
        flags.append("missing_abstract")
    if not row.get("institutions") and not row.get("sri_lankan_institutions"):
        flags.append("missing_institutions")
    if row.get("citation_count_divergence_flag"):
        flags.append("citation_count_divergence")
    if row.get("reference_count_divergence_flag"):
        flags.append("reference_count_divergence")
    source_dataset = {str(value).casefold() for value in row.get("source_dataset", [])}
    local_sources = {"local", "repositories", "repositories_combined", "sljol"}
    global_sources = {"openalex", "crossref"}
    if source_dataset and source_dataset.intersection(local_sources) and not source_dataset.intersection(global_sources):
        flags.append("repository_only")
    if not row.get("doi") and source_dataset.intersection(local_sources):
        flags.append("no_doi_local_record")
    if row.get("topics") or row.get("concepts"):
        flags.append("topic_model_source")
    return flags


def normalize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime) and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_value(item) for item in value]
    return value
