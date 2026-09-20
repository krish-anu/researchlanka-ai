"""Phase 3 — performance budgets for hot read endpoints."""

from __future__ import annotations

import time

import pytest

from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from tests.phase3.helpers import make_api


pytestmark = [pytest.mark.phase3, pytest.mark.performance]


# Offline fake-repo budgets (seconds). Live DB budgets belong in nightly runs.
BUDGETS = {
    "health": 0.05,
    "list": 0.15,
    "suggest": 0.15,
    "overview": 0.20,
    "network": 0.25,
    "semantic": 0.25,
}


@pytest.fixture
def api() -> ResearchLankaAPI:
    service = make_api()
    # Warm real CSV-backed indexes once so budgets measure hot-path latency, not cold load.
    route_get(service, "/api/v1/health", {})
    route_get(service, "/api/v1/publications", {"page": ["1"], "page_size": ["5"]})
    return service


def _timed(callable_):
    start = time.perf_counter()
    result = callable_()
    return result, time.perf_counter() - start


def test_health_latency_budget(api: ResearchLankaAPI):
    _, elapsed = _timed(lambda: route_get(api, "/api/v1/health", {}))
    assert elapsed < BUDGETS["health"], f"health took {elapsed:.3f}s"


def test_publication_list_latency_budget(api: ResearchLankaAPI):
    _, elapsed = _timed(lambda: route_get(api, "/api/v1/publications", {"q": ["Malaria"]}))
    assert elapsed < BUDGETS["list"], f"list took {elapsed:.3f}s"


def test_suggest_latency_budget(api: ResearchLankaAPI):
    _, elapsed = _timed(lambda: route_get(api, "/api/v1/search/suggest", {"q": ["Mal"]}))
    assert elapsed < BUDGETS["suggest"], f"suggest took {elapsed:.3f}s"


def test_analytics_overview_latency_budget(api: ResearchLankaAPI):
    _, elapsed = _timed(lambda: route_get(api, "/api/v1/analytics/overview", {}))
    assert elapsed < BUDGETS["overview"], f"overview took {elapsed:.3f}s"


def test_collaboration_network_latency_budget(api: ResearchLankaAPI):
    _, elapsed = _timed(
        lambda: route_get(api, "/api/v1/analytics/collaboration-network", {})
    )
    assert elapsed < BUDGETS["network"], f"network took {elapsed:.3f}s"


def test_semantic_search_latency_budget(api: ResearchLankaAPI):
    _, elapsed = _timed(
        lambda: route_get(api, "/api/v1/search/semantic", {"q": ["malaria research"]})
    )
    assert elapsed < BUDGETS["semantic"], f"semantic took {elapsed:.3f}s"
