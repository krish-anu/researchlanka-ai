"""HTTP route dispatch for the API package."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote

from src.api.constants import API_PREFIX
from src.api.errors import APIError
from src.api.service import ResearchLankaAPI


def route_get(
    service: ResearchLankaAPI,
    path: str,
    query: dict[str, list[str]],
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
    if path == f"{API_PREFIX}/exports/publications.csv":
        return service.export_publications(query, file_format="csv")
    if path == f"{API_PREFIX}/exports/publications.jsonl":
        return service.export_publications(query, file_format="jsonl")

    match = re.fullmatch(rf"{API_PREFIX}/exports/analytics/([a-z-]+)\.csv", path)
    if match:
        return service.export_analytics(query, name=match.group(1))

    match = re.fullmatch(rf"{API_PREFIX}/publications/(.+)/(references|count-audit)", path)
    if match:
        publication_key = unquote(match.group(1))
        child = match.group(2)
        if child == "references":
            return service.publication_references(publication_key, query)
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
