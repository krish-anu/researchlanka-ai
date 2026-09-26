"""Cross-path public visibility invariants for accepted publication data."""

from __future__ import annotations

from typing import Any

import pytest

from src.api.core.errors import APIError
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from src.api.services.nmf_topics import NmfTopicService


ACCEPTED_KEY = "doi:10.1000/accepted-ai"
REJECTED_KEY = "doi:10.1000/rejected-ai"


RAW_PUBLICATIONS = [
    {
        "publication_key": ACCEPTED_KEY,
        "title": "Accepted AI crop disease diagnosis in Sri Lanka",
        "doi": "10.1000/accepted-ai",
        "publication_year": 2026,
        "type": "journal-article",
        "authors": "Accepted Researcher; Shared Author",
        "institutions": "Accepted University; Shared Institute",
        "sri_lankan_institutions": "Accepted University",
        "countries": "LK",
        "journal": "AI Agriculture Journal",
        "publisher": "Example Publisher",
        "citation_count": 10,
        "reference_count": 20,
        "is_oa": True,
        "oa_status": "gold",
        "primary_field": "Computer Science",
        "primary_subfield": "Artificial Intelligence",
        "topics": "Machine learning; Agriculture",
        "concepts": "artificial intelligence",
        "source_dataset": "openalex",
        "source_record_id": "accepted-1",
        "ownership_decision": "INCLUDE",
        "ownership_confidence": "HIGH",
        "classifier_decision": "AI",
        "classifier_probability": "0.92",
        "review_status": "human_accepted",
        "dataset_version": "researchlanka-2026-09-26",
    },
    {
        "publication_key": REJECTED_KEY,
        "title": "Rejected smart sensor irrigation without AI",
        "doi": "10.1000/rejected-ai",
        "publication_year": 2026,
        "type": "journal-article",
        "authors": "Rejected Researcher; Shared Author",
        "institutions": "Rejected University; Shared Institute",
        "sri_lankan_institutions": "Rejected University",
        "countries": "LK",
        "journal": "Smart Systems Journal",
        "publisher": "Example Publisher",
        "citation_count": 99,
        "reference_count": 20,
        "is_oa": True,
        "oa_status": "gold",
        "primary_field": "Engineering",
        "primary_subfield": "Sensors",
        "topics": "Smart systems; Irrigation",
        "concepts": "sensors",
        "source_dataset": "openalex",
        "source_record_id": "rejected-1",
        "ownership_decision": "INCLUDE",
        "ownership_confidence": "HIGH",
        "classifier_decision": "AI",
        "classifier_probability": "0.81",
        "review_status": "human_rejected",
        "dataset_version": "researchlanka-2026-09-26",
    },
]


def public_eligible(row: dict[str, Any]) -> bool:
    return (
        row.get("review_status") in {"auto_accepted", "human_accepted"}
        and str(row.get("ownership_decision") or "").upper() == "INCLUDE"
        and str(row.get("ownership_confidence") or "").upper() in {"HIGH", "MEDIUM"}
    )


