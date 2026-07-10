"""Small OpenAlex API client used by the collection scripts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


OPENALEX_BASE_URL = "https://api.openalex.org"


@dataclass
class OpenAlexCollector:
    """Fetch records from the OpenAlex API."""

    email: str | None = None
    base_url: str = OPENALEX_BASE_URL
    timeout: int = 30

    def fetch_works(
        self,
        *,
        search: str | None = None,
        filters: list[str] | None = None,
        per_page: int = 5,
        page: int = 1,
        cursor: str | None = None,
        select: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch works from OpenAlex and return the decoded JSON response."""

        params: dict[str, Any] = {
            "per-page": per_page,
        }

        if cursor:
            params["cursor"] = cursor
        else:
            params["page"] = page
        if search:
            params["search"] = search
        if filters:
            params["filter"] = ",".join(filters)
        if select:
            params["select"] = ",".join(select)
        if self.email:
            params["mailto"] = self.email

        response = requests.get(
            f"{self.base_url}/works",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def iter_works(
        self,
        *,
        search: str | None = None,
        filters: list[str] | None = None,
        per_page: int = 200,
        max_records: int | None = None,
        select: list[str] | None = None,
    ):
        """Yield works from OpenAlex using cursor pagination."""

        cursor = "*"
        records_seen = 0

        while cursor:
            response = self.fetch_works(
                search=search,
                filters=filters,
                per_page=per_page,
                cursor=cursor,
                select=select,
            )
            results = response.get("results", [])

            if not results:
                break

            for work in results:
                if max_records is not None and records_seen >= max_records:
                    return
                records_seen += 1
                yield work

            cursor = response.get("meta", {}).get("next_cursor")


def describe_value(
    value: Any,
    *,
    depth: int = 0,
    max_depth: int = 2,
    max_dict_keys: int = 12,
) -> Any:
    """Return a compact type/shape description for a JSON value."""

    if depth >= max_depth:
        return type(value).__name__

    if isinstance(value, dict):
        if depth > 0 and len(value) > max_dict_keys:
            sample = list(value.items())[:max_dict_keys]
            return {
                "type": "dict",
                "keys_count": len(value),
                "sample": {
                    key: describe_value(
                        child,
                        depth=depth + 1,
                        max_depth=max_depth,
                        max_dict_keys=max_dict_keys,
                    )
                    for key, child in sample
                },
            }

        return {
            key: describe_value(
                child,
                depth=depth + 1,
                max_depth=max_depth,
                max_dict_keys=max_dict_keys,
            )
            for key, child in value.items()
        }

    if isinstance(value, list):
        if not value:
            return "list[empty]"
        return {
            "type": "list",
            "length": len(value),
            "first_item": describe_value(
                value[0],
                depth=depth + 1,
                max_depth=max_depth,
                max_dict_keys=max_dict_keys,
            ),
        }

    return type(value).__name__
