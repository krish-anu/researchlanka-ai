"""Locust load profile for the ResearchLanka read-only API.

Run (API must already be serving on --host):

    # Restart API after code changes so the DB pool is active:
    #   python scripts/api/serve_api.py --host 127.0.0.1 --port 8080
    #
    # Start gently — this stdlib threaded server + Postgres is not a CDN:
    locust -f backend/tests/performance/locustfile.py \\
        --host http://127.0.0.1:8080 \\
        --users 10 --spawn-rate 2 --run-time 2m

Avoid jumping straight to hundreds of users; that previously exhausted Postgres
connections and produced false 500s from client disconnects.
"""

from __future__ import annotations

from locust import HttpUser, between, task


class ResearchLankaUser(HttpUser):
    # Pause between tasks so concurrent DB use stays within the API pool.
    wait_time = between(1, 3)
    # Give heavy facet/list queries time before Locust abandons the socket
    # (abandoned sockets caused BrokenPipe → spurious 500s on the server).
    network_timeout = 60.0
    connection_timeout = 10.0

    def _get(self, path: str, *, name: str) -> None:
        with self.client.get(path, name=name, catch_response=True) as response:
            if response.status_code == 0:
                response.failure("connection failed / reset")
            elif response.status_code >= 500:
                response.failure(f"server {response.status_code}: {response.text[:200]}")
            elif response.status_code >= 400:
                response.failure(f"client {response.status_code}")
            else:
                response.success()

    @task(4)
    def publications(self) -> None:
        self._get(
            "/api/v1/publications?page=1&page_size=10",
            name="/api/v1/publications",
        )

    @task(1)
    def search_facets(self) -> None:
        # Facets are heavier; keep weight low under load.
        self._get("/api/v1/search/facets", name="/api/v1/search/facets")

    @task(2)
    def researchers(self) -> None:
        self._get(
            "/api/v1/researchers?page=1&page_size=10",
            name="/api/v1/researchers",
        )

    @task(1)
    def meta(self) -> None:
        self._get("/api/v1/meta", name="/api/v1/meta")

    @task(1)
    def health(self) -> None:
        self._get("/api/v1/health", name="/api/v1/health")
