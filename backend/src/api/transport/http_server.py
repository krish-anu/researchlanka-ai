"""HTTP server for the read-only ResearchLanka API."""

from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.api.core.constants import API_PREFIX
from src.api.core.errors import APIError
from src.api.repositories.postgres import PostgresPublicationRepository
from src.api.routing.routes import route_get, route_post
from src.api.core.serializers import normalize_value
from src.api.services.publications import ResearchLankaAPI


# Client went away mid-response (common under Locust timeouts). Not a server fault.
_CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


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
            _safe_error_response(
                self,
                {"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
                status=HTTPStatus(exc.status),
            )
        except _CLIENT_GONE:
            return
        except Exception as exc:  # pragma: no cover - network-facing guard
            _safe_error_response(
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

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            payload = self.read_json_body()
            json_response(self, self.route_post(path, payload))
        except APIError as exc:
            _safe_error_response(
                self,
                {"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
                status=HTTPStatus(exc.status),
            )
        except _CLIENT_GONE:
            return
        except Exception as exc:  # pragma: no cover - network-facing guard
            _safe_error_response(
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
        return route_get(self.service, path, query, self.normalized_headers())

    def route_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return route_post(self.service, path, payload, self.normalized_headers())

    def normalized_headers(self) -> dict[str, str]:
        return {key.lower(): value for key, value in self.headers.items()}

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length == 0:
            return {}
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise APIError("invalid_json", "JSON request body must be an object.", status=400)
        return payload


def _safe_error_response(
    handler: BaseHTTPRequestHandler,
    payload: dict[str, Any],
    *,
    status: HTTPStatus,
) -> None:
    try:
        json_response(handler, payload, status=status)
    except _CLIENT_GONE:
        return


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
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


def build_handler(service: ResearchLankaAPI) -> type[APIRequestHandler]:
    class ConfiguredAPIRequestHandler(APIRequestHandler):
        pass

    ConfiguredAPIRequestHandler.service = service
    return ConfiguredAPIRequestHandler


def serve(*, host: str, port: int, service: ResearchLankaAPI | None = None) -> ThreadingHTTPServer:
    service = service or ResearchLankaAPI(PostgresPublicationRepository())
    server = ThreadingHTTPServer((host, port), build_handler(service))
    # Avoid unbounded thread growth under aggressive Locust ramps.
    server.daemon_threads = True
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
