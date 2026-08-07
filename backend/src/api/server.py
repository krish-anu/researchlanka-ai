"""Compatibility exports for the standard-library HTTP API server."""

from src.api.transport.http_server import (
    APIRequestHandler,
    add_cors_headers,
    build_handler,
    build_parser,
    bytes_response,
    json_response,
    main,
    serve,
)

__all__ = [
    "APIRequestHandler",
    "add_cors_headers",
    "build_handler",
    "build_parser",
    "bytes_response",
    "json_response",
    "main",
    "serve",
]

