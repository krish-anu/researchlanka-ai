"""NMF topic-model helpers wired into existing /topics and /analytics endpoints."""

from __future__ import annotations

from typing import Any

from src.api.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from src.api.core.errors import APIError
from src.api.core.query import first, parse_positive_int
from src.api.core.serializers import list_response, publication_summary
from src.api.repositories.nmf_topics import NmfTopicStore, get_nmf_topic_store


TOPIC_DIRECTORY_QUERY_PARAMS = {
    "source",
    "trend",
    "sort",
    "topic_id",
    "include",
    "year_min",
    "year_max",
    "page",
    "page_size",
    "limit",
    "metric",
}


def parse_topic_ids(query: dict[str, list[str]]) -> list[int]:
    topic_ids: list[int] = []
    for raw in query.get("topic_id", []):
        for value in raw.split(","):
            value = value.strip()
            if not value:
                continue
            try:
                topic_ids.append(int(value))
            except ValueError as exc:
                raise APIError(
                    "invalid_filter",
                    "topic_id must be an integer.",
                    details={"field": "topic_id"},
                ) from exc
    return topic_ids


class NmfTopicService:
    """Read-only NMF topic modeling operations for existing API routes."""

    def __init__(self, store: NmfTopicStore | None = None) -> None:
        self.store = store

    def _require_store(self) -> NmfTopicStore:
        if self.store is None:
            try:
                self.store = get_nmf_topic_store()
            except FileNotFoundError as exc:
                raise APIError(
                    "service_unavailable",
                    "NMF topic-model artifacts are not available.",
                    details={"reason": str(exc)},
                    status=503,
                ) from exc
        return self.store

    def metadata(self) -> dict[str, Any]:
        return self._require_store().metadata()

    def list_topics(self, query: dict[str, list[str]], *, meta: dict[str, Any]) -> dict[str, Any]:
        store = self._require_store()
        trend = first(query, "trend")
        if trend and trend not in {"emerging", "declining", "stable"}:
            raise APIError(
                "invalid_filter",
                "trend must be emerging, declining, or stable.",
                details={"field": "trend"},
            )
        sort = first(query, "sort") or "publications_desc"
        if sort not in {"topic_id", "slope_desc", "publications_desc", "name_asc"}:
            raise APIError("invalid_filter", "Unsupported topic sort.", details={"field": "sort"})
        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        rows = store.ranking_entries(
            trend=trend,
            sort=sort,
            topic_ids=parse_topic_ids(query) or None,
        )
        include = first(query, "include")
        if include == "detail" and len(parse_topic_ids(query)) == 1:
            detail = store.get_topic(parse_topic_ids(query)[0])
            if detail is not None and rows:
                rows[0] = {**rows[0], **detail}
        start = (page - 1) * page_size
        return list_response(rows[start : start + page_size], page=page, page_size=page_size, total=len(rows), meta=meta)

    def topic_trends(self, query: dict[str, list[str]], *, meta: dict[str, Any]) -> dict[str, Any]:
        store = self._require_store()
        topic_ids = parse_topic_ids(query)
        year_min = parse_positive_int(query, "year_min", default=int(store.trend_shares.index.min()))
        year_max = parse_positive_int(query, "year_max", default=int(store.trend_shares.index.max()))
        if year_min > year_max:
            raise APIError(
                "invalid_filter",
                "year_min must be less than or equal to year_max.",
                details={"field": "year_min"},
            )
        rows = store.topic_trends(
            topic_ids=topic_ids or None,
            year_min=year_min,
            year_max=year_max,
        )
        return {"data": rows, "meta": meta}

    def topic_publications(
        self,
        topic_key: str,
        query: dict[str, list[str]],
        *,
        repository: Any,
        meta: dict[str, Any],
    ) -> dict[str, Any] | None:
        store = self._require_store()
        topic_id = store.resolve_topic_key(topic_key)
        if topic_id is None:
            return None
        page = parse_positive_int(query, "page", default=1)
        page_size = min(parse_positive_int(query, "page_size", default=DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE)
        publication_keys = store.publication_keys_for_topics([topic_id])
        result = repository.list_publications(
            {"publication_keys": publication_keys},
            page=page,
            page_size=page_size,
            sort="year_desc",
            include_facets=False,
        )
        rows = []
        for row in result.get("records", []):
            summary = publication_summary(row)
            assignment = store.assignment_for_publication(summary["publication_key"])
            if assignment:
                summary["nmf_topic_id"] = assignment["nmf_topic_id"]
                summary["nmf_topic_name"] = assignment["nmf_topic_name"]
                summary["nmf_topic_weight"] = assignment["nmf_topic_weight"]
            rows.append(summary)
        return list_response(
            rows,
            page=page,
            page_size=page_size,
            total=int(result.get("total", len(rows))),
            meta=meta,
        )
