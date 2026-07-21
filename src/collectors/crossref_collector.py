from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterator
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.preprocessing.crossref_normalizer import reduce_work

CROSSREF_BASE_URL = "https://api.crossref.org"
USER_AGENT = "SriLankaCollector/1.0"

KEEP_TYPES = {
    "journal-article",
    "proceedings-article",
    "posted-content",
}

logger = logging.getLogger(__name__)


def create_session(
    user_agent: str,
) -> requests.Session:
    """Create a retrying HTTP session for Crossref API requests."""
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

    session.headers.update({"User-Agent": user_agent})

    return session


@dataclass
class CrossrefCollector:
    """Collect and normalize publication records from Crossref."""

    email: str | None = None
    timeout: tuple[int, int] = (10, 60)
    base_url: str = CROSSREF_BASE_URL
    user_agent: str = USER_AGENT
    session: requests.Session = field(init=False)
    keep_types: set[str] | None = field(default_factory=lambda: KEEP_TYPES.copy())

    def __post_init__(self) -> None:
        user_agent = self.user_agent

        if self.email:
            user_agent = f"{self.user_agent} (mailto:{self.email})"

        self.session = create_session(user_agent)

    def fetch_works(
        self,
        *,
        affiliation_query: str,
        filters: list[str] | None = None,
        rows: int = 100,
        cursor: str = "*",
    ) -> dict[str, Any]:

        params = {
            "query.affiliation": affiliation_query,
            "rows": rows,
        }
        if cursor:
            params["cursor"] = cursor

        if filters:
            params["filter"] = ",".join(filters)

        response = self.session.get(
            f"{self.base_url}/works",
            params=params,
            timeout=self.timeout,
        )

        if not response.ok:
            logger.error(
                "Crossref request failed: %s %s",
                response.status_code,
                response.text,
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
        """Iterate over Crossref works with cursor pagination."""

        cursor = "*"
        records_seen = 0

        while cursor and (max_records is None or records_seen < max_records):
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
                if self.keep_types and work.get("type") not in self.keep_types:
                    continue
                if max_records is not None and records_seen >= max_records:
                    return
                try:
                    normalized = reduce_work(work)
                except Exception:
                    logger.exception("Failed to normalize work %s", work.get("DOI"))
                    continue
                records_seen += 1
                yield normalized

            cursor = message.get("next-cursor")

            if not cursor:
                break

    def fetch_work_by_doi(
        self,
        doi: str,
    ) -> dict[str, Any] | None:
        """Fetch a single work from Crossref by DOI."""

        quoted_doi = quote(doi, safe="")
        url = f"{self.base_url}/works/{quoted_doi}"

        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()

            return response.json().get("message")

        except requests.RequestException as exc:
            logger.warning(
                "Failed DOI lookup %s: %s",
                doi,
                exc,
            )
            return None


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

    def total_works(self) -> int:
        params: dict[str, Any] = {"rows": 0}

        if self.email:
            params["mailto"] = self.email

        response = self.session.get(
            f"{self.base_url}/prefixes/{self.prefix}/works",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["message"]["total-results"]

    def iter_works(self, *, max_records: int | None = None) -> Iterator[dict[str, Any]]:
        """Yield raw Crossref work records using cursor pagination."""

        cursor = "*"
        records_seen = 0

        while cursor and (max_records is None or records_seen < max_records):
            params: dict[str, Any] = {"rows": self.rows, "cursor": cursor}

            if self.email:
                params["mailto"] = self.email

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

            if self.delay:
                time.sleep(self.delay)
