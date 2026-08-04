"""Generic REST API source adapter."""

from __future__ import annotations

import os
from typing import Any, Iterator

import requests

from research_analytics.adapters.base import SourceAdapter
from research_analytics.schema import map_to_standard_schema
from research_analytics.transformations import apply_transformations


class APIAdapter(SourceAdapter):
    """Collect records from a configurable REST API."""

    def __init__(
        self,
        *,
        base_url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        authentication: dict[str, Any] | None = None,
        pagination: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        column_mapping: dict[str, str] | None = None,
        transformations: dict[str, dict[str, Any]] | None = None,
        source_name: str = "api_source",
        required_fields: tuple[str, ...] = ("title",),
        require_any_fields: tuple[str, ...] = ("doi", "authors", "publication_year", "source_record_id"),
        adapter_version: str = "1.0",
        mapping_version: str = "1.0",
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url
        self.method = method.upper()
        self.headers = dict(headers or {})
        self.authentication = authentication or {}
        self.pagination = pagination or {"type": "none"}
        self.response = response or {"records_path": ""}
        self.column_mapping = column_mapping or {}
        self.transformations = transformations or {}
        self.source_name = source_name
        self.required_fields = required_fields
        self.require_any_fields = require_any_fields
        self.adapter_version = adapter_version
        self.mapping_version = mapping_version
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self._apply_authentication()

    def connect(self) -> None:
        response = self.session.request(
            self.method,
            self.base_url,
            params=self._initial_params(),
            timeout=self.timeout,
        )
        response.raise_for_status()

    def collect(self) -> Iterator[dict]:
        url: str | None = self.base_url
        params = self._initial_params()
        page_count = 0

        while url:
            response = self.session.request(
                self.method,
                url,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            records = _get_path(payload, self.response.get("records_path", ""))
            if isinstance(records, dict):
                records = [records]
            if not isinstance(records, list):
                raise ValueError("API response records_path did not resolve to a list.")
            for record in records:
                if isinstance(record, dict):
                    yield record

            page_count += 1
            url, params = self._next_request(payload, url, params, page_count)

    def transform(self, raw_record: dict) -> dict:
        mapped = map_to_standard_schema(
            raw_record,
            self.column_mapping,
            source_name=self.source_name,
            adapter_version=self.adapter_version,
            mapping_version=self.mapping_version,
        )
        return apply_transformations(mapped, self.transformations)

    def validate(self, transformed_record: dict) -> list[str]:
        errors = []
        for field in self.required_fields:
            if _is_blank(transformed_record.get(field)):
                errors.append(f"Missing required field: {field}")
        if self.require_any_fields and not any(
            not _is_blank(transformed_record.get(field)) for field in self.require_any_fields
        ):
            errors.append(
                "At least one identifying field is required: "
                + ", ".join(self.require_any_fields)
            )
        return errors

    def _apply_authentication(self) -> None:
        auth_type = self.authentication.get("type", "none")
        if auth_type == "api_key":
            env_name = self.authentication.get("environment_variable")
            header_name = self.authentication.get("header_name")
            if env_name and header_name and os.getenv(env_name):
                self.session.headers[header_name] = os.environ[env_name]
        elif auth_type == "bearer":
            env_name = self.authentication.get("token_environment_variable")
            if env_name and os.getenv(env_name):
                self.session.headers["Authorization"] = f"Bearer {os.environ[env_name]}"
        elif auth_type == "basic":
            username_env = self.authentication.get("username_environment_variable")
            password_env = self.authentication.get("password_environment_variable")
            if username_env and password_env:
                username = os.getenv(username_env)
                password = os.getenv(password_env)
                if username is not None and password is not None:
                    self.session.auth = (username, password)

    def _initial_params(self) -> dict[str, Any]:
        pagination_type = self.pagination.get("type", "none")
        if pagination_type == "page":
            return {
                self.pagination.get("page_parameter", "page"): self.pagination.get("start_page", 1),
                self.pagination.get("page_size_parameter", "limit"): self.pagination.get("page_size", 100),
            }
        if pagination_type == "offset":
            return {
                self.pagination.get("offset_parameter", "offset"): self.pagination.get("start_offset", 0),
                self.pagination.get("page_size_parameter", "limit"): self.pagination.get("page_size", 100),
            }
        return {}

    def _next_request(
        self,
        payload: dict[str, Any],
        url: str,
        params: dict[str, Any],
        page_count: int,
    ) -> tuple[str | None, dict[str, Any]]:
        max_pages = self.pagination.get("max_pages")
        if max_pages is not None and page_count >= int(max_pages):
            return None, {}

        pagination_type = self.pagination.get("type", "none")
        if pagination_type == "none":
            return None, {}
        if pagination_type == "page":
            next_page = _get_path(payload, self.pagination.get("next_page_path", ""))
            if next_page in (None, "", False):
                return None, {}
            next_params = dict(params)
            next_params[self.pagination.get("page_parameter", "page")] = next_page
            return url, next_params
        if pagination_type == "offset":
            records = _get_path(payload, self.response.get("records_path", ""))
            if not records:
                return None, {}
            next_params = dict(params)
            offset_parameter = self.pagination.get("offset_parameter", "offset")
            page_size = int(self.pagination.get("page_size", 100))
            next_params[offset_parameter] = int(next_params.get(offset_parameter, 0)) + page_size
            return url, next_params
        if pagination_type == "cursor":
            cursor = _get_path(payload, self.pagination.get("next_cursor_path", ""))
            if not cursor:
                return None, {}
            next_params = dict(params)
            next_params[self.pagination.get("cursor_parameter", "cursor")] = cursor
            return url, next_params
        if pagination_type == "next_link":
            next_url = _get_path(payload, self.pagination.get("next_url_path", ""))
            return (next_url, {}) if next_url else (None, {})
        return None, {}


def _get_path(payload: Any, path: str | None) -> Any:
    if not path:
        return payload
    value = payload
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit():
            value = value[int(part)]
        else:
            return None
    return value


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value
    return False
