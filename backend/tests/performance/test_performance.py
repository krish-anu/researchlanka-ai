"""Performance and scalability tests.

Run (from backend/):

    pytest tests/performance -v
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from src.api.routes import route_get
from src.api.service import ResearchLankaAPI

# Soft budgets for the in-process real-dataset harness (warm path).
_HEALTH_BUDGET_S = 1.0
_LIST_BUDGET_S = 3.0
_SEARCH_BUDGET_S = 3.0
_ANALYTICS_BUDGET_S = 3.0
_DB_QUERY_BUDGET_S = 5.0


def _warm(api: ResearchLankaAPI) -> None:
    route_get(api, "/api/v1/health", {})
    route_get(api, "/api/v1/publications", {"page": ["1"], "page_size": ["5"]})


def test_api_health_endpoint_responds_within_acceptable_time(api: ResearchLankaAPI):
    """Basic backend responsiveness."""
    _warm(api)
    start = time.perf_counter()
    payload = route_get(api, "/api/v1/health", {})
    elapsed = time.perf_counter() - start
    assert payload["data"]["status"] == "ok"
    assert elapsed < _HEALTH_BUDGET_S


def test_publication_listing_endpoint_handles_repeated_requests(
    api: ResearchLankaAPI,
):
    """Stability under repeated reads."""
    _warm(api)
    elapsed = []
    for _ in range(8):
        start = time.perf_counter()
        listing = route_get(
            api, "/api/v1/publications", {"page": ["1"], "page_size": ["10"]}
        )
        elapsed.append(time.perf_counter() - start)
        assert listing["data"]
    assert max(elapsed) < _LIST_BUDGET_S
    assert sum(elapsed) / len(elapsed) < _LIST_BUDGET_S


def test_publication_search_handles_repeated_concurrent_requests(
    api: ResearchLankaAPI,
):
    """Search performance under load."""
    _warm(api)

    def once(_):
        start = time.perf_counter()
        result = route_get(
            api,
            "/api/v1/publications",
            {"q": ["research"], "page_size": ["10"]},
        )
        return result, time.perf_counter() - start

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(once, range(12)))

    assert len(outcomes) == 12
    assert all("data" in result for result, _ in outcomes)
    assert max(duration for _, duration in outcomes) < _SEARCH_BUDGET_S


def test_analytics_endpoint_handles_repeated_requests(api: ResearchLankaAPI):
    """Performance of heavier analytical queries."""
    _warm(api)
    elapsed = []
    for _ in range(5):
        start = time.perf_counter()
        overview = route_get(api, "/api/v1/analytics/overview", {})
        elapsed.append(time.perf_counter() - start)
        assert overview["data"]["publication_count"] >= 1
    assert max(elapsed) < _ANALYTICS_BUDGET_S


def test_database_publication_queries_remain_responsive_with_realistic_data_volume(
    api: ResearchLankaAPI,
):
    """Database scalability / read performance on realistic corpus volume."""
    _warm(api)
    start = time.perf_counter()
    page1 = route_get(
        api, "/api/v1/publications", {"page": ["1"], "page_size": ["50"]}
    )
    page2 = route_get(
        api, "/api/v1/publications", {"page": ["2"], "page_size": ["50"]}
    )
    meta = route_get(api, "/api/v1/meta", {})
    elapsed = time.perf_counter() - start

    assert page1["data"]
    assert len(page1["data"]) <= 50
    assert "data" in page2
    assert meta["data"]["publication_count"] >= 1
    assert elapsed < _DB_QUERY_BUDGET_S
