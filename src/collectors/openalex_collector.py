"""Small OpenAlex API client used by the collection scripts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


OPENALEX_BASE_URL = "https://api.openalex.org"
SRI_LANKA_COUNTRY_CODE = "LK"


@dataclass
class OpenAlexCollector:
    """Fetch records from the OpenAlex API."""

    email: str | None = None
    api_key: str | None = None
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
        if self.api_key:
            params["api_key"] = self.api_key

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
        per_page: int = 100,
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


def as_list(value: Any) -> list[Any]:
    """Return a JSON value as a list without treating strings as iterables."""

    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def country_codes_from_authorship(authorship: dict[str, Any]) -> set[str]:
    """Extract affiliation country codes from one OpenAlex authorship."""

    country_codes = {
        str(country).upper()
        for country in as_list(authorship.get("countries"))
        if country
    }

    for institution in as_list(authorship.get("institutions")):
        if isinstance(institution, dict) and institution.get("country_code"):
            country_codes.add(str(institution["country_code"]).upper())

    return country_codes


def authorship_has_country(
    authorship: dict[str, Any],
    country_code: str = SRI_LANKA_COUNTRY_CODE,
) -> bool:
    """Return True when an author has an affiliation in the requested country."""

    return country_code.upper() in country_codes_from_authorship(authorship)


def work_has_author_from_country(
    work: dict[str, Any],
    country_code: str = SRI_LANKA_COUNTRY_CODE,
) -> bool:
    """Return True if at least one authorship has that country's affiliation.

    OpenAlex exposes affiliation country, not author nationality. This helper
    therefore treats an author as Sri Lankan when one of their OpenAlex
    authorships has an LK country code or an LK institution.
    """

    for authorship in as_list(work.get("authorships")):
        if isinstance(authorship, dict) and authorship_has_country(
            authorship,
            country_code,
        ):
            return True

    for institution in as_list(work.get("institutions")):
        if (
            isinstance(institution, dict)
            and str(institution.get("country_code", "")).upper()
            == country_code.upper()
        ):
            return True

    return False


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
