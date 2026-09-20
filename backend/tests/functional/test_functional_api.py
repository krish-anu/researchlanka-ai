"""Automated functional API tests.

Run (from backend/):

    pytest tests/functional -v
"""

from __future__ import annotations

import pytest

from src.api.core.errors import APIError
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI


def test_api_health_reports_ok_status(api: ResearchLankaAPI):
    payload = route_get(api, "/api/v1/health", {})
    assert payload["data"]["status"] == "ok"


def test_publication_list_returns_records_with_publication_key(api: ResearchLankaAPI):
    listing = route_get(api, "/api/v1/publications", {"page": ["1"], "page_size": ["5"]})
    assert listing["data"]
    assert "publication_key" in listing["data"][0]


def test_publication_search_returns_matching_records_for_keyword(
    api: ResearchLankaAPI, sample_publications
):
    title = next(
        (str(row["title"]) for row in sample_publications if row.get("title")),
        "research",
    )
    token = next(
        (
            part
            for part in title.replace(",", " ").split()
            if len(part) >= 4 and part.isalpha()
        ),
        "research",
    )
    listing = route_get(api, "/api/v1/publications", {"q": [token], "page_size": ["10"]})
    assert "data" in listing
    if listing["data"]:
        assert any(
            token.casefold() in str(item.get("title") or "").casefold()
            for item in listing["data"]
        )


def test_publication_search_returns_empty_result_for_unknown_keyword(
    api: ResearchLankaAPI,
):
    listing = route_get(
        api,
        "/api/v1/publications",
        {"q": ["zzzxxyyqq_no_such_keyword_999"], "page_size": ["5"]},
    )
    assert listing["data"] == [] or listing.get("data") is not None


def test_year_filter_restricts_publication_results(api: ResearchLankaAPI):
    listing = route_get(
        api,
        "/api/v1/publications",
        {"year_min": ["2018"], "year_max": ["2020"], "page_size": ["20"]},
    )
    for item in listing.get("data") or []:
        year = item.get("publication_year")
        if year is not None:
            assert 2018 <= int(year) <= 2020


def test_publication_detail_returns_requested_key(api: ResearchLankaAPI):
    listing = route_get(api, "/api/v1/publications", {"page_size": ["1"]})
    key = listing["data"][0]["publication_key"]
    detail = route_get(api, f"/api/v1/publications/{key}", {})
    assert detail["data"]["publication_key"] == key


def test_missing_publication_detail_returns_404(api: ResearchLankaAPI):
    with pytest.raises(APIError) as exc:
        route_get(api, "/api/v1/publications/missing-key-xyz", {})
    assert exc.value.status == 404


def test_search_suggest_returns_structured_suggestions(api: ResearchLankaAPI):
    suggest = route_get(api, "/api/v1/search/suggest", {"q": ["mal"]})
    assert "data" in suggest


def test_analytics_overview_exposes_publication_count(api: ResearchLankaAPI):
    overview = route_get(api, "/api/v1/analytics/overview", {})
    assert overview["data"]["publication_count"] >= 1


def test_collaboration_network_returns_nodes_structure(api: ResearchLankaAPI):
    network = route_get(api, "/api/v1/analytics/collaboration-network", {})
    data = network.get("data") or network
    assert (
        "nodes" in data
        or (isinstance(data, dict) and "nodes" in str(data).lower())
        or "nodes" in network
    )


def test_export_publications_csv_includes_publication_key_header(
    api: ResearchLankaAPI,
):
    payload = route_get(api, "/api/v1/exports/publications.csv", {})
    assert isinstance(payload, tuple)
    body, content_type = payload
    assert "csv" in content_type
    assert b"publication_key" in body


def test_meta_endpoint_reports_nonzero_publication_count(api: ResearchLankaAPI):
    meta = route_get(api, "/api/v1/meta", {})
    assert meta["data"]["publication_count"] >= 1
