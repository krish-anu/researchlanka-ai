"""Reusable OpenAlex API collection helpers for Sri Lanka datasets."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.preprocessing.openalex_normalizer import (
    CSV_COLUMNS,
    SRI_LANKA_COUNTRY_CODE,
    as_list,
    author_name,
    author_names,
    authorships,
    country_codes,
    country_codes_from_authorship,
    detected_country_codes,
    display_names,
    get_nested,
    has_sri_lankan_author,
    institution_names,
    is_sri_lankan_authorship,
    is_strict_sri_lanka_only,
    location_values,
    locations,
    normalize_publication_date,
    normalize_publication_year,
    openalex_work_id,
    raw_affiliation_strings,
    unique_join,
    work_to_row,
)


OPENALEX_BASE_URL = "https://api.openalex.org"
LK_AUTHORSHIP_FILTER = "authorships.institutions.country_code:LK"
DEFAULT_FROM_YEAR = 2016
DEFAULT_TO_YEAR = 2026

logger = logging.getLogger(__name__)


def create_session() -> requests.Session:
    """Create a retrying HTTP session for transient OpenAlex API failures."""
    retry_strategy = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )

    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def build_filters(
    filters: list[str] | None = None,
    *,
    from_year: int | None = DEFAULT_FROM_YEAR,
    to_year: int | None = DEFAULT_TO_YEAR,
) -> list[str]:
    """Build OpenAlex filter strings from CLI filters and optional year bounds."""
    built_filters = list(filters or [LK_AUTHORSHIP_FILTER])

    if from_year is not None or to_year is not None:
        start = from_year if from_year is not None else "*"
        end = to_year if to_year is not None else "*"
        built_filters.append(f"publication_year:{start}-{end}")

    return built_filters


@dataclass
class OpenAlexWorkPage:
    """A fetched OpenAlex page after local Sri Lankan-affiliation filtering."""

    cursor: str
    next_cursor: str | None
    filters: list[str]
    works: list[dict[str, Any]]
    skipped_count: int = 0


@dataclass
class OpenAlexCollector:
    """Collect OpenAlex works with Sri Lankan affiliation metadata."""

    email: str | None = None
    api_key: str | None = None
    timeout: int | tuple[int, int] = 60
    base_url: str = OPENALEX_BASE_URL
    session: requests.Session = field(default_factory=create_session)

    def fetch_works(
        self,
        *,
        filters: list[str],
        cursor: str,
        per_page: int,
    ) -> dict[str, Any]:
        """Fetch one cursor page from the OpenAlex works endpoint."""
        params: dict[str, Any] = {
            "filter": ",".join(filters),
            "cursor": cursor,
            "per-page": per_page,
        }
        if self.email:
            params["mailto"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key

        logger.debug(
            "Fetching OpenAlex works cursor=%s per_page=%s filters=%s",
            cursor,
            per_page,
            filters,
        )
        try:
            response = self.session.get(
                f"{self.base_url}/works",
                params=params,
                timeout=self.timeout,
            )
        except requests.RequestException:
            logger.exception("OpenAlex request failed cursor=%s", cursor)
            raise

        if not response.ok:
            logger.error(
                "OpenAlex request returned status=%s cursor=%s body=%s",
                response.status_code,
                cursor,
                response.text[:500],
            )
        response.raise_for_status()
        return response.json()

    def iter_sri_lankan_work_pages(
        self,
        *,
        filters: list[str] | None = None,
        from_year: int | None = DEFAULT_FROM_YEAR,
        to_year: int | None = DEFAULT_TO_YEAR,
        per_page: int = 200,
        start_cursor: str = "*",
        strict_lk_only: bool = False,
    ) -> Iterator[OpenAlexWorkPage]:
        """Yield cursor pages after applying broad or strict LK filtering."""
        built_filters = build_filters(filters, from_year=from_year, to_year=to_year)
        cursor = start_cursor
        seen_ids: set[str] = set()
        logger.info(
            "Starting OpenAlex page iteration start_cursor=%s per_page=%s strict_lk_only=%s filters=%s",
            start_cursor,
            per_page,
            strict_lk_only,
            built_filters,
        )

        while cursor:
            response = self.fetch_works(
                filters=built_filters,
                cursor=cursor,
                per_page=per_page,
            )
            results = as_list(response.get("results"))
            if not results:
                break

            works: list[dict[str, Any]] = []
            skipped_count = 0
            for work in results:
                if not isinstance(work, dict) or not has_sri_lankan_author(work):
                    skipped_count += 1
                    continue
                work_id = openalex_work_id(work)
                if work_id is None or work_id in seen_ids:
                    skipped_count += 1
                    continue
                if strict_lk_only and not is_strict_sri_lanka_only(work):
                    skipped_count += 1
                    continue
                seen_ids.add(work_id)
                works.append(work)

            next_cursor = response.get("meta", {}).get("next_cursor")
            logger.info(
                "Fetched OpenAlex page cursor=%s kept=%s skipped=%s next_cursor=%s",
                cursor,
                len(works),
                skipped_count,
                "yes" if next_cursor else "no",
            )
            yield OpenAlexWorkPage(
                cursor=cursor,
                next_cursor=next_cursor,
                filters=built_filters,
                works=works,
                skipped_count=skipped_count,
            )

            cursor = next_cursor

    def iter_sri_lankan_works(
        self,
        *,
        filters: list[str] | None = None,
        from_year: int | None = DEFAULT_FROM_YEAR,
        to_year: int | None = DEFAULT_TO_YEAR,
        per_page: int = 200,
        max_records: int | None = None,
        start_cursor: str = "*",
        records_saved: int = 0,
        strict_lk_only: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Yield individual Sri Lankan-affiliated works from cursor pages."""
        saved = records_saved

        for page in self.iter_sri_lankan_work_pages(
            filters=filters,
            from_year=from_year,
            to_year=to_year,
            per_page=per_page,
            start_cursor=start_cursor,
            strict_lk_only=strict_lk_only,
        ):
            for work in page.works:
                if max_records is not None and saved >= max_records:
                    return
                saved += 1
                yield work
