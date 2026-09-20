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
from tests.support.real_dataset import RealPublicationRepository, load_real_publications


pytestmark = [pytest.mark.phase2, pytest.mark.api, pytest.mark.api_matrix]

PUBLICATIONS = list(load_real_publications(limit=16))
SAMPLE_KEY = PUBLICATIONS[0]["publication_key"]
SAMPLE_TITLE_TOKEN = next(
    (
        token
        for token in str(PUBLICATIONS[0].get("title") or "research").replace(",", " ").split()
        if len(token) >= 5 and token.isalpha()
    ),
    "research",
)


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
    assert int(payload["data"]["publication_count"]) >= 1


def _check_list(payload: Any) -> None:
    assert_list_payload(payload)
    assert payload["pagination"]["total"] >= 1


def _check_detail(payload: Any) -> None:
    assert_detail_payload(payload)
    assert payload["data"]["publication_key"] == SAMPLE_KEY
    assert payload["data"].get("title")


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
        endpoint=f"GET /api/v1/publications?q={SAMPLE_TITLE_TOKEN}",
        scenario="Keyword publication search against real titles",
        expected="filtered list containing a real corpus title token",
        path="/api/v1/publications",
        query={"q": [SAMPLE_TITLE_TOKEN]},
        checker="list",
    ),
    ApiCase(
        test_id="API-005",
        endpoint="GET /api/v1/publications/{key}",
        scenario="Publication detail by real publication_key",
        expected=f"detail payload for {SAMPLE_KEY}",
        path=f"/api/v1/publications/{SAMPLE_KEY}",
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
        endpoint=f"GET /api/v1/search/suggest?q={SAMPLE_TITLE_TOKEN}",
        scenario="Autocomplete suggestions from real titles",
        expected="suggestion list with publication type",
        path="/api/v1/search/suggest",
        query={"q": [SAMPLE_TITLE_TOKEN]},
        checker="suggest",
    ),
    ApiCase(
        test_id="API-009",
        endpoint=f"GET /api/v1/search/semantic?q={SAMPLE_TITLE_TOKEN}",
        scenario="Semantic search ranking",
        expected="ranked rows with semantic_score",
        path="/api/v1/search/semantic",
        query={"q": [SAMPLE_TITLE_TOKEN]},
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
        path=f"/api/v1/publications/{SAMPLE_KEY}/references",
        checker="list",
    ),
    ApiCase(
        test_id="API-024",
        endpoint="GET /api/v1/publications/{key}/related",
        scenario="Related publications (semantic)",
        expected="ranked related rows",
        path=f"/api/v1/publications/{SAMPLE_KEY}/related",
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
    return ResearchLankaAPI(RealPublicationRepository(PUBLICATIONS))


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