def semicolon_values(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def contains_token(value: Any, token: str) -> bool:
    return token.casefold() in str(value or "").casefold()


class PublicEligibilityRepository:
    """Fake repository that models the common public eligibility source."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.raw_rows = rows

    def health(self) -> bool:
        return True

    def metadata(self) -> dict[str, Any]:
        return {"publication_count": len(self._rows()), "snapshot_date": "2026-09-26"}

    def _rows(self) -> list[dict[str, Any]]:
        return [row for row in self.raw_rows if public_eligible(row)]

    def _filtered_rows(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        rows = self._rows()
        if filters.get("publication_keys") is not None:
            keys = set(filters["publication_keys"])
            rows = [row for row in rows if row["publication_key"] in keys]
        if filters.get("q"):
            query = str(filters["q"])
            rows = [
                row
                for row in rows
                if any(
                    contains_token(row.get(field), query)
                    for field in ("title", "abstract", "authors", "institutions", "journal")
                )
            ]
        for key, fields in {
            "researcher": ("authors",),
            "institution": ("institutions", "sri_lankan_institutions"),
            "topic": ("topics", "concepts"),
        }.items():
            values = filters.get(key) or []
            if values:
                rows = [
                    row
                    for row in rows
                    if any(
                        contains_token(row.get(field), value)
                        for value in values
                        for field in fields
                    )
                ]
        return rows

    def list_publications(self, filters, *, page, page_size, sort, include_facets):
        rows = self._filtered_rows(filters)
        start = (page - 1) * page_size
        return {
            "records": rows[start : start + page_size],
            "total": len(rows),
            "facets": {"publication_year": {"2026": len(rows)}} if include_facets else None,
            "meta": self.metadata(),
        }

    def get_publication(self, publication_key):
        return next((row for row in self._rows() if row["publication_key"] == publication_key), None)

    def get_references(self, publication_key):
        return []

    def get_count_audit(self, publication_key):
        return {"publication_key": publication_key, "citation_count": 10}

    def suggest(self, query, *, limit, types=None):
        rows = self._filtered_rows({"q": query})
        suggestions: list[dict[str, Any]] = []
        for row in rows:
            suggestions.append({"type": "publication", "value": row["title"], "key": row["publication_key"]})
            suggestions.extend(
                {"type": "researcher", "value": author, "key": author}
                for author in semicolon_values(row.get("authors"))
            )
            suggestions.extend(
                {"type": "institution", "value": institution, "key": institution}
                for institution in semicolon_values(row.get("institutions"))
            )
        return suggestions[:limit]

    def semantic_search(self, query, *, filters, limit, min_score):
        return [
            {**row, "semantic_score": 0.9, "semantic_rank": index + 1}
            for index, row in enumerate(self._filtered_rows({"q": query, **filters})[:limit])
        ]

    def related_publications(self, publication_key, *, filters, limit, min_score):
        if self.get_publication(publication_key) is None:
            raise KeyError(publication_key)
        return []

    def researcher_profile(self, researcher_key):
        rows = self._filtered_rows({"researcher": [researcher_key]})
        if not rows:
            return None
        return {"key": researcher_key, "label": researcher_key, "publication_count": len(rows)}

    def researcher_publications(self, researcher_key, *, page, page_size):
        rows = self._filtered_rows({"researcher": [researcher_key]})
        return {"records": rows[(page - 1) * page_size : page * page_size], "total": len(rows)}

    def researcher_coauthors(self, researcher_key, *, limit):
        return []

    def institution_profile(self, institution_key):
        rows = self._filtered_rows({"institution": [institution_key]})
        if not rows:
            return None
        return {"key": institution_key, "label": institution_key, "publication_count": len(rows)}

    def institution_publications(self, institution_key, *, page, page_size):
        rows = self._filtered_rows({"institution": [institution_key]})
        return {"records": rows[(page - 1) * page_size : page * page_size], "total": len(rows)}

    def institution_collaborators(self, institution_key, *, limit):
        return []

    def compare_institutions(self, institution_keys):
        return [
            profile
            for institution_key in institution_keys
            if (profile := self.institution_profile(institution_key)) is not None
        ]

    def topic_publications(self, topic_key, *, page, page_size):
        rows = self._filtered_rows({"topic": [topic_key]})
        return {"records": rows[(page - 1) * page_size : page * page_size], "total": len(rows)}

    def analytics_overview(self, filters):
        rows = self._filtered_rows(filters)
        return {"publication_count": len(rows), "citation_total": sum(row.get("citation_count") or 0 for row in rows)}

    def analytics_trends(self, filters, *, group_by, metric):
        rows = self._filtered_rows(filters)
        return [{"key": 2026, "publication_count": len(rows), "citation_total": 10 if rows else 0}]

    def analytics_rankings(self, filters, *, dimension, metric, limit):
        counter: dict[str, int] = {}
        for row in self._filtered_rows(filters):
            for value in semicolon_values(row.get(dimension)):
                counter[value] = counter.get(value, 0) + 1
        return [
            {"key": label.casefold().replace(" ", "-"), "label": label, "publication_count": count}
            for label, count in sorted(counter.items())
        ][:limit]

    def collaboration_network(self, filters, *, scope, min_weight, limit):
        return {"nodes": [], "edges": [], "summary": {"node_count": 0, "edge_count": 0}}

    def data_quality(self, filters, *, group_by):
        return {"record_count": len(self._filtered_rows(filters))}


class VisibilityTopicStore:
    k = 25

    def metadata(self):
        return {"nmf_k": self.k, "nmf_publication_count": 2}

    def ranking_entries(self, *, trend=None, sort="publications_desc", topic_ids=None):
        return [{"topic_id": 7, "topic_name": "ai / agriculture", "publication_count": 2, "trend": "stable"}]

    def publication_keys_for_topics(self, topic_ids):
        return [ACCEPTED_KEY, REJECTED_KEY] if 7 in topic_ids else []

    def publication_keys_for_topic_names(self, topic_names):
        return [ACCEPTED_KEY, REJECTED_KEY] if "ai / agriculture" in topic_names else []

    def assignment_for_publication(self, publication_key):
        if publication_key in {ACCEPTED_KEY, REJECTED_KEY}:
            return {
                "nmf_topic_id": 7,
                "nmf_topic_name": "ai / agriculture",
                "nmf_topic_weight": 0.74,
            }
        return None

    def resolve_topic_key(self, topic_key):
        return 7 if topic_key in {"7", "ai / agriculture"} else None

    def topic_trends(self, *, topic_ids=None, year_min=None, year_max=None):
        return [{"topic_id": 7, "topic_name": "ai / agriculture", "publication_count": 1}]


@pytest.fixture
def public_api() -> ResearchLankaAPI:
    return ResearchLankaAPI(
        PublicEligibilityRepository(RAW_PUBLICATIONS),
        nmf_service=NmfTopicService(VisibilityTopicStore()),
    )


def publication_keys(payload: dict[str, Any]) -> set[str]:
    return {row["publication_key"] for row in payload["data"]}


def values(payload: dict[str, Any]) -> set[str]:
    return {str(row.get("value") or row.get("label") or "") for row in payload["data"]}


def test_rejected_publication_is_hidden_across_public_paths(public_api: ResearchLankaAPI) -> None:
    search = route_get(public_api, "/api/v1/publications", {"q": ["AI"]})
    suggestions = route_get(public_api, "/api/v1/search/suggest", {"q": ["AI"]})
    analytics = route_get(public_api, "/api/v1/analytics/overview", {})
    nmf = route_get(public_api, "/api/v1/topics/7/publications", {})

    assert REJECTED_KEY not in publication_keys(search)
    assert "Rejected smart sensor irrigation without AI" not in values(suggestions)
    assert "Rejected Researcher" not in values(suggestions)
    assert "Rejected University" not in values(suggestions)
    assert analytics["data"]["publication_count"] == 1
    assert REJECTED_KEY not in publication_keys(nmf)

    with pytest.raises(APIError, match="Publication not found"):
        route_get(public_api, f"/api/v1/publications/{REJECTED_KEY}", {})
    with pytest.raises(APIError, match="Researcher not found"):
        route_get(public_api, "/api/v1/researchers/Rejected Researcher", {})
    with pytest.raises(APIError, match="Institution not found"):
        route_get(public_api, "/api/v1/institutions/Rejected University", {})


def test_accepted_publication_is_visible_across_public_paths(public_api: ResearchLankaAPI) -> None:
    search = route_get(public_api, "/api/v1/publications", {"q": ["AI"]})
    detail = route_get(public_api, f"/api/v1/publications/{ACCEPTED_KEY}", {})
    researcher = route_get(public_api, "/api/v1/researchers/Accepted Researcher", {})
    researcher_publications = route_get(public_api, "/api/v1/researchers/Accepted Researcher/publications", {})
    institution = route_get(public_api, "/api/v1/institutions/Accepted University", {})
    institution_publications = route_get(public_api, "/api/v1/institutions/Accepted University/publications", {})
    suggestions = route_get(public_api, "/api/v1/search/suggest", {"q": ["AI"]})
    analytics = route_get(public_api, "/api/v1/analytics/overview", {})
    nmf = route_get(public_api, "/api/v1/topics/7/publications", {})

    assert ACCEPTED_KEY in publication_keys(search)
    assert detail["data"]["publication_key"] == ACCEPTED_KEY
    assert researcher["data"]["publication_count"] == 1
    assert ACCEPTED_KEY in publication_keys(researcher_publications)
    assert institution["data"]["publication_count"] == 1
    assert ACCEPTED_KEY in publication_keys(institution_publications)
    assert "Accepted AI crop disease diagnosis in Sri Lanka" in values(suggestions)
    assert analytics["data"]["publication_count"] == 1
    assert ACCEPTED_KEY in publication_keys(nmf)
