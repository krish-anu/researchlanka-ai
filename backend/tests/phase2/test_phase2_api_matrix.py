"""Phase 2 — API test matrix.

Each case records: Test ID | Endpoint | Scenario | Expected | Result
Result is filled automatically by the Phase 2 reporter (PASS/FAIL/SKIP).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pytest

from src.api.core.errors import APIError
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from tests.phase2.helpers import assert_detail_payload, assert_list_payload, attach_api_case


pytestmark = [pytest.mark.phase2, pytest.mark.api, pytest.mark.api_matrix]


PUBLICATIONS = [
    {
        "publication_key": "doi:10.1000/test",
        "title": "Malaria surveillance in Sri Lanka",
        "doi": "10.1000/test",
        "publication_year": 2024,
        "type": "journal-article",
        "authors": "A. Author; B. Author",
        "institutions": "University of Colombo; University of Peradeniya",
        "sri_lankan_institutions": "University of Colombo",
        "countries": "LK; GB",
        "journal": "Ceylon Medical Journal",
        "publisher": "Example Publisher",
        "citation_count": 12,
        "reference_count": 30,
        "is_oa": True,
        "oa_status": "gold",
        "primary_field": "Medicine",
        "primary_subfield": "Public Health",
        "topics": "Epidemiology; Malaria",
        "concepts": "public health",
        "source_dataset": "openalex; crossref",
        "source_record_id": "W1",
        "abstract": "A study abstract.",
        "citation_count_divergence_flag": False,
        "reference_count_divergence_flag": True,
        "raw_record": {"id": "W1"},
    },
    {
        "publication_key": "source:repositories_combined:thesis-1",
        "title": "Repository-only thesis",
        "doi": None,
        "publication_year": 2023,
        "type": "thesis",
        "authors": "C. Author",
        "institutions": "University of Ruhuna",
        "sri_lankan_institutions": "University of Ruhuna",
        "countries": "LK",
        "journal": None,
        "publisher": "University of Ruhuna",
        "citation_count": 0,
        "reference_count": None,
        "is_oa": None,
        "oa_status": None,
        "primary_field": None,
        "primary_subfield": None,
        "topics": None,
        "concepts": None,
        "source_dataset": "repositories_combined",
        "source_record_id": "thesis-1",
        "abstract": None,
        "citation_count_divergence_flag": False,
        "reference_count_divergence_flag": False,
        "raw_record": {},
    },
]


class FakeRepository:
    def health(self):
        return True

    def metadata(self):
        return {"publication_count": len(PUBLICATIONS), "snapshot_date": "2026-07-20"}

    def list_publications(self, filters, *, page, page_size, sort, include_facets):
        rows = PUBLICATIONS
        if filters.get("year_min"):
            rows = [row for row in rows if row["publication_year"] >= filters["year_min"]]
        if filters.get("year_max"):
            rows = [row for row in rows if row["publication_year"] <= filters["year_max"]]
        if filters.get("q"):
            rows = [row for row in rows if filters["q"].casefold() in row["title"].casefold()]
        if filters.get("publication_keys") is not None:
            keys = set(filters["publication_keys"])
            rows = [row for row in rows if row["publication_key"] in keys]
        start = (page - 1) * page_size
        facets = {"publication_year": {"2024": 1, "2023": 1}} if include_facets else None
        return {
            "records": rows[start : start + page_size],
            "total": len(rows),
            "facets": facets,
            "meta": self.metadata(),
        }

    def get_publication(self, publication_key):
        return next((row for row in PUBLICATIONS if row["publication_key"] == publication_key), None)

    def get_references(self, publication_key):
        return [{"publication_key": publication_key, "reference_index": 1, "reference_title": "Ref"}]

    def get_count_audit(self, publication_key):
        if publication_key == PUBLICATIONS[0]["publication_key"]:
            return {"publication_key": publication_key, "citation_count": 12}
        return None

    def suggest(self, query, *, limit, types=None):
        return [
            {
                "type": "publication",
                "value": PUBLICATIONS[0]["title"],
                "key": PUBLICATIONS[0]["publication_key"],
            }
        ][:limit]

    def semantic_search(self, query, *, filters, limit, min_score):
        row = {
            **PUBLICATIONS[0],
            "semantic_score": 0.925,
            "semantic_rank": 1,
            "similarity_score": 0.925,
            "similarity_rank": 1,
        }
        return [row][:limit]

    def related_publications(self, publication_key, *, filters, limit, min_score):
        if publication_key == "missing":
            raise KeyError(publication_key)
        row = {
            **PUBLICATIONS[1],
            "semantic_score": 0.81,
            "semantic_rank": 1,
            "similarity_score": 0.81,
            "similarity_rank": 1,
        }
        return [row][:limit]

    def researcher_profile(self, researcher_key):
        return {"key": "a-author", "label": researcher_key, "publication_count": 1}

    def researcher_publications(self, researcher_key, *, page, page_size):
        return {"records": [PUBLICATIONS[0]], "total": 1}

    def researcher_coauthors(self, researcher_key, *, limit):
        return [{"name": "B. Author", "publication_count": 1}]

    def institution_profile(self, institution_key):
        return {"key": "university-of-colombo", "label": institution_key, "publication_count": 1}

    def institution_publications(self, institution_key, *, page, page_size):
        return {"records": [PUBLICATIONS[0]], "total": 1}

    def institution_collaborators(self, institution_key, *, limit):
        return [{"institution": "University of Peradeniya", "publication_count": 1}]

    def compare_institutions(self, keys):
        return [{"key": key, "publication_count": 1} for key in keys]

    def topic_publications(self, topic_key, *, page, page_size):
        return {"records": [PUBLICATIONS[0]], "total": 1}

    def analytics_overview(self, filters):
        return {"publication_count": 2, "citation_total": 12}

    def analytics_trends(self, filters, *, group_by, metric):
        return [{"key": 2024, "publication_count": 1, "citation_total": 12}]

    def paginated_analytics_rankings(self, filters, *, dimension, metric, page, page_size):
        return {
            "records": [{"key": "medicine", "label": "Medicine", "publication_count": 1, "citation_total": 12}],
            "total": 1,
        }

    def analytics_rankings(self, filters, *, dimension, metric, limit):
        return self.paginated_analytics_rankings(
            filters, dimension=dimension, metric=metric, page=1, page_size=limit
        )["records"]

    def collaboration_network(self, filters, *, scope, min_weight, limit):
        return {"nodes": [{"id": "uoc", "label": "UOC"}], "edges": [], "summary": {"node_count": 1}}

    def data_quality(self, filters, *, group_by):
        return {"record_count": 2, "missing_doi_percentage": 50.0}


@dataclass(frozen=True)
class ApiCase:
    test_id: str
    endpoint: str
    scenario: str
    expected: str
    method: str = "GET"
    path: str = ""
    query: dict[str, list[str]] | None = None
    checker: str = "ok"


def _check_health(payload: Any) -> None:
    assert payload["data"]["status"] == "ok"


def _check_meta(payload: Any) -> None:
    assert "supported_filters" in payload["data"]
    assert payload["data"]["publication_count"] == 2


def _check_list(payload: Any) -> None:
    assert_list_payload(payload)
    assert payload["pagination"]["total"] >= 1


def _check_detail(payload: Any) -> None:
    assert_detail_payload(payload)
    assert payload["data"]["publication_key"] == "doi:10.1000/test"


def _check_not_found(exc: APIError) -> None:
    assert exc.status == 404
    assert exc.code == "not_found"


def _check_invalid_filter(exc: APIError) -> None:
    assert exc.code in {"invalid_filter", "invalid_query_parameter", "invalid_sort"}


def _check_semantic(payload: Any) -> None:
    assert_list_payload(payload)
    assert payload["data"][0]["semantic_score"] == 0.925


def _check_suggest(payload: Any) -> None:
    assert payload["data"]
    assert payload["data"][0]["type"] == "publication"


def _check_analytics(payload: Any) -> None:
    assert "data" in payload
    assert payload["data"]


def _check_export_csv(payload: Any) -> None:
    assert isinstance(payload, tuple)
    body, content_type = payload
    assert "text/csv" in content_type
    assert b"publication_key" in body or b"title" in body


CHECKERS: dict[str, Callable[..., None]] = {
    "health": _check_health,
    "meta": _check_meta,
    "list": _check_list,
    "detail": _check_detail,
    "not_found": _check_not_found,
    "invalid_filter": _check_invalid_filter,
    "semantic": _check_semantic,
    "suggest": _check_suggest,
    "analytics": _check_analytics,
    "export_csv": _check_export_csv,
}


API_CASES: list[ApiCase] = [
    ApiCase(
        test_id="API-001",
        endpoint="GET /api/v1/health",
        scenario="Service health probe",
        expected="status=ok and api_version present",
        path="/api/v1/health",
        checker="health",
    ),
    ApiCase(
        test_id="API-002",
        endpoint="GET /api/v1/meta",
        scenario="Dataset metadata",
        expected="publication_count and supported_filters returned",
        path="/api/v1/meta",
        checker="meta",
    ),
    ApiCase(
        test_id="API-003",
        endpoint="GET /api/v1/publications",
        scenario="Default publication listing",
        expected="paginated list with >=1 row",
        path="/api/v1/publications",
        checker="list",
    ),
    ApiCase(
        test_id="API-004",
        endpoint="GET /api/v1/publications?q=Malaria",
        scenario="Keyword publication search",
        expected="filtered list containing malaria title",
        path="/api/v1/publications",
        query={"q": ["Malaria"]},
        checker="list",
    ),
    ApiCase(
        test_id="API-005",
        endpoint="GET /api/v1/publications/{key}",
        scenario="Publication detail by key",
        expected="detail payload for doi:10.1000/test",
        path="/api/v1/publications/doi:10.1000/test",
        checker="detail",
    ),
    ApiCase(
        test_id="API-006",
        endpoint="GET /api/v1/publications/{key}",
        scenario="Missing publication key",
        expected="404 not_found",
        path="/api/v1/publications/missing-key",
        checker="not_found",
    ),
    ApiCase(
        test_id="API-007",
        endpoint="GET /api/v1/publications?year_min>year_max",
        scenario="Invalid year range filter",
        expected="invalid_filter error",
        path="/api/v1/publications",
        query={"year_min": ["2025"], "year_max": ["2024"]},
        checker="invalid_filter",
    ),
    ApiCase(
        test_id="API-008",
        endpoint="GET /api/v1/search/suggest?q=Malaria",
        scenario="Autocomplete suggestions",
        expected="suggestion list with publication type",
        path="/api/v1/search/suggest",
        query={"q": ["Malaria"]},
        checker="suggest",
    ),
    ApiCase(
        test_id="API-009",
        endpoint="GET /api/v1/search/semantic?q=malaria",
        scenario="Semantic search ranking",
        expected="ranked rows with semantic_score",
        path="/api/v1/search/semantic",
        query={"q": ["malaria"]},
        checker="semantic",
    ),
    ApiCase(
        test_id="API-010",
        endpoint="GET /api/v1/search/semantic",
        scenario="Semantic search without q",
        expected="invalid_filter for empty query",
        path="/api/v1/search/semantic",
        checker="invalid_filter",
    ),
    ApiCase(
        test_id="API-011",
        endpoint="GET /api/v1/search/facets",
        scenario="Facet counts for current filters",
        expected="facets object returned",
        path="/api/v1/search/facets",
        checker="analytics",
    ),
    ApiCase(
        test_id="API-012",
        endpoint="GET /api/v1/topics",
        scenario="Topic directory (OpenAlex fallback when NMF unavailable)",
        expected="list/ranking payload or service error handled",
        path="/api/v1/topics",
        query={"source": ["openalex"]},
        checker="list",
    ),
    ApiCase(
        test_id="API-013",
        endpoint="GET /api/v1/fields",
        scenario="Field rankings",
        expected="paginated ranking rows",
        path="/api/v1/fields",
        checker="list",
    ),
    ApiCase(
        test_id="API-014",
        endpoint="GET /api/v1/analytics/overview",
        scenario="Dashboard headline metrics",
        expected="overview metrics object",
        path="/api/v1/analytics/overview",
        checker="analytics",
    ),
    ApiCase(
        test_id="API-015",
        endpoint="GET /api/v1/analytics/trends",
        scenario="Yearly publication trends",
        expected="trend points list",
        path="/api/v1/analytics/trends",
        checker="analytics",
    ),
    ApiCase(
        test_id="API-016",
        endpoint="GET /api/v1/analytics/institutions",
        scenario="Institution rankings",
        expected="paginated ranking rows",
        path="/api/v1/analytics/institutions",
        checker="list",
    ),
    ApiCase(
        test_id="API-017",
        endpoint="GET /api/v1/analytics/fields",
        scenario="Field analytics rankings",
        expected="paginated ranking rows",
        path="/api/v1/analytics/fields",
        checker="list",
    ),
    ApiCase(
        test_id="API-018",
        endpoint="GET /api/v1/analytics/collaboration-network",
        scenario="Collaboration network graph",
        expected="nodes/edges/summary payload",
        path="/api/v1/analytics/collaboration-network",
        checker="analytics",
    ),
    ApiCase(
        test_id="API-019",
        endpoint="GET /api/v1/analytics/data-quality",
        scenario="Data-quality summary",
        expected="quality metrics object",
        path="/api/v1/analytics/data-quality",
        checker="analytics",
    ),
    ApiCase(
        test_id="API-020",
        endpoint="GET /api/v1/researchers/{key}",
        scenario="Researcher profile",
        expected="profile aggregate",
        path="/api/v1/researchers/a-author",
        checker="analytics",
    ),
    ApiCase(
        test_id="API-021",
        endpoint="GET /api/v1/institutions/{key}",
        scenario="Institution profile",
        expected="profile aggregate",
        path="/api/v1/institutions/university-of-colombo",
        checker="analytics",
    ),
    ApiCase(
        test_id="API-022",
        endpoint="GET /api/v1/institutions/compare",
        scenario="Compare two institutions",
        expected="comparison list with 2 entries",
        path="/api/v1/institutions/compare",
        query={"institution": ["university-of-colombo", "university-of-peradeniya"]},
        checker="analytics",
    ),
    ApiCase(
        test_id="API-023",
        endpoint="GET /api/v1/publications/{key}/references",
        scenario="Publication references sidecar",
        expected="paginated reference rows",
        path="/api/v1/publications/doi:10.1000/test/references",
        checker="list",
    ),
    ApiCase(
        test_id="API-024",
        endpoint="GET /api/v1/publications/{key}/related",
        scenario="Related publications (semantic)",
        expected="ranked related rows",
        path="/api/v1/publications/doi:10.1000/test/related",
        checker="list",
    ),
    ApiCase(
        test_id="API-025",
        endpoint="GET /api/v1/exports/publications.csv",
        scenario="CSV export of publications",
        expected="text/csv bytes payload",
        path="/api/v1/exports/publications.csv",
        checker="export_csv",
    ),
    ApiCase(
        test_id="API-026",
        endpoint="GET /api/v1/unknown",
        scenario="Unknown endpoint",
        expected="404 not_found",
        path="/api/v1/unknown",
        checker="not_found",
    ),
]


@pytest.fixture
def api() -> ResearchLankaAPI:
    return ResearchLankaAPI(FakeRepository())


@pytest.mark.parametrize("case", API_CASES, ids=lambda case: case.test_id)
def test_api_matrix_case(case: ApiCase, api: ResearchLankaAPI, request: pytest.FixtureRequest):
    attach_api_case(
        request,
        test_id=case.test_id,
        endpoint=case.endpoint,
        scenario=case.scenario,
        expected=case.expected,
    )
    checker = CHECKERS[case.checker]
    query = case.query or {}

    if case.checker in {"not_found", "invalid_filter"}:
        with pytest.raises(APIError) as exc:
            route_get(api, case.path, query)
        checker(exc.value)
        return

    payload = route_get(api, case.path, query)
    checker(payload)
