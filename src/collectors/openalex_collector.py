"""Reusable OpenAlex API collection helpers for Sri Lanka datasets."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests

from src.collectors.http import DEFAULT_RETRY_STATUSES, create_retry_session
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
    return create_retry_session()


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
    page_number: int = 0
    fetched_count: int = 0
    api_total_count: int | None = None
    estimated_total_pages: int | None = None
    progress_percent: float | None = None
    db_response_time_ms: int | None = None


@dataclass
class OpenAlexCollector:
    """Collect OpenAlex works with Sri Lankan affiliation metadata."""

    email: str | None = None
    api_key: str | None = None
    timeout: int | tuple[int, int] = 60
    retry_limit: int = 3
    retry_backoff_seconds: float = 2.0
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
        attempts = max(1, self.retry_limit + 1)
        for attempt in range(1, attempts + 1):
            try:
                response = self.session.get(
                    f"{self.base_url}/works",
                    params=params,
                    timeout=self.timeout,
                )
                if response.status_code in DEFAULT_RETRY_STATUSES and attempt < attempts:
                    self._sleep_before_retry(attempt, attempts, cursor, response.status_code)
                    continue

                if not response.ok:
                    logger.error(
                        "OpenAlex request returned status=%s cursor=%s body=%s",
                        response.status_code,
                        cursor,
                        response.text[:500],
                    )
                response.raise_for_status()
                return response.json()
            except requests.JSONDecodeError:
                if attempt >= attempts:
                    logger.exception("OpenAlex JSON decode failed cursor=%s", cursor)
                    raise
                self._sleep_before_retry(attempt, attempts, cursor, "invalid-json")
            except requests.RequestException:
                if attempt >= attempts:
                    logger.exception("OpenAlex request failed cursor=%s", cursor)
                    raise
                self._sleep_before_retry(attempt, attempts, cursor, "request-error")

        raise RuntimeError(f"OpenAlex request failed after {attempts} attempts cursor={cursor}")

    def _sleep_before_retry(
        self,
        attempt: int,
        attempts: int,
        cursor: str,
        reason: int | str,
    ) -> None:
        delay = min(self.retry_backoff_seconds * 2 ** (attempt - 1), 30.0)
        logger.warning(
            "OpenAlex request retrying cursor=%s reason=%s attempt=%s/%s delay=%.1fs",
            cursor,
            reason,
            attempt + 1,
            attempts,
            delay,
        )
        time.sleep(delay)

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
        seen_cursors: set[str] = set()
        page_number = 0
        logger.info(
            "Starting OpenAlex page iteration start_cursor=%s per_page=%s strict_lk_only=%s filters=%s",
            start_cursor,
            per_page,
            strict_lk_only,
            built_filters,
        )

        while cursor:
            if cursor in seen_cursors:
                raise RuntimeError(f"OpenAlex pagination cursor repeated: {cursor}")
            seen_cursors.add(cursor)
            page_number += 1

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

            meta = response.get("meta", {})
            if not isinstance(meta, dict):
                meta = {}
            next_cursor = meta.get("next_cursor")
            if next_cursor == cursor:
                raise RuntimeError(
                    f"OpenAlex pagination did not advance from cursor: {cursor}"
                )
            if next_cursor is not None and next_cursor in seen_cursors:
                raise RuntimeError(
                    f"OpenAlex pagination returned an earlier cursor: {next_cursor}"
                )

            api_total_count = meta.get("count")
            if not isinstance(api_total_count, int):
                api_total_count = None
            db_response_time_ms = meta.get("db_response_time_ms")
            if not isinstance(db_response_time_ms, int):
                db_response_time_ms = None
            estimated_total_pages = None
            progress_percent = None
            if api_total_count is not None and per_page > 0:
                estimated_total_pages = max(
                    (api_total_count + per_page - 1) // per_page,
                    1,
                )
                progress_percent = min(page_number / estimated_total_pages * 100, 100.0)

            page_progress = (
                f"{page_number}/{estimated_total_pages}"
                if estimated_total_pages is not None
                else str(page_number)
            )
            logger.info(
                "Fetched OpenAlex page page=%s progress=%s fetched=%s kept=%s skipped=%s next_cursor=%s",
                page_progress,
                f"{progress_percent:.1f}%" if progress_percent is not None else "n/a",
                len(results),
                len(works),
                skipped_count,
                "yes" if next_cursor else "no",
            )
            logger.debug(
                "OpenAlex pagination detail cursor=%s next_cursor=%s api_total_count=%s estimated_total_pages=%s db_response_time_ms=%s",
                cursor,
                next_cursor,
                api_total_count,
                estimated_total_pages,
                db_response_time_ms,
            )
            yield OpenAlexWorkPage(
                cursor=cursor,
                next_cursor=next_cursor,
                filters=built_filters,
                works=works,
                skipped_count=skipped_count,
                page_number=page_number,
                fetched_count=len(results),
                api_total_count=api_total_count,
                estimated_total_pages=estimated_total_pages,
                progress_percent=progress_percent,
                db_response_time_ms=db_response_time_ms,
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
