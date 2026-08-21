"""Application service for the read-only ResearchLanka API."""

from __future__ import annotations

from typing import Any

from src.api.core.constants import (
    API_VERSION,
    ARRAY_FIELDS,
    DATASET_STAGE,
    DEFAULT_PAGE_SIZE,
    LIST_FILTERS,
    MAX_PAGE_SIZE,
    PUBLICATION_SUMMARY_FIELDS,
    SORT_OPTIONS,
)
from src.api.core.errors import APIError
from src.api.core.exports import csv_bytes, publication_rows_to_csv, publication_rows_to_jsonl
from src.api.core.protocols import PublicationRepository
from src.api.core.query import (
    first,
    parse_bool,
    parse_filters,
    parse_optional_float,
    parse_positive_int,
    split_values,
)
from src.api.core.serializers import (
    list_response,
    normalize_value,
    publication_detail,
    publication_summary,
)
from src.api.repositories.postgres import is_institution_like_author
from src.database.final_schema import FINAL_PUBLICATION_COLUMNS


FILTER_QUERY_PARAMS = set(LIST_FILTERS)
PAGINATION_QUERY_PARAMS = {"page", "page_size"}
RANKING_QUERY_PARAMS = FILTER_QUERY_PARAMS | {"limit", "metric"}
SIMILARITY_QUERY_PARAMS = FILTER_QUERY_PARAMS | {"limit", "min_score"}


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
                "publication_summary_fields": PUBLICATION_SUMMARY_FIELDS,
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
        validate_query_params(
            query,
            FILTER_QUERY_PARAMS | PAGINATION_QUERY_PARAMS | {"sort", "include_facets"},
        )
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
        validate_resource_key(publication_key, field="publication_key")
        row = self.repository.get_publication(publication_key)
        if row is None:
            raise APIError("not_found", "Publication not found.", status=404)
        return {"data": publication_detail(row), "meta": self._meta()}

    def publication_references(self, publication_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_resource_key(publication_key, field="publication_key")
        validate_query_params(query, PAGINATION_QUERY_PARAMS)
        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        rows = self.repository.get_references(publication_key)
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        return list_response(page_rows, page=page, page_size=page_size, total=len(rows), meta=self._meta())

    def publication_count_audit(self, publication_key: str) -> dict[str, Any]:
        validate_resource_key(publication_key, field="publication_key")
        row = self.repository.get_count_audit(publication_key)
        if row is None:
            raise APIError("not_found", "Count audit evidence not found.", status=404)
        return {"data": normalize_value(row), "meta": self._meta()}

    def publication_raw(self, publication_key: str) -> dict[str, Any]:
        validate_resource_key(publication_key, field="publication_key")
        raise APIError(
            "disabled_endpoint",
            "Raw publication payloads are disabled for the public MVP.",
            status=403,
            details={"publication_key": publication_key},
        )

    def suggestions(self, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_query_params(query, {"q", "limit"})
        text = first(query, "q") or ""
        limit = min(parse_positive_int(query, "limit", default=10), 50)
        return {"data": self.repository.suggest(text, limit=limit), "meta": self._meta()}

    def facets(self, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_query_params(query, FILTER_QUERY_PARAMS)
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

    def semantic_search(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._query_similarity_response(query, mode="semantic")

    def similarity_search(self, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._query_similarity_response(query, mode="similarity")

    def _query_similarity_response(
        self,
        query: dict[str, list[str]],
        *,
        mode: str,
    ) -> dict[str, Any]:
        validate_query_params(query, SIMILARITY_QUERY_PARAMS)
        text = (first(query, "q") or "").strip()
        if not text:
            raise APIError(
                "invalid_filter",
                "Similarity search requires a non-empty q parameter.",
                details={"field": "q"},
            )
        filters = parse_filters(query)
        filters.pop("q", None)
        limit = min(parse_positive_int(query, "limit", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        min_score = self._semantic_min_score(query)
        rows = self._run_semantic_search(
            text,
            filters=filters,
            limit=limit,
            min_score=min_score,
        )
        return self._semantic_list_response(
            rows,
            filters={"q": text, **filters},
            limit=limit,
            min_score=min_score,
            mode=mode,
        )

    def related_publications(self, publication_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._publication_similarity_response(publication_key, query, mode="semantic")

    def similar_publications(self, publication_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        return self._publication_similarity_response(publication_key, query, mode="similarity")

    def _publication_similarity_response(
        self,
        publication_key: str,
        query: dict[str, list[str]],
        *,
        mode: str,
    ) -> dict[str, Any]:
        validate_resource_key(publication_key, field="publication_key")
        validate_query_params(query, SIMILARITY_QUERY_PARAMS - {"q"})
        filters = parse_filters(query)
        filters.pop("q", None)
        limit = min(parse_positive_int(query, "limit", default=10), MAX_PAGE_SIZE)
        min_score = self._semantic_min_score(query)
        rows = self._run_related_publications(
            publication_key,
            filters=filters,
            limit=limit,
            min_score=min_score,
        )
        return self._semantic_list_response(
            rows,
            filters={"publication_key": publication_key, **filters},
            limit=limit,
            min_score=min_score,
            mode=mode,
        )

    def researchers(self, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_query_params(query, FILTER_QUERY_PARAMS | {"limit"})
        filters = parse_filters(query)
        filters["dimension"] = "authors"
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        overfetch_limit = max(limit * 3, limit + 25)
        rows = self.repository.analytics_rankings(
            filters,
            dimension="authors",
            metric="publications",
            limit=overfetch_limit,
        )
        rows = [
            row
            for row in rows
            if not is_institution_like_author(row.get("label"))
        ][:limit]
        return {"data": rows, "meta": self._meta()}

    def researcher_profile(self, researcher_key: str) -> dict[str, Any]:
        validate_resource_key(researcher_key, field="researcher_key")
        if is_institution_like_author(researcher_key):
            raise APIError("not_found", "Researcher not found.", status=404)
        row = self.repository.researcher_profile(researcher_key)
        if row is None:
            raise APIError("not_found", "Researcher not found.", status=404)
        row = dict(row)
        row.setdefault("disambiguation_level", "name")
        return {"data": normalize_value(row), "meta": self._meta()}

    def researcher_publications(self, researcher_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_resource_key(researcher_key, field="researcher_key")
        if is_institution_like_author(researcher_key):
            raise APIError("not_found", "Researcher not found.", status=404)
        validate_query_params(query, PAGINATION_QUERY_PARAMS)
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
        validate_resource_key(researcher_key, field="researcher_key")
        if is_institution_like_author(researcher_key):
            raise APIError("not_found", "Researcher not found.", status=404)
        validate_query_params(query, {"limit"})
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        overfetch_limit = max(limit * 3, limit + 25)
        rows = self.repository.researcher_coauthors(
            researcher_key,
            limit=overfetch_limit,
        )
        rows = [
            row
            for row in rows
            if not is_institution_like_author(row.get("name"))
        ][:limit]
        return {"data": rows, "meta": self._meta()}

    def institutions(self, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_query_params(query, RANKING_QUERY_PARAMS)
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
        validate_resource_key(institution_key, field="institution_key")
        row = self.repository.institution_profile(institution_key)
        if row is None:
            raise APIError("not_found", "Institution not found.", status=404)
        return {"data": normalize_value(row), "meta": self._meta()}

    def institution_publications(self, institution_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_resource_key(institution_key, field="institution_key")
        validate_query_params(query, PAGINATION_QUERY_PARAMS)
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
        validate_resource_key(institution_key, field="institution_key")
        validate_query_params(query, {"limit"})
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        return {"data": self.repository.institution_collaborators(institution_key, limit=limit), "meta": self._meta()}

    def compare_institutions(self, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_query_params(query, {"institution", "institutions"})
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
        validate_query_params(query, FILTER_QUERY_PARAMS | {"limit"})
        filters = parse_filters(query)
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        rows = self.repository.analytics_rankings(filters, dimension="topics", metric="publications", limit=limit)
        return {"data": rows, "meta": self._meta()}

    def topic_publications(self, topic_key: str, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_resource_key(topic_key, field="topic_key")
        validate_query_params(query, PAGINATION_QUERY_PARAMS)
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
        validate_query_params(query, FILTER_QUERY_PARAMS | {"level", "limit"})
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
        validate_query_params(query, FILTER_QUERY_PARAMS)
        filters = parse_filters(query)
        return {"data": self.repository.analytics_overview(filters), "meta": self._meta()}

    def analytics_trends(self, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_query_params(query, FILTER_QUERY_PARAMS | {"group_by", "metric"})
        filters = parse_filters(query)
        group_by = first(query, "group_by") or "year"
        metric = first(query, "metric") or "publications"
        return {
            "data": self.repository.analytics_trends(filters, group_by=group_by, metric=metric),
            "filters": {"applied": filters},
            "meta": self._meta(),
        }

    def analytics_rankings(self, query: dict[str, list[str]], *, dimension: str) -> dict[str, Any]:
        validate_query_params(query, RANKING_QUERY_PARAMS)
        filters = parse_filters(query)
        metric = first(query, "metric") or "publications"
        limit = min(parse_positive_int(query, "limit", default=50), 100)
        return {
            "data": self.repository.analytics_rankings(filters, dimension=dimension, metric=metric, limit=limit),
            "filters": {"applied": filters},
            "meta": self._meta(),
        }

    def collaboration_network(self, query: dict[str, list[str]]) -> dict[str, Any]:
        validate_query_params(query, FILTER_QUERY_PARAMS | {"scope", "min_weight", "limit"})
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
        validate_query_params(query, FILTER_QUERY_PARAMS | {"group_by"})
        filters = parse_filters(query)
        group_by = first(query, "group_by")
        return {
            "data": self.repository.data_quality(filters, group_by=group_by),
            "filters": {"applied": filters},
            "meta": self._meta(),
        }

    def export_publications(self, query: dict[str, list[str]], *, file_format: str) -> tuple[bytes, str]:
        validate_query_params(query, FILTER_QUERY_PARAMS | {"sort", "limit"})
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
            return publication_rows_to_jsonl(rows), "application/x-ndjson; charset=utf-8"
        if file_format == "csv":
            return publication_rows_to_csv(rows), "text/csv; charset=utf-8"
        raise APIError("not_found", "Export format not found.", status=404)

    def export_analytics(self, query: dict[str, list[str]], *, name: str) -> tuple[bytes, str]:
        validate_query_params(query, FILTER_QUERY_PARAMS | {"group_by", "metric", "limit"})
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

    def _semantic_min_score(self, query: dict[str, list[str]]) -> float | None:
        min_score = parse_optional_float(query, "min_score")
        if min_score is not None and not -1.0 <= min_score <= 1.0:
            raise APIError(
                "invalid_filter",
                "min_score must be between -1 and 1.",
                details={"field": "min_score"},
            )
        return min_score

    def _run_semantic_search(
        self,
        text: str,
        *,
        filters: dict[str, Any],
        limit: int,
        min_score: float | None,
    ) -> list[dict[str, Any]]:
        try:
            return self.repository.semantic_search(
                text,
                filters=filters,
                limit=limit,
                min_score=min_score,
            )
        except FileNotFoundError as exc:
            raise APIError(
                "semantic_search_unavailable",
                "Semantic search artifacts are not available.",
                status=503,
                details={"artifact": str(exc)},
            ) from exc
        except ValueError as exc:
            raise APIError("invalid_filter", str(exc)) from exc

    def _run_related_publications(
        self,
        publication_key: str,
        *,
        filters: dict[str, Any],
        limit: int,
        min_score: float | None,
    ) -> list[dict[str, Any]]:
        try:
            return self.repository.related_publications(
                publication_key,
                filters=filters,
                limit=limit,
                min_score=min_score,
            )
        except KeyError as exc:
            raise APIError(
                "not_found",
                "Publication embedding not found.",
                status=404,
                details={"publication_key": publication_key},
            ) from exc
        except FileNotFoundError as exc:
            raise APIError(
                "semantic_search_unavailable",
                "Semantic search artifacts are not available.",
                status=503,
                details={"artifact": str(exc)},
            ) from exc
        except ValueError as exc:
            raise APIError("invalid_filter", str(exc)) from exc

    def _semantic_list_response(
        self,
        rows: list[dict[str, Any]],
        *,
        filters: dict[str, Any],
        limit: int,
        min_score: float | None,
        mode: str = "semantic",
    ) -> dict[str, Any]:
        summaries = [semantic_publication_summary(row) for row in rows]
        meta = self._meta()
        meta["search"] = {
            "mode": mode,
            "algorithm": "tfidf_svd_cosine_similarity",
            "min_score": min_score,
        }
        return list_response(
            summaries,
            page=1,
            page_size=limit,
            total=len(summaries),
            filters=filters,
            meta=meta,
        )


def semantic_publication_summary(row: dict[str, Any]) -> dict[str, Any]:
    summary = publication_summary(row)
    if row.get("semantic_score") is not None:
        summary["semantic_score"] = row.get("semantic_score")
    if row.get("semantic_rank") is not None:
        summary["semantic_rank"] = row.get("semantic_rank")
    if row.get("similarity_score") is not None:
        summary["similarity_score"] = row.get("similarity_score")
    if row.get("similarity_rank") is not None:
        summary["similarity_rank"] = row.get("similarity_rank")
    return summary


def validate_query_params(query: dict[str, list[str]], allowed: set[str]) -> None:
    unsupported = sorted(set(query) - allowed)
    if unsupported:
        raise APIError(
            "invalid_query_parameter",
            "Unsupported query parameter.",
            details={"fields": unsupported, "allowed": sorted(allowed)},
        )


def validate_resource_key(value: str, *, field: str) -> None:
    if not value or not value.strip():
        raise APIError(
            "invalid_path_parameter",
            f"{field} must be a non-empty value.",
            status=422,
            details={"field": field},
        )


__all__ = ["APIError", "ResearchLankaAPI"]
