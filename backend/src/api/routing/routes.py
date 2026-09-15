"""HTTP route dispatch for the API package."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import unquote

from src.api.core.constants import API_PREFIX
from src.api.core.errors import APIError
from src.api.services.incremental_admin import (
    read_incremental_status,
    require_admin_api_token,
    start_incremental_update,
)
from src.api.services.ai_review import (
    assign_initial_pending,
    backfill_review_records,
    decide_review,
    list_reviews,
    parse_reviewers,
    queue_retry,
    validate_final_dataset,
    with_connection,
)
from src.api.services.publications import ResearchLankaAPI


def route_get(
    service: ResearchLankaAPI,
    path: str,
    query: dict[str, list[str]],
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any] | tuple[bytes, str]:
    if path in {"/health", f"{API_PREFIX}/health"}:
        return service.health()
    if path == f"{API_PREFIX}/meta":
        return service.metadata()
    if path == f"{API_PREFIX}/schema/publications":
        return service.schema()
    if path == f"{API_PREFIX}/limitations":
        return service.limitations()
    if path == f"{API_PREFIX}/publications":
        return service.list_publications(query)
    if path == f"{API_PREFIX}/search/suggest":
        return service.suggestions(query)
    if path == f"{API_PREFIX}/search/semantic":
        return service.semantic_search(query)
    if path in {f"{API_PREFIX}/search/similarity", f"{API_PREFIX}/search/similar"}:
        return service.similarity_search(query)
    if path == f"{API_PREFIX}/search/facets":
        return service.facets(query)
    if path == f"{API_PREFIX}/researchers":
        return service.researchers(query)
    if path == f"{API_PREFIX}/institutions":
        return service.institutions(query)
    if path == f"{API_PREFIX}/institutions/compare":
        return service.compare_institutions(query)
    if path == f"{API_PREFIX}/topics":
        return service.topics(query)
    if path == f"{API_PREFIX}/fields":
        return service.fields(query)
    if path == f"{API_PREFIX}/analytics/overview":
        return service.analytics_overview(query)
    if path == f"{API_PREFIX}/analytics/trends":
        return service.analytics_trends(query)
    if path == f"{API_PREFIX}/analytics/institutions":
        return service.analytics_rankings(query, dimension="institutions")
    if path == f"{API_PREFIX}/analytics/fields":
        return service.analytics_rankings(query, dimension="primary_field")
    if path == f"{API_PREFIX}/analytics/collaboration-network":
        return service.collaboration_network(query)
    if path == f"{API_PREFIX}/analytics/data-quality":
        return service.data_quality(query)
    if path == f"{API_PREFIX}/admin/incremental/status":
        require_admin_api_token(headers)
        return {"data": read_incremental_status(), "meta": service._meta()}
    if path == f"{API_PREFIX}/admin/ai-review":
        require_admin_api_token(headers)
        actor_email = str((headers or {}).get("x-researchlanka-actor-email") or "")
        return {
            "data": with_connection(
                lambda connection: list_reviews(
                    connection,
                    actor_email=actor_email,
                    all_reviews=(query.get("view", ["mine"])[0] == "all"),
                    page=int(query.get("page", ["1"])[0]),
                    page_size=int(query.get("page_size", ["25"])[0]),
                    status=query.get("status", [None])[0],
                    confidence=query.get("confidence", [None])[0],
                    reviewer=query.get("reviewer", [None])[0],
                    q=query.get("q", [None])[0],
                )
            ),
            "meta": service._meta(),
        }
    if path == f"{API_PREFIX}/admin/ai-review/validate-final-dataset":
        require_admin_api_token(headers)
        return {"data": with_connection(validate_final_dataset), "meta": service._meta()}
    if path == f"{API_PREFIX}/exports/publications.csv":
        return service.export_publications(query, file_format="csv")
    if path == f"{API_PREFIX}/exports/publications.jsonl":
        return service.export_publications(query, file_format="jsonl")

    match = re.fullmatch(rf"{API_PREFIX}/exports/analytics/([a-z-]+)\.csv", path)
    if match:
        return service.export_analytics(query, name=match.group(1))

    match = re.fullmatch(rf"{API_PREFIX}/publications/(.+)/(references|count-audit|related|similar)", path)
    if match:
        publication_key = unquote(match.group(1))
        child = match.group(2)
        if child == "references":
            return service.publication_references(publication_key, query)
        if child == "related":
            return service.related_publications(publication_key, query)
        if child == "similar":
            return service.similar_publications(publication_key, query)
        return service.publication_count_audit(publication_key)

    match = re.fullmatch(rf"{API_PREFIX}/publications/(.+)/raw", path)
    if match:
        return service.publication_raw(unquote(match.group(1)))

    match = re.fullmatch(rf"{API_PREFIX}/publications/(.+)", path)
    if match:
        return service.publication_detail(unquote(match.group(1)))

    match = re.fullmatch(rf"{API_PREFIX}/researchers/(.+)/(publications|coauthors)", path)
    if match:
        researcher_key = unquote(match.group(1))
        child = match.group(2)
        if child == "publications":
            return service.researcher_publications(researcher_key, query)
        return service.researcher_coauthors(researcher_key, query)

    match = re.fullmatch(rf"{API_PREFIX}/researchers/(.+)", path)
    if match:
        return service.researcher_profile(unquote(match.group(1)))

    match = re.fullmatch(rf"{API_PREFIX}/institutions/(.+)/(publications|collaborators)", path)
    if match:
        institution_key = unquote(match.group(1))
        child = match.group(2)
        if child == "publications":
            return service.institution_publications(institution_key, query)
        return service.institution_collaborators(institution_key, query)

    match = re.fullmatch(rf"{API_PREFIX}/institutions/(.+)", path)
    if match:
        return service.institution_profile(unquote(match.group(1)))

    match = re.fullmatch(rf"{API_PREFIX}/topics/(.+)/publications", path)
    if match:
        return service.topic_publications(unquote(match.group(1)), query)

    raise APIError("not_found", "Endpoint not found.", status=404)


def route_post(
    service: ResearchLankaAPI,
    path: str,
    payload: dict[str, Any],
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if path == f"{API_PREFIX}/admin/incremental/run":
        require_admin_api_token(headers)
        return {
            "data": start_incremental_update(payload),
            "meta": service._meta(),
        }
    if path == f"{API_PREFIX}/admin/ai-review/backfill":
        require_admin_api_token(headers)
        return {
            "data": with_connection(
                lambda connection: {
                    "backfill": backfill_review_records(connection),
                    "assignment": assign_initial_pending(connection, parse_reviewers()),
                }
            ),
            "meta": service._meta(),
        }
    if path == f"{API_PREFIX}/admin/ai-review/decide":
        require_admin_api_token(headers)
        actor = {
            "id": str((headers or {}).get("x-researchlanka-actor-id") or ""),
            "email": str((headers or {}).get("x-researchlanka-actor-email") or "").lower(),
            "name": str((headers or {}).get("x-researchlanka-actor-name") or ""),
        }
        return {
            "data": with_connection(
                lambda connection: decide_review(
                    connection,
                    publication_key=str(payload.get("publication_key") or ""),
                    decision=str(payload.get("decision") or ""),
                    notes=str(payload.get("notes") or ""),
                    actor=actor,
                    expected_version=int(payload.get("record_version") or 0),
                )
            ),
            "meta": service._meta(),
        }
    if path == f"{API_PREFIX}/admin/ai-review/retry-sync":
        require_admin_api_token(headers)
        return {
            "data": with_connection(
                lambda connection: queue_retry(connection, str(payload.get("publication_key") or ""))
            ),
            "meta": service._meta(),
        }

    raise APIError("not_found", "Endpoint not found.", status=404)
