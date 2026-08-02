"""Application service for the read-only ResearchLanka API."""

from __future__ import annotations

import math
import csv
import io
import json
from datetime import date, datetime, timezone
from typing import Any, Protocol

from src.database.final_schema import FINAL_PUBLICATION_COLUMNS


DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DATASET_STAGE = "final_publications"
API_VERSION = "v1"

LIST_FILTERS = {
    "q",
    "year_min",
    "year_max",
    "type",
    "institution",
    "country",
    "field",
    "subfield",
    "topic",
    "journal",
    "source_dataset",
    "is_oa",
    "has_doi",
    "has_abstract",
    "quality_flag",
}
SORT_OPTIONS = {"relevance", "year_desc", "year_asc", "citations_desc", "title_asc"}

ARRAY_FIELDS = {
    "authors",
    "author_orcids",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "issn",
    "concepts",
    "topics",
    "funder_name",
    "funder_doi",
    "funder_identifier",
    "funder_award",
    "source_dataset",
}


class APIError(Exception):
    """API-facing validation or lookup error."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


class PublicationRepository(Protocol):
    """Storage operations required by the API service."""

    def health(self) -> bool:
        """Return whether the backing store is reachable."""

    def metadata(self) -> dict[str, Any]:
        """Return dataset metadata and counts."""

    def list_publications(
        self,
        filters: dict[str, Any],
        *,
        page: int,
        page_size: int,
        sort: str,
        include_facets: bool,
    ) -> dict[str, Any]:
        """Return publication rows, total count, and optional facet counts."""

    def get_publication(self, publication_key: str) -> dict[str, Any] | None:
        """Return one publication row."""

    def get_references(self, publication_key: str) -> list[dict[str, Any]]:
        """Return sidecar reference rows for a publication."""

    def get_count_audit(self, publication_key: str) -> dict[str, Any] | None:
        """Return count-audit sidecar evidence for a publication."""

    def suggest(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        """Return autocomplete suggestions."""

    def researcher_profile(self, researcher_key: str) -> dict[str, Any] | None:
        """Return an author/researcher aggregate."""

    def researcher_publications(
        self,
        researcher_key: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Return publications for an author/researcher."""

    def researcher_coauthors(self, researcher_key: str, *, limit: int) -> list[dict[str, Any]]:
        """Return coauthor aggregates."""

    def institution_profile(self, institution_key: str) -> dict[str, Any] | None:
        """Return an institution aggregate."""

    def institution_publications(
        self,
        institution_key: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Return publications for an institution."""

    def institution_collaborators(self, institution_key: str, *, limit: int) -> list[dict[str, Any]]:
        """Return collaborator aggregates for an institution."""

    def compare_institutions(self, institution_keys: list[str]) -> list[dict[str, Any]]:
        """Return headline metrics for selected institutions."""

    def topic_publications(
        self,
        topic_key: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Return publications for a topic."""

    def analytics_overview(self, filters: dict[str, Any]) -> dict[str, Any]:
        """Return national headline analytics."""

    def analytics_trends(self, filters: dict[str, Any], *, group_by: str, metric: str) -> list[dict[str, Any]]:
        """Return trend rows."""

    def analytics_rankings(
        self,
        filters: dict[str, Any],
        *,
        dimension: str,
        metric: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return ranked aggregate rows."""

    def collaboration_network(
        self,
        filters: dict[str, Any],
        *,
        scope: str,
        min_weight: int,
        limit: int,
    ) -> dict[str, Any]:
        """Return graph nodes and edges."""

    def data_quality(self, filters: dict[str, Any], *, group_by: str | None) -> dict[str, Any]:
        """Return data-quality metrics."""


class ResearchLankaAPI:
    """High-level read-only API operations."""

    def __init__(self, repository: PublicationRepository) -> None:
        self.repository = repository

    def health(self) -> dict[str, Any]:
        ok = self.repository.health()
        return {
            "data": {
                "status": "ok" if ok else "unavailable",
                "api_version": API_VERSION,
            },
            "meta": self._meta(),
        }

    def metadata(self) -> dict[str, Any]:
        data = self.repository.metadata()
        return {
            "data": {
                "api_version": API_VERSION,
                "dataset_stage": DATASET_STAGE,
                "supported_filters": sorted(LIST_FILTERS),
                "supported_sorts": sorted(SORT_OPTIONS),
                **data,
            },
            "meta": self._meta(data),
        }

    def schema(self) -> dict[str, Any]:
        return {
            "data": {
                "publication_summary_fields": [
                    "publication_key",
                    "title",
                    "doi",
                    "publication_year",
                    "type",
                    "authors",
                    "institutions",
                    "journal",
                    "publisher",
                    "citation_count",
                    "reference_count",
                    "is_oa",
                    "oa_status",
                    "primary_field",
                    "primary_subfield",
                    "source_dataset",
                    "quality_flags",
                ],
                "final_publication_columns": ["publication_key", *FINAL_PUBLICATION_COLUMNS],
                "array_fields": sorted(ARRAY_FIELDS),
            },
            "meta": self._meta(),
        }

    def limitations(self) -> dict[str, Any]:
        return {
            "data": {
                "limitations": [
                    "observed_records_not_national_totals",
                    "doi_poor_local_repositories",
                    "source_specific_missingness",
                    "cross_source_conflicts",
                    "snapshot_counts_can_lag",
                    "author_disambiguation_limited",
                ],
                "required_disclosures": [
                    "source_snapshot_date",
                    "dataset_stage",
                    "denominator",
                    "field_missingness",
                    "conflict_policy",
                    "citation_count_source",
                    "known_exclusions",
                ],
                "document": "docs/11_metadata_quality_limitations.md",
            },
            "meta": self._meta(),
        }

    def list_publications(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        sort = first(query, "sort") or ("relevance" if filters.get("q") else "year_desc")
        if sort not in SORT_OPTIONS:
            raise APIError(
                "invalid_sort",
                f"Unsupported sort: {sort}.",
                details={"field": "sort", "allowed": sorted(SORT_OPTIONS)},
            )
        include_facets = parse_bool(first(query, "include_facets"), default=False)
        result = self.repository.list_publications(
            filters,
            page=page,
            page_size=page_size,
            sort=sort,
            include_facets=include_facets,
        )
        rows = [publication_summary(row) for row in result.get("records", [])]
        total = int(result.get("total", len(rows)))
        return list_response(
            rows,
            page=page,
            page_size=page_size,
            total=total,
            filters=filters,
            facets=result.get("facets"),
            meta=self._meta(result.get("meta")),
        )

    def publication_detail(self, publication_key: str) -> dict[str, Any]:
        row = self.repository.get_publication(publication_key)
        if row is None:
            raise APIError("not_found", "Publication not found.", status=404)
        return {"data": publication_detail(row), "meta": self._meta()}

    def publication_references(self, publication_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        rows = self.repository.get_references(publication_key)
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        return list_response(page_rows, page=page, page_size=page_size, total=len(rows), meta=self._meta())

    def publication_count_audit(self, publication_key: str) -> dict[str, Any]:
        row = self.repository.get_count_audit(publication_key)
        if row is None:
            raise APIError("not_found", "Count audit evidence not found.", status=404)
        return {"data": normalize_value(row), "meta": self._meta()}

    def publication_raw(self, publication_key: str) -> dict[str, Any]:
        raise APIError(
            "disabled_endpoint",
            "Raw publication payloads are disabled for the public MVP.",
            status=403,
            details={"publication_key": publication_key},
        )

    def suggestions(self, query: dict[str, list[str]]) -> dict[str, Any]:
        text = first(query, "q") or ""
        limit = min(parse_positive_int(query, "limit", default=10), 50)
        return {"data": self.repository.suggest(text, limit=limit), "meta": self._meta()}

    def facets(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        result = self.repository.list_publications(
            filters,
            page=1,
            page_size=1,
            sort="year_desc",
            include_facets=True,
        )
        return {
            "data": result.get("facets", {}),
            "filters": {"applied": filters},
            "meta": self._meta(result.get("meta")),
        }

    def researchers(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        filters["dimension"] = "authors"
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        rows = self.repository.analytics_rankings(filters, dimension="authors", metric="publications", limit=limit)
        return {"data": rows, "meta": self._meta()}

    def researcher_profile(self, researcher_key: str) -> dict[str, Any]:
        row = self.repository.researcher_profile(researcher_key)
        if row is None:
            raise APIError("not_found", "Researcher not found.", status=404)
        row = dict(row)
        row.setdefault("disambiguation_level", "name")
        return {"data": normalize_value(row), "meta": self._meta()}

    def researcher_publications(self, researcher_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        result = self.repository.researcher_publications(researcher_key, page=page, page_size=page_size)
        return list_response(
            [publication_summary(row) for row in result.get("records", [])],
            page=page,
            page_size=page_size,
            total=int(result.get("total", 0)),
            meta=self._meta(),
        )

    def researcher_coauthors(self, researcher_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        return {"data": self.repository.researcher_coauthors(researcher_key, limit=limit), "meta": self._meta()}

    def institutions(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        rows = self.repository.analytics_rankings(
            filters,
            dimension="institutions",
            metric=first(query, "metric") or "publications",
            limit=limit,
        )
        return {"data": rows, "meta": self._meta()}

    def institution_profile(self, institution_key: str) -> dict[str, Any]:
        row = self.repository.institution_profile(institution_key)
        if row is None:
            raise APIError("not_found", "Institution not found.", status=404)
        return {"data": normalize_value(row), "meta": self._meta()}

    def institution_publications(self, institution_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        result = self.repository.institution_publications(institution_key, page=page, page_size=page_size)
        return list_response(
            [publication_summary(row) for row in result.get("records", [])],
            page=page,
            page_size=page_size,
            total=int(result.get("total", 0)),
            meta=self._meta(),
        )

    def institution_collaborators(self, institution_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        return {"data": self.repository.institution_collaborators(institution_key, limit=limit), "meta": self._meta()}

    def compare_institutions(self, query: dict[str, list[str]]) -> dict[str, Any]:
        keys = query.get("institution", []) or split_values(first(query, "institutions"))
        keys = [key for key in keys if key]
        if not 2 <= len(keys) <= 3:
            raise APIError(
                "invalid_filter",
                "Compare requires 2-3 institution values.",
                details={"field": "institution"},
            )
        return {"data": self.repository.compare_institutions(keys), "meta": self._meta()}

    def topics(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        rows = self.repository.analytics_rankings(filters, dimension="topics", metric="publications", limit=limit)
        return {"data": rows, "meta": self._meta()}

    def topic_publications(self, topic_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        result = self.repository.topic_publications(topic_key, page=page, page_size=page_size)
        return list_response(
            [publication_summary(row) for row in result.get("records", [])],
            page=page,
            page_size=page_size,
            total=int(result.get("total", 0)),
            meta=self._meta(),
        )

    def fields(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        level = first(query, "level") or "field"
        dimension = {
            "domain": "primary_domain",
            "field": "primary_field",
            "subfield": "primary_subfield",
            "topic": "topics",
        }.get(level)
        if dimension is None:
            raise APIError("invalid_filter", "Unsupported field level.", details={"field": "level"})
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        rows = self.repository.analytics_rankings(filters, dimension=dimension, metric="publications", limit=limit)
        return {"data": rows, "meta": self._meta()}

    def analytics_overview(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        return {"data": self.repository.analytics_overview(filters), "meta": self._meta()}

    def analytics_trends(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        group_by = first(query, "group_by") or "year"
        metric = first(query, "metric") or "publications"
        return {
            "data": self.repository.analytics_trends(filters, group_by=group_by, metric=metric),
            "filters": {"applied": filters},
            "meta": self._meta(),
        }

    def analytics_rankings(self, query: dict[str, list[str]], *, dimension: str) -> dict[str, Any]:
        filters = parse_filters(query)
        metric = first(query, "metric") or "publications"
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        return {
            "data": self.repository.analytics_rankings(filters, dimension=dimension, metric=metric, limit=limit),
            "filters": {"applied": filters},
            "meta": self._meta(),
        }

    def collaboration_network(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        scope = first(query, "scope") or "institution"
        if scope not in {"institution", "country", "researcher"}:
            raise APIError("invalid_filter", "Unsupported network scope.", details={"field": "scope"})
        min_weight = parse_positive_int(query, "min_weight", default=1)
        limit = min(parse_positive_int(query, "limit", default=100), 500)
        return {
            "data": self.repository.collaboration_network(
                filters,
                scope=scope,
                min_weight=min_weight,
                limit=limit,
            ),
            "filters": {"applied": filters},
            "meta": self._meta(),
        }

    def data_quality(self, query: dict[str, list[str]]) -> dict[str, Any]:
        filters = parse_filters(query)
        group_by = first(query, "group_by")
        return {
            "data": self.repository.data_quality(filters, group_by=group_by),
            "filters": {"applied": filters},
            "meta": self._meta(),
        }

    def export_publications(self, query: dict[str, list[str]], *, file_format: str) -> tuple[bytes, str]:
        filters = parse_filters(query)
        sort = first(query, "sort") or ("relevance" if filters.get("q") else "year_desc")
        if sort not in SORT_OPTIONS:
            raise APIError("invalid_sort", f"Unsupported sort: {sort}.", details={"field": "sort"})
        limit = min(parse_positive_int(query, "limit", default=10_000), 50_000)
        result = self.repository.list_publications(
            filters,
            page=1,
            page_size=limit,
            sort=sort,
            include_facets=False,
        )
        rows = [publication_summary(row) for row in result.get("records", [])]
        if file_format == "jsonl":
            payload = "".join(
                json.dumps(normalize_value(row), ensure_ascii=False) + "\n"
                for row in rows
            )
            return payload.encode("utf-8"), "application/x-ndjson; charset=utf-8"
        if file_format == "csv":
            fieldnames = [
                "publication_key",
                "title",
                "doi",
                "publication_year",
                "type",
                "authors",
                "institutions",
                "journal",
                "publisher",
                "citation_count",
                "reference_count",
                "is_oa",
                "oa_status",
                "primary_field",
                "primary_subfield",
                "source_dataset",
                "quality_flags",
            ]
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: "; ".join(str(item) for item in value)
                        if isinstance(value, list)
                        else value
                        for key, value in row.items()
                    }
                )
            return buffer.getvalue().encode("utf-8"), "text/csv; charset=utf-8"
        raise APIError("not_found", "Export format not found.", status=404)

    def export_analytics(self, query: dict[str, list[str]], *, name: str) -> tuple[bytes, str]:
        if name == "overview":
            data = [self.analytics_overview(query)["data"]]
        elif name == "trends":
            data = self.analytics_trends(query)["data"]
        elif name == "institutions":
            data = self.analytics_rankings(query, dimension="institutions")["data"]
        elif name == "fields":
            data = self.analytics_rankings(query, dimension="primary_field")["data"]
        elif name == "data-quality":
            data = [self.data_quality(query)["data"]]
        else:
            raise APIError("not_found", "Analytics export not found.", status=404)
        return csv_bytes(data), "text/csv; charset=utf-8"

    def _meta(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        snapshot_date = None
        if extra:
            snapshot_date = extra.get("snapshot_date") or extra.get("max_loaded_at")
        return {
            "api_version": API_VERSION,
            "dataset_stage": DATASET_STAGE,
            "snapshot_date": snapshot_date,
        }


def parse_filters(query: dict[str, list[str]]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for key in LIST_FILTERS:
        values = query.get(key)
        if not values:
            continue
        if key in {"type", "institution", "country", "field", "subfield", "topic", "journal", "source_dataset", "quality_flag"}:
            filters[key] = [item for value in values for item in split_values(value)]
        elif key in {"is_oa", "has_doi", "has_abstract"}:
            filters[key] = parse_bool(values[-1])
        elif key in {"year_min", "year_max"}:
            filters[key] = parse_int(values[-1], key)
        else:
            filters[key] = values[-1].strip()

    year_min = filters.get("year_min")
    year_max = filters.get("year_max")
    if year_min is not None and year_max is not None and year_min > year_max:
        raise APIError(
            "invalid_filter",
            "year_min must be less than or equal to year_max.",
            details={"field": "year_min"},
        )
    return filters


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


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    fieldnames = sorted({field for row in rows for field in row}) or ["value"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(normalize_value(value), ensure_ascii=False)
                if isinstance(value, (dict, list))
                else normalize_value(value)
                for key, value in row.items()
            }
        )
    return buffer.getvalue().encode("utf-8")


def first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[-1]


def parse_positive_int(query: dict[str, list[str]], key: str, *, default: int) -> int:
    value = first(query, key)
    if value is None or value == "":
        return default
    parsed = parse_int(value, key)
    if parsed < 1:
        raise APIError("invalid_filter", f"{key} must be at least 1.", details={"field": key})
    return parsed


def parse_int(value: str, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise APIError("invalid_filter", f"{field} must be an integer.", details={"field": field}) from exc


def parse_bool(value: str | None, *, default: bool | None = None) -> bool | None:
    if value is None or value == "":
        return default
    text = value.casefold()
    if text in {"true", "t", "yes", "y", "1"}:
        return True
    if text in {"false", "f", "no", "n", "0"}:
        return False
    raise APIError("invalid_filter", f"Invalid boolean value: {value}.")


def split_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]
