"""Phase 3 — concurrent load smoke (service layer)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from tests.phase3.helpers import make_api


pytestmark = [pytest.mark.phase3, pytest.mark.load]


@pytest.fixture
def api() -> ResearchLankaAPI:
    return make_api()


def test_concurrent_health_checks(api: ResearchLankaAPI):
    def one(_):
        payload = route_get(api, "/api/v1/health", {})
        assert payload["data"]["status"] == "ok"
        return True

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(one, i) for i in range(64)]
        results = [future.result() for future in as_completed(futures)]
    assert len(results) == 64
    assert all(results)


def test_concurrent_mixed_read_workload(api: ResearchLankaAPI):
    paths = [
        ("/api/v1/publications", {"q": ["Malaria"]}),
        ("/api/v1/search/suggest", {"q": ["Mal"]}),
        ("/api/v1/analytics/overview", {}),
        ("/api/v1/analytics/trends", {}),
        ("/api/v1/search/facets", {}),
    ]

    def one(index: int):
        path, query = paths[index % len(paths)]
        payload = route_get(api, path, query)
        assert payload is not None
        return path

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(one, i) for i in range(48)]
        completed = [future.result() for future in as_completed(futures)]
    assert len(completed) == 48


def test_concurrent_export_reads_do_not_raise(api: ResearchLankaAPI):
    def one(_):
        payload = route_get(api, "/api/v1/exports/publications.csv", {})
        assert isinstance(payload, tuple)
        return len(payload[0])

    with ThreadPoolExecutor(max_workers=8) as pool:
        sizes = [future.result() for future in as_completed([pool.submit(one, i) for i in range(16)])]
    assert all(size > 0 for size in sizes)
