"""
Crossref Collector
==================

Supports:

1. Affiliation-based collection
   - Used for finding Sri Lankan publications

2. DOI-based batch enrichment
   - Used when DOI list comes from OpenAlex/local sources

Features:
- Cursor pagination
- Retry HTTP sessions
- Large-scale collection
- Metadata normalization
- No publication type filtering
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterator
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from src.collectors.http import create_retry_session
from src.preprocessing.crossref_normalizer import first_author_is_from_sri_lanka
from src.preprocessing.crossref_normalizer import reduce_work


CROSSREF_BASE_URL = "https://api.crossref.org"

USER_AGENT = "SriLankaCollector/1.0"
DEFAULT_PUBLICATION_START_YEAR = 2016
DEFAULT_PUBLICATION_END_YEAR = 2026


logger = logging.getLogger(__name__)


class CrossrefRepeatedCursorError(RuntimeError):
    """Raised when Crossref returns a cursor that would repeat a page."""


def create_session(
    user_agent: str,
) -> requests.Session:
    """Create a retrying HTTP session for Crossref API requests."""
    return create_retry_session(user_agent=user_agent)


@dataclass
class CrossrefCollector:
    """
    Large-scale Crossref collector.

    Supports:
    - affiliation search
    - DOI lookup
    """

    email: str | None = None

    timeout: tuple[int, int] = (10, 60)

    base_url: str = CROSSREF_BASE_URL

    user_agent: str = USER_AGENT

    session: requests.Session = field(init=False)

    def __post_init__(self):

        user_agent = self.user_agent

        if self.email:
            user_agent = f"{self.user_agent} (mailto:{self.email})"

        self.session = create_session(user_agent)

    # =====================================================
    # 1. AFFILIATION BASED LARGE SCALE COLLECTION
    # =====================================================

    def fetch_works(
    self,
    *,
    affiliation_query: str,
    filters: list[str] | None = None,
    rows: int = 100,
    cursor: str = "*",
) -> dict[str, Any]:
        """
        Query Crossref works using affiliation.

        Example:
            University of Moratuwa Sri Lanka
        """

        params = {
            "query.affiliation": affiliation_query,
            "rows": rows,
            "cursor": cursor,
        }
        if filters:
         params["filter"] = ",".join(filters)    

        response = self.session.get(
            f"{self.base_url}/works", params=params, timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()

    def iter_works(
        self,
        *,
        affiliation_query: str,
        filters: list[str] | None = None,
        rows: int = 100,
        max_records: int | None = None,
        require_first_author_lk: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """
        Collect all works matching affiliation.

        Uses Crossref cursor pagination.
        """

        cursor = "*"

        records_seen = 0

        while cursor:
            if max_records and records_seen >= max_records:
                break

            response = self.fetch_works(
                affiliation_query=affiliation_query,
                filters=filters,
                rows=rows,
                cursor=cursor,
            )

            message = response.get("message", {})

            items = message.get("items", [])

            if not items:
                break

            for work in items:
                if max_records and records_seen >= max_records:
                    return

                if work.get("type") != "journal-article":
                    continue
                if require_first_author_lk and not first_author_is_from_sri_lanka(work):
                    continue

                try:
                    normalized = reduce_work(work)

                    records_seen += 1

                    yield normalized

                except Exception:
                    logger.exception("Normalization failed %s", work.get("DOI"))

            cursor = message.get("next-cursor")

            time.sleep(0.2)

    # =====================================================
    # 2. SINGLE DOI LOOKUP
    # =====================================================

    def fetch_work_by_doi(self, doi: str) -> dict[str, Any] | None:
        """
        Fetch one Crossref work using DOI.
        """

        doi = quote(doi, safe="")

        response = self.session.get(
            f"{self.base_url}/works/{doi}", timeout=self.timeout
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()

        return response.json().get("message")

    # =====================================================
    # 3. LARGE SCALE DOI COLLECTION
    # =====================================================

    def fetch_works_by_dois(
        self,
        dois: list[str],
        *,
        workers: int = 5,
    ) -> Iterator[dict[str, Any]]:
        """Fetch multiple Crossref works concurrently by DOI."""

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self.fetch_work_by_doi, doi.replace("https://doi.org/", "").strip()
                ): doi
                for doi in dois
            }

            for future in as_completed(futures):
                doi = futures[future]
                try:
                    work = future.result()
                except requests.RequestException:
                    logger.exception("Crossref DOI lookup failed for %s", doi)
                    continue
                if work:
                    yield work

@dataclass
class CrossrefPrefixCollector:
    """Fetch all works registered under one DOI prefix."""

    prefix: str
    email: str | None = None
    rows: int = 500
    timeout: int | tuple[int, int] = 60
    delay: float = 0.5
    base_url: str = CROSSREF_BASE_URL
    user_agent: str = USER_AGENT
    session: requests.Session = field(init=False)

    def __post_init__(self) -> None:
        user_agent = self.user_agent

        if self.email:
            user_agent = f"{self.user_agent} (mailto:{self.email})"

        self.session = create_session(user_agent)

    def total_works(self, *, filters: list[str] | None = None) -> int:
        params: dict[str, Any] = {"rows": 0}

        if self.email:
            params["mailto"] = self.email
        if filters:
            params["filter"] = ",".join(filters)

        response = self.session.get(
            f"{self.base_url}/prefixes/{self.prefix}/works",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["message"]["total-results"]

    def iter_works(
        self,
        *,
        max_records: int | None = None,
        filters: list[str] | None = None,
        repeated_cursor_policy: str = "stop",
    ) -> Iterator[dict[str, Any]]:
        """Yield raw Crossref work records using cursor pagination."""

        cursor = "*"
        records_seen = 0
        seen_cursors = {cursor}

        while cursor and (max_records is None or records_seen < max_records):
            params: dict[str, Any] = {"rows": self.rows, "cursor": cursor}

            if self.email:
                params["mailto"] = self.email
            if filters:
                params["filter"] = ",".join(filters)

            response = self.session.get(
                f"{self.base_url}/prefixes/{self.prefix}/works",
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            message = response.json()["message"]

            items = message.get("items", [])

            if not items:
                break

            for work in items:
                if max_records is not None and records_seen >= max_records:
                    return
                records_seen += 1
                yield work

            cursor = message.get("next-cursor")

            if cursor:
                if cursor in seen_cursors:
                    cursor_preview = f"{cursor[:80]}..." if len(cursor) > 80 else cursor
                    if repeated_cursor_policy == "raise":
                        raise CrossrefRepeatedCursorError(
                            f"Crossref cursor repeated: {cursor_preview}"
                        )
                    logger.warning(
                        "Stopping Crossref prefix pagination because cursor repeated: %s",
                        cursor_preview,
                    )
                    break
                seen_cursors.add(cursor)

            if self.delay:
                time.sleep(self.delay)

    def iter_works_by_publication_date(
        self,
        *,
        start_year: int = DEFAULT_PUBLICATION_START_YEAR,
        end_year: int | None = DEFAULT_PUBLICATION_END_YEAR,
        max_records: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield prefix works using recursive date windows to avoid cursor loops."""

        final_year = end_year or DEFAULT_PUBLICATION_END_YEAR
        start_date = date(start_year, 1, 1)
        end_date = date(final_year, 12, 31)
        seen_keys: set[str] = set()
        yielded_count = 0

        def emit_window(window_start: date, window_end: date) -> Iterator[dict[str, Any]]:
            nonlocal yielded_count

            if max_records is not None and yielded_count >= max_records:
                return

            yielded_in_window = 0
            filters = [
                f"from-pub-date:{window_start.isoformat()}",
                f"until-pub-date:{window_end.isoformat()}",
            ]

            try:
                remaining = None if max_records is None else max_records - yielded_count
                for work in self.iter_works(
                    max_records=remaining,
                    filters=filters,
                    repeated_cursor_policy="raise",
                ):
                    key = crossref_work_key(work)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    yielded_count += 1
                    yielded_in_window += 1
                    yield work
                    if max_records is not None and yielded_count >= max_records:
                        return
            except CrossrefRepeatedCursorError:
                if max_records is not None and yielded_count >= max_records:
                    return
                if window_start >= window_end:
                    logger.warning(
                        "Crossref cursor repeated for one-day window %s after %s new records.",
                        window_start.isoformat(),
                        yielded_in_window,
                    )
                    return

                days = (window_end - window_start).days
                midpoint = window_start + timedelta(days=days // 2)
                logger.info(
                    "Splitting Crossref prefix window %s to %s after repeated cursor.",
                    window_start.isoformat(),
                    window_end.isoformat(),
                )
                yield from emit_window(window_start, midpoint)
                yield from emit_window(midpoint + timedelta(days=1), window_end)

        yield from emit_window(start_date, end_date)


def crossref_work_key(work: dict[str, Any]) -> str:
    """Build a stable identity key for deduplicating sliced Crossref scans."""

    doi = work.get("DOI") or work.get("doi")
    if doi:
        return f"doi:{str(doi).strip().casefold()}"

    url = work.get("URL") or work.get("url")
    if url:
        return f"url:{str(url).strip().casefold()}"

    title = work.get("title")
    if isinstance(title, list):
        title_text = " ".join(str(part).strip() for part in title if str(part).strip())
    else:
        title_text = "" if title is None else str(title).strip()
    year = _first_year(work)
    return f"title-year:{title_text.casefold()}:{year or ''}"


def _first_year(work: dict[str, Any]) -> int | None:
    for field_name in ("published", "published-print", "published-online", "issued", "created"):
        value = work.get(field_name)
        if not isinstance(value, dict):
            continue
        date_parts = value.get("date-parts")
        if not date_parts or not isinstance(date_parts, list) or not date_parts[0]:
            continue
        try:
            return int(date_parts[0][0])
        except (TypeError, ValueError):
            continue
    return None
