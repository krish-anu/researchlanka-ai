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
from typing import Any, Iterator
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from src.collectors.http import create_retry_session
from src.preprocessing.crossref_normalizer import reduce_work


CROSSREF_BASE_URL = "https://api.crossref.org"

USER_AGENT = "SriLankaCollector/1.0"


logger = logging.getLogger(__name__)


def create_session(user_agent: str) -> requests.Session:
    """
    Create retry-enabled HTTP session.
    """

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

    def iter_doi_works(
        self, dois: list[str], workers: int = 10
    ) -> Iterator[dict[str, Any]]:
        """
        Fetch thousands of DOI records
        in parallel.
        """

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

                    if work:
                        yield reduce_work(work)

                except Exception:
                    logger.exception("Failed DOI %s", doi)
