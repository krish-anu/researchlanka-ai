"""Phase 3 — integration smoke flow (service layer)."""

from __future__ import annotations

import pytest

from src.api.core.errors import APIError
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from tests.phase3.helpers import assert_no_secret_leak, make_api


pytestmark = [pytest.mark.phase3, pytest.mark.integration]


@pytest.fixture
def api() -> ResearchLankaAPI:
    return make_api()


def test_health_meta_list_detail_flow(api: ResearchLankaAPI):
    health = route_get(api, "/api/v1/health", {})
    assert health["data"]["status"] == "ok"

    meta = route_get(api, "/api/v1/meta", {})
    assert meta["data"]["publication_count"] >= 1

    listing = route_get(api, "/api/v1/publications", {"q": ["Malaria"]})
    assert listing["data"]
    key = listing["data"][0]["publication_key"]

    detail = route_get(api, f"/api/v1/publications/{key}", {})
    assert detail["data"]["publication_key"] == key
    assert_no_secret_leak(detail)


def test_search_suggest_facets_and_analytics_chain(api: ResearchLankaAPI):
    suggest = route_get(api, "/api/v1/search/suggest", {"q": ["Malaria"]})
    assert suggest["data"]

    facets = route_get(api, "/api/v1/search/facets", {})
    assert "facets" in facets or "data" in facets

    overview = route_get(api, "/api/v1/analytics/overview", {})
    assert overview["data"]

    trends = route_get(api, "/api/v1/analytics/trends", {})
    assert isinstance(trends["data"], list)


def test_researcher_and_institution_profiles(api: ResearchLankaAPI):
    researcher = route_get(api, "/api/v1/researchers/a-author", {})
    assert researcher["data"]["key"] == "a-author"

    institution = route_get(api, "/api/v1/institutions/university-of-colombo", {})
    assert institution["data"]["key"] == "university-of-colombo"

    compare = route_get(
        api,
        "/api/v1/institutions/compare",
        {"institution": ["university-of-colombo", "university-of-ruhuna"]},
    )
    assert len(compare["data"]) == 2


def test_export_csv_integration(api: ResearchLankaAPI):
    payload = route_get(api, "/api/v1/exports/publications.csv", {})
    assert isinstance(payload, tuple)
    body, content_type = payload
    assert "csv" in content_type
    assert b"publication_key" in body


def test_missing_resources_are_404(api: ResearchLankaAPI):
    with pytest.raises(APIError) as exc:
        route_get(api, "/api/v1/publications/missing", {})
    assert exc.value.status == 404
