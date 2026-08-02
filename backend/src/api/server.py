"""HTTP server for the read-only ResearchLanka API."""

from __future__ import annotations

import argparse
import json
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from src.api.repository import PostgresPublicationRepository
from src.api.service import APIError, ResearchLankaAPI, normalize_value


API_PREFIX = "/api/v1"


class APIRequestHandler(BaseHTTPRequestHandler):
    """Route read-only API requests."""

    service: ResearchLankaAPI

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"
        try:
            payload = self.route_get(path, query)
            if isinstance(payload, tuple):
                body, content_type = payload
                bytes_response(self, body, content_type=content_type)
                return
            json_response(self, payload)
        except APIError as exc:
            json_response(
                self,
                {"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
                status=HTTPStatus(exc.status),
            )
        except Exception as exc:  # pragma: no cover - network-facing guard
            json_response(
                self,
                {
                    "error": {
                        "code": "internal_error",
                        "message": str(exc),
                        "details": {},
                    }
                },
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        add_cors_headers(self)
        self.end_headers()

    def route_get(self, path: str, query: dict[str, list[str]]) -> dict[str, Any] | tuple[bytes, str]:
        if path in {"/health", f"{API_PREFIX}/health"}:
            return self.service.health()
        if path == f"{API_PREFIX}/meta":
            return self.service.metadata()
        if path == f"{API_PREFIX}/schema/publications":
            return self.service.schema()
        if path == f"{API_PREFIX}/limitations":
            return self.service.limitations()
        if path == f"{API_PREFIX}/publications":
            return self.service.list_publications(query)
        if path == f"{API_PREFIX}/search/suggest":
            return self.service.suggestions(query)
        if path == f"{API_PREFIX}/search/facets":
            return self.service.facets(query)
        if path == f"{API_PREFIX}/researchers":
            return self.service.researchers(query)
        if path == f"{API_PREFIX}/institutions":
            return self.service.institutions(query)
        if path == f"{API_PREFIX}/institutions/compare":
            return self.service.compare_institutions(query)
        if path == f"{API_PREFIX}/topics":
            return self.service.topics(query)
        if path == f"{API_PREFIX}/fields":
            return self.service.fields(query)
        if path == f"{API_PREFIX}/analytics/overview":
            return self.service.analytics_overview(query)
        if path == f"{API_PREFIX}/analytics/trends":
            return self.service.analytics_trends(query)
        if path == f"{API_PREFIX}/analytics/institutions":
            return self.service.analytics_rankings(query, dimension="institutions")
        if path == f"{API_PREFIX}/analytics/fields":
            return self.service.analytics_rankings(query, dimension="primary_field")
        if path == f"{API_PREFIX}/analytics/collaboration-network":
            return self.service.collaboration_network(query)
        if path == f"{API_PREFIX}/analytics/data-quality":
            return self.service.data_quality(query)
        if path == f"{API_PREFIX}/exports/publications.csv":
            return self.service.export_publications(query, file_format="csv")
        if path == f"{API_PREFIX}/exports/publications.jsonl":
            return self.service.export_publications(query, file_format="jsonl")
        match = re.fullmatch(rf"{API_PREFIX}/exports/analytics/([a-z-]+)\.csv", path)
        if match:
            return self.service.export_analytics(query, name=match.group(1))

        match = re.fullmatch(rf"{API_PREFIX}/publications/(.+)/(references|count-audit)", path)
        if match:
            publication_key = unquote(match.group(1))
            child = match.group(2)
            if child == "references":
                return self.service.publication_references(publication_key, query)
            return self.service.publication_count_audit(publication_key)

        match = re.fullmatch(rf"{API_PREFIX}/publications/(.+)/raw", path)
        if match:
            return self.service.publication_raw(unquote(match.group(1)))

        match = re.fullmatch(rf"{API_PREFIX}/publications/(.+)", path)
        if match:
            return self.service.publication_detail(unquote(match.group(1)))

        match = re.fullmatch(rf"{API_PREFIX}/researchers/(.+)/(publications|coauthors)", path)
        if match:
            researcher_key = unquote(match.group(1))
            child = match.group(2)
            if child == "publications":
                return self.service.researcher_publications(researcher_key, query)
            return self.service.researcher_coauthors(researcher_key, query)

        match = re.fullmatch(rf"{API_PREFIX}/researchers/(.+)", path)
        if match:
            return self.service.researcher_profile(unquote(match.group(1)))

        match = re.fullmatch(rf"{API_PREFIX}/institutions/(.+)/(publications|collaborators)", path)
        if match:
            institution_key = unquote(match.group(1))
            child = match.group(2)
            if child == "publications":
                return self.service.institution_publications(institution_key, query)
            return self.service.institution_collaborators(institution_key, query)

        match = re.fullmatch(rf"{API_PREFIX}/institutions/(.+)", path)
        if match:
            return self.service.institution_profile(unquote(match.group(1)))

        match = re.fullmatch(rf"{API_PREFIX}/topics/(.+)/publications", path)
        if match:
            return self.service.topic_publications(unquote(match.group(1)), query)

        raise APIError("not_found", "Endpoint not found.", status=404)


def json_response(
    handler: BaseHTTPRequestHandler,
    payload: dict[str, Any],
    *,
    status: HTTPStatus = HTTPStatus.OK,
) -> None:
    data = json.dumps(normalize_value(payload), ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    add_cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(data)


def bytes_response(
    handler: BaseHTTPRequestHandler,
    data: bytes,
    *,
    content_type: str,
    status: HTTPStatus = HTTPStatus.OK,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    add_cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(data)


def add_cors_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


def build_handler(service: ResearchLankaAPI) -> type[APIRequestHandler]:
    class ConfiguredAPIRequestHandler(APIRequestHandler):
        pass

    ConfiguredAPIRequestHandler.service = service
    return ConfiguredAPIRequestHandler


def serve(*, host: str, port: int, service: ResearchLankaAPI | None = None) -> ThreadingHTTPServer:
    service = service or ResearchLankaAPI(PostgresPublicationRepository())
    server = ThreadingHTTPServer((host, port), build_handler(service))
    print(f"ResearchLanka API listening on http://{host}:{port}{API_PREFIX}")
    return server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the read-only ResearchLanka API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    server = serve(host=args.host, port=args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping ResearchLanka API.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
